# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

MuMupow is a Windows desktop app for automating multiple MuMu Player (Android emulator) instances simultaneously. It controls emulators via ADB, runs JSON-defined macros against multiple accounts, and reports per-account results.

There are **two front-ends driving one macro engine**:

| | Legacy app (customer fallback, lighter on RAM) | New app (where active work happens) |
|---|---|---|
| Entry point | `main.py` → `MuMuGUI` (`gui.py`) | `web_app.py` → pywebview + `Api` |
| UI | Tkinter, custom dark theme, single file | HTML/CSS/JS in `webui/` |
| Build | `MuMupow.spec` → `MuMupow.exe` | `MuMupow_web.spec` → `MuMupow_new.exe` |

**Both run macros through `macro_runner.MacroRunner` — there is exactly one engine.** `gui.py` used to carry a hand-kept port of it (`_run_macro_steps` + a `_step_*` handler per type); that copy is gone. Do not reintroduce it: two engines that "should" match drift silently every time only one side is edited. `tests/test_runner_parity.py` fails if a second copy reappears.

Consequences worth knowing:
- A script built in the web flow editor — branches, anchors, crash-proof blocks — runs **identically** under Tkinter.
- The one deliberate difference is `anchor_on_fail: "pause"`. The web app parks the device and lets you fix and resume live; Tkinter has no such panel, so `execute_device_macro` converts `"paused"` into `device_error`, writes the failure report, and moves to the next account.
- The Tkinter **editor** still cannot edit `if_image` steps (no such type in its dropdown, and `update_step` carries over only `anchor_*` keys — updating one would drop `then`/`else`). Build and edit branching scripts in the web app; run them anywhere.

## Commands

**Run the new (web) app in development mode:**
```
python web_app.py
```

**Run the legacy Tkinter app:**
```
python main.py
```

**Run tests:**
```
python -m pytest tests/ -q
```

**Run a single test file:**
```
python -m pytest tests/test_quick_builder.py
```

**Build the new app:**
```
python -m PyInstaller --clean MuMupow_web.spec
```

**Build the legacy app:**
```
python -m PyInstaller --clean MuMupow.spec
Copy-Item dist/MuMupow.exe ./MuMupow.exe -Force
```

## Architecture

### Device layer — `mumu_controller.py`

All ADB interactions go through `MuMuController`. Key responsibilities:
- Locate ADB (checks Android SDK and LDPlayer paths, then PATH)
- Connect to emulators via TCP ports; deduplicate connections by device serial
- `run_parallel_action()` — ThreadPoolExecutor fan-out for simultaneous multi-device commands
- `capture_screenshot_bytes()` — `exec-out screencap -p` straight to memory (no on-device temp file/pull); `take_screenshot()` uses it then falls back to legacy screencap+pull
- `find_image_in_bytes()` / `find_image_on_screen()` / `match_template_bytes()` — OpenCV template matching (shared `_match_template` core) at 0.8 default threshold; macro image steps use the in-memory bytes variants

Module-level helpers beyond the class:
- OCR — `find_tesseract()`, `ocr_text_tesseract()`, `ocr_find_button()`, `extract_guild_member_names()` (Tesseract, `tessdata/`)
- Vision heuristics — `find_yellow_frame()`, `find_highlighted_stage()`, `find_swipe_glow()`, `in_match_autoplay()` (used by the story runner)
- UI tree — `find_element_center()`, `list_ui_elements()` (parse `uiautomator dump` XML)
- Gemini vision fallback — `gemini_tap_suggestion()`, `gemini_find_stage()` (API key in `gemini_config.json`)
- Host sizing — `get_host_specs()`, `estimate_mumu_capacity()` (how many emulators this PC can handle)

### Macro engine — `macro_runner.py`

GUI-free run logic; **both apps execute macros through this and nothing else**. Communicates via callbacks: `log(text, kind)`, `progress(device, **state)`, `running_check() -> bool`.

- `MacroRunner.run_queue(devices, accounts)` — account queue fanned out across devices
- `MacroRunner.run_batch_once(devices, accounts)` — one batch (one account per device), used by the "pause between batches" mode
- `_run_steps()` — the core loop. Recurses into `if_image` branches, walks with an explicit index (not `for`) so `anchor_on_fail="retry"` can jump backwards. Returns `"completed" | "stopped" | "device_error" | "paused"`
- `_dispatch()` — per-step-type execution. `_check()` raises on ADB failure so a step that did not actually happen never silently continues
- `_run_block()` — "crash-proof block" retry (see Macro system below)
- `_save_failure_report()` — screenshot + JSON record into `error_reports/`
- `StoryRunner` — auto-play-the-story loop (yellow stage detection → clear → repeat), used both by the Story Auto button and by the `story_auto` step

`script_sets` (a `{name: steps}` dict) may be passed in; omit it and the runner reads `script_sets/*.json` itself. Tkinter passes its in-memory copy so the editor's state is the source of truth rather than "did it get saved to disk yet".

Note `anchor_poll` is clamped to 0.1–10 s in `__init__`. This is not cosmetic: a non-positive value turns `_wait_anchor` into a busy loop that hammers ADB with screenshots and freezes the whole machine.

### New app backend — `web_app.py`

One `Api` class (~200 methods) exposed to JS through pywebview; every `PY.foo()` call in `webui/*.js` is a method here. Grouped roughly as: device scan/connect, profile + step CRUD, flow (path-based) CRUD, run control (`run`/`stop`/`continue_batch`/`run_from`), pause/resume (`list_paused`/`resume_paused`), accounts, manual tools, diamond OCR + web push, guild grabber, error reports, presets, settings, window chrome.

`base_dir()` = user-data folder next to the .exe (macros, accounts, configs). `resource_dir()` = bundled assets (`webui/`, `_MEIPASS` when frozen). Keep them straight — mixing them breaks the frozen build.

### New app front-end — `webui/`

`index.html` (inline styles, five nav pages: หน้าแรก / บัญชี / สคริปต์ / อื่นๆ / ตั้งค่า) + three scripts:
- `app.js` — nav, state render, device list, accounts, list-view step editor, run controls
- `tools.js` — modals and tools (export/import, region pickers, keyboard setup, error reports)
- `flow.js` — the block-flow editor (`if_image` tree view, path-based editing, screen-picking)

Opened in a plain browser (no pywebview) it falls back to `DEMO` data so the design still renders.

**Script tags are cache-busted with `?v=…` in `index.html` — bump it every time you edit a JS file.** WebView2 otherwise serves stale JS and the change looks like it never happened.

### Legacy GUI — `gui.py` (~8,600 lines)

The entire Tkinter UI in one file: header bar → sidebar (device checkboxes) → right panel with tabs (Macro Editor, Account Management, Manual Sync, Settings, Log Console). `ModernButton`, `ModernEntry`, `make_panel()`, `make_checkbutton()` provide the dark theme without an external library; palette constants sit near the top.

Macro execution runs on a **worker thread** to keep the GUI responsive. `gui.py` owns the *orchestration* — run modes (sequential / batch-with-pause / continuous queue), stagger delay, resume checkpoints, per-device progress cards, the run summary — and hands each account to the shared engine:

- `execute_device_macro(device, account)` builds a `MacroRunner` via `_build_macro_runner()` and calls `runner._run_steps(...)`, then maps the returned status into the run-result dict the reporting system expects.
- `_runner_log_cb` maps the engine's `info/warn/err/ok` onto the log console's `info/warning/error/success` tags.
- `prog()` forwards `step_idx`/`step_desc` to `_device_run_state`, deliberately dropping `done_count`/`total_accounts` because the Tkinter queue counts those itself.
- `_highlight_running_step()` highlights the listbox row — only for main-line steps, since branch steps have no row of their own.

This app is the customers' fallback. Rebuild `MuMupow.spec` when you change it.

## Macro system

Macros ("profiles") are JSON files in `macros/`. Step types:

`tap`, `swipe`, `text`, `keyevent`, `sleep`, `start_app`, `stop_app`, `screenshot`, `detect_image`, `wait_for_image`, `tap_text`, `wait_for_text`, `clear_ads_loop`, `fetch_otp`, `read_diamond`, `find_yellow_stage`, `run_set`, `keyboard`, `if_image`, `story_auto`

Canonical field/default tables for the editor live in `Api.STEP_FIELDS` / `Api.STEP_DEFAULTS` / `Api._STEP_TH` / `Api._STEP_ICON` in `web_app.py`. **Adding a step type means touching all four**, plus `_step_type_options()` and a branch in `MacroRunner._dispatch` — nothing in `gui.py`. A type that reaches `_dispatch` without a branch is logged as unknown and silently skipped, which is why `tests/test_macro_handlers.py` asserts every offered type actually dispatches.

Steps with no `delay` key fall back to `DEFAULT_STEP_DELAYS[type]` (in `macro_runner.py`, re-exported by `gui.py`); an explicit `delay: 0` means zero. Every non-zero delay is jittered ×0.8–1.4.

### Branching — `if_image`

```json
{
  "type": "if_image",
  "desc": "ถ้ามีป๊อปอัพโฆษณา",
  "text": "ads_close.png",       // template file, OR…
  "anchor_img": "<base64 png>",  // …an image dragged out of the live screen
  "threshold": 0.8,
  "timeout": 2.0,
  "then": [ { "type": "tap", "x": "880", "y": "40" } ],
  "else": []
}
```

Evaluated **once** per arrival (screenshot → match → pick a branch); it does not loop itself. After the branch finishes, execution rejoins the main line. Nesting is capped at `MAX_BRANCH_DEPTH = 5` (defined identically in both engines). Flat legacy scripts must keep running unchanged — `if_image` is additive.

Blocks are addressed by **path**: `[2]` = third block of the main line, `[2, "then", 0]` = first block inside its "found" branch (`Api._locate`). At runtime paths are logged as dotted strings (`"2.then"`, `"3.set"`, `"3.home"`).

### Anchors (per-step wait-for-image guard)

Any step can carry `anchor_img` (base64), `anchor_region`, `anchor_timeout` (30 s), `anchor_threshold` (0.8), `anchor_on_fail`, and `anchor_tap`. Before executing, `_wait_anchor` polls the screen for the anchor image every `anchor_poll` seconds. On miss, `anchor_on_fail` decides:

- `pause` (**the default**) — stop this device and wait for a human. First it steps back one index once as a self-heal (in case the previous tap didn't land), then `_pause_checkpoint` ships the screenshot and account to the UI's "จอที่รอแก้ไข" panel without touching the device further. Returns `"paused"`.
- `retry` — jump the index back to `anchor_retry_target`, up to `anchor_retry_limit` (default 3) rounds; exhausted or unset target ⇒ failure report + `"device_error"`.
- `skip` — log and move to the next step.
- `tap` — tap the stored coordinate anyway (flagged as risky).
- anything else (including the old `abort`) — failure report + `"device_error"`.

Inside a crash-proof block (`block_mode`), a missed anchor short-circuits all of this and returns `"device_error"` so the block's own retry takes over.

`anchor_tap` is separate: with it set, the tap coordinate is translated by however far the anchor moved from `anchor_region`.

### Crash-proof blocks

A `run_set` step marked `block_on_fail: "home_retry"` is *not* flattened. If the set fails, the runner plays the `block_home` set ("go back to the home screen") and re-runs the whole set, up to `block_retries` (default 3) extra rounds — `_run_block`. Ordinary `run_set` steps are inlined at load time by `_expand_sets`, recursing into `then`/`else`.

### Text input and placeholders

`{EMAIL}`, `{PASSWORD}`, `{NAME}` in `text` steps are substituted from the current account (`substitute_account`). ASCII goes through `input text`; Thai/Unicode routes through `input_text_unicode` (base64 broadcast to ADBKeyboard), which needs the ADBKeyboard IME installed — set it up per emulator from Settings (`setup_adb_keyboard` / `restore_keyboard`) with `ADBKeyboard.apk` next to the app.

### Text vs. image targeting

`tap_text` / `wait_for_text` locate elements via `uiautomator dump` (`find_element_center`) — reliable on native Android screens (login, registration, email) but blind to game canvases (Unity/Cocos), where image steps are still required. The `inspect_ui` tool dumps the current screen's elements so you can tell which approach a screen needs. A query starting with `id:` matches `resource-id`; otherwise it matches visible text / content-desc.

### Script sets — `script_sets.py`

Reusable step sequences in `script_sets/*.json`, referenced by `run_set`. `expand_steps_with_sets()` inlines them with cycle detection. It only walks a flat list — branch-aware expansion lives in `MacroRunner._expand_sets`.

## Account management

`accounts.json` is a flat array. Fields: `email`, `password`, `checked`, `group`, `ingamename`, `refresh_token`, `client_id` (plus `save_web_game_title`/`title` from web imports). After a run the report system writes `last_status`, `last_error`, `last_device`, `last_run` onto each account that ran (`Api._persist_run_results`; `finalize_run_results`/`show_run_summary` in `gui.py`).

`_get_effective_status()` (duplicated in both files) treats a status as stale once the 05:00 daily farming boundary has passed, so yesterday's results don't count as done today.

`account_display_name()` exists in `gui.py`, `macro_runner.py`, and `web_app.py` and **must resolve identically**: `save_web_game_title` → `title` → `ingamename` → `name` → `email`. (Still three copies — a good next consolidation.)

`save_web_game_import.py` parses Save Web Game exports and merges into `accounts.json`. OTP comes from the `read-mail.me` web API (OAuth2 refresh token + client id) with IMAP `outlook.office365.com` as fallback.

## Diamond OCR and reporting

`read_diamond` steps OCR the diamond counter from the region in `diamond_ocr.json`, collect rows on the runner, and at end of run write `diamond_export.json` and optionally push to the configured `web_base_url` (`_auto_push_diamonds`, `match_web_accounts`, `push_diamonds_web`).

Failures write `error_reports/report.jsonl` (one JSON object per line: time, device, email, profile, step path/type/desc, reason, image path) plus a screenshot under `error_reports/YYYYMMDD/`. The UI lists these via `list_error_reports` / `error_image_b64`.

## Key Files

| File | Purpose |
|------|---------|
| `web_app.py` | New app: pywebview host + the whole `Api` surface |
| `webui/` | New app front-end (`index.html`, `app.js`, `tools.js`, `flow.js`) |
| `macro_runner.py` | **The** macro engine (`MacroRunner`, `StoryRunner`) — both apps run through it |
| `mumu_controller.py` | ADB wrapper, parallel device control, vision/OCR helpers |
| `gui.py` | Legacy Tkinter UI + run orchestration (modes, checkpoints, reporting) |
| `tests/conftest.py` | One shared Tk root for the whole session (see Ground rules #7) |
| `script_sets.py` | Reusable script set loading/expansion + cycle detection |
| `quick_builder.py` | Macro step factory functions |
| `save_web_game_import.py` | Account import from Save Web Game exports |
| `plan.md` | Flow-editor roadmap; phase status and ground rules |
| `presets.json` | Named coordinate presets (Thai labels) |
| `accounts.json` | Account database |
| `diamond_ocr.json` | Diamond OCR region + export/push settings |
| `game_reset.json` | Game reset package, boot wait, and re-login steps |
| `MuMupow_web.spec` / `MuMupow.spec` | PyInstaller configs (new / legacy) |

## Data Formats

**Macro file** (`macros/*.json`):
```json
{
  "name": "My Macro",
  "steps": [
    {"type": "tap", "x": "450", "y": "211", "delay": 0.5, "desc": "..."},
    {"type": "text", "text": "{EMAIL}", "desc": "..."},
    {"type": "if_image", "text": "popup.png", "timeout": 2.0,
     "then": [{"type": "tap", "x": "880", "y": "40"}], "else": []},
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

## Ground rules

These come from `plan.md` and are non-negotiable:

1. **Old flat scripts must keep running exactly as before.** `if_image` and blocks are additive.
2. **Values stored in files stay English** (`abort`/`skip`/`tap`, `then`/`else`, type names). Only the visible labels are translated to Thai.
3. **Do not break `MuMupow.exe` (Tkinter)** — it is the customers' fallback.
4. **Never point a write-path test at the real `accounts.json`.** Copy to a temp file and monkey-patch `Api._accounts_path`.
5. **Every change ends with** `python -m pytest tests/ -q` passing, then a rebuild of the spec you touched.
6. **Bump `?v=` on the `<script>` tags in `index.html`** whenever you edit `webui/*.js`.
7. **Never call `tk.Tk()`/`MuMuGUI()` in a test** — use the session-scoped `gui_app` fixture. Creating and destroying multiple roots exhausts Tcl on Windows and makes unrelated tests fail at random.
8. **One macro engine.** New step behavior goes in `macro_runner.py`; `gui.py` orchestrates, it does not execute steps.

## Notes

- UI labels are Thai; code identifiers and comments are English (comments in the newer files are Thai — match whatever file you are in).
- Windows only (ADB path defaults, `.exe` output, `win32` keyboard injection in `send_keyboard_input`).
- `build/` and `dist/` are PyInstaller output — do not hand-edit. `dist/` currently also holds real runtime data (accounts, error reports) that is tracked in git.
- `templates/` holds user-supplied PNGs for OpenCV template matching; `tessdata/` holds Tesseract language data.
- `scratch/` is a scratch pad for throwaway dev scripts (gitignored).
- `gemini_config.json` and `accounts.json` contain live secrets and are currently tracked in git — do not add more, and prefer the `*.example.json` files when documenting.
