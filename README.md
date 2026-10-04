# Terminal

Terminal is the standalone terminal application maintained by
[KryonLabs](https://github.com/kryonlabs), using Kryon for windowing,
rendering, input, and platform integration. The terminal emulator belongs here,
not in Kryon.

```sh
make -j1
make standalone-window-test
make independent-window-test
make pane-ziran-test
make standalone-test install-test
make install
```

The application, terminal engine, pane and shared application host are
maintained in Ziran. `make` generates native C from the current `.zi`
entrypoint and links Kryon's Raylib backend over SDL2. The build needs a C/C++
compiler, CMake, pkg-config, SDL2 and OpenGL development files. Raylib's source
is resolved from the Git-backed package lock. Builds default to one job;
`T9_BUILD_JOBS` may select up to four.

`standalone-window-test` runs the actual executable on a private Xvfb display.
It checks CLI routes, a rendered window, real child-process input, held and
repeated Control keys, menu input ownership, and closing its own window.
`standalone-test` repeats these checks for C and C++ from source and saved IR.
`independent-window-test` opens separate agent-terminal views on a private display,
checks that repeated launches keep the first window and input working, and verifies
that closing a view preserves the other window and both tmux sessions. Its display,
configuration, state, runtime locks and tmux socket are disposable.

The window tests need Xvfb, xauth, xdotool, xset and tmux; they scrub inherited
session and display variables before creating their private display.

The focused Ziran suites exercise the actual engine, configuration, sessions,
launch options, application state, input, view, host, widget, clipboard and
process transports. Native Plan 9 module checks use a headless Taiji guest
with one CPU, 256 MB RAM, a 32 MB translation buffer and a 120-second limit:

```sh
TAIJI_DIR=/path/to/taijiosnet/taiji make standalone-plan9-test
TAIJI_DIR=/path/to/taijiosnet/taiji make standalone-plan9-graphics-test
TAIJI_DIR=/path/to/taijiosnet/taiji make terminal-plan9-test host-plan9-test
make plan9-c
```

`plan9-c` emits the complete application for native `mk`/8c/8l. The standalone
native test builds the real executable and checks its CLI and forwarding to
Rill from source and saved IR. `standalone-plan9-graphics-test` adds captures
from the real native application and checks child output, ANSI truecolor and
rendered glyphs on its owned offscreen target. It runs through private Xvfb
and the bounded guest. This new gate remains unverified because the sandbox
blocks the guest filesystem connection; native graphical input, font fallback
and Rill's actual embedded integration remain migration gates.
Rill can import `t9/app_host`; its integration must own the surrounding frame,
device input and window operations.

## Embedding as a Ziran package

Terminal is also a Git-backed Ziran package. Add it to an existing application:

```sh
ziran add https://github.com/kryonlabs/terminal.git --name t9
ziran pkg list t9
```

Commit the generated `ziran.lock` with the application's manifest. Use
`#import "t9/terminal"` for the parser, `Terminal`/`Cell` state, scrollback and
owned PTY lifecycle, and `#import "t9/terminal_pane_widget"` for
`TerminalPane` and `DrawTerminalPane`. The pane accepts the host's existing
Kryon session and bounds; it creates no window, event loop or application
configuration. `t9/app_host` is available when embedding the complete tabbed
Terminal application instead of a single pane.

Initialize each state with `terminal_init`, then either `terminal_spawn` for
an owned child or `terminal_resize` and `terminal_feed` for host-supplied
output. Draw it inside the host's `BeginFrame`/`EndFrame`, with `handle_input`
enabled only while the terminal owns keyboard focus. Call `terminal_poll` for
owned children and `terminal_close` when removing a terminal to release its
buffers and supervised child. Display and window lifecycle stay with the host.

For a remote or otherwise host-managed process, set the pane's `write_input`
callback and `input_userdata`; keyboard input is encoded by Terminal and handed to
that callback instead of a local PTY. Hosts that capture input themselves can
call `TerminalPaneHandleInputTo` with a `KeyboardFrame`. Set `scroll_offset`
to the number of history rows above the live screen (zero follows the live
screen); cells retain their ANSI colors and styles while drawing history.

The package also exports `t9/terminal_keyboard`, `t9/terminal_pane_keys`,
`t9/terminal_pane_profile_colors` and `t9/terminal_clipboard` for hosts that
manage input frames, protocol encoding, colors or clipboard routing directly.
Internal parser modules remain private. Applications should use the same
locked Kryon dependency as Terminal so their session and geometry types are shared.
Local application overrides may name the canonical `kryonlabs/terminal` checkout
in an ignored `ziran.local.toml`; no source copies or sibling module paths are
needed in application code.

`make package-test` adds Terminal by its public HTTPS URL to a generated consumer,
then compiles and runs package-qualified imports in C and C++ from source and
saved IR. It checks Unicode/ANSI parsing, pane painting through the host's
Kryon session, keyboard encoding and clipboard storage without a desktop
display. The consumer has its own module roots and checks that Terminal's
private modules stay unavailable through package-qualified imports.
`T9_PACKAGE_LOCKED=1 make package-test` checks committed Git packages with
`--locked` after generating the consumer's dependency lock.

`make install` installs the `terminal` command (with the compatible `t9` command) and a desktop launcher named Terminal.
The default `PREFIX` is `~/.local`; `DESTDIR` supports staged packaging.
`install-test` checks a disposable staged installation.

The Linux release workflow is in `.github/workflows/release.yml`. Its intended
assets are `tar.gz`, `.deb`, and `.AppImage` packages. The remaining behavior
and release-readiness work is tracked in `docs/REMAINING_FEATURE_PLAN.md` and
`docs/ZIRAN_MIGRATION.md`; passing the standalone checks does not establish a
complete Rill migration or native Plan 9 graphical session.

Dependencies resolve through `scripts/ziran.sh`, `ziran.toml`, and the
command-generated `ziran.lock`. Install Ziran on `PATH` for a locked checkout.
The wrapper selects the package toolchain; if it has not been built, it prints
the exact compiler build command. Without local overrides, build and test
routes require `--locked`.

For local development, create the ignored `ziran.local.toml` with canonical
organization-root overrides:

```toml
[overrides]
ziran = "../../ziranlang/ziran"
kryon = "../../kryonlabs/kryon"
```

Additional source-package overrides, such as Kryon's `raylib` dependency,
may point to an existing local package checkout. Local overrides do not
belong in the manifest or release artifacts.

Run options:

```sh
terminal --working-directory /path/to/project
terminal --default-working-directory /path/to/project
terminal --shell /bin/bash
terminal --command 'make test'
terminal --command='make test'
terminal -e 'make test'
terminal -x make test
terminal --title 'Build'
terminal --command 'make test' --tab --title 'Logs' --command 'tail -f build.log'
terminal --drop-down --title 'System' --command htop
terminal --geometry 120x40
terminal --fullscreen
terminal --maximize
terminal --hold
terminal --font-size 18
terminal --scrollback 10000
terminal --cursor-style bar
terminal --terminal-font /usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf
terminal --terminal-foreground '#f2f2f2' --terminal-background '#101010' --terminal-cursor '#f2f2f2'
terminal --terminal-selection-foreground '#101010' --terminal-selection-background '#5a8fd8'
```

Terminal accepts common xfce4-terminal launch options:
`--command`/`-e`, `--execute`/`-x`, `--default-working-directory`,
`--title`/`-T`, `--hold`/`-H`, `--geometry`, `--fullscreen`, `--maximize`,
`--drop-down`, `--disable-server`, `--tab`, `--window`, and
menubar/toolbar/border visibility flags. `--tab` starts additional tabs from
command-line specs. `--drop-down` starts a borderless top-of-screen terminal
window. `--window` is accepted as a separator and currently opens another tab
because Terminal does not have multi-window process/server support yet.

Config is read from `$XDG_CONFIG_HOME/t9/config` or
`~/.config/t9/config`:

```ini
font_size=16
scrollback=5000
cursor_style=block
terminal_font=/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf
terminal_foreground=#f2f2f2
terminal_background=#101010
terminal_cursor=#f2f2f2
terminal_selection_foreground=#101010
terminal_selection_background=#5a8fd8
shell=/bin/bash
working_directory=/home/me/project
```

String values saved by Terminal use backslash escapes for tabs, newlines, and
literal backslashes.

Terminal restores open tabs on startup when no command is configured, including
the active tab plus each tab's working directory, shell, command, scroll
position, and manual title override. The restore file lives under
`$XDG_STATE_HOME/t9/session`
or `~/.local/state/t9/session`.

Terminal chrome and default terminal foreground/background/cursor colors follow
the Kryon system theme. Explicit profile colors and OSC color changes stay in
control until reset.

Use the Terminal menu to update profile defaults for shell, working directory,
terminal font, font size, colors, selection colors, scrollback, cursor color,
and cursor style. Changes are saved to the same config file and apply to
future tabs; font, colors, scrollback, and cursor changes also apply to the
running window.

Shortcuts:

- `Ctrl+Shift+T`: new tab
- `Ctrl+Shift+W`: close tab
- `Ctrl+Tab`: next tab
- `Ctrl+Shift+Tab`: previous tab
- `Ctrl+PageUp` / `Ctrl+PageDown`: previous tab, next tab
- `Alt+1` through `Alt+8`: switch directly to that tab
- `Ctrl+Shift+C`: copy selection
- `Ctrl+Shift+V`: paste
- `Ctrl+Insert` / `Shift+Insert`: copy selection, paste
- `Ctrl+Shift+F`: find
- `Ctrl+Shift+G`: find next
- `Ctrl+Shift+B`: find previous
- `Ctrl++` / `Ctrl+-` / `Ctrl+0`: zoom in, zoom out, reset size
- `Shift+PageUp` / `Shift+PageDown`: scroll

Find searches scrollback plus the visible terminal. Lowercase queries match
case-insensitively; queries containing uppercase letters are case-sensitive.

Mouse selection keeps a local primary selection for the terminal; middle click
pastes that selection before falling back to the system clipboard, and the
right-click menu exposes both clipboard paste and primary-selection paste.
Copied soft-wrapped lines are joined without adding artificial newlines.
Bracketed paste wraps pasted text and strips embedded terminal control
sequences so copied text cannot break out of the paste bracket.
OSC 52 clipboard queries are synced from the host clipboard before terminal
output is parsed, and OSC 52 clipboard writes update the host clipboard.
OSC 8 terminal hyperlinks are underlined with the theme link color and open
with `Ctrl` + left click.

Terminal graphics:

- Sixel images are decoded from DCS sequences and rendered inline in the
  terminal viewport.
- DEC special graphics character sets are mapped to Unicode line-drawing
  characters for ncurses-style terminal UIs.
- Insert/replace mode (`CSI 4 h/l`) is supported, including terminal mode
  reports.
- ANSI newline mode (`CSI 20 h/l`) controls whether LF/VT/FF also return to
  column zero, including terminal mode reports.
- SGR rendering covers bold, faint, italic, underline, underline color, blink,
  inverse, conceal, strike, overline, indexed colors, and truecolor.
- Application cursor-key mode covers arrow keys plus Home/End, including
  modified Home/End sequences.
- Function-key output covers F1-F24 with xterm-style modifier sequences, and
  XTGETTCAP advertises those emitted key capabilities.
- Application keypad mode covers digits, operators, center/corner keys, and
  Enter, with matching XTGETTCAP keypad capability reports.
- Printable-key input maps Ctrl letters and common Ctrl punctuation, including
  `Ctrl+/` and `Ctrl+-`, to terminal control bytes, with Alt preserved as an
  ESC prefix.
- xterm `modifyOtherKeys` mode (`CSI > 4 ; n m`) is supported for modified
  printable-key reporting, including the xterm disable sequence (`CSI > 4 n`).
- Mouse reporting covers X10, normal, button-event, any-event, SGR coordinates,
  SGR-Pixels coordinates, UTF-8 coordinates, urxvt coordinates, wheel events,
  motion events, and modifier bits.
- Cursor save/restore keeps cursor position, rendition, active character set,
  origin/wrap mode, insert mode, and hyperlink state.
- Alternate-screen mode presents only the alternate grid while preserving normal
  scrollback for restoration after full-screen apps exit.
- xterm alternate-scroll mode (`DECSET 1007`) sends wheel movement as cursor
  keys in the alternate screen when mouse reporting is not active.
- xterm focus reporting (`DECSET 1004`) sends focus changes for both window
  focus and active-tab changes.
- 8-bit C1 CSI/OSC/DCS plus IND/NEL/HTS/RI controls are parsed, and APC/PM/SOS
  control strings are ignored so their payloads do not leak into the terminal
  grid.
- BEL triggers a short theme-colored visual bell without writing text into the
  terminal grid.
- CAN/SUB cancel active control sequences and return the parser to text mode.
- Common CSI aliases are supported, including horizontal/vertical relative
  moves, horizontal absolute moves, and repeat preceding graphic character.
- DECSTR soft reset (`CSI ! p`) resets terminal modes, margins, rendition, and
  character sets without clearing the visible grid.
- DECRQSS status-string reports answer SGR, scroll-margin, cursor-style, and
  character-protection queries with valid DCS responses.
- XTGETTCAP (`DCS + q`) reports the terminal name, color capabilities, and the
  special-key sequences Terminal actually emits.
- Horizontal tab set/clear controls are supported, including clearing all tab
  stops for terminal UI alignment.
- DEC private cursor-position reports and DEC screen-alignment test are
  handled.
- DEC private cursor visibility and blink modes are reported and rendered.
- DECSCUSR cursor-shape controls distinguish blinking and steady block,
  underline, and bar cursors.
- XTWINOPS text-area and screen character-size reports return the active
  terminal grid dimensions.
- VT next-line and DECID escape controls are handled.
- OSC palette queries return xterm-style indexed responses and fall back to the
  built-in 256-color palette when a color has not been overridden.
- OSC color parsing accepts compact and wide X-style hash forms in addition to
  `rgb:` values.
- OSC dynamic colors cover default foreground/background, cursor, selection
  background, selection foreground, and indexed palette entries.
- OSC title handling distinguishes window and icon titles, and includes
  target-aware save/restore stack controls for terminal programs that
  temporarily replace titles.
- OSC 52 clipboard sequences can set the host clipboard and answer bounded
  clipboard queries from the current host clipboard.
- Terminal foreground, background, and cursor-color resets return to the
  resolved Kryon/system theme colors unless the profile explicitly overrides
  them.
- Sixel color registers, RGB/HLS color definitions, raster attributes, repeat
  commands, row advance, carriage return, transparency, 7-bit DCS, and 8-bit
  DCS/ST are supported.
- Erase-line, erase-display, reset, alternate-screen clear, scrolling, and
  scrollback eviction keep sixel images attached to the terminal content.

## Name and repository compatibility

The app is **Terminal** and its canonical checkout is `kryonlabs/terminal`.
The GitHub organization transfer/rename is a separate remote operation; local
source and references are prepared for that destination. No push or transfer
is implied by this source change.

The Ziran package/import identifier remains `t9` so existing consumers keep
working; use `--name t9` when adding the new repository URL. The configuration
(`~/.config/t9/config`, Plan 9 `/lib/t9/config`), saved sessions
(`~/.local/state/t9/session`), existing `t9` executable, Debian package ID,
`t9.desktop`/icon IDs, `T9_*` build/test variables and Plan 9 `open t9` host
protocol are retained. The preferred `terminal` command is an alias to the
same executable. Harmony and Rill retain their saved `t9` app/host IDs.
Showcase slugs and existing banner paths stay stable for inbound links.
Release asset names and all visible app labels use Terminal.
