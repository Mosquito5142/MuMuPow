# Robust Duplicate-Device Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** สแกนแล้วไม่นับจอ MuMu เดียวกันซ้ำ (เคสเพื่อน 6 จอโผล่ 10) — spec: `docs/superpowers/specs/2026-11-18-device-dedup-design.md`

**Architecture:** เขียน `MuMuController.get_unique_devices()` ใหม่เป็น 2 ชั้น: (1) รวมชื่อเล่น `emulator-N` ≡ `127.0.0.1:N+1` โดยไม่ถามเครื่อง (2) ระบุตัวตนด้วย serial+boot serial+android_id (timeout 5s ลองซ้ำ 1) แล้วเก็บตัวที่อันดับดีที่สุด (`127.0.0.1:` ≥16384 ก่อน) หมายเหตุการตัด/ระบุไม่ได้เก็บใน `last_dedup_notes` ให้ `web_app.Api` ดันเข้า log

**Tech Stack:** Python 3, pytest, ADB ผ่าน `run_adb_cmd`

## Global Constraints

- แก้ logic ที่ `mumu_controller.py` ที่เดียว ไม่แตะ `gui.py`
- ไม่ fallback เป็น MAC หรือชื่อที่อยู่อีกต่อไป; ระบุไม่ได้ = เก็บไว้ + หมายเหตุ `⚠️`
- ค่าไร้ความหมาย: `""`, `unknown`, `null`, `none` (ไม่สนตัวพิมพ์)
- `adb disconnect` เฉพาะที่อยู่ที่ไม่ขึ้นต้น `emulator-`
- เทสห้ามยิง ADB จริง; จบด้วย `python -m pytest tests/ -q` ผ่านครบ
- Commit ลงท้าย `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

---

### Task 1: Dedup logic in MuMuController

**Files:**
- Modify: `mumu_controller.py` — แทนที่ทั้งเมธอด `get_unique_devices` (~บรรทัด 860–888) และเพิ่ม `self.last_dedup_notes = []` ใน `__init__` (~บรรทัด 717)
- Test: `tests/test_device_dedup.py` (ใหม่)

**Interfaces:**
- Produces: `MuMuController.get_unique_devices(connected_devices: list[str]) -> list[str]`, `MuMuController.last_dedup_notes: list[str]` (ข้อความตัดจอซ้ำขึ้นต้น `"ตัดจอซ้ำ "`, ข้อความระบุไม่ได้ขึ้นต้น `"⚠️ "`)

- [ ] **Step 1: Write the failing tests** — `tests/test_device_dedup.py`

```python
"""กรองจอซ้ำตอนสแกน — เคสเพื่อน: MuMu 6 จอ แต่ ADB เห็น 10 ที่อยู่
(emulator-N คือพอร์ต N+1; MuMu บางเวอร์ชันเปิดพอร์ต 555x คู่กับ 16xxx)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mumu_controller import MuMuController


def make(ids, fail_first=()):
    """ids: {device: "serial\\nboot\\nandroid_id"} — ไม่มีใน dict = ถามไม่ได้ (timeout)
    fail_first: device ที่ครั้งแรก timeout ครั้งสองตอบได้"""
    c = MuMuController.__new__(MuMuController)  # ข้าม __init__ (ไม่หา adb จริง)
    c.disconnected = []
    calls = {}

    def run_adb_cmd(args, timeout=15):
        dev = args[1]
        calls[dev] = calls.get(dev, 0) + 1
        if dev in fail_first and calls[dev] == 1:
            return False, "Command timed out"
        if dev in ids:
            return True, ids[dev]
        return False, "Command timed out"

    c.run_adb_cmd = run_adb_cmd
    c.disconnect_device = lambda d: c.disconnected.append(d) or (True, "")
    c.calls = calls
    return c


REAL = [f"127.0.0.1:{16416 + 32 * i}" for i in range(6)]


def real_ids():
    return {d: f"SER{i}\nSER{i}\nAID{i}" for i, d in enumerate(REAL)}


def test_friend_case_ten_becomes_six():
    ids = real_ids()
    ids["127.0.0.1:5561"] = "SER3\nSER3\nAID3"
    ids["emulator-5560"] = "SER3\nSER3\nAID3"
    ids["emulator-5556"] = "SER1\nSER1\nAID1"
    ids["emulator-5558"] = "SER2\nSER2\nAID2"
    connected = ["emulator-5556", "emulator-5558", "emulator-5560"] + REAL + ["127.0.0.1:5561"]
    c = make(ids)
    # ตัวที่ถูกเก็บแทนจะอยู่ตำแหน่งของตัวซ้ำที่มาก่อน — เทียบแบบไม่สนลำดับ
    assert sorted(c.get_unique_devices(connected)) == sorted(REAL)


def test_alias_merged_without_identity():
    c = make({})
    out = c.get_unique_devices(["emulator-5560", "127.0.0.1:5561"])
    assert out == ["127.0.0.1:5561"]
    assert any(n.startswith("⚠️") and "127.0.0.1:5561" in n for n in c.last_dedup_notes)


def test_keeps_16xxx_even_if_duplicate_listed_first():
    c = make({"127.0.0.1:5557": "S\nS\nA", "127.0.0.1:16416": "S\nS\nA"})
    assert c.get_unique_devices(["127.0.0.1:5557", "127.0.0.1:16416"]) == ["127.0.0.1:16416"]
    assert c.disconnected == ["127.0.0.1:5557"]


def test_same_serial_different_android_id_are_two_devices():
    c = make({REAL[0]: "S\nS\nA1", REAL[1]: "S\nS\nA2"})
    assert c.get_unique_devices(REAL[:2]) == REAL[:2]


def test_unknown_identity_kept_with_warning():
    c = make({REAL[0]: "S0\nS0\nA0"})
    out = c.get_unique_devices([REAL[0], REAL[1]])
    assert out == [REAL[0], REAL[1]]
    assert any(n.startswith("⚠️") and REAL[1] in n for n in c.last_dedup_notes)


def test_null_values_count_as_unknown():
    c = make({REAL[0]: "unknown\n\nnull", REAL[1]: "unknown\n\nnull"})
    out = c.get_unique_devices(REAL[:2])
    assert out == REAL[:2], "ค่าว่าง/unknown ต้องไม่ทำให้สองจอถูกรวมผิด"
    assert sum(n.startswith("⚠️") for n in c.last_dedup_notes) == 2


def test_retry_once_after_timeout():
    c = make({REAL[0]: "S\nS\nA", REAL[1]: "S\nS\nA"}, fail_first={REAL[1]})
    assert c.get_unique_devices(REAL[:2]) == [REAL[0]]
    assert c.calls[REAL[1]] == 2


def test_normal_machine_unchanged():
    c = make(real_ids())
    assert c.get_unique_devices(list(REAL)) == REAL
    assert c.disconnected == []
    assert c.last_dedup_notes == []


def test_never_disconnects_emulator_entries():
    c = make({"emulator-5556": "S\nS\nA", REAL[0]: "S\nS\nA"})
    assert c.get_unique_devices(["emulator-5556", REAL[0]]) == [REAL[0]]
    assert c.disconnected == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_device_dedup.py -q`
Expected: FAIL (เช่น friend case ได้ 10 ตัว / ไม่มี `last_dedup_notes`)

- [ ] **Step 3: Implement** — ใน `mumu_controller.py` แทนที่ `get_unique_devices` ทั้งเมธอดด้วย:

```python
    _NULL_IDS = {"", "unknown", "null", "none"}

    @staticmethod
    def _alias_key(device_id):
        """emulator-N, 127.0.0.1:N+1 และ localhost:N+1 คือการเชื่อมต่อเดียวกัน"""
        m = re.fullmatch(r"emulator-(\d+)", device_id)
        if m:
            return f"127.0.0.1:{int(m.group(1)) + 1}"
        m = re.fullmatch(r"localhost:(\d+)", device_id)
        if m:
            return f"127.0.0.1:{m.group(1)}"
        return device_id

    @staticmethod
    def _keep_rank(device_id):
        """ยิ่งน้อยยิ่งอยากเก็บ: พอร์ต MuMu 12 (>=16384) > 127.0.0.1 อื่น > emulator-* > อื่น ๆ"""
        m = re.fullmatch(r"127\.0\.0\.1:(\d+)", device_id)
        if m:
            return 0 if int(m.group(1)) >= 16384 else 1
        if device_id.startswith("emulator-"):
            return 2
        return 3

    def _device_identity(self, device_id):
        """serial|boot serial|android_id ของเครื่อง — None ถ้าถามไม่ได้หรือว่างหมด"""
        cmd = ["-s", device_id, "shell",
               "getprop ro.serialno; getprop ro.boot.serialno; settings get secure android_id"]
        for _ in range(2):  # เปิดหลายจอพร้อมกันอาจตอบไม่ทัน — ลองซ้ำ 1 ครั้ง
            ok, out = self.run_adb_cmd(cmd, timeout=5)
            if not ok:
                continue
            lines = [ln.strip() for ln in (out or "").splitlines()][:3]
            lines += [""] * (3 - len(lines))
            vals = ["" if v.lower() in self._NULL_IDS else v for v in lines]
            if any(vals):
                return "|".join(vals)
        return None

    def _drop_duplicate(self, device_id):
        if not device_id.startswith("emulator-"):
            self.disconnect_device(device_id)  # เก็บ ADB ให้สะอาด

    def get_unique_devices(self, connected_devices):
        """ตัดการเชื่อมต่อที่ชี้ไปจอเดียวกันออก — หมายเหตุอยู่ใน self.last_dedup_notes"""
        notes = []

        # 1) รวมชื่อเล่นของการเชื่อมต่อเดียวกัน (ไม่ต้องถามเครื่อง)
        groups, order = {}, []
        for d in connected_devices:
            k = self._alias_key(d)
            if k not in groups:
                groups[k] = []
                order.append(k)
            groups[k].append(d)
        reps = []
        for k in order:
            members = sorted(groups[k], key=self._keep_rank)
            reps.append(members[0])
            for dup in members[1:]:
                notes.append(f"ตัดจอซ้ำ {dup} (= {members[0]})")
                self._drop_duplicate(dup)

        # 2) ระบุตัวตนแล้วรวมตัวที่ id ตรงกันทุกค่า
        ids = {}
        if reps:
            with ThreadPoolExecutor(max_workers=len(reps)) as executor:
                ids = dict(zip(reps, executor.map(self._device_identity, reps)))
        kept, by_id = [], {}
        for d in reps:
            ident = ids.get(d)
            if ident is None:
                notes.append(f"⚠️ ระบุตัวตน {d} ไม่ได้ — อาจเป็นจอซ้ำ")
                kept.append(d)
                continue
            cur = by_id.get(ident)
            if cur is None:
                by_id[ident] = d
                kept.append(d)
            elif self._keep_rank(d) < self._keep_rank(cur):
                kept[kept.index(cur)] = d
                by_id[ident] = d
                notes.append(f"ตัดจอซ้ำ {cur} (= {d})")
                self._drop_duplicate(cur)
            else:
                notes.append(f"ตัดจอซ้ำ {d} (= {cur})")
                self._drop_duplicate(d)

        self.last_dedup_notes = notes
        return kept
```

และใน `__init__` เพิ่มบรรทัดท้าย:

```python
        self.last_dedup_notes = []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_device_dedup.py -q`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add mumu_controller.py tests/test_device_dedup.py
git commit -m "fix: dedup emulator aliases and identify devices by serial+android_id on scan

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Show dedup notes in the web app log + build

**Files:**
- Modify: `web_app.py` — `Api.scan()` (~บรรทัด 292) และ `Api.connect_manual()` (~บรรทัด 306), เพิ่มเมธอด `_push_dedup_notes`
- Test: `tests/test_device_dedup.py` (ต่อท้าย)

**Interfaces:**
- Consumes: `controller.last_dedup_notes: list[str]` จาก Task 1
- Produces: `Api._push_dedup_notes() -> None`

- [ ] **Step 1: Write the failing test** — ต่อท้าย `tests/test_device_dedup.py`

```python
def test_scan_pushes_dedup_notes_to_log():
    import web_app

    class Ctl:
        last_dedup_notes = ["ตัดจอซ้ำ emulator-5556 (= 127.0.0.1:16416)",
                            "⚠️ ระบุตัวตน 127.0.0.1:5561 ไม่ได้ — อาจเป็นจอซ้ำ"]

        def load_ports(self):
            return [16416]

        def scan_and_connect_all(self):
            return ["127.0.0.1:16416"], ""

    api = web_app.Api()
    api.controller = Ctl()
    api.scan()
    kinds = {e["text"]: e["kind"] for e in api._log}
    assert kinds["ตัดจอซ้ำ emulator-5556 (= 127.0.0.1:16416)"] == "info"
    assert kinds["⚠️ ระบุตัวตน 127.0.0.1:5561 ไม่ได้ — อาจเป็นจอซ้ำ"] == "warn"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_device_dedup.py::test_scan_pushes_dedup_notes_to_log -q`
Expected: FAIL with KeyError

- [ ] **Step 3: Implement** — ใน `web_app.py` เพิ่มเมธอดเหนือ `def scan(self):`

```python
    def _push_dedup_notes(self):
        for n in getattr(self.controller, "last_dedup_notes", None) or []:
            self._push_log(n, "warn" if n.startswith("⚠️") else "info")
```

ใน `scan()` หลัง `self.selected = set(devices)` เพิ่ม `self._push_dedup_notes()`
ใน `connect_manual()` หลัง `self.selected |= set(self.devices)` เพิ่ม `self._push_dedup_notes()`

- [ ] **Step 4: Run full suite**

Run: `python -m pytest tests/ -q`
Expected: ผ่านทั้งหมด 0 failed

- [ ] **Step 5: Commit**

```bash
git add web_app.py tests/test_device_dedup.py
git commit -m "feat: show duplicate-device notes in the scan log

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Build the new app (ไม่เปิดโปรแกรมเอง)**

```bash
python -m PyInstaller --clean MuMupow_web.spec
cp dist/MuMupow_new.exe ./MuMupow_new.exe && rm -rf dist
```
Expected: build สำเร็จ มี `MuMupow_new.exe` ใหม่ที่ root
