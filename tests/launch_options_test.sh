#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
unset DISPLAY WAYLAND_DISPLAY XAUTHORITY ENV BASH_ENV
ziran=${ZIRAN:-"$root/scripts/ziran.sh"}
lock_flags=
if test ! -f ziran.local.toml; then lock_flags=--locked; fi
mkdir -p build/ziran
work=$(mktemp -d "$root/build/ziran/launch-test.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM
entry=terminal_launch_options_test:main
source=tests/terminal_launch_options_test.zi
"$ziran" ir --project $lock_flags --entry "$entry" -o "$work/ir" "$source"
for form in source saved; do
    input=$source
    if test "$form" = saved; then input=$work/ir/terminal_launch_options_test.zir; fi
    "$ziran" build --project $lock_flags --target=c --entry "$entry" \
        --exe -o "$work/$form-c" "$input"
    timeout --kill-after=2s 10s "$work/$form-c/terminal_launch_options_test" > "$work/$form-c/output"
done
cmp "$work/source-c/output" "$work/saved-c/output"
echo 'Terminal launch options passed source and saved-IR C parsing and output'
