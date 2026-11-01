#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
suite=${1:-application}
case "$suite" in
    application) module=terminal_application_test ;;
    input) module=terminal_input_test ;;
    view) module=terminal_view_test ;;
    host) module=terminal_host_test ;;
    *) echo "Unknown Terminal application suite: $suite" >&2; exit 2 ;;
esac
unset DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS SESSION_MANAGER ENV BASH_ENV
export YUE_DESKTOP_RECOVERY=0
ziran=${ZIRAN:-"$root/scripts/ziran.sh"}
lock_flags=
if test ! -f ziran.local.toml; then lock_flags=--locked; fi
mkdir -p build/ziran
work=$(mktemp -d "$root/build/ziran/$suite-test.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM
# Persistence fixtures must never read or replace the owner's saved tabs.
export XDG_CONFIG_HOME="$work/config" XDG_STATE_HOME="$work/state"
mkdir -p "$XDG_CONFIG_HOME" "$XDG_STATE_HOME/terminal"
printf 'active=0\n' > "$work/session.before"
cp "$work/session.before" "$XDG_STATE_HOME/terminal/session"
cat > "$work/shell" <<'SHELL'
#!/bin/sh
exec /bin/sh -c "$2"
SHELL
chmod 700 "$work/shell"
mkdir "$work/completion-folder"
export TERMINAL_COMPLETION_DIRECTORY="$work"
entry=$module:main
source=tests/$module.zi
"$ziran" ir --project $lock_flags --entry "$entry" -o "$work/ir" "$source"
for form in source saved; do
    input=$source
    if test "$form" = saved; then input=$work/ir/$module.zir; fi
    "$ziran" build --project $lock_flags --target=c --entry "$entry" \
        --exe -o "$work/$form-c" "$input"
    (cd "$work/$form-c" && TERMINAL_TEST_SHELL="$work/shell" timeout --kill-after=2s 15s "./$module")
    cmp "$work/session.before" "$XDG_STATE_HOME/terminal/session"
done
echo "Terminal $suite source and saved IR passed C behavior checks"
