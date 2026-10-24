#!/bin/sh
# Profile detached capture parsing, allocation and reflow separately.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
unset DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS ENV BASH_ENV
target=${1:-c}
form=${2:-source}
case "$target" in c) ;; *) echo 'Expected c' >&2; exit 2 ;; esac
case "$form" in source|saved) ;; *) echo 'Expected source or saved' >&2; exit 2 ;; esac
ziran=${ZIRAN:-"$root/scripts/ziran.sh"}
lock_flags=
if test ! -f ziran.local.toml; then lock_flags=--locked; fi
mkdir -p build/ziran
work=$(mktemp -d "$root/build/ziran/capture-replay.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM
input=benchmarks/capture_replay.zi
if test "$form" = saved; then
    "$ziran" ir --project $lock_flags --define CAPTURE_REPLAY --entry capture_replay:main -o "$work/ir" "$input"
    input=$work/ir/capture_replay.zir
fi
"$ziran" build --project $lock_flags --define CAPTURE_REPLAY --target="$target" \
    --entry capture_replay:main -o "$work/generated" "$input"
compiler=${CC:-cc}; standard=c11
"$compiler" -std="$standard" -O2 -I"$work/generated" "$work/generated"/*."$target" -o "$work/run"
timeout --kill-after=2s 30s "$work/run"
