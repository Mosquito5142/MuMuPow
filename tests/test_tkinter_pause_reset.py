"""เทส Tkinter (gui.py) ให้ตรงกับฝั่ง webui: anchor_on_fail ค่าเริ่มต้นเป็น 'pause' (ไม่ใช่ 'abort')
และไม่มีนโยบายไหนสั่งรีเซ็ตเกม (_reset_device_to_login) อัตโนมัติอีกต่อไป — เดิมทุกครั้งที่ 'ติดปัญหา'
(device_error/macro_error) จะรีเซ็ตเกมเสมอ ตอนนี้ถอดออกแล้วตามที่ผู้ใช้ขอ ให้สอดคล้องกับ webui"""
import base64
import os
import sys
import tempfile
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gui as G

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


def _make_app():
    """สร้าง MuMuGUI() จริง แต่กัน __init__ แตะไฟล์/ADB จริง (load_accounts อ่าน accounts.json จริง,
    scan_devices ยิง ADB จริง) — ไม่จำเป็นสำหรับเทสนี้ที่ตั้ง controller/macro_steps เองอยู่แล้ว
    และย้าย error_reports_dir ไปโฟลเดอร์ชั่วคราว กัน _save_failure_report เขียนไฟล์จริงลงเรโป
    (self.error_reports_dir เป็น instance attribute จาก base_dir จริงเสมอ ไม่มี base_dir() แบบ
    macro_runner.py ให้ monkeypatch ได้ตรงๆ)"""
    with unittest.mock.patch.object(G.MuMuGUI, "load_accounts", lambda self: None), \
         unittest.mock.patch.object(G.MuMuGUI, "scan_devices", lambda self: None):
        app = G.MuMuGUI()
    app.controller = FakeController()
    app.error_reports_dir = tempfile.mkdtemp()
    app.macro_running = True  # _run_macro_steps คืน 'stopped' ทันทีถ้า False (เหมือนกดหยุดไปแล้ว)
    return app


def _tap_step(x, y, **extra):
    step = {"type": "tap", "x": str(x), "y": str(y), "desc": "ปุ่มทดสอบ"}
    step.update(extra)
    return step


def test_missing_anchor_on_fail_defaults_to_pause_and_does_not_reset():
    app = _make_app()
    try:
        reset_calls = []
        app._reset_device_to_login = lambda device: reset_calls.append(device)
        app.macro_steps = [_tap_step(2, 2, anchor_img=B64, anchor_timeout=0.001)]  # ไม่ตั้ง anchor_on_fail เลย

        result = app.execute_device_macro(":7555", {"email": "a@b.c"}, highlight=False)

        assert result["status"] == "device_error"
        assert "anchor_fail_pause" in result["error"]
        assert reset_calls == []  # ไม่รีเซ็ตเกม
        assert app.controller.calls == []  # ไม่กดอะไรเลย (anchor ไม่เจอ ต้องไม่กดตาบอด)
    finally:
        app.destroy()


def test_explicit_pause_policy_does_not_reset():
    app = _make_app()
    try:
        reset_calls = []
        app._reset_device_to_login = lambda device: reset_calls.append(device)
        app.macro_steps = [_tap_step(2, 2, anchor_img=B64, anchor_timeout=0.001, anchor_on_fail="pause")]

        result = app.execute_device_macro(":7555", {"email": "a@b.c"}, highlight=False)

        assert result["status"] == "device_error"
        assert reset_calls == []
    finally:
        app.destroy()


def test_explicit_abort_policy_no_longer_resets():
    """abort ยังหยุดจอเหมือนเดิม แต่ต้องไม่รีเซ็ตเกมอีกต่อไป (พฤติกรรมเดิมถูกถอดออกทั้งระบบ)"""
    app = _make_app()
    try:
        reset_calls = []
        app._reset_device_to_login = lambda device: reset_calls.append(device)
        app.macro_steps = [_tap_step(2, 2, anchor_img=B64, anchor_timeout=0.001, anchor_on_fail="abort")]

        result = app.execute_device_macro(":7555", {"email": "a@b.c"}, highlight=False)

        assert result["status"] == "device_error"
        assert reset_calls == []
    finally:
        app.destroy()


def test_flat_script_without_anchor_still_completes_normally():
    """สคริปต์ปกติที่ไม่มี anchor เลย ต้องไม่กระทบจากการเปลี่ยนดีฟอลต์ (no regression)"""
    app = _make_app()
    try:
        app.macro_steps = [_tap_step(1, 1)]
        result = app.execute_device_macro(":7555", {"email": "a@b.c"}, highlight=False)
        assert result["status"] == "completed"
        assert (":7555", "1", "1") in [(c[1], str(c[2]), str(c[3])) for c in app.controller.calls]
    finally:
        app.destroy()
