CC ?= cc
AR ?= ar
.DEFAULT_GOAL := all
ZIRAN ?= ./scripts/ziran.sh
LOCK_FLAGS := $(if $(wildcard ziran.local.toml),,--locked)
BUILD_ROOT ?= build
BUILD_DIR ?= $(BUILD_ROOT)/linux-$(shell uname -m)
PREFIX ?= $(HOME)/.local
BINDIR ?= $(PREFIX)/bin
APPDIR ?= $(PREFIX)/share/applications
INSTALL ?= install
APP := $(BUILD_DIR)/bin/terminal
SOURCES := $(wildcard src/*.zi src/app/*.zi src/engine/*.zi src/terminal_pane/*.zi)
PACKAGE_INPUTS := ziran.toml ziran.lock $(wildcard ziran.local.toml)
TERMINAL_GEN := $(BUILD_DIR)/generated/terminal
TERMINAL_LIB := $(BUILD_DIR)/lib/libterminal.a
PANE_GEN := $(BUILD_DIR)/generated/pane
PANE_LIB := $(BUILD_DIR)/lib/libterminal_pane.a
PTY_GEN := $(BUILD_DIR)/generated/pty
ZIRAN_MIGRATION_TEST := tests/ziran_migration_test.sh

.PHONY: all run test clean install install-test standalone-test standalone-window-test pty-native parser-replay parser-replay-test package-test
all: $(APP)

$(APP): $(SOURCES) $(PACKAGE_INPUTS) scripts/build.sh scripts/ziran.sh Makefile
	ZIRAN="$(ZIRAN)" CC="$(CC)" sh scripts/build.sh c "$(BUILD_DIR)"

run: $(APP)
	$(APP)

standalone-window-test: $(APP)
	env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY -u DBUS_SESSION_BUS_ADDRESS -u SESSION_MANAGER \
		LP_NUM_THREADS=1 OMP_NUM_THREADS=1 xvfb-run -a -s '-screen 0 1024x768x24' \
		env TERMINAL_PRIVATE_XVFB=1 python3 tests/standalone_window_test.py "$(APP)"

.PHONY: link-window-test
link-window-test: $(APP)
	env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY -u DBUS_SESSION_BUS_ADDRESS -u SESSION_MANAGER \
		YUE_DESKTOP_RECOVERY=0 LP_NUM_THREADS=1 OMP_NUM_THREADS=1 xvfb-run -a -s '-screen 0 1024x768x24' \
		env TERMINAL_PRIVATE_XVFB=1 python3 tests/link_window_test.py "$(APP)"

.PHONY: selection-copy-window-test
selection-copy-window-test: $(APP)
	env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY -u DBUS_SESSION_BUS_ADDRESS -u SESSION_MANAGER \
		YUE_DESKTOP_RECOVERY=0 LP_NUM_THREADS=1 OMP_NUM_THREADS=1 xvfb-run -a -s '-screen 0 1024x768x24' \
		env TERMINAL_PRIVATE_XVFB=1 python3 tests/selection_copy_window_test.py "$(APP)"

.PHONY: independent-window-test
independent-window-test: $(APP)
	env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY -u DBUS_SESSION_BUS_ADDRESS -u SESSION_MANAGER \
		LP_NUM_THREADS=1 OMP_NUM_THREADS=1 xvfb-run -a -s '-screen 0 1024x768x24' \
		env TERMINAL_PRIVATE_XVFB=1 python3 tests/independent_windows_test.py "$(APP)"

.PHONY: keyboard-layout-window-test
keyboard-layout-window-test: $(APP)
	env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY -u DBUS_SESSION_BUS_ADDRESS -u SESSION_MANAGER -u TMUX -u TMUX_PANE \
		LP_NUM_THREADS=1 OMP_NUM_THREADS=1 xvfb-run -a -s '-screen 0 1024x768x24 -noreset' \
		env TERMINAL_PRIVATE_XVFB=1 python3 tests/keyboard_layout_window_test.py "$(APP)"

standalone-test: $(APP)
	ZIRAN="$(ZIRAN)" RAYLIB_A="$(if $(RAYLIB_A),$(RAYLIB_A),$(abspath $(BUILD_DIR))/raylib/raylib/libraylib.a)" sh tests/standalone_test.sh

parser-replay:
	ZIRAN="$(ZIRAN)" sh scripts/parser-replay.sh

parser-replay-test:
	ZIRAN="$(ZIRAN)" sh tests/parser_replay_test.sh

pty-native:
	env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY $(ZIRAN) build --project $(LOCK_FLAGS) \
		--target=c --no-main --prune-stale -o $(PTY_GEN) src/terminal_pty_linux.zi
	set -e; for source in $(PTY_GEN)/*.c; do \
		$(CC) -std=c11 -O1 -fPIC -I$(PTY_GEN) -c "$$source" -o "$${source%.c}.o"; \
	done

.PHONY: ziran-migration-check
ziran-migration-check:
	$(ZIRAN_MIGRATION_TEST)

# Module fixtures use isolated host effects and never need a desktop display.
.PHONY: clipboard-test clipboard-protocol-test selection-test keys-test osc-test metrics-test pty-test pane-ziran-test
clipboard-test:
	sh tests/clipboard_test.sh clipboard
	sh tests/clipboard_test.sh protocol
	sh tests/clipboard_test.sh drop

clipboard-protocol-test:
	sh tests/clipboard_test.sh protocol

selection-test:
	sh tests/clipboard_test.sh selection

keys-test:
	sh tests/keys_test.sh

osc-test:
	sh tests/osc_test.sh

metrics-test:
	sh tests/metrics_test.sh

pty-test:
	sh tests/pty_test.sh

.PHONY: terminal-test terminal-native config-test
config-test:
	sh tests/config_test.sh

terminal-test:
	sh tests/terminal_engine_test.sh

.PHONY: terminal-capture-test terminal-capture-storage-test reflow-span-test terminal-viewport-test
terminal-viewport-test:
	sh tests/terminal_viewport_test.sh

terminal-capture-test:
	sh tests/terminal_capture_test.sh

terminal-capture-storage-test:
	sh tests/terminal_capture_storage_test.sh

reflow-span-test:
	sh tests/reflow_span_test.sh

terminal-native:
	env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY $(ZIRAN) build --project $(LOCK_FLAGS) \
		--target=c --no-main -o $(TERMINAL_GEN) src/terminal.zi
	mkdir -p $(BUILD_DIR)/lib
	set -e; for source in $(TERMINAL_GEN)/*.c; do \
		$(CC) -std=c11 -O2 -fPIC -I$(TERMINAL_GEN) -c "$$source" -o "$${source%.c}.o"; \
	done
	rm -f $(TERMINAL_LIB)
	$(AR) rcs $(TERMINAL_LIB) $(TERMINAL_GEN)/*.o

.PHONY: widget-test profile-test session-test launch-test pane-native
widget-test:
	sh tests/widget_test.sh

profile-test:
	sh tests/profile_test.sh

session-test:
	sh tests/session_test.sh

launch-test:
	sh tests/launch_options_test.sh

pane-native:
	env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY $(ZIRAN) build --project $(LOCK_FLAGS) \
		--target=c --no-main -o $(PANE_GEN) src/terminal_pane/terminal_pane_widget.zi
	mkdir -p $(BUILD_DIR)/lib
	set -e; for source in $(PANE_GEN)/*.c; do \
		$(CC) -std=c11 -O1 -fPIC -I$(PANE_GEN) -c "$$source" -o "$${source%.c}.o"; \
	done
	rm -f $(PANE_LIB)
	$(AR) rcs $(PANE_LIB) $(PANE_GEN)/*.o

.PHONY: application-test input-test view-test host-test
application-test:
	ZIRAN="$(ZIRAN)" sh tests/application_test.sh

input-test:
	ZIRAN="$(ZIRAN)" sh tests/application_test.sh input

view-test:
	ZIRAN="$(ZIRAN)" sh tests/application_test.sh view

host-test:
	ZIRAN="$(ZIRAN)" sh tests/application_test.sh host

pane-ziran-test: terminal-test terminal-capture-test terminal-capture-storage-test reflow-span-test config-test widget-test profile-test session-test launch-test application-test input-test view-test host-test clipboard-test selection-test keys-test osc-test metrics-test pty-test ziran-migration-check

package-test:
	ZIRAN="$(ZIRAN)" sh tests/package_test.sh

test: package-test pane-ziran-test link-window-test selection-copy-window-test standalone-test independent-window-test install-test parser-replay-test reflow-cursor-test

.PHONY: reflow-cursor-test
reflow-cursor-test:
	sh tests/reflow_cursor_test.sh

install: $(APP)
	mkdir -p "$(DESTDIR)$(BINDIR)" "$(DESTDIR)$(APPDIR)"
	$(INSTALL) -m 755 "$(APP)" "$(DESTDIR)$(BINDIR)/terminal"
	{ \
		printf '%s\n' '[Desktop Entry]' 'Type=Application' 'Name=Terminal'; \
		printf '%s\n' 'Comment=Kryon terminal emulator' 'Exec=$(BINDIR)/terminal'; \
		printf '%s\n' 'Icon=utilities-terminal' 'Terminal=false' 'Categories=System;TerminalEmulator;'; \
		printf '%s\n' 'Keywords=terminal;shell;' 'StartupNotify=true'; \
	} > "$(DESTDIR)$(APPDIR)/terminal.desktop"
	if command -v update-desktop-database >/dev/null 2>&1; then update-desktop-database "$(DESTDIR)$(APPDIR)"; fi

install-test: $(APP)
	@set -eu; mkdir -p build/ziran; stage=$$(mktemp -d "$(CURDIR)/build/ziran/install.XXXXXX"); \
		trap 'rm -rf "$$stage"' EXIT HUP INT TERM; \
		$(MAKE) --no-print-directory install DESTDIR="$$stage" PREFIX=/usr; \
		test -x "$$stage/usr/bin/terminal"; test -f "$$stage/usr/share/applications/terminal.desktop"; \
		env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY "$$stage/usr/bin/terminal" --version | grep -qx "Terminal 0.1"; \
		if command -v desktop-file-validate >/dev/null 2>&1; then desktop-file-validate "$$stage/usr/share/applications/terminal.desktop"; fi

clean:
	rm -rf "$(BUILD_ROOT)"
