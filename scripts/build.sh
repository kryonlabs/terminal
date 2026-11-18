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

mkdir -p "$output/bin"
temporary=$(mktemp "$output/bin/terminal.XXXXXX")
trap 'rm -f "$temporary"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -O1 -ffunction-sections -fdata-sections \
    -I"$generated" "$generated"/*.c -Wl,--gc-sections \
    $(pkg-config --libs sdl2 cairo pangocairo fontconfig freetype2 glib-2.0 libwebpdemux libwebp gtk+-3.0 x11 xcb) \
    -ldl -lpthread -lm -o "$temporary"
chmod 755 "$temporary"
mv "$temporary" "$output/bin/terminal"
trap - EXIT HUP INT TERM
echo "Terminal executable: $output/bin/terminal"
