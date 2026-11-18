"""Rendered xfce4-terminal 1.1.4 context-menu reference on private Xvfb."""
import os
from pathlib import Path
from difflib import SequenceMatcher
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
from standalone_window_test import close_window


REFERENCE = (
    'open tab', 'open terminal', 'open file manager here',
    'copy', 'copy as html', 'paste', 'paste selection',
    'show menubar', 'fullscreen', 'read-only', 'send signal', 'zoom',
    'save contents', 'preferences',
)


def wait(predicate, message, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.06)
    raise AssertionError(message)


def normalized(text):
    return re.sub(r'[^a-z0-9+.-]+', ' ', text.lower()).strip()


def in_order(text, phrases):
    rows = tuple(filter(None, text.splitlines()))
    at = 0
    for phrase in phrases:
        for index in range(at, len(rows)):
            if phrase in rows[index] or SequenceMatcher(None, phrase, rows[index]).ratio() >= .72:
                at = index + 1
                break
        else:
            return False
    return True


def screenshot_text(window, env, root):
    image = root / 'context-menu.png'
    subprocess.run(['import', '-window', window, '-resize', '400%', str(image)], env=env,
                   check=True, timeout=5, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    result = subprocess.run(['tesseract', str(image), 'stdout', '--psm', '4'],
                            env=env, check=True, timeout=8, text=True,
                            capture_output=True)
    return '\n'.join(normalized(line) for line in result.stdout.splitlines())


def main():
    assert os.environ.get('TERMINAL_PRIVATE_XVFB') == '1'
    assert os.environ['DISPLAY'].startswith(':')
    assert os.environ.get('HARMONY_DESKTOP_RECOVERY') == '0'
    for program in ('xdotool', 'import', 'tesseract'):
        assert shutil.which(program), f'{program} is required for the rendered menu comparison'
    binary = str(Path(sys.argv[1]).resolve())
    Path('build/ziran').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='terminal-context-menu-', dir='build/ziran') as directory:
        root = Path(directory).resolve()
        shell = root / 'shell'
        shell.write_text('#!/bin/sh\nexec /bin/sh -c "$2"\n')
        shell.chmod(0o700)
        child = root / 'child.py'
        ready = root / 'ready'
        child.write_text(
            'import os,sys,tty\n'
            'tty.setraw(0)\n'
            'open(sys.argv[1],"wb").close()\n'
            'while os.read(0,1024): pass\n')
        env = dict(os.environ, XDG_CONFIG_HOME=str(root / 'config'),
                   XDG_STATE_HOME=str(root / 'state'), SDL_VIDEODRIVER='x11',
                   LP_NUM_THREADS='1', OMP_NUM_THREADS='1')

        def xdo(*args):
            return subprocess.run(['xdotool', *map(str, args)], env=env, text=True,
                                  capture_output=True, check=True, timeout=5).stdout.strip()

        with (root / 'window.log').open('w') as log:
            command = 'python3 ' + shlex.quote(str(child)) + ' ' + shlex.quote(str(ready))
            app = subprocess.Popen([
                binary, '--hide-menubar', '--hide-toolbar', '--geometry', '80x34',
                '--shell', str(shell), '-e', command,
            ], env=env, stdout=log, stderr=log)
            try:
                def find_window():
                    found = subprocess.run(
                        ['xdotool', 'search', '--onlyvisible', '--pid', str(app.pid)],
                        env=env, capture_output=True, text=True)
                    lines = found.stdout.splitlines()
                    return lines[-1] if found.returncode == 0 and lines and ready.exists() else None

                window = wait(find_window, 'Terminal context-menu fixture did not open')
                assert int(xdo('getwindowpid', window)) == app.pid
                xdo('windowfocus', '--sync', window)
                time.sleep(.3)
                xdo('mousemove', '--window', window, 60, 100)
                xdo('mousedown', '3'); time.sleep(.15); xdo('mouseup', '3')

                # Each capture is read until the expected rows appear, so a frame
                # taken before the menu or submenu is painted is not judged.
                def rendered(phrases):
                    def read():
                        text = screenshot_text(window, env, root)
                        return text if in_order(text, phrases) else None
                    return read

                text = wait(rendered(REFERENCE), 'Context menu was not rendered')
                assert in_order(text, REFERENCE), repr(text)
                assert 'open link' not in text and 'compose email' not in text

                # The reference Zoom row is 335 units below the panel top and
                # is 26 units tall. Hovering it must render the three reference
                # submenu actions and their accelerator labels.
                xdo('mousemove', '--window', window, 120, 448)
                zoom = wait(rendered(('zoom in', 'zoom out', 'normal size')),
                            'Zoom submenu was not rendered')
                assert in_order(zoom, ('zoom in', 'zoom out', 'normal size')), zoom
                # OCR reads the monospaced "Ctrl" as "ctr1" at some sizes.
                assert len(re.findall(r'ctr[l1i]', zoom)) >= 3, zoom
                close_window(window, app.pid, env)
                assert app.wait(timeout=5) == 0
            finally:
                if app.poll() is None:
                    app.terminate()
                    app.wait(timeout=5)
    print('Terminal rendered context menu and Zoom submenu match the captured xfce4-terminal 1.1.4 reference')


if __name__ == '__main__':
    main()
