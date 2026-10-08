#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
unset DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS ENV BASH_ENV
export YUE_DESKTOP_RECOVERY=0
work="$root/build/ziran/viewport"
mkdir -p "$work"
exec 9>"$work/check.lock"
flock -n 9 || { echo 'Viewport checks are already running' >&2; exit 1; }
ziran=${ZIRAN:-"$root/scripts/ziran.sh"}
locked=
if test ! -f ziran.local.toml; then locked=--locked; fi
entry=terminal_viewport_test:main
source=tests/terminal_viewport_test.zi
"$ziran" ir --project $locked --entry "$entry" -o "$work/ir" "$source"
"${CC:-cc}" -std=c11 -O2 -c tests/terminal_capture_storage_allocator.c -o "$work/allocator.o"
for form in source saved; do
    input=$source
    if test "$form" = saved; then input=$work/ir/terminal_viewport_test.zir; fi
    for target in c cpp; do
        out="$work/$form-$target"
        "$ziran" build --project $locked --target="$target" --entry "$entry" -o "$out" "$input"
        if test "$target" = c; then compiler=${CC:-cc}; standard=c11
        else compiler=${CXX:-c++}; standard=c++17; fi
        "$compiler" -std="$standard" -O2 -I"$out" "$out"/*."$target" "$work/allocator.o" \
            -Wl,--wrap=malloc,--wrap=calloc,--wrap=realloc -o "$out/run"
        timeout --kill-after=2s 90s "$out/run"
    done
done
echo 'Read-only viewport source/saved-IR C/C++ checks passed'
