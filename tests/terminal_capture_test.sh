#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
unset DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS ENV BASH_ENV
ziran=${ZIRAN:-"$root/scripts/ziran.sh"}
lock_flags=
if test ! -f ziran.local.toml; then lock_flags=--locked; fi
mkdir -p build/ziran
work=$(mktemp -d "$root/build/ziran/terminal-capture.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM
entry=terminal_capture_test:main
source=tests/terminal_capture_test.zi
"$ziran" ir --project $lock_flags --entry "$entry" -o "$work/ir" "$source"
for form in source saved; do
    input=$source
    if test "$form" = saved; then input=$work/ir/terminal_capture_test.zir; fi
    "$ziran" build --project $lock_flags --target=c --entry "$entry" -o "$work/$form-c" "$input"
    compiler=${CC:-cc}; standard=c11
    "$compiler" -std="$standard" -O2 -I"$work/$form-c" "$work/$form-c"/*.c -o "$work/run"
    timeout --kill-after=2s 30s "$work/run"
done
echo 'Terminal captures match original replay in source/saved-IR C execution'
