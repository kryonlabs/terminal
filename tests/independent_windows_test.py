"""Repeated agent-terminal launches preserve each owned window and tmux session."""
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
from standalone_window_test import close_window, run


def wait_for(check, message, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError(message)


def owned_windows(app, env):
    found = subprocess.run(["xdotool", "search", "--onlyvisible", "--pid", str(app.pid)],
                           env=env, capture_output=True, text=True, timeout=3)
    return found.stdout.split() if found.returncode == 0 else []


def main():
    assert os.environ.get("T9_PRIVATE_XVFB") == "1", "Run through the private Xvfb test target"
    binary = str(Path(sys.argv[1]).resolve())
    Path("build/ziran").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="t9-independent-", dir="build/ziran") as directory:
        work = Path(directory).resolve()
        runtime = work / "runtime"
        runtime.mkdir(mode=0o700)
        env = os.environ.copy()
        for key in ("WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "SESSION_MANAGER",
                    "KRYON_CAPTURE_PATH", "ENV", "BASH_ENV", "TMUX"):
            env.pop(key, None)
        env.update(XDG_CONFIG_HOME=str(work / "config"), XDG_STATE_HOME=str(work / "state"),
                   XDG_RUNTIME_DIR=str(runtime), SDL_VIDEODRIVER="x11", YUE_DESKTOP_RECOVERY="0",
                   KTREM_TARGET_FPS="15", KTREM_ACTIVE_FPS="30", KTREM_PTY_BURST_MS="0",
                   LP_NUM_THREADS="1", OMP_NUM_THREADS="1")
        # Isolate the legacy runtime's singleton lock as well as the display.
        # A failing old executable can only replace a window from this fixture.
        socket = str(work / "tmux.sock")
        sessions = ("t9-test-window-first", "t9-test-window-second")
        outputs = [work / (name + ".bytes") for name in sessions]
        apps = []
        logs = []
        server_started = False

        def tmux(*arguments):
            return run(["tmux", "-S", socket, "-f", "/dev/null", *arguments], env).stdout.strip()

        def attached(name):
            return tmux("display-message", "-p", "-t", "=" + name + ":", "#{session_attached}")

        def launch(name):
            log = (work / (name + "-" + str(len(apps)) + ".log")).open("w")
            logs.append(log)
            app = subprocess.Popen([binary, "--disable-server", "--dynamic-title-mode=ignore",
                                    "--title", name, "--shell", "/bin/sh", "--execute",
                                    "/usr/bin/tmux", "-S", socket, "attach-session", "-t", "=" + name],
                                   env=env, stdout=log, stderr=subprocess.STDOUT)
            apps.append(app)

            def ready():
                assert app.poll() is None, "Terminal exited before its view attached"
                windows = owned_windows(app, env)
                if windows and attached(name) == "1":
                    assert len(windows) == 1, windows
                    return windows[0]
                return None

            window = wait_for(ready, "The owned Terminal window did not attach")
            assert int(run(["xdotool", "getwindowpid", window], env).stdout) == app.pid
            return app, window

        def assert_first(app, window):
            assert app.poll() is None, "Opening another Terminal replaced the first window"
            assert owned_windows(app, env) == [window], "The first owned window changed"
            assert attached(sessions[0]) == "1", "The first tmux view was detached"

        try:
            for name, output in zip(sessions, outputs):
                command = "stty raw -echo; exec cat > " + shlex.quote(str(output))
                tmux("new-session", "-d", "-s", name, shlex.join(["/bin/sh", "-c", command]))
                server_started = True
            wait_for(lambda: all(path.exists() for path in outputs), "Fixture children did not start")
            first, first_window = launch(sessions[0])
            second, second_window = launch(sessions[1])
            assert_first(first, first_window)
            assert first_window != second_window, "Two Terminal processes shared one window"
            run(["xdotool", "windowfocus", "--sync", first_window], env)
            run(["xdotool", "type", "--clearmodifiers", "--delay", "40", "FirstAgentInput"], env)
            wait_for(lambda: outputs[0].read_bytes() == b"FirstAgentInput",
                     "The first terminal stopped accepting input after the second launch")
            assert outputs[1].read_bytes() == b"", "First-window input reached the other session"
            close_window(second_window, second.pid, env)
            assert second.wait(timeout=5) == 0
            wait_for(lambda: attached(sessions[1]) == "0", "The closed view remained attached")
            assert_first(first, first_window)
            # Reopen the closed view: the original process, window and child stay alive.
            third, third_window = launch(sessions[1])
            assert_first(first, first_window)
            close_window(third_window, third.pid, env)
            assert third.wait(timeout=5) == 0
            assert_first(first, first_window)
            close_window(first_window, first.pid, env)
            assert first.wait(timeout=5) == 0
            assert tmux("has-session", "-t", "=" + sessions[0]) == ""
            assert tmux("has-session", "-t", "=" + sessions[1]) == ""
        finally:
            for app in apps:
                if app.poll() is None:
                    app.terminate()
                    try:
                        app.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        app.kill()
                        app.wait(timeout=3)
            if server_started:
                tmux("kill-server")
            for log in logs:
                log.close()
    print("Terminal independent windows: repeated tmux launches, input isolation, owned close and session preservation passed")


if __name__ == "__main__":
    main()
