# Clipboard, Alt-click links and the xfce4-terminal context menu

Owner request (2026-11-12): full, correct clipboard; Alt+click links; a right-click
menu that matches xfce4-terminal 1:1; shared pieces fixed in canonical Kryon so
Terminal uses clean Kryon widgets with no local copies.

## Findings

- Harmony's embedded Terminal window (`harness/harmony/client/src/terminal_*_linux.zi`)
  never sets `app_clipboard.image_path`, so Ctrl+V there is consumed and does
  nothing. Standalone sets it to a local GTK reader (`app_image_clipboard.zi`),
  which duplicates Kryon's `SystemClipboardLinux.SystemClipboardImage`.
- Ctrl+V with a text-only clipboard does nothing (the key is swallowed).
- PRIMARY is in-process only (`terminal_clipboard.primary_bytes`); selecting text
  never sets the X PRIMARY selection and middle-click never reads another
  application's selection. Middle-click falls back to CLIPBOARD; xfce4-terminal
  does not.
- Links are opened by each window adapter with `SDL_OpenURL`; Kryon already has
  `kryon/open_uri` (xdg-open, test capture hook).
- Kryon `ContextMenuItem` has no accelerator label and no check state, so the
  terminal fakes shortcuts with padded label text.

## Reference: installed xfce4-terminal 1.1.4

Captured in a private Xvfb with the owner's terminalrc. No icons; no shortcut
labels in the main menu.

    [over a URL]   Open Link / Copy Link Address, separator
    [over e-mail]  Compose Email / Copy Email Address, separator
    Open Tab
    Open Terminal
    Open File Manager Here
    ---
    Copy            (disabled without a selection)
    Copy as HTML    (disabled without a selection)
    ---
    Paste
    Paste Selection
    ---
    [ ] Show Menubar
    [ ] Fullscreen
    [ ] Read-Only
    ---
    Send Signal >   1 - HUP ... 30 - PWR
    ---
    Zoom >          Zoom In Ctrl++ / Zoom Out Ctrl+- / Normal Size Ctrl+0
    ---
    Save Contents...
    ---
    Preferences...

Right-click with a selection opens this menu (Copy enabled); it does not copy.

## Kryon (canonical, master)

1. `ContextMenuItem`: `accelerator` label (right-aligned, dimmed) and
   `checkable`/`checked` check rows. Docs and tests.
2. `system_clipboard`: primary selection text read/write through the host
   (`SystemPrimaryText`, `SystemPrimarySet`); SDL desktop host implements it,
   other hosts report it unavailable. Docs and tests.
3. Terminal uses the existing `SystemClipboardLinux` image read,
   `MimeClipboardLinux` for the HTML copy, and `open_uri` for links.

## Terminal

- Ctrl+V: PNG on CLIPBOARD -> saved private file path pasted; otherwise text.
- Ctrl+Shift+V / menu Paste: CLIPBOARD text only, never an image.
- Selection end publishes X PRIMARY; middle-click, Shift+Insert and
  Paste Selection read X PRIMARY only.
- Alt+click (and Ctrl+click) opens http(s), OSC 8 and e-mail targets through
  `kryon/open_uri`, inside Terminal for both standalone and embedded hosts.
- Context menu rebuilt to the reference above with working actions.
- Remove `app_image_clipboard.zi` (GTK) and window-level `SDL_OpenURL`.

## Verification

Private Xvfb (scrubbed DISPLAY/WAYLAND_DISPLAY/XAUTHORITY/DBUS_SESSION_BUS_ADDRESS,
HARMONY_DESKTOP_RECOVERY=0) with xclip clipboard owners offering image/png and
text; menu screenshot compared with the xfce4-terminal reference. Kryon
`make test`, Terminal test suite, then `ziran update kryon`, install from the
working tree, one commit per repo.

## Implementation progress

- Kryon's public PRIMARY API and SDL desktop host support are implemented,
  with unavailable stubs for hosts that do not have a distinct PRIMARY selection.
- Per the owner's filename correction, the shared clipboard fixture and focused
  test are now `system_clipboard_host.zi` and `system_clipboard_test.zi`; the
  redundant `ziran_` prefix and all references to it were removed.
- Terminal now routes selection ownership to host PRIMARY, replaces its GTK
  image reader with `SystemClipboardLinux`, uses `MimeClipboardLinux` for safe
  plain+HTML ownership, and routes link opening through `kryon/open_uri`.
- Shortcut, middle-click, read-only, dynamic link/e-mail, and the complete
  xfce4-terminal context-menu action structure are implemented.
- 2026-11-14: integrated with the 0.1.0 release commit and moved to Kryon's
  package-qualified widget imports. `make test` and `standalone-window-test`
  pass on private Xvfb. The application context-menu
  test now finds rows by label in the xfce4-terminal structure; the link test
  focuses the window and uses Shift+right-click while the child tracks the mouse;
  the selection test uses a 10-row window so Copy is reachable and gives each
  menu copy a fresh CLIPBOARD owner (and waits for text/html) instead of racing
  the previous copy; the rendered-menu test reads 2x captures and waits for the
  submenu to paint; the Thunar test launches the real Terminal through Exo.
- The Xfce helper passes `--working-directory=.` (Terminal starts in HOME
  unless told otherwise, and Exo starts it in the selected folder) and runs
  launch commands with `-x`, because Exo splits them into words.
- Kryon `RaylibInputPoll` lost a Control press released again within one
  poll, so scripted quick Control+C taps arrived as a plain C. With the
  owner's approval it is fixed in Kryon, covered by `raylib_window_test`, and
  `keyboard-layout-window-test` passes again.
- Kryon keeps menus inside the window: a window shorter than the 21-row menu
  pins it to the top and clips the lower rows (Zoom, Save Contents, Preferences).
- Kryon's `SystemPrimaryText`, `SystemPrimaryAvailable` and `SystemPrimarySet`
  with the SDL desktop and Raylib hosts are committed and pushed together with
  that fix, and `system-clipboard-test` now runs in Kryon's `make test`.
  Terminal's `ziran.lock` pins that Kryon commit and the matching Ziran.

## Open

- "ifx the olols" is unclear; waiting on the owner through the parent.
