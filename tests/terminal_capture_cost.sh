#!/bin/sh
# Stable private diagnostic output; no display, PTY or installed app is used.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
unset DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS ENV BASH_ENV
export YUE_DESKTOP_RECOVERY=0
work="$root/build/ziran/capture-cost"
mkdir -p "$work"
exec 9>"$work/check.lock"
flock -n 9 || { echo 'Capture cost diagnostic is already running' >&2; exit 1; }
ziran=${ZIRAN:-"$root/scripts/ziran.sh"}
lock_flags=
if test ! -f ziran.local.toml; then lock_flags=--locked; fi
source=tests/terminal_capture_cost_probe.zi
entry=terminal_capture_cost_probe:main
"$ziran" ir --project $lock_flags --entry "$entry" -o "$work/ir" "$source"
for form in source saved; do
    input=$source
    if test "$form" = saved; then input=$work/ir/terminal_capture_cost_probe.zir; fi
    out="$work/$form-c"
    "$ziran" build --project $lock_flags --target=c --entry "$entry" -o "$out" "$input"
    compiler=${CC:-cc}; standard=c11
    "$compiler" -std="$standard" -O2 -I"$out" "$out"/*.c -o "$out/run"
    timeout --kill-after=2s 120s "$out/run" >"$work/$form-c.jsonl"
done
python3 - "$work" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
rows = {}
for form in ['source', 'saved']:
    for target in ['c']:
        name = f'{form}-{target}'
        data = [json.loads(line) for line in (root / f'{name}.jsonl').read_text().splitlines()]
        assert len(data) == 96, (name, len(data))
        assert all(row['iterations'] == 16 for row in data)
        assert len({(row['run'], row['history_input_rows'], row['styled'], row['view_cols'], row['view_rows']) for row in data}) == 96
        rows[name] = data
reference = [{k: v for k, v in row.items() if not k.endswith('_ns')} for row in rows['source-c']]
assert all([{k: v for k, v in row.items() if not k.endswith('_ns')} for row in data] == reference for data in rows.values())
result = {'scope': 'Detached native terminal allocation, full capture replay and source-to-view reflow only; no transport, rendering, PTY, display or full interaction claim.',
          'forms': list(rows), 'samples_per_form': 96, 'iterations_per_sample': 16,
          'all_form_digests_identical': True, 'rows': rows}
(root / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))
PY
