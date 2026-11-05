"""Right-click copy of a dragged selection in the real window on private Xvfb."""
import os
from pathlib import Path
import shlex
import struct
import subprocess
import sys
import tempfile
import time

from standalone_window_test import close_window

COLUMNS, ROWS, TEXT_ROW = 40, 8, 3


def wait(predicate, message, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.05)
    raise AssertionError(message() if callable(message) else message)


def window_rows(window, env, first, last):
    """Pixel bytes of grid rows first..last from the private window."""
    data = subprocess.run(['xwd', '-silent', '-id', window], env=env, capture_output=True,
                          check=True, timeout=5).stdout
    header = struct.unpack('>25I', data[:100])
    size, width, height, bits, stride, colors = header[0], header[4], header[5], header[11], header[12], header[19]
    assert bits in (24, 32), header
    pixels = data[size + colors * 12:]
    line = height / ROWS
    top, bottom = int(line * first), int(line * (last + 1))
    return b''.join(pixels[y * stride:y * stride + width * bits // 8] for y in range(top, bottom))


def selection(env, name):
    result = subprocess.run(['xclip', '-selection', name, '-o'], env=env, capture_output=True, timeout=5)
    return result.stdout.decode(errors='replace') if result.returncode == 0 else None


def main():
    assert os.environ.get('TERMINAL_PRIVATE_XVFB') == '1'
    assert os.environ['DISPLAY'].startswith(':')
    assert os.environ.get('YUE_DESKTOP_RECOVERY') == '0'
    binary = str(Path(sys.argv[1]).resolve())
    Path('build/ziran').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='terminal-selection-copy-', dir='build/ziran') as directory:
        root = Path(directory).resolve()
        shell = root / 'shell'
        shell.write_text('#!/bin/sh\nexec /bin/sh -c "$2"\n'); shell.chmod(0o700)
        child = root / 'child.py'; incoming = root / 'input'
        child.write_text('import os,tty\ntty.setraw(0)\nos.write(1,' + repr(
            b'\r\n' * TEXT_ROW + b'alpha beta gamma\r\n') + ')\n'
            'with open(' + repr(str(incoming)) + ', "wb", buffering=0) as log:\n'
            ' while True:\n  data=os.read(0,1024)\n  if not data: break\n  log.write(data)\n')
        env = dict(os.environ, XDG_CONFIG_HOME=str(root / 'config'), XDG_STATE_HOME=str(root / 'state'),
                   SDL_VIDEODRIVER='x11', LP_NUM_THREADS='1', OMP_NUM_THREADS='1')

        def xdo(*args):
            return subprocess.run(['xdotool', *map(str, args)], env=env, text=True, capture_output=True,
                                  check=True, timeout=5).stdout.strip()
        with (root / 'window.log').open('w') as log:
            app = subprocess.Popen([binary, '--hide-menubar', '--hide-toolbar', '--geometry', f'{COLUMNS}x{ROWS}',
                                    '--shell', str(shell), '-e', 'python3 ' + shlex.quote(str(child))],
                                   env=env, stdout=log, stderr=log)
            try:
                def find():
                    result = subprocess.run(['xdotool', 'search', '--onlyvisible', '--pid', str(app.pid)],
                                            env=env, capture_output=True, text=True)
                    return result.stdout.splitlines()[-1] if result.returncode == 0 and incoming.exists() else None
                window = wait(find, 'Terminal window and raw child')
                assert int(xdo('getwindowpid', window)) == app.pid
                geometry = dict(line.split('=', 1) for line in xdo('getwindowgeometry', '--shell', window).splitlines())
                cell = int(geometry['WIDTH']) / COLUMNS; line = int(geometry['HEIGHT']) / ROWS
                y = int(line * (TEXT_ROW + .5))
                xdo('windowfocus', '--sync', window)
                xdo('mousemove', '--window', window, int(cell * 20), int(line * 6.5))
                time.sleep(.5)
                # Rows above the cursor hold the text; cursor blink stays out of them.
                def stable():
                    first = window_rows(window, env, 0, TEXT_ROW)
                    return first if first == window_rows(window, env, 0, TEXT_ROW) else None
                baseline = wait(stable, 'Stable text rows')
                assert selection(env, 'clipboard') != 'beta'

                xdo('mousemove', '--window', window, int(cell * 6.5), y); time.sleep(.1)
                xdo('mousedown', '1')
                for column in (7, 8, 9):
                    time.sleep(.05); xdo('mousemove', '--window', window, int(cell * (column + .5)), y)
                time.sleep(.1); xdo('mouseup', '1')
                wait(lambda: window_rows(window, env, 0, TEXT_ROW) != baseline, 'Dragged selection is highlighted')
                assert selection(env, 'clipboard') != 'beta', 'Selecting alone must not replace the clipboard'

                xdo('mousedown', '3'); time.sleep(.1); xdo('mouseup', '3')
                started = time.monotonic()
                wait(lambda: selection(env, 'clipboard') == 'beta',
                     lambda: f'Right-click copies exactly beta, got {selection(env, "clipboard")!r}', 2)
                wait(lambda: window_rows(window, env, 0, TEXT_ROW) == baseline,
                     'Right-click clears the visible selection without opening a menu', 2)
                cleared = time.monotonic() - started
                time.sleep(.6)
                assert window_rows(window, env, 0, TEXT_ROW) == baseline, 'Selection stays cleared'
                assert incoming.read_bytes() == b'', 'Right-click copy must not write to the child'
                close_window(window, app.pid, env); app.wait(timeout=5)
            finally:
                if app.poll() is None:
                    app.terminate(); app.wait(timeout=5)
        print(f'Terminal right-click copied the dragged selection and cleared it in {cleared:.2f}s on private Xvfb')


if __name__ == '__main__':
    main()
