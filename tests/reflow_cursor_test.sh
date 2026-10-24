#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo"
unset DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS
ziran=${ZIRAN:-"$repo/scripts/ziran.sh"}
work="$repo/build/ziran/reflow-cursor"
mkdir -p "$work"
source=tests/terminal_pane_reflow_test.zi
"$ziran" ir --project --root tests -o "$work/ir" "$source"
"$ziran" build --project --root tests --target=c --entry terminal_pane_reflow_test:main \
    --exe -o "$work/c" "$source"
"$work/c/terminal_pane_reflow_test"
source=tests/terminal_pane_cursor_test.zi
"$ziran" ir --project --root tests -o "$work/portable-ir" "$source"
for target in c go; do
    package=; if test "$target" = go; then package='--pkg main'; fi
    "$ziran" build --project --root tests --target="$target" --entry terminal_pane_cursor_test:main \
        --exe $package -o "$work/portable-$target" "$source"
    if test "$target" = go; then GOCACHE="$work/go-cache" GO111MODULE=off go run "$work/portable-$target"/*.go
    else "$work/portable-$target/terminal_pane_cursor_test"; fi
done
"$ziran" bundle --project --root tests --entry terminal_pane_cursor_test:main -o "$work/source.zx" "$source"
"$ziran" bundle --root "$work/portable-ir" --module-path "$work/portable-ir" --entry terminal_pane_cursor_test:main -o "$work/saved.zx" "$work/portable-ir/terminal_pane_cursor_test.zir"
test "$("$ziran" run "$work/source.zx" | tail -1)" = 0
test "$("$ziran" run "$work/saved.zx" | tail -1)" = 0
echo 'Cursor metadata matches full reflow across wrap boundaries and blank rows'
