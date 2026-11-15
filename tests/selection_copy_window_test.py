"""PRIMARY publication, right-click copy and xfce-style menu on private Xvfb."""
import os
from pathlib import Path
import shlex
import struct
import subprocess
import sys
import tempfile
import time

from standalone_window_test import close_window

# The 21-row xfce4-terminal menu is taller than this window. Kryon keeps menus
# inside the window, pinned to its top, so the window needs 10 rows for the
# Copy row (about 160 units down) to be reachable.
COLUMNS, ROWS, TEXT_ROW = 56, 10, 4
OAUTH = ('https://auth.openai.com/oauth/authorize?response_type=code&client_id=app&'
         'redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback&scope=openid&'
         'state=state-value-0123456789abcdef&codex_cli_simplified_flow=true')


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
    assert os.environ.get('HARMONY_DESKTOP_RECOVERY') == '0'
    binary = str(Path(sys.argv[1]).resolve())
    Path('build/ziran').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='terminal-selection-copy-', dir='build/ziran') as directory:
        root = Path(directory).resolve()
        shell = root / 'shell'
        shell.write_text('#!/bin/sh\nexec /bin/sh -c "$2"\n'); shell.chmod(0o700)
        child = root / 'child.py'; incoming = root / 'input'
        child.write_text('import os,tty\ntty.setraw(0)\nos.write(1,' + repr(
            OAUTH.encode() + b'\r\nalpha beta gamma\r\n') + ')\n'
            'with open(' + repr(str(incoming)) + ', "wb", buffering=0) as log:\n'
            ' while True:\n  data=os.read(0,1024)\n  if not data: break\n  log.write(data)\n')
        env = dict(os.environ, XDG_CONFIG_HOME=str(root / 'config'), XDG_STATE_HOME=str(root / 'state'),
                   SDL_VIDEODRIVER='x11', LP_NUM_THREADS='1', OMP_NUM_THREADS='1')

        def xdo(*args):
            return subprocess.run(['xdotool', *map(str, args)], env=env, text=True, capture_output=True,
                                  check=True, timeout=5).stdout.strip()

        def shift_right_click():
            xdo('keydown', 'Shift_L'); xdo('mousedown', '3'); time.sleep(.1)
            xdo('mouseup', '3'); xdo('keyup', 'Shift_L'); time.sleep(.2)
        with (root / 'window.log').open('w') as log:
            app = subprocess.Popen([binary, '--hide-menubar', '--hide-toolbar', '--geometry', f'{COLUMNS}x{ROWS}',
                                    '--shell', str(shell), '-e', 'python3 ' + shlex.quote(str(child))],
                                   env=env, stdout=log, stderr=log)
            owners = []
            try:
                def find():
                    result = subprocess.run(['xdotool', 'search', '--onlyvisible', '--pid', str(app.pid)],
                                            env=env, capture_output=True, text=True)
                    return result.stdout.splitlines()[-1] if result.returncode == 0 and incoming.exists() else None
                window = wait(find, 'Terminal window and raw child')
                assert int(xdo('getwindowpid', window)) == app.pid
                geometry = dict(line.split('=', 1) for line in xdo('getwindowgeometry', '--shell', window).splitlines())
                width = int(geometry['WIDTH']); cell = width / COLUMNS; line = int(geometry['HEIGHT']) / ROWS
                y = int(line * (TEXT_ROW + .5))
                xdo('windowfocus', '--sync', window)
                xdo('mousemove', '--window', window, int(cell * 20), int(line * 6.5))
                time.sleep(.5)
                # Rows above the cursor hold the text; cursor blink stays out of them.
                def stable():
                    first = window_rows(window, env, 0, TEXT_ROW)
                    return first if first == window_rows(window, env, 0, TEXT_ROW) else None
                baseline = wait(stable, 'Stable text rows')
                owner = subprocess.Popen(['xclip','-quiet','-selection','clipboard','-in'],env=env,
                                         stdin=subprocess.PIPE,stdout=log,stderr=log)
                owners.append(owner); owner.stdin.write(b'clipboard sentinel'); owner.stdin.close(); time.sleep(.2)

                # Select all four visual rows of one logical OAuth line. At 56
                # columns the wrap splits 1455 and later the state value.
                xdo('mousemove', '--window', window, int(cell * .5), int(line * .5))
                xdo('mousedown', '1')
                for row, column in ((0, 55.5), (1, 55.5), (2, 55.5), (3, 43.5)):
                    time.sleep(.06)
                    xdo('mousemove', '--window', window, int(cell * column), int(line * (row + .5)))
                time.sleep(.1); xdo('mouseup', '1')
                wait(lambda: selection(env, 'primary') == OAUTH,
                     lambda: f'Wrapped OAuth PRIMARY differs: {selection(env, "primary")!r}')

                xdo('keydown', 'Control_L'); xdo('keydown', 'Shift_L'); xdo('key', 'c')
                xdo('keyup', 'Shift_L'); xdo('keyup', 'Control_L')
                wait(lambda: selection(env, 'clipboard') == OAUTH,
                     'Keyboard copy did not preserve the exact wrapped OAuth URL')

                # Shift+right-click opens the link-aware menu on a selection.
                # Copy is the first row after the link actions and open rows.
                # Each menu copy starts from a fresh owner, so its check waits
                # for that copy instead of passing on the previous one.
                owner = subprocess.Popen(['xclip','-quiet','-selection','clipboard','-in'],env=env,
                                         stdin=subprocess.PIPE,stdout=log,stderr=log)
                owners.append(owner); owner.stdin.write(b'copy sentinel'); owner.stdin.close(); time.sleep(.2)
                assert selection(env, 'clipboard') == 'copy sentinel'
                xdo('mousemove', '--window', window, int(cell * 2.5), int(line * 2.5))
                shift_right_click()
                xdo('mousemove', '--window', window, int(cell * 2.5) + 60, 160)
                xdo('mousedown', '1'); time.sleep(.12); xdo('mouseup', '1')
                wait(lambda: selection(env, 'clipboard') == OAUTH,
                     'Shift+right-click menu Copy did not preserve the exact wrapped OAuth selection')

                # A plain click leaves no chosen selection, so right-click opens
                # the menu. Copy Link Address is row two in the link-aware menu.
                xdo('mousemove', '--window', window, int(cell * 20), int(line * 6.5))
                xdo('mousedown', '1'); time.sleep(.12); xdo('mouseup', '1'); time.sleep(.6)
                owner = subprocess.Popen(['xclip','-quiet','-selection','clipboard','-in'],env=env,
                                         stdin=subprocess.PIPE,stdout=log,stderr=log)
                owners.append(owner); owner.stdin.write(b'link sentinel'); owner.stdin.close(); time.sleep(.2)
                assert selection(env, 'clipboard') == 'link sentinel'
                xdo('mousemove', '--window', window, int(cell * 2.5), int(line * 2.5))
                xdo('mousedown', '3'); time.sleep(.1); xdo('mouseup', '3'); time.sleep(.2)
                assert selection(env, 'clipboard') == 'link sentinel', 'Right-click after a plain click copied'
                xdo('mousemove', '--window', window, int(cell * 2.5) + 60, 43)
                xdo('mousedown', '1'); time.sleep(.12); xdo('mouseup', '1')
                wait(lambda: selection(env, 'clipboard') == OAUTH,
                     'Context-menu Copy Link changed the wrapped OAuth URL')

                owner = subprocess.Popen(['xclip','-quiet','-selection','clipboard','-in'],env=env,
                                         stdin=subprocess.PIPE,stdout=log,stderr=log)
                owners.append(owner); owner.stdin.write(b'clipboard sentinel'); owner.stdin.close(); time.sleep(.2)

                xdo('mousemove', '--window', window, int(cell * 6.5), y); time.sleep(.1)
                xdo('mousedown', '1')
                for column in (7, 8, 9):
                    time.sleep(.05); xdo('mousemove', '--window', window, int(cell * (column + .5)), y)
                time.sleep(.1); xdo('mouseup', '1')
                wait(lambda: window_rows(window, env, 0, TEXT_ROW) != baseline, 'Dragged selection is highlighted')
                wait(lambda: selection(env, 'primary') == 'beta',
                     lambda: f'Selection did not publish PRIMARY: {selection(env, "primary")!r}')
                assert selection(env, 'clipboard') == 'clipboard sentinel', 'Selecting alone replaced CLIPBOARD'

                # Right-click on a selection copies it to CLIPBOARD, keeps
                # PRIMARY and opens no menu: typed text still reaches the shell.
                xdo('mousedown', '3'); time.sleep(.1); xdo('mouseup', '3')
                wait(lambda: selection(env, 'clipboard') == 'beta',
                     lambda: f'Right-click did not copy exactly beta: {selection(env, "clipboard")!r}', 2)
                assert selection(env, 'primary') == 'beta', 'Right-click cleared PRIMARY selection'
                before = incoming.stat().st_size
                xdo('type', 'z')
                data = wait(lambda: incoming.read_bytes() if incoming.stat().st_size > before else None,
                            'Right-click on a selection opened a menu that took the keyboard')
                assert data[before:] == b'z', data[before:]

                # Re-select before testing the independent HTML action; a menu
                # activation must not make that action depend on stale UI state.
                time.sleep(.5)
                owner = subprocess.Popen(['xclip','-quiet','-selection','primary','-in'],env=env,
                                         stdin=subprocess.PIPE,stdout=log,stderr=log)
                owners.append(owner); owner.stdin.write(b'primary sentinel'); owner.stdin.close(); time.sleep(.2)
                assert selection(env, 'primary') == 'primary sentinel'
                xdo('mousemove', '--window', window, int(cell * 6.5), y)
                xdo('mousedown', '1')
                for column in (7, 8, 9):
                    time.sleep(.05); xdo('mousemove', '--window', window, int(cell * (column + .5)), y)
                time.sleep(.1); xdo('mouseup', '1')
                wait(lambda: selection(env, 'primary') == 'beta', 'Second selection did not publish PRIMARY')

                # Copy as HTML, from the Shift+right-click menu, owns both safe
                # plain text and escaped HTML.
                xdo('mousemove', '--window', window, int(cell * 8), y)
                shift_right_click()
                xdo('mousemove', '--window', window, int(cell * 8) + 60, 130)
                xdo('mousedown', '1'); time.sleep(.12); xdo('mouseup', '1')
                def clipboard_html():
                    result = subprocess.run(['xclip','-selection','clipboard','-target','text/html','-out'],
                                            env=env,capture_output=True,timeout=5)
                    return result.stdout if result.returncode == 0 else None
                html = wait(clipboard_html, 'Copy as HTML did not offer text/html')
                assert html == b'<pre>beta</pre>', html
                assert selection(env, 'clipboard') == 'beta'

                # An external PRIMARY owner is used by middle-click and
                # Shift+Insert; neither falls back to CLIPBOARD.
                owner = subprocess.Popen(['xclip','-quiet','-selection','primary','-in'],env=env,
                                         stdin=subprocess.PIPE,stdout=log,stderr=log)
                owners.append(owner); owner.stdin.write(b'external primary'); owner.stdin.close(); time.sleep(.2)
                assert selection(env, 'primary') == 'external primary'
                before = incoming.stat().st_size
                xdo('mousemove', '--window', window, int(cell * 20), int(line * 6.5))
                xdo('mousedown', '2'); time.sleep(.12); xdo('mouseup', '2')
                data = wait(lambda: incoming.read_bytes() if incoming.stat().st_size > before else None,
                            'Middle-click did not paste external PRIMARY')
                assert data[before:].replace(b'\x1b[200~',b'').replace(b'\x1b[201~',b'') == b'external primary'
                before = len(data)
                xdo('keydown','shift'); xdo('key','Insert'); xdo('keyup','shift')
                data = wait(lambda: incoming.read_bytes() if incoming.stat().st_size > before else None,
                            'Shift+Insert did not paste PRIMARY')
                assert data[before:].replace(b'\x1b[200~',b'').replace(b'\x1b[201~',b'') == b'external primary'
                close_window(window, app.pid, env); app.wait(timeout=5)
            finally:
                for owner in owners:
                    if owner.poll() is None: owner.terminate()
                    owner.wait(timeout=5)
                if app.poll() is None:
                    app.terminate(); app.wait(timeout=5)
        print('Terminal publishes PRIMARY, copies a selection on right-click, opens the menu without one or with Shift, serves plain+HTML menu copies, and pastes external PRIMARY only')


if __name__ == '__main__':
    main()
