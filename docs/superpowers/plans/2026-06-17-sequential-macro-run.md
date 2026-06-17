# Sequential Macro Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a user-selectable mode that runs macro work one account/device pair at a time, finishing one run before starting the next.

**Architecture:** Keep the existing parallel runner intact and add a small scheduling helper plus a sequential branch in `run_macro_task`. The helper is pure and testable; the runner branch reuses `execute_device_macro` so account substitution, OTP, screenshots, stop checks, and step behavior stay unchanged.

**Tech Stack:** Python, Tkinter, unittest/pytest, existing `MuMuGUI` macro runner.

---

## File Structure

- Modify `gui.py`: add `build_sequential_macro_pairs`, add a `BooleanVar` and checkbox in the Macro run card, and add sequential execution branches in `run_macro_task`.
- Modify `tests/test_gui_helpers.py`: cover sequential pair scheduling as a pure helper.
- No new runtime files are needed.

---

### Task 1: Add Sequential Scheduling Helper

**Files:**
- Modify: `gui.py`
- Test: `tests/test_gui_helpers.py`

- [ ] **Step 1: Write failing tests for sequential pairing**

Add `build_sequential_macro_pairs` to the import list in `tests/test_gui_helpers.py`:

```python
from gui import (
    BUTTON_VARIANTS,
    build_account_summary,
    build_macro_step_summary,
    build_sequential_macro_pairs,
    build_status_summary,
    get_button_colors,
)
```

Add these tests before the `if __name__ == "__main__":` block:

```python
    def test_sequential_pairs_cycle_devices_for_accounts(self):
        accounts = [
            {"email": "a1@example.com"},
            {"email": "a2@example.com"},
            {"email": "a3@example.com"},
            {"email": "a4@example.com"},
        ]

        pairs = build_sequential_macro_pairs(["dev1", "dev2", "dev3"], accounts)

        self.assertEqual(
            pairs,
            [
                ("dev1", accounts[0], 0, 4),
                ("dev2", accounts[1], 1, 4),
                ("dev3", accounts[2], 2, 4),
                ("dev1", accounts[3], 3, 4),
            ],
        )

    def test_sequential_pairs_run_each_device_without_accounts(self):
        pairs = build_sequential_macro_pairs(["dev1", "dev2"], [])

        self.assertEqual(
            pairs,
            [
                ("dev1", None, 0, 2),
                ("dev2", None, 1, 2),
            ],
        )

    def test_sequential_pairs_return_empty_without_devices(self):
        self.assertEqual(build_sequential_macro_pairs([], [{"email": "a1@example.com"}]), [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_gui_helpers.py -q
```

Expected: FAIL with an import error for `build_sequential_macro_pairs`.

- [ ] **Step 3: Implement the helper**

Add this helper near the other top-level GUI helper functions in `gui.py`, after `build_status_summary`:

```python
def build_sequential_macro_pairs(devices, accounts):
    if not devices:
        return []

    if not accounts:
        total = len(devices)
        return [(device, None, idx, total) for idx, device in enumerate(devices)]

    total = len(accounts)
    return [
        (devices[idx % len(devices)], account, idx, total)
        for idx, account in enumerate(accounts)
    ]
```

- [ ] **Step 4: Run tests to verify helper behavior**

Run:

```powershell
python -m pytest tests/test_gui_helpers.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit helper and tests**

Run:

```powershell
git add -- gui.py tests/test_gui_helpers.py
git commit -m "feat: add sequential macro scheduler"
```

---

### Task 2: Add Sequential Mode UI State

**Files:**
- Modify: `gui.py`

- [ ] **Step 1: Add the Tk state variable**

In `MuMuGUI.__init__`, near `self.pause_between_sets = tk.BooleanVar(value=False)`, add:

```python
        self.run_sequentially = tk.BooleanVar(value=False)
```

- [ ] **Step 2: Add the checkbox to the run card**

In `build_macro_tab`, after the existing `self.pause_chk.pack(anchor="w", pady=5)` block and before `self.run_macro_btn = ModernButton(...)`, add:

```python
        self.sequential_chk = self.make_checkbutton(
            run_card,
            "รันทีละจอจนจบ",
            variable=self.run_sequentially,
            bg=BG_PANEL,
            activebackground=BG_PANEL,
        )
        self.sequential_chk.pack(anchor="w", pady=(0, 3))

        tk.Label(
            run_card,
            text="เหมาะกับสมัครรหัส ลดการเริ่มหลายจอพร้อมกัน",
            bg=BG_PANEL,
            fg=FG_MUTED,
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(0, 6))
```

- [ ] **Step 3: Compile check**

Run:

```powershell
python -m py_compile gui.py
```

Expected: no output and exit code 0.

- [ ] **Step 4: Run helper tests**

Run:

```powershell
python -m pytest tests/test_gui_helpers.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit UI state**

Run:

```powershell
git add -- gui.py
git commit -m "feat: add sequential run option"
```

---

### Task 3: Implement Sequential Macro Execution

**Files:**
- Modify: `gui.py`

- [ ] **Step 1: Add the sequential branch before existing account/no-account branches**

In `run_macro_task`, after the `sleep_stagger` helper and before `if not checked_accounts:`, add:

```python
            if self.run_sequentially.get():
                pairs = build_sequential_macro_pairs(devices, checked_accounts)
                self.write_log(
                    f"Sequential: เริ่มรันทีละจอจนจบทั้งหมด {len(pairs)} งาน "
                    f"(ไม่ใช้หน่วงเริ่มหลายจอและไม่รันคู่ขนาน)",
                    "warning",
                )

                for dev, acc, pair_idx, pair_total in pairs:
                    if not self.macro_running:
                        break

                    if acc:
                        email = acc.get("email")
                        self.write_log(
                            f"Sequential: เริ่มบัญชี {pair_idx + 1}/{pair_total} บน {dev}: {email}",
                            "warning",
                        )
                    else:
                        self.write_log(
                            f"Sequential: เริ่มจอ {pair_idx + 1}/{pair_total} บน {dev}",
                            "warning",
                        )

                    self.execute_device_macro(dev, acc, highlight)

                    if self.macro_running:
                        if acc:
                            self.write_log(
                                f"Sequential: บัญชี {pair_idx + 1}/{pair_total} เสร็จแล้ว",
                                "success",
                            )
                        else:
                            self.write_log(
                                f"Sequential: จอ {pair_idx + 1}/{pair_total} เสร็จแล้ว",
                                "success",
                            )

                if self.macro_running:
                    self.write_log("🎉 Sequential: รันครบทุกบัญชีและทุกหน้าจอแล้ว!", "success")
                    messagebox.showinfo(
                        "เสร็จสิ้นการทำงาน",
                        "Sequential mode ทำงานตามสคริปต์มาโครครบแล้ว!",
                    )
                return
```

This branch must come before the existing `if not checked_accounts:` branch so it takes precedence over both parallel mode and pause-between-sets mode.

- [ ] **Step 2: Compile check**

Run:

```powershell
python -m py_compile gui.py
```

Expected: no output and exit code 0.

- [ ] **Step 3: Run focused tests**

Run:

```powershell
python -m pytest tests/test_gui_helpers.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit execution path**

Run:

```powershell
git add -- gui.py
git commit -m "feat: run macros sequentially when enabled"
```

---

### Task 4: Final Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run compile verification**

Run:

```powershell
python -m py_compile gui.py quick_builder.py
```

Expected: no output and exit code 0.

- [ ] **Step 2: Run focused tests**

Run:

```powershell
python -m pytest tests/test_gui_helpers.py tests/test_quick_builder.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected: `24 passed` or more if new tests increased the count.

- [ ] **Step 4: Inspect git status**

Run:

```powershell
git status --short
```

Expected: no unstaged source changes from this feature. Existing generated/build artifacts may still be dirty and should not be staged unless explicitly requested.

