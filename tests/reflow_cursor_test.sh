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
for target in c cpp; do
    executable=--exe; if test "$target" = cpp; then executable=; fi
    package=; if test "$target" = go; then package='--pkg main'; fi
    "$ziran" build --project --root tests --target="$target" --entry terminal_pane_reflow_test:main \
        $executable $package -o "$work/$target" "$source"
    if test "$target" = cpp; then
        rm -f "$work/$target/entry.cpp"
        "${CXX:-c++}" -std=c++17 -O2 -I"$work/$target" "$work/$target"/*.cpp -o "$work/$target/test"
        "$work/$target/test"
    elif test "$target" = go; then GO111MODULE=off go run "$work/$target"/*.go
    else "$work/$target/terminal_pane_reflow_test"; fi
done
source=tests/terminal_pane_cursor_test.zi
"$ziran" ir --project --root tests -o "$work/portable-ir" "$source"
for target in c cpp go; do
    executable=--exe; if test "$target" = cpp; then executable=; fi
    package=; if test "$target" = go; then package='--pkg main'; fi
    "$ziran" build --project --root tests --target="$target" --entry terminal_pane_cursor_test:main \
        $executable $package -o "$work/portable-$target" "$source"
    if test "$target" = cpp; then
        "${CXX:-c++}" -std=c++17 -O2 -I"$work/portable-$target" "$work/portable-$target"/*.cpp -o "$work/portable-$target/test"
        "$work/portable-$target/test"
    elif test "$target" = go; then GOCACHE="$work/go-cache" GO111MODULE=off go run "$work/portable-$target"/*.go
    else "$work/portable-$target/terminal_pane_cursor_test"; fi
done
"$ziran" bundle --project --root tests --entry terminal_pane_cursor_test:main -o "$work/source.zib" "$source"
"$ziran" bundle --root "$work/portable-ir" --module-path "$work/portable-ir" --entry terminal_pane_cursor_test:main -o "$work/saved.zib" "$work/portable-ir/terminal_pane_cursor_test.zir"
test "$("$ziran" run "$work/source.zib" | tail -1)" = 0
test "$("$ziran" run "$work/saved.zib" | tail -1)" = 0
echo 'Cursor metadata matches full reflow across wrap boundaries and blank rows'
