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
trap 'close_private_display; rm -rf "$work"' EXIT HUP INT TERM
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
echo 'Thunar Exo working-directory, real Terminal through Exo and canonical Terminal working-directory passed'
