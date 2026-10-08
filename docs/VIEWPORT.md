# Read-only terminal viewport

`terminal_viewport_build` projects a source `Terminal` into a different display
width and height without resizing the source, changing its parser state or
calling the PTY. It stores row references and borrows the original complete
cells. This supports a remote or shared terminal whose source geometry must
remain independent of a host's display geometry.

The source must outlive the viewport. Rebuild after a feed, source resize,
cursor change or any other source mutation; references are not immutable
snapshots. Close the viewport before closing its source. A failed allocation
leaves the previous viewport and source unchanged; the caller must wait for a
successful rebuild before displaying a changed source.

```ziran
Engine :: #import "t9/terminal";
view: Engine.TerminalViewport;
defer { Engine.terminal_viewport_close(*view) }
if !Engine.terminal_viewport_build(*view, source, display_cols, display_rows) {
    return
}
count := Engine.terminal_viewport_line_count(*view);
cell := Engine.terminal_viewport_cell(*view, col, visible_row);
```

The projection preserves the established resize's retained history, blank
padding, delayed soft wraps, cursor placement, cropped alternate screen and
complete cell attributes. `terminal_viewport_line` produces the same visible
UTF-8 text, including combining characters and wide continuation handling.
Colors, modes and other source metadata remain on the original `Terminal`.
The existing configured history limit applies; the viewport adds no new limit.

Metadata capacity follows retained history plus viewport height. Repeated
builds of the same capacity allocate nothing. For a history limit of 2,000
and a 120-row display, row metadata occupies 25,440 bytes, excluding the
viewport structure, original source cells and any host storage. This is a
component storage bound, not a whole-application RAM measurement.

Run `make terminal-viewport-test` for complete comparisons with the current
resize in source/saved-IR C and C++, allocation-free attached-source rebuilds,
and failed-allocation guards. `make terminal-viewport-plan9-test` runs the same
source/saved-IR fixture through native Plan 9 `8c`/`8l`, with `TAIJI_DIR` set to
the canonical Taiji checkout. These tests open no desktop windows.

The prepared row index is a reusable engine primitive. Adoption by the
existing `TerminalPane` widget and Harmony still needs complete paint/input
equivalence and balanced native-window CPU/PSS checks, including narrow
displays: retaining the source grid can cost more RAM than resizing it to a
narrower viewport. No whole-application speedup or deployment follows from
the engine checks alone.
