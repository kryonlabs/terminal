#!/bin/sh
# Build the maintained Ziran application; dependency source stays in its package.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
unset DISPLAY WAYLAND_DISPLAY XAUTHORITY

target=${1:-c}
output=${2:-build/linux-$(uname -m)}
input=${3:-src/app/app_main.zi}
case "$target" in c) ;; *) echo "Unknown Terminal target: $target" >&2; exit 2 ;; esac
mkdir -p "$output"
output=$(CDPATH= cd -- "$output" && pwd)
case "$output" in "$root"/build/*) ;; *) echo 'Terminal build output must be under build/' >&2; exit 2 ;; esac
ziran=${ZIRAN:-"$root/scripts/ziran.sh"}
lock_flags=
if test ! -f ziran.local.toml; then lock_flags=--locked; fi
generated=$output/generated
"$ziran" build --project $lock_flags --target="$target" --no-main --prune-stale \
    --root src -o "$generated" "$input"

jobs=${TERMINAL_BUILD_JOBS:-1}
case "$jobs" in 1|2|3|4) ;; *) echo 'TERMINAL_BUILD_JOBS must be between 1 and 4' >&2; exit 2 ;; esac
if test -n "${RAYLIB_A:-}"; then
    raylib_archive=$RAYLIB_A
else
    raylib=$("$ziran" pkg path raylib $lock_flags)
    cmake -S "$raylib" -B "$output/raylib" -DPLATFORM=SDL \
        -DCMAKE_DISABLE_FIND_PACKAGE_SDL3=ON -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_EXAMPLES=OFF -DBUILD_SHARED_LIBS=OFF -DCMAKE_POSITION_INDEPENDENT_CODE=ON
    cmake --build "$output/raylib" --parallel "$jobs"
    raylib_archive=$output/raylib/raylib/libraylib.a
fi
test -f "$raylib_archive"
mkdir -p "$output/bin"
temporary=$(mktemp "$output/bin/terminal.XXXXXX")
trap 'rm -f "$temporary"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -O1 -ffunction-sections -fdata-sections \
    -I"$generated" "$generated"/*.c -Wl,--gc-sections "$raylib_archive" \
    $(pkg-config --libs sdl2) -lGL -ldl -lpthread -lm -o "$temporary"
chmod 755 "$temporary"
mv "$temporary" "$output/bin/terminal"
trap - EXIT HUP INT TERM
echo "Terminal executable: $output/bin/terminal"
