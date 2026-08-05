"""เทส Tkinter (gui.py) ให้ตรงกับฝั่ง webui: anchor_on_fail ค่าเริ่มต้นเป็น 'pause' (ไม่ใช่ 'abort')
และไม่มีนโยบายไหนสั่งรีเซ็ตเกม (_reset_device_to_login) อัตโนมัติอีกต่อไป — เดิมทุกครั้งที่ 'ติดปัญหา'
(device_error/macro_error) จะรีเซ็ตเกมเสมอ ตอนนี้ถอดออกแล้วตามที่ผู้ใช้ขอ ให้สอดคล้องกับ webui

Tk root มาจาก session fixture ตัวเดียว (tests/conftest.py) ห้ามสร้างใหม่ที่นี่:
สร้าง tk.Tk() แล้ว destroy หลายรอบบน Windows ทำให้ Tcl หมดทรัพยากรแล้วเทสล้มแบบสุ่ม"""
import base64
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

B64 = base64.b64encode(b"TMPL").decode()


class FakeController:
    """anchor หาไม่เจอเสมอ (found=False) -> ไล่เข้า anchor_on_fail ทุกครั้ง"""

    def __init__(self):
        self.found = False
        self.calls = []

    def capture_screenshot_bytes(self, d):
        return True, b"SCREEN"

    def find_image_in_bytes(self, screen_bytes, template_path, threshold=0.8):
        return (self.found, 5, 6, "m")

    def match_template_bytes(self, screen_bytes, tmpl_bytes, threshold=0.8):
        return (self.found, 5, 6, "m")

    def tap(self, d, x, y):
        self.calls.append(("tap", d, x, y))
        return True, ""


@pytest.fixture
def app(gui_app):
    """รีเซ็ตสถานะต่อเทส: controller ใหม่, ยกเลิกการรีเซ็ตเกมด้วย stub, เปิด macro_running
    Tk root มาจาก session fixture ตัวเดียว (ดู tests/conftest.py) — ห้ามสร้างใหม่ที่นี่"""
    gui_app.controller = FakeController()
    gui_app.macro_running = True
    gui_app.script_sets = {}
    gui_app._anchor_poll_interval = 0.01
    gui_app.reset_calls = []
    gui_app._reset_device_to_login = lambda device: gui_app.reset_calls.append(device)
    return gui_app


def _tap_step(x, y, **extra):
    step = {"type": "tap", "x": str(x), "y": str(y), "desc": "ปุ่มทดสอบ"}
    step.update(extra)
    return step


def test_missing_anchor_on_fail_defaults_to_pause_and_does_not_reset(app):
    app.macro_steps = [_tap_step(2, 2, anchor_img=B64, anchor_timeout=0.001)]  # ไม่ตั้ง anchor_on_fail เลย
    result = app.execute_device_macro(":7555", {"email": "a@b.c"}, highlight=False)
    assert result["status"] == "device_error"
    assert "anchor_fail_pause" in result["error"]
    assert app.reset_calls == []          # ไม่รีเซ็ตเกม
    assert app.controller.calls == []     # ไม่กดอะไรเลย (anchor ไม่เจอ ต้องไม่กดตาบอด)


def test_explicit_pause_policy_does_not_reset(app):
    app.macro_steps = [_tap_step(2, 2, anchor_img=B64, anchor_timeout=0.001, anchor_on_fail="pause")]
    result = app.execute_device_macro(":7555", {"email": "a@b.c"}, highlight=False)
    assert result["status"] == "device_error"
    assert app.reset_calls == []


def test_explicit_abort_policy_no_longer_resets(app):
    """abort ยังหยุดจอเหมือนเดิม แต่ต้องไม่รีเซ็ตเกมอีกต่อไป (พฤติกรรมเดิมถูกถอดออกทั้งระบบ)"""
    app.macro_steps = [_tap_step(2, 2, anchor_img=B64, anchor_timeout=0.001, anchor_on_fail="abort")]
    result = app.execute_device_macro(":7555", {"email": "a@b.c"}, highlight=False)
    assert result["status"] == "device_error"
    assert app.reset_calls == []


def test_pause_self_heals_by_redoing_previous_step_once(app):
    """ตรงกับ webui: ก่อนหยุดรอจริง ต้องลองย้อนไปทำขั้นก่อนหน้าซ้ำ 1 ครั้งแล้วเช็ค anchor ใหม่ก่อนเสมอ"""
    app.macro_steps = [
        _tap_step(1, 1),
        _tap_step(2, 2, anchor_img=B64, anchor_timeout=0.001, anchor_on_fail="pause"),
    ]
    result = app.execute_device_macro(":7555", {"email": "a@b.c"}, highlight=False)
    assert result["status"] == "device_error"  # anchor ไม่เจอเลยไม่ว่ากี่รอบ (FakeController.found=False)
    # ขั้น 1 ถูกทำ 2 ครั้ง: ครั้งแรก + self-heal ย้อนไปทำซ้ำ 1 ครั้ง ก่อนยอมหยุดรอจริง
    tap11 = [c for c in app.controller.calls if (str(c[2]), str(c[3])) == ("1", "1")]
    assert len(tap11) == 2


def test_flat_script_without_anchor_still_completes_normally(app):
    """สคริปต์ปกติที่ไม่มี anchor เลย ต้องไม่กระทบจากการเปลี่ยนดีฟอลต์ (no regression)"""
    app.macro_steps = [_tap_step(1, 1)]
    result = app.execute_device_macro(":7555", {"email": "a@b.c"}, highlight=False)
    assert result["status"] == "completed"
    assert (":7555", "1", "1") in [(c[1], str(c[2]), str(c[3])) for c in app.controller.calls]
