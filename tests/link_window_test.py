"""Actual SDL pointer/modifier routing and OS opener on verified private Xvfb."""
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time

from standalone_window_test import close_window


def wait(predicate, message):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.05)
    raise AssertionError(message)


def main():
    assert os.environ.get('TERMINAL_PRIVATE_XVFB') == '1'
    assert os.environ['DISPLAY'].startswith(':')
    assert os.environ.get('YUE_DESKTOP_RECOVERY') == '0'
    binary = str(Path(sys.argv[1]).resolve())
    Path('work').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='link-window-', dir='work') as directory:
        root = Path(directory).resolve()
        opener = root / 'xdg-open'
        opened = root / 'opened'
        opener.write_text('#!/bin/sh\nprintf "%s\\n" "$1" >> "$TERMINAL_LINK_RECEIPT"\n')
        opener.chmod(0o700)
        shell = root / 'shell'
        shell.write_text('#!/bin/sh\nexec /bin/sh -c "$2"\n'); shell.chmod(0o700)
        url = 'https://example.org/a(b)?q=1#part'
        target = 'https://example.org/hidden'
        child = root / 'child.py'; incoming = root / 'input'
        child.write_text('import os,tty\ntty.setraw(0)\nos.write(1,' + repr(
            (url + '.\r\n\x1b]8;;' + target + '\x07label\x1b]8;;\x07\r\n\x1b[?1000h\x1b[?1006h').encode()) + ')\n'
            'with open(' + repr(str(incoming)) + ', "wb", buffering=0) as log:\n'
            ' while True:\n  data=os.read(0,1024)\n  if not data: break\n  log.write(data)\n')
        env = dict(os.environ, PATH=str(root) + ':' + os.environ['PATH'], TERMINAL_LINK_RECEIPT=str(opened),
                   XDG_CONFIG_HOME=str(root / 'config'), XDG_STATE_HOME=str(root / 'state'),
                   SDL_VIDEODRIVER='x11', LP_NUM_THREADS='1', OMP_NUM_THREADS='1')
        def xdo(*args):
            return subprocess.run(['xdotool', *map(str, args)], env=env, text=True, capture_output=True, check=True, timeout=5).stdout.strip()
        with (root / 'window.log').open('w') as log:
            app = subprocess.Popen([binary, '--hide-menubar', '--hide-toolbar', '--geometry', '40x8', '--shell', str(shell),
                                    '-e', 'python3 ' + shlex.quote(str(child))], env=env, stdout=log, stderr=log)
            try:
                def find():
                    result = subprocess.run(['xdotool', 'search', '--onlyvisible', '--pid', str(app.pid)], env=env, capture_output=True, text=True)
                    return result.stdout.splitlines()[-1] if result.returncode == 0 and incoming.exists() else None
                window = wait(find, 'Terminal window and raw child')
                assert int(xdo('getwindowpid', window)) == app.pid
                geometry = dict(line.split('=', 1) for line in xdo('getwindowgeometry', '--shell', window).splitlines())
                cell = int(geometry['WIDTH']) / 40; line = int(geometry['HEIGHT']) / 8
                def click(modifier, row, before_focus=False):
                    if before_focus:
                        xdo('windowfocus', '0')
                    xdo('keydown', modifier)
                    xdo('windowfocus', '--sync', window)
                    xdo('mousemove', '--window', window, int(cell * 2.5), int(line * (row + .5)))
                    time.sleep(.1)
                    xdo('mousedown', '1'); time.sleep(.1); xdo('mouseup', '1')
                    xdo('keyup', modifier)
                click('Alt_L', 0, True)
                wait(lambda: opened.exists(), 'Alt-click visible URL opens')
                assert opened.read_text().splitlines() == [url]
                click('Alt_R', 1)
                wait(lambda: len(opened.read_text().splitlines()) == 2, 'Right Alt-click OSC 8 opens')
                assert opened.read_text().splitlines() == [url, target]
                click('Control_L', 0)
                wait(lambda: len(opened.read_text().splitlines()) == 3, 'Ctrl-click compatibility')
                assert opened.read_text().splitlines() == [url, target, url]
                time.sleep(.2)
                assert incoming.read_bytes() == b'', 'Link gestures must not send half a mouse click'
                close_window(window, app.pid, env); app.wait(timeout=5)
            finally:
                if app.poll() is None:
                    app.terminate(); app.wait(timeout=5)
        print('Terminal native SDL Alt/Ctrl URL and OSC 8 link opening passed on private Xvfb')


if __name__ == '__main__':
    main()
