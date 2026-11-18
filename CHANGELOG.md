# Changelog

## [Unreleased]

- Run on Kryon's desktop host instead of raylib: the window, PTY-aware
  activity waits, frame pacing, fullscreen, monitor placement, dropped files
  and typefaces come from `desktop_runtime`, `desktop_window_state`,
  `desktop_keyboard`, `desktop_activity` and `cairo_typefaces`. Builds need no
  CMake raylib step. Pins Kryon b5a61b37 with Ziran 7fbc8152.
- Keep the Find and other text dialogs closing on an outside click under
  Kryon's modals, which now stay open unless they opt in.
- Keep every button press, release and wheel step that arrives while the
  terminal waits on its shells, at the cell where the press happened, so
  quick clicks and drags select from the right place.
- A Ctrl shortcut that a key press triggered (such as Ctrl+V paste) no longer
  also types its control byte while the key is still held.
- Keep captured terminal rows in their own colors when reflowing or resizing,
  so a colored diff or status row cannot flood later blank rows.
- Consume Kryon's ordered per-session key and text delivery.
- Build against Kryon's package-qualified widget imports (`kryon/menu`,
  `kryon/context_menu`, `kryon/tab_bar`, `kryon/text_field` and others) now that
  the `Widgets` facade and `*_props` modules are gone.
- Use the platform PRIMARY selection for selected text, middle-click,
  Shift+Insert, and Paste Selection. Ctrl+V prefers a clipboard PNG and falls
  back to text, while Ctrl+Shift+V and the Paste menu action stay text-only.
- Match the xfce4-terminal 1.1.4 right-click menu, including link and email
  actions, Copy as HTML, open/save actions, checked state, signals, zoom
  accelerators, and preferences. Right-click on selected text copies it to the
  clipboard and keeps the selection and PRIMARY; with nothing selected, or
  with Shift held, right-click opens the menu.
- Alt-click also opens email addresses, and links open through Kryon in both
  standalone and embedded Terminal windows.
- `make install` also installs the Xfce TerminalEmulator helper, so Thunar's
  Open Terminal Here and `exo-open --launch TerminalEmulator` start this
  terminal in the selected folder, and Exo launch commands run through `-x`.
- A working directory that is missing, a file, or cannot be entered no
  longer closes the window as soon as it opens: the shell starts in the home
  folder and Terminal says why (missing, not a folder, or not permitted), on
  the terminal and on standard error. Thunar custom actions pass
  `--working-directory=%f` without extra quotes, because Thunar quotes `%f`
  itself.

## [0.1.0] - 2026-11-13

- Releases publish `terminal-linux-amd64.deb` and
  `terminal-linux-x86_64.AppImage` under fixed names, so
  `/releases/latest/download/` links always fetch the newest build. The
  package's dependencies now come from the binary itself, GTK included, and
  the AppImage bundles SDL2 and WebP.
- Keep inactive window cursors steady and restart cursor blinking on focus,
  typing, and tab changes instead of blinking all windows together.

- Paste clipboard images with Ctrl+V, paste text with Ctrl+Shift+V, and drop image files into the active terminal. Keep running windows intact during installation.

- New tabs open in the current folder of the tab they were opened from instead
  of the configured working directory or home folder.

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
