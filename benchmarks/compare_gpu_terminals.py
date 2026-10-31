#!/usr/bin/env python3
"""Compare Terminal with other terminals on the real GPU, off the owner's desktop.

Foot is Wayland-only and CPU-rendered; it stays selectable but off by default.
A private headless Weston renders with the GPU and hosts Xwayland, so windows
never reach the desktop while GLX still reaches radeonsi. Each terminal runs
bench_child mode as its only child. Throughput ends with a cursor report the
terminal must answer after parsing everything; output latency runs from the
child's write to the XDamage of the terminal's next presented frame.

  compare_gpu_terminals.py --out DIR [--runs 3] [--only terminal,kitty]
      [--workloads ascii,sgr] [--terminal-bin PATH] [--extra-root ROOT]
"""
import argparse
import json
import os
import random
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import termios
import time
import tty
from pathlib import Path

COLS, ROWS, FONT_SIZE = 120, 40, 12
MEGABYTE = 1 << 20


def block(kind):
    """About 1 MiB of a repeatable workload, and the bytes to send in total."""
    rng = random.Random(7)
    printable = [chr(c) for c in range(33, 127)]
    if kind == 'ascii':
        lines = (''.join(rng.choices(printable, k=COLS - 1)) + '\r\n' for _ in range(8700))
        return ''.join(lines), 32 * MEGABYTE
    if kind == 'sgr':
        cells = (f'\x1b[38;5;{rng.randrange(256)};48;5;{rng.randrange(256)}m{rng.choice(printable)}' for _ in range(52000))
        return ''.join(cells) + '\x1b[0m\r\n', 16 * MEGABYTE
    if kind == 'unicode':
        wide = [chr(c) for c in range(0x4e00, 0x4f00)]
        lines = ('é' * 10 + ''.join(rng.choices(wide, k=COLS // 2 - 6)) + '\r\n' for _ in range(5000))
        return ''.join(lines), 16 * MEGABYTE
    if kind == 'region':
        lines = (''.join(rng.choices(printable, k=COLS - 1)) + '\r\n' for _ in range(8700))
        return f'\x1b[5;{ROWS - 5}r\x1b[5;1H' + ''.join(lines) + '\x1b[r', 16 * MEGABYTE
    if kind == 'redraw':
        frames = []
        for frame in range(100):
            rows = (f'\x1b[{row + 1};1H\x1b[38;5;{(frame + row) % 256}m' + ''.join(rng.choices(printable, k=COLS)) for row in range(ROWS))
            frames.append(''.join(rows))
        return ''.join(frames), 16 * MEGABYTE
    raise ValueError(kind)


WORKLOADS = ('ascii', 'sgr', 'unicode', 'region', 'redraw')


def cursor_report():
    """Blocks until the terminal has parsed everything written before it."""
    os.write(1, b'\x1b[6n')
    reply = b''
    while not reply.endswith(b'R'):
        reply += os.read(0, 32)


def child(args):
    """Runs inside the terminal: one workload, or echo for latency."""
    tty.setraw(0)
    os.write(1, b'\x1b[?25l')
    cursor_report()
    state = Path(args.child_state)
    (state / 'size').write_text(json.dumps(tuple(os.get_terminal_size(1))))
    (state / 'ready').write_text(str(time.monotonic()))
    while True:
        names = sorted(state.glob('*.job'))
        if not names:
            time.sleep(.002)
            continue
        job = names[0]
        kind = job.stem.split('-', 1)[1]
        job.unlink()
        if kind == 'quit':
            return
        if kind == 'latency':
            latency_child(state)
            continue
        text, total = block(kind)
        data = text.encode()
        alternate = kind == 'redraw'
        if alternate:
            os.write(1, b'\x1b[?1049h')
        sent, began = 0, time.monotonic()
        while sent < total:
            view = memoryview(data)
            while view:
                view = view[os.write(1, view):]
            sent += len(data)
        cursor_report()
        elapsed = time.monotonic() - began
        if alternate:
            os.write(1, b'\x1b[0m\x1b[?1049l')
        os.write(1, b'\x1b[0m\x1b[2J\x1b[H')
        cursor_report()
        (state / (kind + '.result')).write_text(json.dumps(dict(seconds=elapsed, bytes=sent)))


def latency_child(state):
    """Writes one cell per request so each write must produce one new frame."""
    fifo = os.open(state / 'latency.fifo', os.O_RDONLY)
    written = 0
    while True:
        value = os.read(fifo, 1)
        if not value or value == b'q':
            break
        column = written % COLS
        # Each pass over the row uses another glyph, so every cell changes.
        glyph = '#@'[(written // COLS) % 2]
        written += 1
        os.write(1, f'\x1b[2;{column + 1}H{glyph}'.encode())
    os.close(fifo)


def clean_env(home, runtime, display, wayland=None):
    env = {key: os.environ[key] for key in ('PATH', 'LANG') if key in os.environ}
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / '.config'), XDG_CACHE_HOME=str(home / '.cache'),
               XDG_DATA_HOME=str(home / '.local/share'), XDG_STATE_HOME=str(home / '.local/state'),
               XDG_RUNTIME_DIR=str(runtime), DISPLAY=display, TERM='xterm-256color', LC_ALL='C.UTF-8')
    if wayland:
        env['WAYLAND_DISPLAY'] = wayland
        env.pop('DISPLAY')
    return env


def launch_command(name, args, title, command, extra):
    if name == 'terminal':
        return [args.terminal_bin, '--disable-server', '--title', title, '--geometry', f'{COLS}x{ROWS}',
                '--font-size', str(FONT_SIZE), '--hide-menubar', '--dynamic-title-mode', 'ignore', '-x', *command]
    if name == 'alacritty':
        return [str(extra / 'usr/bin/alacritty'), '--config-file', '/dev/null', '-T', title,
                '-o', f'window.dimensions.columns={COLS}', '-o', f'window.dimensions.lines={ROWS}',
                '-o', f'font.size={FONT_SIZE}', '-e', *command]
    if name == 'kitty':
        return [str(extra / 'usr/bin/kitty'), '--config', 'NONE', '--title', title, '-o', 'allow_remote_control=no',
                '-o', f'font_size={FONT_SIZE}', '-o', 'remember_window_size=no',
                '-o', f'initial_window_width={COLS}c', '-o', f'initial_window_height={ROWS}c',
                '-o', 'update_check_interval=0', *command]
    if name == 'foot':
        return [str(extra / 'usr/bin/foot'), '--title', title, '--window-size-chars', f'{COLS}x{ROWS}',
                '--override', f'font=monospace:size={FONT_SIZE}', *command]
    if name == 'xterm':
        return ['xterm', '-T', title, '-geometry', f'{COLS}x{ROWS}', '-fa', 'monospace', '-fs', str(FONT_SIZE), '-e', *command]
    raise ValueError(name)


def wait_for(condition, seconds, what):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(.005)
    raise TimeoutError(what)


class Compositor:
    """A private GPU compositor; the same Xwayland hosts every X11 terminal."""

    def __init__(self, root):
        self.runtime = root / 'run'
        self.runtime.mkdir(mode=0o700)
        self.home = root / 'compositor'
        self.home.mkdir()
        self.log = root / 'weston.log'
        self.socket = 'terminal-bench-' + str(os.getpid())
        env = clean_env(self.home, self.runtime, ':none')
        env.pop('DISPLAY')
        with open(self.log, 'w') as output:
            self.process = subprocess.Popen(['weston', '--backend=headless', '--renderer=gl', '--xwayland',
                f'--socket={self.socket}', '--width=1920', '--height=1200', '--idle-time=0'], env=env,
                stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        text = wait_for(lambda: (lambda t: t if 'xserver listening on display' in t else '')(self.log.read_text()), 20, 'Xwayland display')
        self.display = text.split('xserver listening on display ')[1].split()[0]
        renderer = [line for line in text.splitlines() if 'GL renderer:' in line]
        self.renderer = renderer[0].split('GL renderer:')[1].strip() if renderer else 'unknown'
        probe = dict(env, DISPLAY=self.display)
        glx = subprocess.run(['glxinfo', '-B'], env=probe, capture_output=True, text=True, timeout=60).stdout
        rows = [line for line in glx.splitlines() if 'OpenGL renderer string' in line]
        self.glx = rows[0].split(':', 1)[1].strip() if rows else 'unknown'

    def close(self):
        os.killpg(self.process.pid, signal.SIGTERM)
        self.process.wait(timeout=10)


def find_window(display, title):
    from Xlib import X
    atom = display.intern_atom('_NET_WM_NAME')

    def walk(window):
        try:
            for child in window.query_tree().children:
                name = child.get_full_text_property(atom) if hasattr(child, 'get_full_text_property') else None
                if not name:
                    try:
                        prop = child.get_full_property(atom, X.AnyPropertyType)
                        name = prop.value.decode() if prop else child.get_wm_name()
                    except Exception:
                        name = None
                if name and title in str(name):
                    return child
                found = walk(child)
                if found:
                    return found
        except Exception:
            return None
        return None

    return walk(display.screen().root)


def tree_stat(pid):
    """Own CPU seconds and memory of the terminal, without its benchmark child."""
    try:
        stat = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        rss = hwm = 0
        for line in Path(f'/proc/{pid}/status').read_text().splitlines():
            if line.startswith('VmRSS:'):
                rss = int(line.split()[1])
            if line.startswith('VmHWM:'):
                hwm = int(line.split()[1])
        return (int(stat[11]) + int(stat[12])) / os.sysconf('SC_CLK_TCK'), rss / 1024, hwm / 1024
    except (OSError, IndexError, ValueError):
        return 0.0, 0.0, 0.0


def measure_latency(state, window, samples, control=False):
    """Milliseconds from one written cell to its pixels reaching the window.

    Frame events can't show this: an idle terminal may present constantly. A
    band of rows around the written one is read back until it changes.
    """
    import ctypes
    x11 = ctypes.CDLL('libX11.so.6')
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    x11.XGetImage.restype = ctypes.c_void_p
    x11.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_uint,
                              ctypes.c_uint, ctypes.c_ulong, ctypes.c_int]
    x11.XDestroyImage = x11.XFree
    x11.XFree.argtypes = [ctypes.c_void_p]
    connection = x11.XOpenDisplay(os.environ['DISPLAY'].encode())
    if not connection:
        raise RuntimeError('No display')
    geometry = window.get_geometry()
    top, height = 0, geometry.height // 4

    class Image(ctypes.Structure):
        _fields_ = [('width', ctypes.c_int), ('height', ctypes.c_int), ('xoffset', ctypes.c_int), ('format', ctypes.c_int),
                    ('data', ctypes.c_void_p), ('byte_order', ctypes.c_int), ('bitmap_unit', ctypes.c_int),
                    ('bitmap_bit_order', ctypes.c_int), ('bitmap_pad', ctypes.c_int), ('depth', ctypes.c_int),
                    ('bytes_per_line', ctypes.c_int)]

    def snapshot():
        pointer = x11.XGetImage(connection, window.id, 0, top, geometry.width, height, 0xffffffff, 2)
        if not pointer:
            return b''
        image = Image.from_address(pointer)
        data = ctypes.string_at(image.data, image.bytes_per_line * image.height)
        libc = ctypes.CDLL(None)
        libc.free.argtypes = [ctypes.c_void_p]
        libc.free(image.data)
        x11.XFree(pointer)
        return data

    fifo_path = state / 'latency.fifo'
    os.mkfifo(fifo_path)
    (state / 'z-latency.job').write_text('')
    fifo = os.open(fifo_path, os.O_WRONLY)
    values = []
    rng = random.Random(11)
    try:
        time.sleep(.3)
        for _ in range(samples):
            time.sleep(rng.uniform(.03, .08))
            before = snapshot()
            began = time.monotonic()
            if not control:
                os.write(fifo, b'x')
            limit = began + (.2 if control else 1.0)
            while time.monotonic() < limit:
                if snapshot() != before:
                    values.append((time.monotonic() - began) * 1000)
                    break
    finally:
        os.write(fifo, b'q')
        os.close(fifo)
        fifo_path.unlink()
        x11.XCloseDisplay(connection)
    return values


def one_run(name, args, compositor, workloads, extra, root, number):
    from Xlib import display as xdisplay
    title = f'bench-{name}-{number}-{os.getpid()}'
    home = root / f'home-{name}-{number}'
    state = root / f'state-{name}-{number}'
    (home / '.config').mkdir(parents=True)
    state.mkdir()
    command = [sys.executable, '-I', str(Path(__file__).resolve()), '--child', '--child-state', str(state)]
    wayland = compositor.socket if name == 'foot' else None
    env = clean_env(home, compositor.runtime, compositor.display, wayland)
    if name == 'terminal':
        env.update(item.split('=', 1) for item in args.terminal_env)
    if name == 'foot':
        env['LD_LIBRARY_PATH'] = str(extra / 'usr/lib/x86_64-linux-gnu')
    report = dict(terminal=name, run=number)
    began = time.monotonic()
    log = open(root / f'{name}-{number}.log', 'w')
    process = subprocess.Popen(launch_command(name, args, title, command, extra), env=env, cwd=home,
                               stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        ready = wait_for(lambda: (state / 'ready').exists() and (state / 'ready').read_text(), 30, 'child ready')
        report['startup_ms'] = (float(ready) - began) * 1000
        report['cells'] = json.loads((state / 'size').read_text())
        time.sleep(.5)
        cpu_before, _, _ = tree_stat(process.pid)
        time.sleep(3)
        cpu_after, rss, _ = tree_stat(process.pid)
        report['idle_cpu_percent'] = (cpu_after - cpu_before) / 3 * 100
        report['startup_rss_mb'] = rss
        os.environ['DISPLAY'] = compositor.display
        if wayland is None and 'latency' in workloads:
            connection = xdisplay.Display(compositor.display)
            window = wait_for(lambda: find_window(connection, title), 10, 'window')
            # With nothing written the band must hold still, or latency means nothing.
            state_control = measure_latency(state, window, 20, True)
            report['idle_pixel_changes'] = len(state_control)
            samples = measure_latency(state, window, args.latency_samples)
            connection.close()
            if samples:
                samples.sort()
                report['latency_ms'] = statistics.median(samples)
                report['latency_p95_ms'] = samples[int(len(samples) * .95) - 1]
                report['latency_samples'] = len(samples)
        for kind in workloads:
            if kind == 'latency':
                continue
            cpu_before, _, _ = tree_stat(process.pid)
            (state / f'a-{kind}.job').write_text('')
            result = state / f'{kind}.result'
            wait_for(lambda: result.exists() or process.poll() is not None, args.timeout, kind)
            if process.poll() is not None:
                report[kind + '_error'] = f'terminal exited {process.returncode}'
                break
            time.sleep(.05)
            data = json.loads(result.read_text())
            cpu_after, _, _ = tree_stat(process.pid)
            report[kind + '_mb_s'] = data['bytes'] / MEGABYTE / data['seconds']
            report[kind + '_cpu_s'] = cpu_after - cpu_before
        _, rss, hwm = tree_stat(process.pid)
        report['final_rss_mb'] = rss
        report['peak_rss_mb'] = hwm
        (state / 'z-quit.job').write_text('')
    except TimeoutError as error:
        report['error'] = 'timed out: ' + str(error)
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        log.close()
    return report


def summary(reports, names):
    fields = [('startup_ms', 'Startup ms'), ('idle_cpu_percent', 'Idle CPU %'), ('latency_ms', 'Output→frame median ms'),
              ('latency_p95_ms', 'Output→frame p95 ms')]
    fields += [(kind + '_mb_s', kind + ' MB/s') for kind in WORKLOADS]
    fields += [(kind + '_cpu_s', kind + ' terminal CPU s') for kind in WORKLOADS]
    fields += [('startup_rss_mb', 'RSS at start MB'), ('peak_rss_mb', 'Peak RSS MB')]
    lines = ['| Measure | ' + ' | '.join(names) + ' |', '|---|' + '---:|' * len(names)]
    for key, label in fields:
        cells = []
        for name in names:
            values = [r[key] for r in reports if r['terminal'] == name and key in r]
            cells.append(f'{statistics.median(values):.1f}' if values else '–')
        lines.append(f'| {label} | ' + ' | '.join(cells) + ' |')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--child-state')
    parser.add_argument('--out', default='build/benchmarks/gpu')
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--only', default='terminal,alacritty,kitty,xterm')
    parser.add_argument('--workloads', default='latency,' + ','.join(WORKLOADS))
    parser.add_argument('--terminal-bin', default=str(Path.home() / '.local/bin/terminal'))
    parser.add_argument('--extra-root', default=str(Path.home() / '.local/share/terminal-bench/root'))
    parser.add_argument('--latency-samples', type=int, default=200)
    parser.add_argument('--timeout', type=float, default=240)
    parser.add_argument('--terminal-env', action='append', default=[], help='NAME=VALUE for Terminal only')
    args = parser.parse_args()
    if args.child:
        child(args)
        return 0
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    names = args.only.split(',')
    workloads = args.workloads.split(',')
    # /tmp directly: a long TMPDIR overflows the compositor's socket path.
    root = Path(tempfile.mkdtemp(prefix='tgb-', dir='/tmp'))
    compositor = Compositor(root)
    reports = []
    stamp = time.strftime('%Y%m%dT%H%M%S')
    path = out / f'gpu-{stamp}.jsonl'
    try:
        print('compositor:', compositor.renderer, '| GLX:', compositor.glx, flush=True)
        with open(path, 'w') as output:
            output.write(json.dumps(dict(renderer=compositor.renderer, glx=compositor.glx, load=os.getloadavg())) + '\n')
            for number in range(args.runs):
                for name in names:
                    report = one_run(name, args, compositor, workloads, Path(args.extra_root), root, number)
                    reports.append(report)
                    output.write(json.dumps(report) + '\n')
                    output.flush()
                    print(json.dumps(report), flush=True)
    finally:
        compositor.close()
        shutil.rmtree(root, ignore_errors=True)
    table = summary(reports, names)
    (out / f'gpu-{stamp}.md').write_text(table + '\n')
    print(table)
    return 0


if __name__ == '__main__':
    sys.exit(main())
