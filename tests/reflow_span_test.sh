#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
unset DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS ENV BASH_ENV
ziran=${ZIRAN:-"$root/scripts/ziran.sh"}
lock_flags=
if test ! -f ziran.local.toml; then lock_flags=--locked; fi
mkdir -p build/ziran
work=$(mktemp -d "$root/build/ziran/reflow-span.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM
entry=reflow_span_test:main
source=tests/reflow_span_test.zi
"$ziran" ir --project $lock_flags --entry "$entry" -o "$work/ir" "$source"
for form in source saved; do
    input=$source
    if test "$form" = saved; then input=$work/ir/reflow_span_test.zir; fi
    for target in c cpp; do
        "$ziran" build --project $lock_flags --target="$target" --entry "$entry" -o "$work/$form-$target" "$input"
        if test "$target" = c; then compiler=${CC:-cc}; standard=c11
        else compiler=${CXX:-c++}; standard=c++17; fi
        "$compiler" -std="$standard" -O2 -I"$work/$form-$target" "$work/$form-$target"/*."$target" -o "$work/run"
        timeout --kill-after=2s 30s "$work/run"
    done
done
echo 'Reflow cell spans match scalar replay in source/saved-IR C/C++ execution'
