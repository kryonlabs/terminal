#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
unset DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS SESSION_MANAGER ENV BASH_ENV
export HARMONY_DESKTOP_RECOVERY=0
ziran=${ZIRAN:-"$root/scripts/ziran.sh"}
lock_flags=
if test ! -f ziran.local.toml; then lock_flags=--locked; fi
mkdir -p build/ziran
work=$(mktemp -d "$root/build/ziran/context-menu.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM
"$ziran" build --project $lock_flags --target=c --entry context_menu_test:main \
    --exe -o "$work/c" tests/context_menu_test.zi
"$work/c/context_menu_test"
echo 'Terminal context menu matches the xfce4-terminal 1.1.4 structure and state fields'
