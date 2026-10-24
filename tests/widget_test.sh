#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
unset DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS ENV BASH_ENV
export YUE_DESKTOP_RECOVERY=0
ziran=${ZIRAN:-"$root/scripts/ziran.sh"}
lock_flags=
if test ! -f ziran.local.toml; then lock_flags=--locked; fi
mkdir -p build/ziran
work=$(mktemp -d "$root/build/ziran/widget-test.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM
cat > "$work/shell" <<'SHELL'
#!/bin/sh
exec /bin/sh -c "$2"
SHELL
chmod 700 "$work/shell"
entry=terminal_pane_widget_test:main
source=tests/terminal_pane_widget_test.zi
"$ziran" ir --project $lock_flags --entry "$entry" -o "$work/ir" "$source"
for form in source saved; do
    input=$source
    if test "$form" = saved; then input=$work/ir/terminal_pane_widget_test.zir; fi
    "$ziran" build --project $lock_flags --target=c --entry "$entry" \
        --exe -o "$work/$form-c" "$input"
    TERMINAL_TEST_SHELL="$work/shell" timeout --kill-after=2s 15s "$work/$form-c/terminal_pane_widget_test"
done
echo 'Terminal pane source and saved IR passed C rendering and real process input'
