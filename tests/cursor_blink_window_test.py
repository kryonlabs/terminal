"""Cursor timing and focus in two owned Terminal windows on private Xvfb."""
import os
from pathlib import Path
import shlex
import struct
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
from standalone_window_test import close_window


def wait(predicate, message):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.04)
    raise AssertionError(message)


def cursor_visible(window, env):
    data = subprocess.run(['xwd', '-silent', '-id', window], env=env,
                          capture_output=True, check=True, timeout=5).stdout
    header = struct.unpack('>25I', data[:100])
    size, width, height, bits, stride, colors = (
        header[0], header[4], header[5], header[11], header[12], header[19])
    assert bits in (24, 32), header
    # Both windows have a blank 20x8 grid with the cursor at column/row zero.
    x, y = width // 40, height // 16
    offset = size + colors * 12 + y * stride + x * (bits // 8)
    pixel = int.from_bytes(data[offset:offset + bits // 8],
                           'little' if header[7] == 0 else 'big')
    return pixel & header[14] == 0xf00000 and pixel & header[15] == 0x1000 and pixel & header[16] == 0x20


def main():
    assert os.environ.get('TERMINAL_PRIVATE_XVFB') == '1'
    assert os.environ['DISPLAY'].startswith(':')
    assert os.environ.get('HARMONY_DESKTOP_RECOVERY') == '0'
    binary = str(Path(sys.argv[1]).resolve())
    Path('build/ziran').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='terminal-cursor-', dir='build/ziran') as directory:
        root = Path(directory).resolve()
        shell = root / 'shell'
        shell.write_text('#!/bin/sh\nexec /bin/sh -c "$2"\n')
        shell.chmod(0o700)
        child = root / 'child.py'
        child.write_text(
            'import os,sys,tty\n'
            'tty.setraw(0)\n'
            'os.write(1,b"\\x1b[2J\\x1b[H\\x1b[1 q\\x1b[?12h")\n'
            'with open(sys.argv[1],"wb",buffering=0) as log:\n'
            ' while True:\n'
            '  data=os.read(0,1024)\n'
            '  if not data: break\n'
            '  log.write(data)\n'
            '  if b"s" in data: os.write(1,b"\\x1b[2 q")\n'
            '  if b"h" in data: os.write(1,b"\\x1b[?25l")\n')
        env = os.environ.copy()
        for key in ('WAYLAND_DISPLAY', 'DBUS_SESSION_BUS_ADDRESS', 'SESSION_MANAGER',
                    'KRYON_CAPTURE_PATH', 'ENV', 'BASH_ENV'):
            env.pop(key, None)
        env.update(XDG_CONFIG_HOME=str(root / 'config'), XDG_STATE_HOME=str(root / 'state'),
                   SDL_VIDEODRIVER='x11', HARMONY_DESKTOP_RECOVERY='0',
                   LP_NUM_THREADS='1', OMP_NUM_THREADS='1')
        apps, windows, logs, inputs = [], [], [], []

        def xdo(*args):
            return subprocess.run(['xdotool', *map(str, args)], env=env, text=True,
                                  capture_output=True, check=True, timeout=5).stdout.strip()

        def visible(index):
            assert apps[index].poll() is None
            return cursor_visible(windows[index], env)

        def sample(active, background):
            seen = set()
            deadline = time.monotonic() + 1.8
            while time.monotonic() < deadline:
                assert visible(background), 'Inactive cursor blinked off'
                seen.add(visible(active))
                time.sleep(.04)
            assert seen == {False, True}, ('Focused cursor did not blink', seen)

        try:
            for index in range(2):
                incoming = root / f'input-{index}'
                inputs.append(incoming)
                log = (root / f'window-{index}.log').open('w')
                logs.append(log)
                command = shlex.join(['python3', str(child), str(incoming)])
                app = subprocess.Popen([
                    binary, '--hide-menubar', '--hide-toolbar', '--geometry', '20x8',
                    '--terminal-cursor', '#f01020', '--terminal-background', '#000000',
                    '--shell', str(shell), '-e', command], env=env, stdout=log, stderr=log)
                apps.append(app)

                def find():
                    assert app.poll() is None, (root / f'window-{index}.log').read_text()
                    result = subprocess.run(['xdotool', 'search', '--onlyvisible', '--pid', str(app.pid)],
                                            env=env, capture_output=True, text=True, timeout=5)
                    return result.stdout.splitlines()[-1] if result.returncode == 0 and incoming.exists() else None

                window = wait(find, 'Owned terminal window and raw child')
                assert int(xdo('getwindowpid', window)) == app.pid
                windows.append(window)
                xdo('windowmove', window, 10 + index * 400, 10)
            xdo('windowfocus', '--sync', windows[1])
            time.sleep(.15)
            sample(1, 0)
            xdo('windowfocus', '--sync', windows[0])
            time.sleep(.15)
            assert visible(0), 'Focus gain did not show the cursor'
            sample(0, 1)
            wait(lambda: not visible(0), 'Focused cursor off phase')
            xdo('type', '--clearmodifiers', 'a')
            wait(lambda: inputs[0].read_bytes() == b'a', 'Typing reached the focused child')
            deadline = time.monotonic() + .3
            while time.monotonic() < deadline:
                assert visible(0), 'Typing did not restart a visible cursor interval'
                time.sleep(.04)
            assert inputs[1].read_bytes() == b'', 'Input reached the inactive child'
            xdo('type', '--clearmodifiers', 's')
            wait(lambda: inputs[0].read_bytes() == b'as', 'Steady cursor request reached child')
            time.sleep(.15)
            deadline = time.monotonic() + 1.2
            while time.monotonic() < deadline:
                assert visible(0), 'DECSCUSR steady cursor blinked'
                time.sleep(.06)
            xdo('type', '--clearmodifiers', 'h')
            wait(lambda: not visible(0), 'DECTCEM hid the cursor')
            xdo('windowfocus', '--sync', windows[1])
            time.sleep(.15)
            assert not visible(0), 'Inactive window showed a protocol-hidden cursor'
            for app, window in zip(apps, windows):
                close_window(window, app.pid, env)
                assert app.wait(timeout=5) == 0
        finally:
            for app in apps:
                if app.poll() is None:
                    app.terminate()
                    app.wait(timeout=5)
            for log in logs:
                log.close()
    print('Terminal cursor blink: focus, two windows, typing, steady and hidden modes passed on private Xvfb')


if __name__ == '__main__':
    main()
