#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
unset DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS ENV BASH_ENV
export YUE_DESKTOP_RECOVERY=0
work="$root/build/ziran/capture-storage"
mkdir -p "$work"
exec 9>"$work/check.lock"
flock -n 9 || { echo 'Capture storage checks are already running' >&2; exit 1; }
ziran=${ZIRAN:-"$root/scripts/ziran.sh"}
locked=
if test ! -f ziran.local.toml; then locked=--locked; fi
entry=terminal_capture_storage_test:main
source=tests/terminal_capture_storage_test.zi
"$ziran" ir --project $locked --entry "$entry" -o "$work/ir" "$source"
"${CC:-cc}" -std=c11 -O2 -c tests/terminal_capture_storage_allocator.c -o "$work/allocator.o"
for form in source saved; do
    input=$source
    if test "$form" = saved; then input=$work/ir/terminal_capture_storage_test.zir; fi
    out="$work/$form-c"
    "$ziran" build --project $locked --target=c --entry "$entry" -o "$out" "$input"
    compiler=${CC:-cc}; standard=c11
    "$compiler" -std="$standard" -O2 -I"$out" "$out"/*.c "$work/allocator.o" \
        -Wl,--wrap=malloc,--wrap=calloc,--wrap=realloc -o "$out/run"
    timeout --kill-after=2s 60s "$out/run"
done
echo 'Capture storage source/saved-IR C checks passed'
