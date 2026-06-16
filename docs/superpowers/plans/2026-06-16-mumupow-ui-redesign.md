# MuMupow UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework MuMupow's Tkinter UI into the approved dark Operational Console layout while preserving existing behavior.

**Architecture:** Keep the existing Tkinter application and central `gui.py` structure, but add reusable styling/layout helpers before changing individual tabs. Preserve existing widget attributes and method names where runtime code depends on them, especially `self.step_listbox`, account fields, run buttons, and selection state.

**Tech Stack:** Python 3, Tkinter/ttk, existing `unittest` tests, existing `pytest` test runner.

---

## File Structure

- Modify: `gui.py`
  - Theme constants, button/input helpers, panel/toolbar helpers.
  - Main app chrome, sidebar, macro tab, accounts tab, manual sync tab, settings tab.
  - Keep behavior methods and data storage unchanged.
- Modify: `tests/test_gui_helpers.py`
  - Add pure helper tests for button variants, macro step summaries, and account display summaries.
- Do not modify packaged binaries or PyInstaller build artifacts during UI implementation.
- Do not stage existing unrelated dirty files unless they are intentionally changed by the UI implementation.

## Task 1: Theme Foundation And Pure Formatting Helpers

**Files:**
- Modify: `gui.py:24-90`
- Modify: `tests/test_gui_helpers.py`

- [ ] **Step 1: Add failing tests for button palette and macro row formatting**

Replace `tests/test_gui_helpers.py` with this complete test file:

```python
import unittest

from gui import (
    BUTTON_VARIANTS,
    build_account_summary,
    build_macro_step_summary,
    build_status_summary,
    get_button_colors,
)


class GuiHelperTests(unittest.TestCase):
    def test_status_summary_counts_selected_items_and_profile(self):
        summary = build_status_summary(
            total_devices=3,
            selected_devices=2,
            total_accounts=8,
            selected_accounts=5,
            macro_steps=12,
            profile_name="Default Login",
            is_running=False,
        )

        self.assertIn("Emulator: 2/3", summary)
        self.assertIn("Accounts: 5/8", summary)
        self.assertIn("Steps: 12", summary)
        self.assertIn("Profile: Default Login", summary)
        self.assertIn("Ready", summary)

    def test_status_summary_reports_running_state(self):
        summary = build_status_summary(
            total_devices=1,
            selected_devices=1,
            total_accounts=0,
            selected_accounts=0,
            macro_steps=4,
            profile_name="",
            is_running=True,
        )

        self.assertIn("Running", summary)
        self.assertIn("Profile: Custom", summary)

    def test_button_variants_define_operational_console_hierarchy(self):
        self.assertIn("neutral", BUTTON_VARIANTS)
        self.assertEqual(get_button_colors("primary")["bg"], "#0F766E")
        self.assertEqual(get_button_colors("danger")["bg"], "#7F1D1D")
        self.assertEqual(get_button_colors("unknown"), get_button_colors("neutral"))

    def test_macro_step_summary_formats_tap_as_columns(self):
        summary = build_macro_step_summary(
            3,
            {"type": "tap", "x": 450, "y": 320, "delay": 0.5, "desc": "click email"},
        )

        self.assertIn("04", summary)
        self.assertIn("Tap", summary)
        self.assertIn("450, 320", summary)
        self.assertIn("0.5s", summary)
        self.assertIn("click email", summary)

    def test_macro_step_summary_formats_token_text(self):
        summary = build_macro_step_summary(
            1,
            {"type": "text", "text": "{EMAIL}", "delay": 0.5, "desc": "email"},
        )

        self.assertIn("02", summary)
        self.assertIn("Text", summary)
        self.assertIn("{EMAIL}", summary)
        self.assertIn("0.5s", summary)

    def test_account_summary_keeps_group_and_otp_signal(self):
        summary = build_account_summary(
            {"email": "player@example.com", "name": "Main", "group": "A", "refresh_token": "token"}
        )

        self.assertIn("Main", summary)
        self.assertIn("player@example.com", summary)
        self.assertIn("A", summary)
        self.assertIn("OTP", summary)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest tests/test_gui_helpers.py -q
```

Expected: tests fail because `BUTTON_VARIANTS`, `get_button_colors`, `build_macro_step_summary`, and `build_account_summary` are not defined yet.

- [ ] **Step 3: Add theme constants and helper functions**

In `gui.py`, replace the existing color constants and `ModernButton` implementation near the top with this code. Keep the existing imports as-is.

```python
# Operational Console dark theme
BG_DARK = "#080D16"
BG_PANEL = "#0C1422"
BG_CARD = "#0D1523"
BG_SURFACE = "#121D2E"
BG_INPUT = "#0A111D"
BG_HOVER = "#18243A"
FG_WHITE = "#E6EDF7"
FG_MUTED = "#8DA0B8"
FG_DIM = "#64748B"
LINE_SOFT = "#223046"
ACCENT_BLUE = "#38BDF8"
ACCENT_HOVER = "#0EA5E9"
ACCENT_GREEN = "#0F766E"
ACCENT_RED = "#7F1D1D"
ACCENT_ORANGE = "#A16207"

BUTTON_VARIANTS = {
    "neutral": {"bg": "#18243A", "hover": "#24344B", "fg": FG_WHITE},
    "primary": {"bg": ACCENT_GREEN, "hover": "#115E59", "fg": FG_WHITE},
    "accent": {"bg": "#0F2F4A", "hover": "#164E72", "fg": FG_WHITE},
    "danger": {"bg": ACCENT_RED, "hover": "#991B1B", "fg": FG_WHITE},
    "warning": {"bg": ACCENT_ORANGE, "hover": "#854D0E", "fg": FG_WHITE},
    "subtle": {"bg": BG_SURFACE, "hover": BG_HOVER, "fg": FG_WHITE},
}


def get_button_colors(variant="neutral"):
    return BUTTON_VARIANTS.get(variant, BUTTON_VARIANTS["neutral"])


def build_macro_step_summary(idx, step):
    step_type = (step.get("type") or "").lower()
    label_map = {
        "tap": "Tap",
        "text": "Text",
        "keyevent": "Key",
        "swipe": "Swipe",
        "sleep": "Sleep",
        "start_app": "Start App",
        "stop_app": "Stop App",
        "clear_app": "Clear App",
        "detect_image": "Image Match",
        "clear_ads_loop": "Ads Loop",
        "fetch_otp": "Auto OTP",
        "run_set": "Run Set",
        "screenshot": "Screenshot",
        "keyboard": "Keyboard",
    }
    label = label_map.get(step_type, step_type.title() or "Step")

    if step_type == "tap":
        detail = f"{step.get('x', '')}, {step.get('y', '')}"
    elif step_type == "swipe":
        detail = f"{step.get('x', '')},{step.get('y', '')} -> {step.get('x2', '')},{step.get('y2', '')}"
    elif step_type == "keyevent":
        detail = str(step.get("code") or step.get("text") or "")
    elif step_type == "sleep":
        detail = f"wait {step.get('duration', step.get('delay', ''))}"
    else:
        detail = str(step.get("text") or step.get("set_name") or "")

    delay = step.get("delay")
    if delay is None:
        delay_text = ""
    else:
        delay_text = f"{delay:g}s" if isinstance(delay, (int, float)) else f"{delay}s"

    desc = step.get("desc") or ""
    return f"{idx + 1:02d}  {label:<12}  {detail:<28}  {delay_text:<6}  {desc}"


def build_account_summary(account):
    name = account.get("name") or "-"
    email = account.get("email") or "-"
    group = account.get("group") or "ทั่วไป"
    otp = "OTP" if account.get("refresh_token") and account.get("client_id", "") is not None else ""
    return f"{name:<16}  {email:<32}  {group:<12}  {otp}"


class ModernButton(tk.Button):
    def __init__(
        self,
        parent,
        text,
        command=None,
        bg=None,
        fg=None,
        activebg=None,
        variant="neutral",
        **kwargs,
    ):
        colors = get_button_colors(variant)
        bg = bg or colors["bg"]
        fg = fg or colors["fg"]
        activebg = activebg or colors["hover"]
        button_font = kwargs.pop("font", ("Segoe UI", 10, "bold"))
        px = kwargs.pop("padx", 12)
        py = kwargs.pop("pady", 7)
        super().__init__(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=activebg,
            activeforeground=fg,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=button_font,
            padx=px,
            pady=py,
            **kwargs,
        )
        self._normal_bg = bg
        self._hover_bg = activebg
        self.bind("<Enter>", lambda e: self.configure(bg=self._hover_bg))
        self.bind("<Leave>", lambda e: self.configure(bg=self._normal_bg))
```

- [ ] **Step 4: Update `ModernEntry` styling**

Replace `ModernEntry.__init__` with:

```python
class ModernEntry(tk.Entry):
    def __init__(self, parent, **kwargs):
        super().__init__(
            parent,
            bg=BG_INPUT,
            fg=FG_WHITE,
            insertbackground=FG_WHITE,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground="#2B3C55",
            highlightcolor=ACCENT_BLUE,
            font=("Segoe UI", 10),
            **kwargs,
        )
```

- [ ] **Step 5: Run helper tests and verify they pass**

Run:

```bash
pytest tests/test_gui_helpers.py -q
```

Expected: all tests in `tests/test_gui_helpers.py` pass.

- [ ] **Step 6: Commit Task 1**

Run:

```bash
git add gui.py tests/test_gui_helpers.py
git commit -m "feat: add operational console UI helpers"
```

Before committing, run `git diff --cached --name-only` and confirm it lists only `gui.py` and `tests/test_gui_helpers.py`.

## Task 2: Shared Layout Helpers And App Chrome

**Files:**
- Modify: `gui.py:90-390`

- [ ] **Step 1: Add panel, toolbar, and checkbox helper methods**

Inside `class MuMuGUI`, after `__init__` and before `load_icon`, add these methods:

```python
    def make_panel(self, parent, title=None, fill="both", expand=False, padx=0, pady=0):
        panel = tk.Frame(parent, bg=BG_CARD, highlightthickness=1, highlightbackground=LINE_SOFT)
        panel.pack(fill=fill, expand=expand, padx=padx, pady=pady)
        if title:
            header = tk.Frame(panel, bg=BG_PANEL, height=38)
            header.pack(fill="x")
            header.pack_propagate(False)
            tk.Label(
                header,
                text=title,
                bg=BG_PANEL,
                fg=FG_WHITE,
                font=("Segoe UI", 10, "bold"),
            ).pack(side="left", padx=12)
            body = tk.Frame(panel, bg=BG_CARD, padx=12, pady=12)
            body.pack(fill="both", expand=True)
            return panel, body
        return panel, panel

    def make_toolbar(self, parent):
        toolbar = tk.Frame(parent, bg=BG_CARD)
        toolbar.pack(fill="x", pady=(0, 10))
        return toolbar

    def make_checkbutton(self, parent, text, variable, **kwargs):
        return tk.Checkbutton(
            parent,
            text=text,
            variable=variable,
            bg=kwargs.pop("bg", BG_CARD),
            fg=kwargs.pop("fg", FG_WHITE),
            activebackground=kwargs.pop("activebackground", BG_CARD),
            activeforeground=kwargs.pop("activeforeground", FG_WHITE),
            selectcolor=kwargs.pop("selectcolor", BG_INPUT),
            relief="flat",
            font=kwargs.pop("font", ("Segoe UI", 10)),
            **kwargs,
        )
```

- [ ] **Step 2: Update root sizing and ttk styles**

In `__init__`, keep `self.geometry("1280x760")` but change `self.minsize(1100, 700)` to:

```python
        self.minsize(1180, 720)
```

In `configure_styles`, set notebook and scrollbar colors to the new palette:

```python
        style.configure("TNotebook", background=BG_DARK, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=BG_PANEL,
            foreground=FG_MUTED,
            padding=[14, 8],
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", BG_CARD)],
            foreground=[("selected", FG_WHITE)],
        )
        style.configure(
            "TScrollbar",
            gripcount=0,
            background=BG_PANEL,
            troughcolor=BG_DARK,
            borderwidth=0,
            arrowcolor=FG_MUTED,
        )
```

- [ ] **Step 3: Update header and status bar**

In `build_ui`, replace the header/status frame color usage with:

```python
        header = tk.Frame(self, bg=BG_PANEL, height=58)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        title_lbl = tk.Label(
            header,
            text="MuMupow",
            bg=BG_PANEL,
            fg=FG_WHITE,
            font=("Segoe UI", 16, "bold"),
        )
        title_lbl.pack(side="left", padx=(20, 12), pady=14)

        subtitle_lbl = tk.Label(
            header,
            text="Operational console for multi-emulator automation",
            bg=BG_PANEL,
            fg=FG_MUTED,
            font=("Segoe UI", 10),
        )
        subtitle_lbl.pack(side="left", pady=18)

        content_frame = tk.Frame(self, bg=BG_DARK)
        content_frame.pack(fill="both", expand=True, padx=12, pady=12)

        status_frame = tk.Frame(self, bg=BG_PANEL, height=34)
        status_frame.pack(fill="x", side="top")
        status_frame.pack_propagate(False)
```

Keep the existing `self.status_summary_lbl` and `self.status_hint_lbl` creation, but change their backgrounds to `BG_PANEL` and muted foreground to `FG_MUTED`.

- [ ] **Step 4: Restyle emulator sidebar**

In `build_sidebar_and_tabs`, change sidebar width to 260 and use neutral/accent variants:

```python
        sidebar = tk.Frame(parent, bg=BG_PANEL, width=260)
        sidebar.pack(fill="y", side="left", padx=(0, 12))
        sidebar.pack_propagate(False)
```

Update scan/connect buttons in the same method:

```python
        scan_btn = ModernButton(btn_frame, text="สแกนพอร์ต", command=self.scan_devices, variant="accent")
        connect_btn = ModernButton(conn_frame, text="เชื่อมต่อ", command=self.manual_connect, variant="primary")
```

Keep existing behavior and variable names.

- [ ] **Step 5: Run launch smoke test**

Run:

```bash
python -m py_compile gui.py
```

Expected: command exits with code 0.

- [ ] **Step 6: Commit Task 2**

Run:

```bash
git add gui.py
git commit -m "feat: refresh app chrome and shared layout helpers"
```

## Task 3: Macro Tab Operational Console Layout

**Files:**
- Modify: `gui.py:394-660`
- Modify: `gui.py:2708-2777`

- [ ] **Step 1: Update macro page container sizes**

In `build_macro_tab`, set the main pane and columns to:

```python
        main_pane = tk.Frame(parent, bg=BG_DARK)
        main_pane.pack(fill="both", expand=True, padx=0, pady=0)

        left_panel = tk.Frame(main_pane, bg=BG_CARD, width=360, highlightthickness=1, highlightbackground=LINE_SOFT)
        left_panel.pack(side="left", fill="both", expand=True, padx=(0, 12))

        right_panel = tk.Frame(main_pane, bg=BG_CARD, width=340, highlightthickness=1, highlightbackground=LINE_SOFT)
        right_panel.pack(side="right", fill="both")
        right_panel.pack_propagate(False)
```

This makes the step list the main center work surface and the editor the right column.

- [ ] **Step 2: Replace profile action grid with a toolbar**

Replace the `profile_actions_frame` button grid and `quick_builder_frame` with:

```python
        profile_actions_frame = self.make_toolbar(left_panel)
        ModernButton(profile_actions_frame, text="บันทึก", command=self.save_profile, variant="primary").pack(side="left", padx=(0, 6))
        ModernButton(profile_actions_frame, text="ลบ", command=self.delete_profile, variant="danger").pack(side="left", padx=(0, 6))
        ModernButton(profile_actions_frame, text="Export", command=self.export_profile_package, variant="neutral").pack(side="left", padx=(0, 6))
        ModernButton(profile_actions_frame, text="Import", command=self.import_profile_package, variant="neutral").pack(side="left", padx=(0, 6))

        quick_builder_frame = self.make_toolbar(left_panel)
        ModernButton(quick_builder_frame, text="สร้างสคริปต์เร็ว", command=self.open_quick_builder_dialog, variant="warning").pack(side="left", fill="x", expand=True, padx=(0, 6))
        ModernButton(quick_builder_frame, text="จัดการ Sets", command=self.open_script_sets_dialog, variant="accent").pack(side="left", fill="x", expand=True)
```

- [ ] **Step 3: Restyle macro listbox as structured rows**

Change `self.step_listbox` creation to:

```python
        self.step_listbox = tk.Listbox(
            list_frame,
            bg=BG_INPUT,
            fg=FG_WHITE,
            selectbackground="#102F48",
            selectforeground=FG_WHITE,
            bd=0,
            highlightthickness=1,
            highlightbackground=LINE_SOFT,
            font=("Consolas", 10),
            activestyle="none",
            exportselection=False,
        )
```

Keep the existing bindings and scrollbar.

- [ ] **Step 4: Update reorder/delete button variants**

Replace reorder buttons with:

```python
        ModernButton(reorder_frame, text="▲ ขึ้น", command=lambda: self.move_step(-1), variant="subtle").pack(side="left", fill="x", expand=True, padx=(0, 6))
        ModernButton(reorder_frame, text="▼ ลง", command=lambda: self.move_step(1), variant="subtle").pack(side="left", fill="x", expand=True, padx=(0, 6))
        ModernButton(reorder_frame, text="ลบขั้นตอน", command=self.delete_step, variant="danger").pack(side="right")
```

- [ ] **Step 5: Move run controls into bottom run bar style**

Keep the current `run_card` parent at the bottom of `right_panel`, but restyle the controls:

```python
        run_card = tk.Frame(right_panel, bg=BG_PANEL, highlightthickness=1, highlightbackground=LINE_SOFT, padx=12, pady=12)
        run_card.pack(side="bottom", fill="x", padx=0, pady=(12, 0))
```

Use `self.make_checkbutton` for `self.stagger_chk` and `self.pause_chk`, and set:

```python
        self.run_macro_btn = ModernButton(
            run_card,
            text="รันมาโคร",
            command=self.start_macro_flow,
            variant="primary",
            font=("Segoe UI", 11, "bold"),
            height=2,
        )
        self.stop_macro_btn = ModernButton(
            run_card,
            text="หยุดทันที",
            command=self.stop_macro_flow,
            variant="danger",
            font=("Segoe UI", 11, "bold"),
            height=2,
        )
```

- [ ] **Step 6: Update form action button hierarchy**

In the form button section, use these variants:

```python
        ModernButton(primary_step_row, text="เพิ่มขั้นตอน", command=self.add_step, variant="accent").pack(side="left", fill="x", expand=True, padx=(0, 6))
        ModernButton(primary_step_row, text="อัปเดต", command=self.update_step, variant="warning").pack(side="left", fill="x", expand=True)
        ModernButton(secondary_step_row, text="บันทึกพิกัดด้วยภาพ", command=self.open_visual_recorder, variant="primary").pack(fill="x", pady=(6, 4))
        ModernButton(secondary_step_row, text="ล้างฟอร์ม", command=self.clear_form, variant="subtle").pack(fill="x", pady=2)
```

- [ ] **Step 7: Use `build_macro_step_summary` in `refresh_step_list`**

Replace the body of `refresh_step_list` with:

```python
    def refresh_step_list(self):
        self.step_listbox.delete(0, tk.END)
        for idx, step in enumerate(self.macro_steps):
            self.step_listbox.insert(tk.END, build_macro_step_summary(idx, step))
        self.update_status_summary()
```

- [ ] **Step 8: Run tests and smoke compile**

Run:

```bash
pytest tests/test_gui_helpers.py -q
python -m py_compile gui.py
```

Expected: tests pass and compile exits with code 0.

- [ ] **Step 9: Commit Task 3**

Run:

```bash
git add gui.py tests/test_gui_helpers.py
git commit -m "feat: redesign macro console layout"
```

## Task 4: Accounts Tab Operational Layout

**Files:**
- Modify: `gui.py:669-805`
- Modify: `gui.py:1870-2075`

- [ ] **Step 1: Restyle accounts tab columns**

In `build_accounts_tab`, replace `left_panel = tk.LabelFrame(...)` with:

```python
        left_panel = tk.Frame(main_pane, bg=BG_CARD, highlightthickness=1, highlightbackground=LINE_SOFT)
        left_panel.pack(side="left", fill="both", expand=True, padx=(0, 12))
```

Add a header inside it:

```python
        left_header = tk.Frame(left_panel, bg=BG_PANEL, height=40)
        left_header.pack(fill="x")
        left_header.pack_propagate(False)
        tk.Label(left_header, text="บัญชีทั้งหมด", bg=BG_PANEL, fg=FG_WHITE, font=("Segoe UI", 10, "bold")).pack(side="left", padx=12)
```

- [ ] **Step 2: Restyle search and batch toolbar**

Use a single toolbar:

```python
        control_panel = tk.Frame(left_panel, bg=BG_CARD, padx=12, pady=12)
        control_panel.pack(fill="x")

        search_frame = tk.Frame(control_panel, bg=BG_CARD)
        search_frame.pack(fill="x", pady=(0, 8))
        tk.Label(search_frame, text="ค้นหา", bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 8))
```

Set batch button variants:

```python
        ModernButton(batch_frame, text="ลบที่เลือก", command=self.delete_selected_accounts, variant="danger", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 6))
        ModernButton(batch_frame, text="ย้ายกลุ่ม", command=self.move_selected_accounts, variant="accent", font=("Segoe UI", 9, "bold")).pack(side="left", padx=6)
```

- [ ] **Step 3: Restyle right account form**

Replace `add_box = tk.LabelFrame(...)` with:

```python
        add_box_outer, add_box = self.make_panel(right_scroll_frame, "เพิ่ม / แก้ไขบัญชี", fill="x", pady=(0, 12))
```

Keep all existing `self.new_acc_*` fields and grid rows inside `add_box`.

Set:

```python
        self.save_acc_btn = ModernButton(add_box, text="เพิ่มบัญชีเข้าคิว", command=self.add_account, variant="primary")
        self.batch_import_btn = ModernButton(add_box, text="นำเข้าบัญชีแบบกลุ่ม", command=self.open_batch_import_dialog, variant="accent")
```

- [ ] **Step 4: Compact the help block**

Replace the long `info_text` content with:

```python
        info_text = (
            "ใช้ {EMAIL}, {PASSWORD}, {NAME}, {GROUP} ในมาโครเพื่อแทนค่าจากบัญชีที่เลือก "
            "ระบบจะหยิบบัญชีตามคิวและกระจายลง Emulator ที่เลือกไว้"
        )
```

Set wrap length to `300` and keep muted styling.

- [ ] **Step 5: Use `build_account_summary` in account rows**

Inside `refresh_accounts_ui`, where each account row currently creates labels for email/name/password/OTP, keep the checkbox and edit/delete buttons but add a single summary label:

```python
                summary_lbl = tk.Label(
                    frame,
                    text=build_account_summary(acc),
                    bg=BG_SURFACE,
                    fg=FG_WHITE,
                    font=("Consolas", 9),
                    anchor="w",
                )
                summary_lbl.pack(side="left", fill="x", expand=True, padx=8)
```

Use `BG_SURFACE` for row frame backgrounds and `LINE_SOFT` for highlight borders.

- [ ] **Step 6: Run tests and compile**

Run:

```bash
pytest tests/test_gui_helpers.py -q
python -m py_compile gui.py
```

Expected: tests pass and compile exits with code 0.

- [ ] **Step 7: Commit Task 4**

Run:

```bash
git add gui.py tests/test_gui_helpers.py
git commit -m "feat: redesign account management layout"
```

## Task 5: Manual Sync And Settings Visual Pass

**Files:**
- Modify: `gui.py:807-1010`

- [ ] **Step 1: Restyle manual sync panels**

In `build_sync_tab`, replace each `tk.LabelFrame` command group with `self.make_panel`:

```python
        tap_outer, tap_box = self.make_panel(control_grid, "คลิกพิกัด", fill="both", expand=True)
        tap_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=8)
```

Use the same pattern for:

```python
        txt_outer, txt_box = self.make_panel(control_grid, "พิมพ์ข้อความ", fill="both", expand=True)
        key_outer, key_box = self.make_panel(control_grid, "ปุ่มระบบ", fill="both", expand=True)
        screenshot_outer, screenshot_box = self.make_panel(control_grid, "ถ่ายภาพหน้าจอ", fill="x")
```

Keep all existing fields and commands.

- [ ] **Step 2: Update manual sync button variants**

Use these variants:

```python
        ModernButton(tap_box, text="ส่งคลิก", command=self.send_manual_click, variant="accent")
        ModernButton(txt_box, text="ส่งข้อความ", command=self.send_manual_text, variant="accent")
        ModernButton(key_box, text="BACK", command=lambda: self.send_manual_key(4), variant="subtle")
        ModernButton(key_box, text="HOME", command=lambda: self.send_manual_key(3), variant="subtle")
        ModernButton(key_box, text="MENU", command=lambda: self.send_manual_key(82), variant="subtle")
        ModernButton(screenshot_input_frame, text="ถ่ายทุกเครื่อง", command=self.send_manual_screenshot, variant="primary")
        ModernButton(cmd_input_frame, text="รันทันที", command=self.send_custom_cmd, variant="warning")
```

- [ ] **Step 3: Restyle settings panels**

In `build_settings_tab`, replace each `tk.LabelFrame` settings section with `self.make_panel` while keeping all existing controls:

```python
        path_outer, path_box = self.make_panel(settings_frame, "เส้นทางไฟล์ที่จำเป็น", fill="x", pady=(0, 12))
        port_outer, port_box = self.make_panel(settings_frame, "พอร์ต Emulator", fill="x", pady=(0, 12))
        diag_outer, diag_box = self.make_panel(settings_frame, "ตรวจสอบขนาดหน้าจอ Emulator", fill="x", pady=(0, 12))
        helper_outer, helper_box = self.make_panel(settings_frame, "ตัวช่วยหาพิกัดหน้าจอ", fill="x", pady=(0, 12))
```

Change settings action buttons to variants:

```python
        ModernButton(adb_path_frame, text="บันทึกและโหลดใหม่", command=self.save_adb_path, variant="primary")
        ModernButton(port_btn_frame, text="นำเข้าพอร์ตจาก JSON", command=self.open_port_config_dialog, variant="accent")
        ModernButton(port_btn_frame, text="คัดลอกพร้อมต์ถาม AI", command=copy_ai_prompt, variant="warning")
        ModernButton(port_btn_frame, text="แสดงพอร์ตปัจจุบัน", command=show_current_ports, variant="subtle")
        ModernButton(diag_box, text="ตรวจสอบความละเอียดและ DPI", command=self.validate_resolutions, variant="primary")
```

- [ ] **Step 4: Run tests and compile**

Run:

```bash
pytest tests/test_gui_helpers.py -q
python -m py_compile gui.py
```

Expected: tests pass and compile exits with code 0.

- [ ] **Step 5: Commit Task 5**

Run:

```bash
git add gui.py
git commit -m "feat: align manual and settings UI with console theme"
```

## Task 6: Runtime Verification And Visual Cleanup

**Files:**
- Modify: `gui.py` only if verification finds text overflow or broken layout.

- [ ] **Step 1: Run full tests**

Run:

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Run compile check**

Run:

```bash
python -m py_compile gui.py main.py mumu_controller.py quick_builder.py script_sets.py
```

Expected: command exits with code 0.

- [ ] **Step 3: Launch the app for visual inspection**

Run:

```bash
python main.py
```

Expected:

- App launches without traceback.
- Header, sidebar, tabs, macro page, account page, manual page, and settings page render.
- Run and Stop buttons are visible on the macro page without scrolling.
- Macro rows are readable and selected row is visible.
- Account rows show email/name/group/OTP status.
- Buttons do not overflow their containers.

- [ ] **Step 4: Fix any visual overflow found during launch**

If a button label overflows, shorten the visible label rather than increasing the whole app size. Use these replacements:

```python
"บันทึกพิกัดด้วยภาพ (Visual Recorder)" -> "บันทึกพิกัดด้วยภาพ"
"นำเข้าบัญชีแบบกลุ่ม (Batch)" -> "นำเข้าบัญชีแบบกลุ่ม"
"ตรวจสอบความละเอียดและค่า DPI ของ Emulator ที่เลือก" -> "ตรวจสอบความละเอียดและ DPI"
```

Then rerun:

```bash
python -m py_compile gui.py
```

Expected: command exits with code 0.

- [ ] **Step 5: Commit verification fixes if any**

If Step 4 changed files, run:

```bash
git add gui.py
git commit -m "fix: polish console layout overflow"
```

If Step 4 made no changes, do not create an empty commit.

## Self-Review

Spec coverage:

- Operational Console layout is covered by Tasks 2 and 3.
- Dark minimal visual system is covered by Task 1 and reused in Tasks 2-5.
- Macro tab structured rows and persistent run controls are covered by Task 3.
- Accounts tab reuse and compact help are covered by Task 4.
- Manual Sync command groups are covered by Task 5.
- Settings utility sections are covered by Task 5.
- Behavior preservation is addressed by preserving existing widget attributes and command callbacks in every task.
- Verification requirements are covered by Task 6.

Placeholder scan:

- This plan contains no `TBD`, `TODO`, or open-ended placeholder implementation steps.
- Each code-changing task includes exact snippets or concrete replacement text.

Type and name consistency:

- Helper names introduced in Task 1 are reused as `BUTTON_VARIANTS`, `get_button_colors`, `build_macro_step_summary`, and `build_account_summary`.
- Existing runtime names such as `self.step_listbox`, `self.run_macro_btn`, `self.stop_macro_btn`, and account entry fields are preserved.
