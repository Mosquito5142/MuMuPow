# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

MuMupow is a Windows desktop app for automating multiple MuMu Player (Android emulator) instances simultaneously. It controls emulators via ADB, runs JSON-defined macros against multiple accounts, and provides a Tkinter GUI with a custom dark theme. The compiled artifact is `MuMupow.exe` (PyInstaller).

## Commands

**Run in development mode:**
```
python main.py
```

**Run tests:**
```
python -m pytest tests/
```

**Run a single test file:**
```
python -m pytest tests/test_quick_builder.py
```

**Build the executable:**
```
python -m PyInstaller --clean MuMupow.spec
Copy-Item dist/MuMupow.exe ./MuMupow.exe -Force
```

## Architecture

### Entry point and wiring

`main.py` instantiates `MuMuGUI` (from `gui.py`) and starts the Tkinter event loop. `MuMuGUI.__init__` creates a single `MuMuController` instance (from `mumu_controller.py`) and wires it to the GUI.

### Device layer — `mumu_controller.py`

All ADB interactions go through `MuMuController`. Key responsibilities:
- Locate ADB (checks Android SDK and LDPlayer paths, then PATH)
- Connect to emulators via TCP ports; deduplicate connections by device serial
- `run_parallel_action()` — ThreadPoolExecutor fan-out for simultaneous multi-device commands
- `capture_screenshot_bytes()` — `exec-out screencap -p` straight to memory (no on-device temp file/pull); `take_screenshot()` uses it then falls back to legacy screencap+pull
- `find_image_in_bytes()` / `find_image_on_screen()` — OpenCV template matching (shared `_match_template` core) at 0.8 confidence threshold; macro image steps use the in-memory bytes variant

### GUI — `gui.py` (4,576 lines)

The entire UI is in this one file. Layout: header bar → sidebar (device checkboxes) → right panel with five tabs (Macro Editor, Account Management, Manual Sync, Settings, Log Console). The log panel is collapsible.

Custom widget helpers (`ModernButton`, `ModernEntry`, `make_panel()`, `make_checkbutton()`) produce the premium dark theme without an external theme library. Color palette constants are defined near the top of the file.

Macro execution runs on a **worker thread** (not the main thread) to keep the GUI responsive. Parallel vs. sequential account processing is toggled via UI checkboxes.

### Macro system

Macros are JSON files in `macros/`. Supported step types: `tap`, `swipe`, `text`, `keyevent`, `sleep`, `start_app`, `stop_app`, `screenshot`, `detect_image`, `wait_for_image`, `tap_text`, `wait_for_text`, `clear_ads_loop`, `fetch_otp`, `run_set`, `keyboard`.

The macro engine dispatches each step type to a `_step_<type>` handler method on `MuMuGUI`, registered in `_get_step_handlers()`. To add a new step type: write a `_step_xxx(self, ctx, step)` handler, register it there, add it to `STEP_LABEL_MATCHERS`/`DEFAULT_STEP_DELAYS`, the dropdown list, `_build_step_from_form`, and the load/visibility logic in `on_listbox_select`/`on_step_type_change`. `wait_for_image` polls the screen until a template appears (or `timeout`), a reliable replacement for fixed `sleep` waits.

`tap_text`/`wait_for_text` locate UI elements via `uiautomator dump` (parsed by `find_element_center` in `mumu_controller.py`) — robust for native Android screens (login/registration/email) but blind to game canvases (Unity/Cocos), where image steps are still required. The Manual Sync tab's "UI Inspector" button (`inspect_ui`) dumps the current screen's elements so you can tell which approach a screen needs. A search string starting with `id:` matches `resource-id`; otherwise it matches visible text/content-desc.

`{EMAIL}`, `{PASSWORD}`, and `{NAME}` placeholders in `text` steps are substituted at runtime from the selected account (`_substitute_account`). ASCII text uses `input text`; Thai/Unicode text routes through `input_text_unicode` (base64 broadcast to ADBKeyboard), which requires the ADBKeyboard IME — set it up per-emulator via the Settings tab buttons (`setup_adb_keyboard`/`restore_keyboard`), with `ADBKeyboard.apk` placed next to the app.

`quick_builder.py` provides factory functions for building steps. Coordinate presets (Thai UI labels → x/y pairs) live in `presets.json` and are loaded by the GUI at startup.

### Script sets — `script_sets.py`

Script sets are reusable step sequences stored in `script_sets/*.json`. The `run_set` step type inlines them at execution time. `script_sets.py` handles cycle detection to prevent infinite loops.

### Account management

Accounts are stored in `accounts.json` as a flat array. Fields: `email`, `password`, `checked`, `group`, `ingamename`, `refresh_token`, `client_id`. After a macro run, the run-report system also writes `last_status`, `last_error`, `last_device`, and `last_run` onto each account that ran (see `finalize_run_results`/`show_run_summary` in `gui.py`).

`save_web_game_import.py` parses Save Web Game export format and merges accounts into `accounts.json`. OTP retrieval uses either a web API (`read-mail.me` with OAuth2 tokens) or IMAP fallback (`outlook.office365.com`).

## Key Files

| File | Purpose |
|------|---------|
| `gui.py` | Entire UI and macro orchestration |
| `mumu_controller.py` | ADB wrapper and parallel device control |
| `quick_builder.py` | Macro step factory functions |
| `script_sets.py` | Reusable script set loading/expansion |
| `save_web_game_import.py` | Account import from Save Web Game exports |
| `presets.json` | Named coordinate presets (Thai labels) |
| `accounts.json` | Account credentials database |
| `MuMupow.spec` | PyInstaller build configuration |

## Data Formats

**Macro file** (`macros/*.json`):
```json
{
  "name": "My Macro",
  "steps": [
    {"type": "tap", "x": "450", "y": "211", "delay": 0.5, "desc": "..."},
    {"type": "text", "text": "{EMAIL}", "desc": "..."},
    {"type": "sleep", "seconds": 1.0, "desc": "..."}
  ]
}
```

**Account** (`accounts.json` entry):
```json
{
  "email": "user@example.com", "password": "pass",
  "checked": true, "group": "ชุดที่ 1",
  "refresh_token": "", "client_id": "", "ingamename": ""
}
```

## Notes

- UI labels are in Thai; code identifiers and comments are in English.
- The app targets Windows only (ADB path defaults, `.exe` output).
- `build/` and `dist/` are PyInstaller artifacts — do not edit.
- `templates/` holds user-supplied PNG images for OpenCV template matching.
- `scratch/` is a scratch pad for throwaway dev scripts.
