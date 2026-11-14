"""Real PNG clipboard and Xdnd input through an owned native Terminal window."""
import ctypes as C
import ctypes.util
import os
from pathlib import Path
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib

from standalone_window_test import close_window


def wait(predicate, message, seconds=8):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        result = predicate()
        if result:
            return result
        time.sleep(.03)
    raise AssertionError(message)


class Data(C.Union):
    _fields_ = [('longs', C.c_long * 5), ('bytes', C.c_char * 20)]


class Message(C.Structure):
    _fields_ = [('type', C.c_int), ('serial', C.c_ulong), ('send', C.c_int),
                ('display', C.c_void_p), ('window', C.c_ulong),
                ('message_type', C.c_ulong), ('format', C.c_int), ('data', Data)]


class SelectionRequest(C.Structure):
    _fields_ = [('type', C.c_int), ('serial', C.c_ulong), ('send', C.c_int),
                ('display', C.c_void_p), ('owner', C.c_ulong), ('requestor', C.c_ulong),
                ('selection', C.c_ulong), ('target', C.c_ulong), ('property', C.c_ulong),
                ('time', C.c_ulong)]


class SelectionNotify(C.Structure):
    _fields_ = [('type', C.c_int), ('serial', C.c_ulong), ('send', C.c_int),
                ('display', C.c_void_p), ('requestor', C.c_ulong),
                ('selection', C.c_ulong), ('target', C.c_ulong), ('property', C.c_ulong),
                ('time', C.c_ulong)]


class Event(C.Union):
    _fields_ = [('message', Message), ('request', SelectionRequest),
                ('notify', SelectionNotify), ('pad', C.c_long * 24)]


def drop(window, path, received):
    x = C.CDLL(ctypes.util.find_library('X11'))
    x.XOpenDisplay.argtypes = [C.c_char_p]; x.XOpenDisplay.restype = C.c_void_p
    x.XDefaultRootWindow.argtypes = [C.c_void_p]; x.XDefaultRootWindow.restype = C.c_ulong
    x.XCreateSimpleWindow.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_int,
                                    C.c_uint, C.c_uint, C.c_uint, C.c_ulong, C.c_ulong]
    x.XCreateSimpleWindow.restype = C.c_ulong
    x.XInternAtom.argtypes = [C.c_void_p, C.c_char_p, C.c_int]; x.XInternAtom.restype = C.c_ulong
    x.XSetSelectionOwner.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong, C.c_ulong]
    x.XSendEvent.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_long, C.POINTER(Event)]
    x.XChangeProperty.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong, C.c_ulong,
                                 C.c_int, C.c_int, C.c_void_p, C.c_int]
    x.XFlush.argtypes = [C.c_void_p]; x.XPending.argtypes = [C.c_void_p]
    x.XNextEvent.argtypes = [C.c_void_p, C.POINTER(Event)]
    x.XCloseDisplay.argtypes = [C.c_void_p]
    d = x.XOpenDisplay(None); assert d
    atom = lambda name: x.XInternAtom(d, name.encode(), 0)
    source = x.XCreateSimpleWindow(d, x.XDefaultRootWindow(d), 0, 0, 1, 1, 0, 0, 0)
    def send(name, values):
        e = Event(); e.message.type = 33; e.message.display = d; e.message.window = int(window)
        e.message.message_type = atom(name); e.message.format = 32
        e.message.data.longs[:] = values
        assert x.XSendEvent(d, int(window), 0, 0, C.byref(e)); x.XFlush(d)
    try:
        uri = atom('text/uri-list'); selection = atom('XdndSelection')
        x.XSetSelectionOwner(d, selection, source, 0)
        send('XdndEnter', [source, 5 << 24, uri, 0, 0])
        send('XdndPosition', [source, 0, (120 << 16) | 120, 0, atom('XdndActionCopy')])
        deadline = time.monotonic() + 6; sent = False; events = []
        payload = (path.as_uri() + '\r\n').encode()
        while time.monotonic() < deadline:
            if received():
                return
            if not x.XPending(d):
                time.sleep(.01); continue
            e = Event(); x.XNextEvent(d, C.byref(e))
            events.append((e.message.type, list(e.message.data.longs) if e.message.type == 33 else e.request.target))
            if e.message.type == 33 and e.message.message_type == atom('XdndStatus') and not sent:
                assert e.message.data.longs[1] & 1, 'Terminal did not accept file drops'
                send('XdndDrop', [source, 0, 0, 0, 0]); sent = True
            elif e.request.type == 30:
                r = e.request; prop = r.property or r.target
                data = C.create_string_buffer(payload)
                x.XChangeProperty(d, r.requestor, prop, r.target, 8, 0, data, len(payload))
                reply = Event(); reply.notify.type = 31; reply.notify.display = d
                reply.notify.requestor = r.requestor; reply.notify.selection = r.selection
                reply.notify.target = r.target; reply.notify.property = prop; reply.notify.time = r.time
                x.XSendEvent(d, r.requestor, 0, 0, C.byref(reply)); x.XFlush(d)
        raise AssertionError(f'The native Xdnd drop did not reach the child: sent={sent}, events={events}')
    finally:
        x.XCloseDisplay(d)


def main():
    assert os.environ.get('TERMINAL_PRIVATE_XVFB') == '1'
    assert os.environ.get('HARMONY_DESKTOP_RECOVERY') == '0'
    binary = str(Path(sys.argv[1]).resolve())
    Path('backup/tests').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='image-input-', dir='backup/tests') as directory:
        root = Path(directory).resolve(); incoming = root / 'input'
        shell = root / 'shell'; shell.write_text('#!/bin/sh\nexec /bin/sh -c "$2"\n'); shell.chmod(0o700)
        child = root / 'child.py'
        child.write_text('import os,tty\ntty.setraw(0)\nos.write(1,b"\\x1b[?2004hready")\n'
                         'with open(' + repr(str(incoming)) + ',"wb",buffering=0) as log:\n'
                         ' while True:\n  data=os.read(0,65536)\n  if not data: break\n  log.write(data)\n')
        def chunk(name, data):
            return struct.pack('>I', len(data)) + name + data + struct.pack('>I', zlib.crc32(name+data))
        png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB',1,1,8,6,0,0,0))
        png += chunk(b'IDAT', zlib.compress(b'\x00\x11\x99\xdd\xff')) + chunk(b'IEND', b'')
        image = root / "drag it's image.png"; image.write_bytes(png)
        env = dict(os.environ, XDG_CONFIG_HOME=str(root/'config'), XDG_STATE_HOME=str(root/'state'),
                   XDG_CACHE_HOME=str(root/'cache'), SDL_VIDEODRIVER='x11', LP_NUM_THREADS='1', OMP_NUM_THREADS='1')
        xdo = lambda *args: subprocess.run(['xdotool',*map(str,args)],env=env,check=True,
                                          capture_output=True,text=True,timeout=5).stdout.strip()
        with (root/'window.log').open('w') as log:
            app = subprocess.Popen(['stdbuf','-oL',binary,'--hide-menubar','--hide-toolbar','--shell',str(shell),
                                    '-e','python3 '+shlex.quote(str(child))],env=env,stdout=log,stderr=log)
            clips = []
            try:
                def find():
                    found = subprocess.run(['xdotool','search','--onlyvisible','--pid',str(app.pid)],env=env,
                                           capture_output=True,text=True)
                    return found.stdout.splitlines()[-1] if found.returncode==0 and incoming.exists() else None
                window = wait(find,'Owned Terminal window and raw PTY child')
                xdo('windowfocus','--sync',window)
                clip = subprocess.Popen(['xclip','-quiet','-selection','clipboard','-target','image/png','-in',str(image)],
                                        env=env,stdout=log,stderr=log); clips.append(clip)
                time.sleep(.2)
                probe = subprocess.run(['xclip','-selection','clipboard','-target','image/png','-out'],env=env,capture_output=True,timeout=3)
                assert probe.stdout==png, (probe.returncode,probe.stderr)
                image_before = incoming.stat().st_size
                xdo('keydown','ctrl','shift'); time.sleep(.1); xdo('key','v'); time.sleep(.2); xdo('keyup','shift','ctrl')
                time.sleep(.2)
                assert incoming.stat().st_size == image_before, 'Ctrl+Shift+V must never paste an image'
                xdo('keydown','ctrl'); time.sleep(.1); xdo('key','v'); time.sleep(.2); xdo('keyup','ctrl')
                data = wait(lambda: incoming.read_bytes(),'PNG paste never reached the PTY')
                assert b'\x16' not in data, data
                paths = shlex.split(data.replace(b'\x1b[200~',b'').replace(b'\x1b[201~',b'').decode())
                assert len(paths)==1 and Path(paths[0]).read_bytes()==png, data
                before = len(data)
                text = "Plain clipboard text stays text"
                clip = subprocess.Popen(['xclip','-quiet','-selection','clipboard','-target','UTF8_STRING','-in'],
                                        env=env,stdin=subprocess.PIPE,stdout=log,stderr=log)
                clips.append(clip); clip.stdin.write(text.encode()); clip.stdin.close(); time.sleep(.2)
                xdo('keydown','ctrl'); time.sleep(.1); xdo('key','v'); time.sleep(.2); xdo('keyup','ctrl')
                data = wait(lambda: incoming.read_bytes() if incoming.stat().st_size>before else None,
                            'Ctrl+V text fallback lost text')
                assert data[before:].replace(b'\x1b[200~',b'').replace(b'\x1b[201~',b'')==text.encode()
                before = len(data)
                xdo('keydown','ctrl','shift'); time.sleep(.1); xdo('key','v'); time.sleep(.2); xdo('keyup','shift','ctrl')
                data = wait(lambda: incoming.read_bytes() if incoming.stat().st_size>before else None,'Shift paste lost text')
                assert data[before:].replace(b'\x1b[200~',b'').replace(b'\x1b[201~',b'')==text.encode()
                before = len(data)
                drop(window,image,lambda: incoming.stat().st_size>before)
                dropped = incoming.read_bytes()[before:]
                assert shlex.split(dropped.replace(b'\x1b[200~',b'').replace(b'\x1b[201~',b'').decode()) == [str(image)], dropped
                assert b'\r' not in dropped and b'\n' not in dropped, 'Drop submitted a command'
                print('Local native image input: Ctrl+V pastes PNG or text fallback, Ctrl+Shift+V stays text-only, Xdnd preserves the path; no command submitted')
                close_window(window,app.pid,env); app.wait(timeout=5)
                assert app.returncode==0, (root/'window.log').read_text()
            except BaseException:
                shutil.copyfile(root/'window.log',Path('backup/image-input-window.log'))
                print('Private image input files:',[str(p.relative_to(root)) for p in root.rglob('*.png')])
                print((root/'window.log').read_text()[-4000:])
                raise
            finally:
                for clip in clips:
                    if clip.poll() is None: clip.terminate()
                    clip.wait(timeout=5)
                if app.poll() is None: app.terminate(); app.wait(timeout=5)


if __name__ == '__main__':
    main()
