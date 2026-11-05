# Changelog

## [Unreleased]

- Alt-click opens visible web URLs and OSC 8 hyperlinks, including wrapped links
  and scrollback; Ctrl-click remains available, including in full-screen programs.

- Start new terminal windows in the home folder instead of restoring the last
  visited folder; explicit working-directory options still take priority.
- Keep saved tabs intact so terminal launches do not exit after restoring
  temporary shell entries.
- An idle window uses almost no CPU instead of redrawing constantly.
- Output appears faster and large floods scroll much faster, stay interruptible
  with Ctrl+C, and show new CJK text without stalling.
- Output inside a scroll region, such as below a fixed status line, scrolls
  almost twice as fast.
- `--geometry` opens a window with exactly the requested columns and rows.
- Ctrl+C and other Control keys and shortcuts such as Ctrl+Shift+T follow the active keyboard layout, including inside tmux, and a very quick press is no longer lost.
- Keep Tab completion and subsequent shell input in the terminal instead of moving focus to its controls.
- Right-click copies selected text and clears the selection; the context menu
  still opens when nothing is selected.
- Update to the latest Kryon and Ziran.
