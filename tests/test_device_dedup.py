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
