#!/usr/bin/env python3
"""Control keys and shortcuts follow a software layout, directly and in tmux.

Runs only on a private Xvfb display with the layout set to Dvorak there, where
Control+C is physical I and Control+Shift+T is physical K.
"""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time


def run(arguments, env, check=True):
    return subprocess.run(arguments, env=env, capture_output=True, text=True,
                          timeout=15, check=check)


def wait_until(predicate, what, seconds=10.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for {what}")


def window_count(pid, env):
    found = run(["xdotool", "search", "--onlyvisible", "--pid", str(pid)], env, check=False)
    return found.stdout.split()


def recorder_script(root):
    """Print one line per key byte and leave the terminal raw, so ^C is data."""
    script = root / "record.py"
    script.write_text(
        "import os, sys, tty\n"
        "path = sys.argv[1]\n"
        "tty.setraw(0)\n"
        "with open(path, 'ab', buffering=0) as log:\n"
        "    log.write(b'ready\\n')\n"
        "    while True:\n"
        "        data = os.read(0, 64)\n"
        "        if not data:\n"
        "            break\n"
        "        log.write(data.hex().encode() + b'\\n')\n",
        encoding="utf-8")
    return script


def signal_script(root):
    """A cooked child: Control+C must arrive as SIGINT, the real user case."""
    script = root / "signal.py"
    script.write_text(
        "import signal, sys, time\n"
        "path = sys.argv[1]\n"
        "def stop(number, frame):\n"
        "    open(path, 'a').write('sigint\\n')\n"
        "    sys.exit(0)\n"
        "signal.signal(signal.SIGINT, stop)\n"
        "open(path, 'a').write('ready\\n')\n"
        "time.sleep(30)\n",
        encoding="utf-8")
    return script


class Terminal:
    def __init__(self, executable, root, name, command, env):
        self.env = dict(env, XDG_CONFIG_HOME=str(root / name / "config"),
                        XDG_STATE_HOME=str(root / name / "state"),
                        XDG_DATA_HOME=str(root / name / "data"),
                        HOME=str(root / name), PYTHONDONTWRITEBYTECODE="1")
        os.makedirs(root / name, exist_ok=True)
        self.process = subprocess.Popen([executable, "-e", command],
                                        env=self.env, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.PIPE, cwd=root)
        try:
            self.window = wait_until(lambda: window_count(self.process.pid, self.env),
                                     "the Terminal window")[0]
        except AssertionError:
            self.process.terminate()
            detail = self.process.communicate(timeout=5)[1]
            raise AssertionError((name, command, self.process.returncode, detail[-800:]))
        run(["xdotool", "windowfocus", "--sync", self.window], self.env)

    def key(self, name):
        """Press like a person: modifiers first, held across several frames."""
        parts = name.split("+")
        run(["xdotool"] + [word for part in parts for word in ("keydown", part)], self.env)
        time.sleep(0.15)
        run(["xdotool"] + [word for part in reversed(parts) for word in ("keyup", part)], self.env)
        time.sleep(0.05)

    def tap(self, name):
        """The fastest press and release a script can send."""
        run(["xdotool", "key", "--delay", "0", name], self.env)

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)


def bytes_seen(path):
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").split()


def expect_control(terminal, log, name, value, what):
    before = len(bytes_seen(log))
    terminal.key(name)
    wait_until(lambda: len(bytes_seen(log)) > before, what)
    seen = bytes_seen(log)[before:]
    assert seen == [value], (what, seen)


def main():
    assert os.environ.get("TERMINAL_PRIVATE_XVFB") == "1", "Run through make keyboard-layout-window-test"
    assert os.environ.get("DISPLAY"), "Private display required"
    executable = str(Path(sys.argv[1]).resolve())
    tmux = shutil.which("tmux")
    assert tmux, "tmux is required"
    env = {name: value for name, value in os.environ.items()
           if name not in {"WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS",
                           "SESSION_MANAGER", "TMUX", "TMUX_PANE"}}
    env.update(SDL_VIDEODRIVER="x11", LP_NUM_THREADS="1", OMP_NUM_THREADS="1")
    run(["setxkbmap", "-layout", "us", "-variant", "dvorak"], env)
    query = run(["setxkbmap", "-query"], env).stdout
    assert "dvorak" in query, query

    with tempfile.TemporaryDirectory(prefix="terminal-layout-") as temporary:
        root = Path(temporary)
        recorder = recorder_script(root)
        interrupted = signal_script(root)
        python = shlex.quote(sys.executable)

        # 1. Raw child directly in Terminal.
        log = root / "direct.log"
        terminal = Terminal(executable, root, "direct",
                            f"exec {python} -I {recorder} {log}", env)
        try:
            wait_until(lambda: "ready" in bytes_seen(log), "the direct recorder")
            expect_control(terminal, log, "ctrl+c", "03", "direct Control+C")
            expect_control(terminal, log, "ctrl+t", "14", "direct Control+T")
            # A script's fastest tap finishes inside one frame.
            before = len(bytes_seen(log))
            for attempt in range(10):
                terminal.tap("ctrl+c")
                time.sleep(0.2)
            seen = bytes_seen(log)[before:]
            assert seen == ["03"] * 10, ("quick Control+C taps", seen)
        finally:
            terminal.close()

        # 2. Control+Shift+T opens a tab in place of sending a key.
        log = root / "shortcut.log"
        terminal = Terminal(executable, root, "shortcut",
                            f"exec {python} -I {recorder} {log}", env)
        try:
            wait_until(lambda: "ready" in bytes_seen(log), "the shortcut recorder")
            before = len(bytes_seen(log))
            terminal.key("ctrl+shift+t")
            # The new tab runs the same command, which reports ready again.
            seen = wait_until(lambda: bytes_seen(log)[before:], "the new tab")
            assert seen == ["ready"], ("Control+Shift+T reached the child", seen)
        finally:
            terminal.close()

        # 3. Through tmux, in each key mode the outer terminal can be asked for.
        for mode in ("off", "on", "always"):
            socket = f"terminal-layout-{os.getpid()}-{mode}"
            log = root / f"tmux-{mode}.log"
            config = root / f"tmux-{mode}.conf"
            config.write_text(f"set -s extended-keys {mode}\nset -s escape-time 0\n"
                              "set -g status off\n", encoding="utf-8")
            command = (f"exec {shlex.quote(tmux)} -L {socket} -f {config} new-session "
                       f"{shlex.quote(f'{sys.executable} -I {recorder} {log}')}")
            terminal = Terminal(executable, root, f"tmux-{mode}", command, env)
            try:
                wait_until(lambda: "ready" in bytes_seen(log), f"the tmux {mode} recorder")
                time.sleep(0.3)
                expect_control(terminal, log, "ctrl+c", "03", f"tmux {mode} Control+C")
                expect_control(terminal, log, "ctrl+t", "14", f"tmux {mode} Control+T")
            finally:
                terminal.close()
                run([tmux, "-L", socket, "kill-server"], env, check=False)

            log = root / f"signal-{mode}.log"
            command = (f"exec {shlex.quote(tmux)} -L {socket} -f {config} new-session "
                       f"{shlex.quote(f'{sys.executable} -I {interrupted} {log}')}")
            terminal = Terminal(executable, root, f"signal-{mode}", command, env)
            try:
                wait_until(lambda: "ready" in bytes_seen(log), f"the tmux {mode} cooked child")
                time.sleep(0.3)
                terminal.key("ctrl+c")
                wait_until(lambda: "sigint" in bytes_seen(log), f"tmux {mode} SIGINT")
            finally:
                terminal.close()
                run([tmux, "-L", socket, "kill-server"], env, check=False)

    print("Terminal keyboard layout: Dvorak Control keys, shortcuts and tmux Control+C passed")


if __name__ == "__main__":
    main()
