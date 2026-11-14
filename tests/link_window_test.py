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
    assert os.environ.get('HARMONY_DESKTOP_RECOVERY') == '0'
    binary = str(Path(sys.argv[1]).resolve())
    Path('backup/tests').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='link-window-', dir='backup/tests') as directory:
        root = Path(directory).resolve()
        opened = root / 'opened'
        shell = root / 'shell'
        shell.write_text('#!/bin/sh\nexec /bin/sh -c "$2"\n'); shell.chmod(0o700)
        url = 'https://example.org/a(b)?q=1#part'
        target = 'https://example.org/hidden'
        email = 'person@example.org'
        wrapped = ('https://auth.openai.com/oauth/authorize?response_type=code&client_id=app&'
                   'redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback&scope=openid&'
                   'state=state-value-0123456789abcdef&codex_cli_simplified_flow=true')
        child = root / 'child.py'; incoming = root / 'input'
        child.write_text('import os,tty\ntty.setraw(0)\nos.write(1,' + repr(
            (wrapped + '\r\n' + url + '.\r\n\x1b]8;;' + target +
             '\x07label\x1b]8;;\x07\r\n' + email +
             '\r\n\x1b[?1000h\x1b[?1006h').encode()) + ')\n'
            'with open(' + repr(str(incoming)) + ', "wb", buffering=0) as log:\n'
            ' while True:\n  data=os.read(0,1024)\n  if not data: break\n  log.write(data)\n')
        env = dict(os.environ, KRYON_TEST_OPEN_URI_CAPTURE=str(opened),
                   XDG_CONFIG_HOME=str(root / 'config'), XDG_STATE_HOME=str(root / 'state'),
                   SDL_VIDEODRIVER='x11', LP_NUM_THREADS='1', OMP_NUM_THREADS='1')
        def xdo(*args):
            return subprocess.run(['xdotool', *map(str, args)], env=env, text=True, capture_output=True, check=True, timeout=5).stdout.strip()
        with (root / 'window.log').open('w') as log:
            app = subprocess.Popen([binary, '--hide-menubar', '--hide-toolbar', '--geometry', '56x8', '--shell', str(shell),
                                    '-e', 'python3 ' + shlex.quote(str(child))], env=env, stdout=log, stderr=log)
            try:
                def find():
                    result = subprocess.run(['xdotool', 'search', '--onlyvisible', '--pid', str(app.pid)], env=env, capture_output=True, text=True)
                    return result.stdout.splitlines()[-1] if result.returncode == 0 and incoming.exists() else None
                window = wait(find, 'Terminal window and raw child')
                assert int(xdo('getwindowpid', window)) == app.pid
                geometry = dict(line.split('=', 1) for line in xdo('getwindowgeometry', '--shell', window).splitlines())
                cell = int(geometry['WIDTH']) / 56; line = int(geometry['HEIGHT']) / 8
                def click(modifier, row, column=2.5, before_focus=False, unfocused=False):
                    if before_focus or unfocused:
                        xdo('windowfocus', '0')
                    xdo('keydown', modifier)
                    if not unfocused:
                        xdo('windowfocus', '--sync', window)
                    xdo('mousemove', '--window', window, int(cell * column), int(line * (row + .5)))
                    time.sleep(.1)
                    xdo('mousedown', '1'); time.sleep(.1); xdo('mouseup', '1')
                    xdo('keyup', modifier)
                click('Alt_L', 4, before_focus=True)
                wait(lambda: opened.exists() and opened.read_text() == url, 'Alt-click visible URL opens')
                click('Alt_R', 5)
                wait(lambda: opened.read_text() == target, 'Right Alt-click OSC 8 opens')
                click('Alt_L', 6)
                wait(lambda: opened.read_text() == 'mailto:' + email, 'Alt-click email composes mail')
                click('Alt_L', 0)
                wait(lambda: opened.read_text() == wrapped, 'Alt-click wrapped URL opens from first row')
                click('Alt_R', 2)
                wait(lambda: opened.read_text() == wrapped, 'Alt-click wrapped URL opens from continuation row')
                click('Alt_L', 3)
                wait(lambda: opened.read_text() == wrapped, 'Alt-click wrapped URL opens after state split')
                click('Control_L', 4)
                wait(lambda: opened.read_text() == url, 'Ctrl-click compatibility')
                click('Alt_L', 4, unfocused=True)
                wait(lambda: opened.read_text() == url, 'Unfocused/embedded Alt-click opens')
                # The wrapped continuation resolves identically through the
                # context menu's independent Copy Link and Open Link actions.
                # The child tracks the mouse, so a plain right-click is its own;
                # Shift bypasses mouse reporting and opens the menu, as in
                # xfce4-terminal. The unfocused click above left focus elsewhere,
                # and a private display has no window manager to restore it.
                def menu():
                    xdo('windowfocus', '--sync', window)
                    xdo('mousemove', '--window', window, int(cell * 2.5), int(line * 2.5))
                    xdo('keydown', 'Shift_L')
                    xdo('mousedown', '3'); time.sleep(.1); xdo('mouseup', '3')
                    xdo('keyup', 'Shift_L'); time.sleep(.2)
                menu()
                xdo('mousemove', '--window', window, int(cell * 2.5) + 60, 43)
                xdo('mousedown', '1'); time.sleep(.12); xdo('mouseup', '1')
                wait(lambda: subprocess.run(['xclip', '-selection', 'clipboard', '-o'], env=env,
                                             capture_output=True).stdout == wrapped.encode(),
                     'Context-menu Copy Link preserves the exact wrapped OAuth URL')
                opened.write_text('sentinel')
                menu()
                xdo('mousemove', '--window', window, int(cell * 2.5) + 60, 17)
                xdo('mousedown', '1'); time.sleep(.12); xdo('mouseup', '1')
                wait(lambda: opened.read_text() == wrapped,
                     'Context-menu Open Link preserves the exact wrapped OAuth URL')
                time.sleep(.2)
                assert incoming.read_bytes() == b'', 'Link gestures must not send half a mouse click'
                close_window(window, app.pid, env); app.wait(timeout=5)
            finally:
                if app.poll() is None:
                    app.terminate(); app.wait(timeout=5)
        print('Terminal native Alt/Ctrl opens HTTP, OSC 8, email, and wrapped links through Kryon without leaking mouse input')


if __name__ == '__main__':
    main()
