set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
app=$(CDPATH= cd -- "$(dirname -- "$1")" && pwd)/$(basename -- "$1")
test -x "$app"
unset DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS SESSION_MANAGER
mkdir -p "$root/build/ziran"
work=$(mktemp -d "$root/build/ziran/thunar-terminal-test.XXXXXX")
xvfb_pid=
private_display=
start_private_display() {
    display_number=$(( $$ % 5000 + 100 ))
    while test -e "/tmp/.X$display_number-lock"; do display_number=$((display_number + 1)); done
    Xvfb ":$display_number" -screen 0 640x480x24 -nolisten tcp -ac &
    xvfb_pid=$!
    deadline=$(( $(date +%s) + 5 ))
    while test "$(date +%s)" -lt "$deadline"; do
        test -S "/tmp/.X11-unix/X$display_number" && break
        sleep 0.1
    done
    test -S "/tmp/.X11-unix/X$display_number"
    private_display=":$display_number"
    export PRIVATE_DISPLAY="$private_display"
}
close_private_display() {
    test -n "$xvfb_pid" || return 0
    kill "$xvfb_pid" 2>/dev/null || true
    wait "$xvfb_pid" 2>/dev/null || true
    xvfb_pid=
}
launch_pids=
outside=
stop_launches() {
    for pid in $launch_pids; do kill "$pid" 2>/dev/null || :; done
    launch_pids=
}
trap 'stop_launches; close_private_display; rm -rf "$work" ${outside:+"$outside"}' EXIT HUP INT TERM
prefix=$work/prefix
install -d "$prefix/bin" "$prefix/share/applications" "$prefix/share/xfce4/helpers" "$work/config/xfce4" "$work/data" "$work/runtime"
install -m 644 data/terminal-helper.desktop "$prefix/share/xfce4/helpers/terminal.desktop"
{
    printf '%s\n' '[Desktop Entry]' 'Type=Application' 'Name=Terminal'
    printf '%s\n' 'Comment=Kryon terminal emulator' "Exec=$prefix/bin/terminal"
    printf '%s\n' 'Icon=utilities-terminal' 'Terminal=false' 'Categories=System;TerminalEmulator;'
    printf '%s\n' 'Keywords=terminal;shell;' 'StartupNotify=true'
} > "$prefix/share/applications/terminal.desktop"
if command -v desktop-file-validate >/dev/null 2>&1; then desktop-file-validate "$prefix/share/applications/terminal.desktop"; fi
rg -q '^Type=X-XFCE-Helper$' "$prefix/share/xfce4/helpers/terminal.desktop"
rg -q '^X-XFCE-Category=TerminalEmulator$' "$prefix/share/xfce4/helpers/terminal.desktop"
rg -q '^X-XFCE-Binaries=terminal;$' "$prefix/share/xfce4/helpers/terminal.desktop"
# Terminal starts in HOME unless told otherwise, so the helper names the folder
# Exo starts it in.
rg -q '^X-XFCE-Commands=%B --working-directory=\.;$' "$prefix/share/xfce4/helpers/terminal.desktop"
# Exo splits a launch parameter into words, so it follows -x as in xfce4-terminal.
rg -q '^X-XFCE-CommandsWithParameter=%B --working-directory=\. -x %s;$' "$prefix/share/xfce4/helpers/terminal.desktop"
record_script=$work/record-launch
cat > "$record_script" <<'RECORD'
#!/bin/sh
printf '%s\0' "$@" > "$TERMINAL_RECORD_ARGV"
pwd > "$TERMINAL_RECORD_CWD"
RECORD
chmod 755 "$record_script"
install -m 755 "$record_script" "$prefix/bin/terminal"
printf '%s\n' 'TerminalEmulator=terminal' > "$work/config/xfce4/helpers.rc"
export XDG_CONFIG_HOME="$work/config"
export XDG_DATA_HOME="$work/data"
export XDG_DATA_DIRS="$prefix/share${XDG_DATA_DIRS:+:$XDG_DATA_DIRS}"
export XDG_RUNTIME_DIR="$work/runtime"
export PATH="$prefix/bin:$PATH"
export HOME="$work"
export HARMONY_DESKTOP_RECOVERY=0
export LP_NUM_THREADS=1 OMP_NUM_THREADS=1
launch_count=0
check_exo_directory() {
    directory=$1
    launch_count=$((launch_count + 1))
    argv_record=$work/argv.$launch_count
    cwd_record=$work/cwd.$launch_count
    export TERMINAL_RECORD_ARGV="$argv_record"
    export TERMINAL_RECORD_CWD="$cwd_record"
    status=0
    start_private_display
    # A desktop session's PATH: the installed prefix first, then the system.
    # Exo 4.20 hands the launch to xfce4-mime-helper and returns before the
    # helper starts Terminal; with only the prefix on PATH it cannot find that
    # helper and starts the binary without the helper's arguments.
    full_path=$PATH
    PATH="$prefix/bin:$full_path"
    export PATH
    DISPLAY="$private_display" /usr/bin/timeout --kill-after=2s 10s /usr/bin/exo-open --working-directory "$directory" --launch TerminalEmulator || status=$?
    PATH="$full_path"
    export PATH
    deadline=$(( $(date +%s) + 8 ))
    while test "$(date +%s)" -lt "$deadline" && ! test -s "$cwd_record"; do sleep 0.1; done
    close_private_display
    test "$status" -eq 0
    test -f "$argv_record"
    test -f "$cwd_record"
    test "$(cat "$cwd_record")" = "$(cd "$directory" && pwd)"
    tr '\0' '\n' < "$argv_record" | rg -qx -- '--working-directory=\.'
}
install -d "$work/ordinary-directory" "$work/Thunar Selected Dir"
check_exo_directory "$work/ordinary-directory"
check_exo_directory "$work/Thunar Selected Dir"
actual_directory="$work/Canonical Terminal Selected Dir"
actual_record=$work/canonical-cwd
install -d "$actual_directory"
actual_script=$work/check-canonical-cwd
cat > "$actual_script" <<CHECK
#!/bin/sh
set -eu
terminal="$app"
directory="$actual_directory"
record="$actual_record"
"\$terminal" --working-directory "\$directory" --disable-server --hold --command "pwd > '\$record'; sleep 0.2" &
pid=\$!
deadline=\$(( \$(date +%s) + 8 ))
while test \$(date +%s) -lt \$deadline; do
    test -f "\$record" && break
    sleep 0.2
done
test -f "\$record"
test "\$(cat "\$record")" = "\$directory"
kill "\$pid" 2>/dev/null || :
wait "\$pid" 2>/dev/null || :
CHECK
chmod 755 "$actual_script"
status=0
start_private_display
DISPLAY="$private_display" timeout --kill-after=2s 12s "$actual_script" || status=$?
close_private_display
test "$status" -eq 0
# The real Terminal through Exo, as Thunar's default Open Terminal Here action
# launches it: the shell must start in the selected folder, not in HOME.
install -m 755 "$app" "$prefix/bin/terminal"
exo_directory="$work/Exo Real Selected Dir"
exo_record=$work/exo-real-cwd
install -d "$exo_directory"
status=0
start_private_display
DISPLAY="$private_display" /usr/bin/timeout --kill-after=2s 10s /usr/bin/exo-open \
    --working-directory "$exo_directory" --launch TerminalEmulator "sh -c 'pwd > $exo_record'" || status=$?
deadline=$(( $(date +%s) + 8 ))
while test "$(date +%s)" -lt "$deadline" && ! test -s "$exo_record"; do sleep 0.2; done
close_private_display
test "$status" -eq 0
test -s "$exo_record"
test "$(cat "$exo_record")" = "$exo_directory"

# Thunar's right-click Open Terminal Here is a custom action, and Thunar puts
# %f in already shell-quoted. Real Thunar runs on the private display with a
# private bus that activates no services; accelerators trigger its actions.
# The Terminal wrapper records Thunar's argv, and the shell records where it
# started and which Terminal started it, then stays running like a shell.
real_app=$(readlink -f "$app")
record_dir=$work/launch-record
install -d "$record_dir" "$work/config/Thunar"
cat > "$prefix/bin/terminal" <<WRAP
#!/bin/sh
printf '%s\0' "\$@" > "$record_dir/argv"
exec "$real_app" "\$@"
WRAP
chmod 755 "$prefix/bin/terminal"
record_shell=$work/record-shell
cat > "$record_shell" <<SHELL
#!/bin/sh
{ pwd -P; echo "\$PPID"; echo "\$\$"; } > "$record_dir/shell.tmp"
mv "$record_dir/shell.tmp" "$record_dir/shell"
exec sleep 60
SHELL
chmod 755 "$record_shell"
# The reported failure: the window opened, its shell never started, and the
# window closed within a second. The shell must start in the expected folder
# and its Terminal must still be open afterwards.
expect_open_terminal() {
    running_before=$launch_pids
    expected=$(cd "$1" && pwd -P)
    deadline=$(( $(date +%s) + 10 ))
    while test "$(date +%s)" -lt "$deadline" && ! test -s "$record_dir/shell"; do sleep 0.1; done
    if ! test -s "$record_dir/shell"; then
        echo "Terminal closed before its shell started; expected $expected" >&2
        return 1
    fi
    shell_cwd=$(sed -n 1p "$record_dir/shell")
    terminal_pid=$(sed -n 2p "$record_dir/shell")
    shell_pid=$(sed -n 3p "$record_dir/shell")
    launch_pids="$launch_pids $shell_pid $terminal_pid"
    test "$shell_cwd" = "$expected" || { echo "shell started in $shell_cwd, expected $expected" >&2; return 1; }
    test "$(readlink -f "/proc/$terminal_pid/exe")" = "$real_app"
    sleep 1.5
    kill -0 "$terminal_pid" 2>/dev/null || { echo "Terminal closed after starting in $expected" >&2; return 1; }
    # Ending its shell ends the Terminal.
    kill "$shell_pid" 2>/dev/null || :
    deadline=$(( $(date +%s) + 5 ))
    while test "$(date +%s)" -lt "$deadline" && kill -0 "$terminal_pid" 2>/dev/null; do sleep 0.1; done
    kill "$terminal_pid" 2>/dev/null || :
    launch_pids=$running_before
    rm -f "$record_dir/shell"
}
recorded_argv() { tr '\0' '\n' < "$record_dir/argv"; }
# The selected folder is outside HOME and its name has spaces.
outside=$(mktemp -d "$root/build/ziran/Thunar Outside Home.XXXXXX")
thunar_directory="$outside/Selected Project Dir"
install -d "$thunar_directory"
cat > "$work/config/Thunar/uca.xml" <<UCA
<?xml version="1.0" encoding="UTF-8"?>
<actions>
<action><icon>utilities-terminal</icon><name>Open Terminal Here</name><unique-id>terminal-direct</unique-id>
<command>$prefix/bin/terminal --working-directory=%f</command><description>Terminal</description>
<range></range><patterns>*</patterns><startup-notify/><directories/></action>
<action><icon>utilities-terminal</icon><name>Open Terminal Here (Exo)</name><unique-id>terminal-exo</unique-id>
<command>exo-open --working-directory %f --launch TerminalEmulator</command><description>Terminal</description>
<range></range><patterns>*</patterns><startup-notify/><directories/></action>
<action><icon>utilities-terminal</icon><name>Open Terminal Here (quoted)</name><unique-id>terminal-quoted</unique-id>
<command>$prefix/bin/terminal --working-directory=&quot;%f&quot;</command><description>Terminal</description>
<range></range><patterns>*</patterns><startup-notify/><directories/></action>
</actions>
UCA
cat > "$work/config/Thunar/accels.scm" <<'ACCELS'
(gtk_accel_path "<Actions>/ThunarActions/uca-action-terminal-direct" "<Primary><Alt>t")
(gtk_accel_path "<Actions>/ThunarActions/uca-action-terminal-exo" "<Primary><Alt>e")
(gtk_accel_path "<Actions>/ThunarActions/uca-action-terminal-quoted" "<Primary><Alt>q")
ACCELS
cat > "$work/bus.conf" <<'BUS'
<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <type>session</type>
  <listen>unix:tmpdir=/tmp</listen>
  <auth>EXTERNAL</auth>
  <policy context="default">
    <allow send_destination="*" eavesdrop="true"/>
    <allow eavesdrop="true"/>
    <allow own="*"/>
  </policy>
</busconfig>
BUS
start_private_display
DISPLAY="$private_display" SHELL="$record_shell" NO_AT_BRIDGE=1 GIO_USE_VFS=local GIO_USE_VOLUME_MONITOR=unix \
    dbus-run-session --config-file="$work/bus.conf" -- thunar "$thunar_directory" > "$work/thunar.log" 2>&1 &
thunar_session=$!
launch_pids="$thunar_session"
thunar_window=$(DISPLAY="$private_display" timeout 15s xdotool search --sync --onlyvisible --class Thunar | head -n 1)
test -n "$thunar_window"
thunar_pid=$(DISPLAY="$private_display" xdotool getwindowpid "$thunar_window")
launch_pids="$thunar_pid $thunar_session"
thunar_action() {
    DISPLAY="$private_display" xdotool windowfocus --sync "$thunar_window"
    sleep 0.5
    DISPLAY="$private_display" xdotool key "$1"
}
# Open Terminal Here as installed on the desktop: Thunar quotes %f itself.
thunar_action ctrl+alt+t
expect_open_terminal "$thunar_directory"
test "$(recorded_argv)" = "--working-directory=$thunar_directory"
# Thunar's default action goes through Exo and the TerminalEmulator helper.
thunar_action ctrl+alt+e
expect_open_terminal "$thunar_directory"
test "$(recorded_argv)" = "--working-directory=."
# Quoting %f again hands Terminal the quotes as part of the path. Terminal
# says so and starts in HOME instead of closing.
thunar_action ctrl+alt+q
expect_open_terminal "$HOME"
test "$(recorded_argv)" = "--working-directory='$thunar_directory'"
rg -qF "Terminal: working directory \"'$thunar_directory'\" does not exist; starting in $HOME" "$work/thunar.log"
stop_launches
wait "$thunar_session" 2>/dev/null || :
close_private_display

# An existing folder outside HOME, with spaces, opens as it is, without notice.
start_private_display
DISPLAY="$private_display" SHELL="$record_shell" "$app" "--working-directory=$thunar_directory" 2> "$work/direct.err" &
direct_pid=$!
launch_pids=$direct_pid
expect_open_terminal "$thunar_directory"
wait "$direct_pid" 2>/dev/null || :
launch_pids=
close_private_display
if rg -q 'Terminal: working directory' "$work/direct.err"; then
    echo "An existing folder fell back: $(cat "$work/direct.err")" >&2
    exit 1
fi

# A folder that is missing, a file, or a folder Terminal may not enter starts
# the shell in HOME and leaves the window open.
missing_directory="$work/Missing Selected Dir"
selected_file="$work/Selected File.txt"
: > "$selected_file"
check_fallback() {
    start_private_display
    DISPLAY="$private_display" SHELL="$record_shell" "$app" "--working-directory=$1" 2> "$work/fallback.err" &
    direct_pid=$!
    launch_pids=$direct_pid
    expect_open_terminal "$HOME"
    wait "$direct_pid" 2>/dev/null || :
    launch_pids=
    close_private_display
}
check_fallback "$missing_directory"
rg -qF "Terminal: working directory \"$missing_directory\" does not exist; starting in $HOME" "$work/fallback.err"
check_fallback "$selected_file"
rg -qF "Terminal: working directory \"$selected_file\" is not a folder; starting in $HOME" "$work/fallback.err"
if test "$(id -u)" -ne 0; then
    locked_directory="$work/Locked Selected Dir"
    install -d -m 000 "$locked_directory"
    check_fallback "$locked_directory"
fi
echo 'Thunar Exo working-directory, real Terminal through Exo and canonical Terminal working-directory passed'
echo 'Thunar Open Terminal Here (custom action, Exo helper, quoted path) and working-directory fallback passed'
