"""กรองจอซ้ำตอนสแกน — เคสเพื่อน: MuMu 6 จอ แต่ ADB เห็น 10 ที่อยู่
(emulator-N คือพอร์ต N+1; MuMu บางเวอร์ชันเปิดพอร์ต 555x คู่กับ 16xxx)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mumu_controller import MuMuController


def make(ids, fail_first=(), same_instance=None, probe_fail=False, cat_error=None):
    """ids: {device: "serial\nboot\nandroid_id"} (หรือ output แบบ label "S=..\nB=..\nA=.." ดิบ)
    ไม่มีใน dict = ถามไม่ได้ (timeout); fail_first: device ที่ครั้งแรก timeout ครั้งสองตอบได้
    same_instance: {device: ชื่อ instance} — จอที่ไม่ได้ระบุ = instance ของตัวเอง (ไฟล์ /data แยกกัน)
    probe_fail: เขียน/อ่านไฟล์ probe ไม่ได้
    cat_error: ข้อความ error ของ cat ที่ไม่ใช่ "No such file" (เช่น device offline)"""
    c = MuMuController.__new__(MuMuController)  # ข้าม __init__ (ไม่หา adb จริง)
    c.disconnected = []
    calls = {}
    same_instance = same_instance or {}
    fs = {}  # instance -> เนื้อไฟล์ probe

    def run_adb_cmd(args, timeout=15):
        dev, shell = args[1], args[3]
        if shell.startswith("echo S="):
            calls[dev] = calls.get(dev, 0) + 1
            if dev in fail_first and calls[dev] == 1:
                return False, "Command timed out"
            if dev in ids:
                v = ids[dev]
                if not v.startswith("S="):
                    p = (v.split("\n") + ["", "", ""])[:3]
                    v = f"S={p[0]}\nB={p[1]}\nA={p[2]}\n"
                return True, v.strip()
            return False, "Command timed out"
        inst = same_instance.get(dev, dev)
        if probe_fail:
            return False, "probe failed"
        if shell.startswith("echo "):
            fs[inst] = shell.split()[1]
            return True, ""
        if shell.startswith("cat "):
            if cat_error:
                return False, cat_error
            return (True, fs[inst]) if inst in fs else (False, "cat: No such file or directory")
        return False, "?"

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
    same = {"127.0.0.1:5561": "i3", "emulator-5560": "i3", REAL[3]: "i3",
            "emulator-5556": "i1", REAL[1]: "i1", "emulator-5558": "i2", REAL[2]: "i2"}
    c = make(ids, same_instance=same)
    # ตัวที่ถูกเก็บแทนจะอยู่ตำแหน่งของตัวซ้ำที่มาก่อน — เทียบแบบไม่สนลำดับ
    assert sorted(c.get_unique_devices(connected)) == sorted(REAL)


def test_alias_merged_without_identity():
    c = make({})
    out = c.get_unique_devices(["emulator-5560", "127.0.0.1:5561"])
    assert out == ["127.0.0.1:5561"]
    assert any(n.startswith("⚠️") and "127.0.0.1:5561" in n for n in c.last_dedup_notes)


def test_keeps_16xxx_even_if_duplicate_listed_first():
    c = make({"127.0.0.1:5557": "S\nS\nA", "127.0.0.1:16416": "S\nS\nA"},
             same_instance={"127.0.0.1:5557": "x", "127.0.0.1:16416": "x"})
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
    c = make({REAL[0]: "S\nS\nA", REAL[1]: "S\nS\nA"}, fail_first={REAL[1]},
             same_instance={REAL[0]: "x", REAL[1]: "x"})
    assert c.get_unique_devices(REAL[:2]) == [REAL[0]]
    assert c.calls[REAL[1]] == 2


def test_normal_machine_unchanged():
    c = make(real_ids())
    assert c.get_unique_devices(list(REAL)) == REAL
    assert c.disconnected == []
    assert c.last_dedup_notes == []


def test_never_disconnects_emulator_entries():
    c = make({"emulator-5556": "S\nS\nA", REAL[0]: "S\nS\nA"},
             same_instance={"emulator-5556": "x", REAL[0]: "x"})
    assert c.get_unique_devices(["emulator-5556", REAL[0]]) == [REAL[0]]
    assert c.disconnected == []


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

SAME01 = {REAL[0]: "x", REAL[1]: "x"}
IDENT = "S\nS\nA"


def test_cloned_instances_same_identity_both_kept():
    c = make({REAL[0]: IDENT, REAL[1]: IDENT})  # คนละ instance
    assert c.get_unique_devices(REAL[:2]) == REAL[:2]
    assert c.disconnected == []
    assert c.last_dedup_notes == []


def test_probe_failure_keeps_both_with_warning():
    c = make({REAL[0]: IDENT, REAL[1]: IDENT}, same_instance=SAME01, probe_fail=True)
    assert c.get_unique_devices(REAL[:2]) == REAL[:2]
    assert c.disconnected == []
    assert f"⚠️ {REAL[1]} อาจเป็นจอเดียวกับ {REAL[0]} (ตรวจยืนยันไม่ได้)" in c.last_dedup_notes


def test_empty_serial_labels_still_dedup():
    raw = "S=\nB=\nA=AID9\n"
    c = make({REAL[0]: raw, REAL[1]: raw}, same_instance=SAME01)
    assert c.get_unique_devices(REAL[:2]) == [REAL[0]]


def test_missing_android_id_line_parses_as_empty():
    c = make({REAL[0]: "S=SER0\nB=SER0", REAL[1]: "S=SER1\nB=SER1"})
    assert c._device_identity(REAL[0]) == "SER0|SER0|"
    assert c.get_unique_devices(REAL[:2]) == REAL[:2]


def test_in_place_replacement_order_pinned():
    ids = {"127.0.0.1:5557": IDENT, "127.0.0.1:16416": IDENT, REAL[1]: "T\nT\nB"}
    c = make(ids, same_instance={"127.0.0.1:5557": "x", "127.0.0.1:16416": "x"})
    assert c.get_unique_devices(["127.0.0.1:5557", REAL[1], "127.0.0.1:16416"]) == \
        ["127.0.0.1:16416", REAL[1]]


def test_notes_reset_at_start_of_each_call():
    import pytest
    c = make({REAL[0]: "S0\nS0\nA0"})
    c.last_dedup_notes = ["stale note"]

    def boom(d):
        raise RuntimeError("identity lookup failed")

    c._device_identity = boom
    with pytest.raises(RuntimeError):
        c.get_unique_devices([REAL[0], REAL[1]])
    assert "stale note" not in c.last_dedup_notes


def test_multi_clone_interleaved_connections():
    A1, B1, A2, B2 = (f"127.0.0.1:{p}" for p in (16416, 16448, 16480, 16512))
    c = make({d: IDENT for d in (A1, B1, A2, B2)},
             same_instance={A1: "A", A2: "A", B1: "B", B2: "B"})
    assert c.get_unique_devices([A1, B1, A2, B2]) == [A1, B1]
    assert sum(n.startswith("ตัดจอซ้ำ") for n in c.last_dedup_notes) == 2


def test_probe_non_nosuchfile_error_keeps_both_with_warning():
    c = make({REAL[0]: IDENT, REAL[1]: IDENT}, cat_error="error: device offline")
    assert c.get_unique_devices(REAL[:2]) == REAL[:2]
    assert c.disconnected == []
    assert f"⚠️ {REAL[1]} อาจเป็นจอเดียวกับ {REAL[0]} (ตรวจยืนยันไม่ได้)" in c.last_dedup_notes


def test_connect_manual_pushes_notes():
    import web_app

    class Ctl:
        last_dedup_notes = []

        def connect_device(self, a):
            return True, ""

        def get_connected_devices(self):
            return ["127.0.0.1:16416", "emulator-5556"]

        def get_unique_devices(self, conn):
            self.last_dedup_notes = ["ตัดจอซ้ำ emulator-5556 (= 127.0.0.1:16416)", "⚠️ x"]
            return ["127.0.0.1:16416"]

    api = web_app.Api()
    api.controller = Ctl()
    api.connect_manual("127.0.0.1:16416")
    kinds = {e["text"]: e["kind"] for e in api._log}
    assert kinds["ตัดจอซ้ำ emulator-5556 (= 127.0.0.1:16416)"] == "info"
    assert kinds["⚠️ x"] == "warn"
