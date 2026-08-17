"""เทสโหมด 'ถ้าจอติด → ข้ามไปไอดีถัดไป' (on_stuck='next') — พฤติกรรมเดิมที่ผู้ใช้ขอกลับมา

ระบบ 'หยุดรอแก้ไข' (pause) ที่เพิ่มเข้ามาทีหลังทำให้รันยาวทิ้งไว้ไม่ได้:
พอจอไหนติด มันจอดรอคนมากดปุ่ม ทั้งที่ผู้ใช้อยากให้ข้ามไอดีนั้นไปทำตัวถัดไป
แล้วค่อยตามเก็บตัวที่ติด (ซึ่งถูกทำเครื่องหมายไว้แล้ว) ทีหลัง

โหมดนี้: ติด -> บันทึกรายงาน -> ปิดเกมเปิดใหม่กลับหน้า login -> ไปไอดีถัดไป
"""
import base64
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import macro_runner as M

B64 = base64.b64encode(b"TMPL").decode()

RESET_CFG = {"enabled": True, "package": "com.game.app", "boot_wait": 0,
             "open_login_steps": [{"x": "100", "y": "200", "delay": 0}]}


class Ctl:
    """anchor ไม่เจอเสมอ -> ไล่เข้า anchor_on_fail ทุกครั้ง"""

    def __init__(self):
        self.calls = []

    def capture_screenshot_bytes(self, d):
        return True, b"SCREEN"

    def match_template_bytes(self, *a, **k):
        return False, 0, 0, "no"

    def find_image_in_bytes(self, *a, **k):
        return False, 0, 0, "no"

    def tap(self, d, x, y):
        self.calls.append(("tap", int(float(x)), int(float(y))))
        return True, ""

    def stop_app(self, d, pkg):
        self.calls.append(("stop_app", pkg))
        return True, ""

    def launch_app_by_package(self, d, pkg):
        self.calls.append(("launch", pkg))
        return True, ""


def stuck_step():
    return {"type": "tap", "x": "5", "y": "6", "desc": "ปุ่มที่หาไม่เจอ",
            "anchor_img": B64, "anchor_timeout": 0.001, "delay": 0}


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch):
    """ตัดการรอจริงออก — _reset_device มี sleep คงที่ ถ้าปล่อยไว้ชุดเทสช้าขึ้นเป็นนาที
    (ไม่กระทบตรรกะที่กำลังทดสอบ ซึ่งคือ 'เรียกอะไรบ้าง' ไม่ใช่ 'รอนานเท่าไร')"""
    monkeypatch.setattr(M.time, "sleep", lambda *_a, **_k: None)


def runner(steps, on_stuck, reset_cfg=None, tmp_path=None, monkeypatch=None):
    if monkeypatch and tmp_path:
        monkeypatch.setattr(M, "base_dir", lambda: str(tmp_path))   # รายงานลง temp ไม่ปนของจริง
    return M.MacroRunner(Ctl(), steps, log_cb=lambda t, k="info": None,
                         running_check=lambda: True, anchor_poll=0.01,
                         reset_cfg=reset_cfg or {}, on_stuck=on_stuck)


# ---------- โหมด next: ไม่จอดรอ ----------

def test_next_mode_fails_the_account_instead_of_parking(tmp_path, monkeypatch):
    r = runner([stuck_step()], "next", RESET_CFG, tmp_path, monkeypatch)
    assert r.execute_one(":7555", {"email": "a@x.com"}) == "device_error"


def test_pause_mode_still_parks_the_device(tmp_path, monkeypatch):
    """โหมดเดิมต้องไม่เปลี่ยน — ใครชอบแบบเรียนรู้ทีละจอยังใช้ได้"""
    r = runner([stuck_step()], "pause", RESET_CFG, tmp_path, monkeypatch)
    assert r.execute_one(":7555", {"email": "a@x.com"}) == "paused"


def test_next_mode_resets_the_game_back_to_login(tmp_path, monkeypatch):
    """ถ้าไม่ล้างจอ ไอดีถัดไปจะเริ่มกลางคันของไอดีเดิม"""
    r = runner([stuck_step()], "next", RESET_CFG, tmp_path, monkeypatch)
    r.execute_one(":7555", {"email": "a@x.com"})

    kinds = [c[0] for c in r.controller.calls]
    assert "stop_app" in kinds and "launch" in kinds
    assert ("tap", 100, 200) in r.controller.calls      # เล่นขั้นเปิดหน้า login ให้ด้วย


def test_pause_mode_does_not_touch_the_screen(tmp_path, monkeypatch):
    """โหมดจอดรอต้องเก็บจอไว้ตามสภาพ ให้คนมาดูว่าติดอะไร"""
    r = runner([stuck_step()], "pause", RESET_CFG, tmp_path, monkeypatch)
    r.execute_one(":7555", {"email": "a@x.com"})
    assert not any(c[0] in ("stop_app", "launch") for c in r.controller.calls)


def test_next_mode_marks_the_account_as_failed(tmp_path, monkeypatch):
    """ไอดีที่ติดต้องถูกทำเครื่องหมายไว้ (ขึ้นสีแดงในหน้าบัญชี) ให้ตามเก็บทีหลังได้"""
    r = runner([stuck_step()], "next", RESET_CFG, tmp_path, monkeypatch)
    r.execute_one(":7555", {"email": "a@x.com"})

    assert len(r.account_results) == 1
    assert r.account_results[0]["status"] == "device_error"
    assert r.account_results[0]["email"] == "a@x.com"


def test_next_mode_writes_a_failure_report(tmp_path, monkeypatch):
    r = runner([stuck_step()], "next", RESET_CFG, tmp_path, monkeypatch)
    r.execute_one(":7555", {"email": "a@x.com"})
    assert (tmp_path / "error_reports" / "report.jsonl").exists()


def test_queue_keeps_going_to_the_next_account(tmp_path, monkeypatch):
    """หัวใจของสิ่งที่ผู้ใช้ขอ: จอติดแล้วคิวต้องเดินต่อ ไม่ใช่หยุดทั้งจอ"""
    monkeypatch.setattr(M, "base_dir", lambda: str(tmp_path))
    r = M.MacroRunner(Ctl(), [stuck_step()], log_cb=lambda t, k="info": None,
                      running_check=lambda: True, anchor_poll=0.01,
                      reset_cfg=RESET_CFG, on_stuck="next")
    accounts = [{"email": f"a{i}@x.com"} for i in range(4)]
    r.run_queue([":7555"], accounts)

    assert len(r.account_results) == 4, "ต้องพยายามครบทุกไอดี ไม่ใช่หยุดที่ตัวแรก"
    assert all(x["status"] == "device_error" for x in r.account_results)


def test_pause_mode_stops_the_queue_for_that_device(tmp_path, monkeypatch):
    """เทียบให้เห็นความต่าง: โหมด pause จอดจริง คิวไม่เดินต่อ"""
    monkeypatch.setattr(M, "base_dir", lambda: str(tmp_path))
    r = M.MacroRunner(Ctl(), [stuck_step()], log_cb=lambda t, k="info": None,
                      running_check=lambda: True, anchor_poll=0.01,
                      reset_cfg=RESET_CFG, on_stuck="pause")
    r.run_queue([":7555"], [{"email": f"a{i}@x.com"} for i in range(4)])
    assert len(r.account_results) == 0      # ค้างตั้งแต่ตัวแรก ไม่มีผลบัญชีถูกบันทึก


def test_reset_is_skipped_when_disabled(tmp_path, monkeypatch):
    r = runner([stuck_step()], "next", {"enabled": False, "package": "com.game.app"},
               tmp_path, monkeypatch)
    r.execute_one(":7555", {"email": "a@x.com"})
    assert not any(c[0] in ("stop_app", "launch") for c in r.controller.calls)


def test_default_is_still_pause_for_backwards_compatibility():
    r = M.MacroRunner(Ctl(), [], log_cb=lambda t, k="info": None)
    assert r.on_stuck == "pause"


def test_unknown_mode_falls_back_to_pause():
    r = M.MacroRunner(Ctl(), [], log_cb=lambda t, k="info": None, on_stuck="อะไรไม่รู้")
    assert r.on_stuck == "pause"


# ---------- ฝั่ง Api ----------

def test_api_defaults_to_next_mode(tmp_path, monkeypatch):
    """ผู้ใช้อยากได้พฤติกรรมเดิมเป็นค่าตั้งต้น — รันยาวทิ้งไว้ได้โดยไม่ต้องมานั่งเฝ้า"""
    import web_app
    monkeypatch.setattr(web_app, "base_dir", lambda: str(tmp_path))
    api = web_app.Api.__new__(web_app.Api)
    api._push_log = lambda *a, **k: None
    assert api._load_stuck_mode() == "next"


def test_api_remembers_the_chosen_mode(tmp_path, monkeypatch):
    import web_app
    monkeypatch.setattr(web_app, "base_dir", lambda: str(tmp_path))
    api = web_app.Api.__new__(web_app.Api)
    api._push_log = lambda *a, **k: None

    api.save_stuck_mode("pause")
    assert api.get_stuck_mode()["on_stuck"] == "pause"
    api.save_stuck_mode("next")
    assert api.get_stuck_mode()["on_stuck"] == "next"
