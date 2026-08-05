"""เทสตัวจัดการ step รายชนิด — ยิงที่ MacroRunner ซึ่งตอนนี้เป็นตัวรันของทั้งสองแอป

เดิมไฟล์นี้เทส MuMuGUI._step_* (เอนจินสำเนาฝั่ง Tkinter) แต่สำเนานั้นถูกถอดออกแล้ว
Tkinter เรียก MacroRunner ตัวเดียวกับ MuMupow_new ดังนั้นเคสเดิมทั้งหมดย้ายมาที่นี่:
ผ่านที่นี่ = ผ่านทั้งสองแอป ไม่ต้องเทสซ้ำสองที่ให้เลื่อนออกจากกันอีก
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import macro_runner as M


class FakeController:
    """controller ปลอมไว้บันทึกการเรียกและจำลองความล้มเหลวของ ADB"""

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def _ret(self):
        return (not self.fail, "device offline" if self.fail else "")

    def tap(self, device, x, y):
        self.calls.append(("tap", device, x, y))
        return self._ret()

    def swipe(self, device, x1, y1, x2, y2, duration):
        self.calls.append(("swipe", device, x1, y1, x2, y2, duration))
        return self._ret()

    def input_text(self, device, text):
        self.calls.append(("text", device, text))
        return self._ret()

    def input_text_unicode(self, device, text):
        self.calls.append(("text_unicode", device, text))
        return self._ret()

    def keyevent(self, device, code):
        self.calls.append(("keyevent", device, code))
        return self._ret()

    # ใช้สำหรับ handler ที่อิงรูปภาพ (detect/wait)
    found_image = True
    match_point = (100, 200)

    def take_screenshot(self, device, path):
        self.calls.append(("screenshot", device, path))
        return (True, "")

    def capture_screenshot_bytes(self, device):
        self.calls.append(("screenshot_bytes", device))
        return (True, b"PNGDATA")

    def find_image_in_bytes(self, screen_bytes, template_path, threshold=0.8):
        if self.found_image:
            return (True, self.match_point[0], self.match_point[1], "match")
        return (False, 0, 0, "no match")

    # ใช้สำหรับ handler ที่อิง uiautomator (tap_text/wait_for_text)
    ui_xml = '<hierarchy><node text="ยืนยัน" resource-id="" bounds="[100,400][300,500]"/></hierarchy>'
    ui_ok = True

    def dump_ui(self, device):
        self.calls.append(("dump_ui", device))
        if self.ui_ok:
            return (True, self.ui_xml)
        return (False, "no elements")


DEV = "127.0.0.1:5555"


def run_step(controller, step, account=None, running=True):
    """รัน step เดียวผ่านตัวรันจริง คืน (status, runner) — delay ถูกบังคับเป็น 0 ให้เทสไว"""
    step = dict(step)
    step.setdefault("delay", 0)
    runner = M.MacroRunner(controller, [step], log_cb=lambda t, k="info": None,
                           running_check=(running if callable(running) else (lambda: running)))
    status = runner._run_steps(DEV, account, runner.steps, lambda **kw: None)
    return status, runner


class StepHandlerTests(unittest.TestCase):

    # ---------- tap ----------

    def test_tap_sends_command_and_reports_no_error_on_success(self):
        ctrl = FakeController()
        status, _ = run_step(ctrl, {"type": "tap", "x": "10", "y": "20"})

        self.assertEqual(ctrl.calls, [("tap", DEV, 10, 20)])
        self.assertEqual(status, "completed")

    def test_tap_stops_the_account_when_adb_fails(self):
        """ADB พัง = ต้องหยุดบัญชีนี้ ไม่ใช่เดินหน้าทำขั้นถัดไปทั้งที่ขั้นนี้ไม่ได้กดจริง"""
        ctrl = FakeController(fail=True)
        status, _ = run_step(ctrl, {"type": "tap", "x": "10", "y": "20"})

        self.assertEqual(status, "device_error")

    def test_failed_step_does_not_run_the_next_one(self):
        ctrl = FakeController(fail=True)
        runner = M.MacroRunner(ctrl, [{"type": "tap", "x": "1", "y": "1", "delay": 0},
                                      {"type": "tap", "x": "9", "y": "9", "delay": 0}],
                               log_cb=lambda t, k="info": None, running_check=lambda: True)
        runner._run_steps(DEV, None, runner.steps, lambda **kw: None)

        self.assertNotIn(("tap", DEV, 9, 9), ctrl.calls)

    def test_tap_accepts_decimal_coordinates(self):
        """พิกัดจากการลากกรอบเป็นทศนิยมได้ — ADB รับแต่จำนวนเต็ม ถ้าไม่ปัดจะพังเงียบ"""
        ctrl = FakeController()
        run_step(ctrl, {"type": "tap", "x": "293.5", "y": "77.4"})

        self.assertEqual(ctrl.calls, [("tap", DEV, 294, 77)])

    # ---------- swipe ----------

    def test_swipe_passes_all_points_and_duration(self):
        ctrl = FakeController()
        run_step(ctrl, {"type": "swipe", "x": "1", "y": "2", "x2": "3", "y2": "4", "duration": 250})

        self.assertEqual(ctrl.calls, [("swipe", DEV, 1, 2, 3, 4, 250)])

    # ---------- text ----------

    def test_text_substitutes_account_placeholders(self):
        ctrl = FakeController()
        account = {"email": "p@e.com", "password": "secret", "name": "Ace"}
        run_step(ctrl, {"type": "text", "text": "{EMAIL}/{PASSWORD}/{NAME}"}, account=account)

        self.assertEqual(ctrl.calls, [("text", DEV, "p@e.com/secret/Ace")])

    def test_text_without_account_sends_literal(self):
        ctrl = FakeController()
        run_step(ctrl, {"type": "text", "text": "{EMAIL}"}, account=None)

        self.assertEqual(ctrl.calls, [("text", DEV, "{EMAIL}")])

    def test_thai_text_routes_to_unicode_input(self):
        """ข้อความไทยต้องไปทาง ADBKeyboard (broadcast base64) ไม่ใช่ input text ที่พิมพ์ไทยไม่ได้"""
        ctrl = FakeController()
        account = {"email": "p@e.com", "password": "x", "name": "บอส"}
        run_step(ctrl, {"type": "text", "text": "{NAME}"}, account=account)

        self.assertEqual(ctrl.calls, [("text_unicode", DEV, "บอส")])

    # ---------- keyevent ----------

    def test_keyevent_passes_code(self):
        ctrl = FakeController()
        run_step(ctrl, {"type": "keyevent", "code": "4"})

        self.assertEqual(ctrl.calls, [("keyevent", DEV, "4")])

    # ---------- sleep ----------

    def test_sleep_stops_when_macro_halted(self):
        ctrl = FakeController()
        status, _ = run_step(ctrl, {"type": "sleep", "seconds": 1}, running=False)

        self.assertEqual(status, "stopped")

    def test_sleep_completes_when_running(self):
        ctrl = FakeController()
        status, _ = run_step(ctrl, {"type": "sleep", "seconds": 0})

        self.assertEqual(status, "completed")

    # ---------- wait_for_image ----------

    def test_wait_for_image_taps_when_image_appears(self):
        ctrl = FakeController()
        ctrl.found_image = True
        ctrl.match_point = (123, 456)
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "tpl.png"), "wb").close()
            orig = M.templates_dir
            M.templates_dir = lambda: tmp
            try:
                run_step(ctrl, {"type": "wait_for_image", "text": "tpl.png",
                                "timeout": 5, "interval": 0.1, "click": True})
            finally:
                M.templates_dir = orig

        self.assertIn(("tap", DEV, 123, 456), ctrl.calls)

    def test_wait_for_image_skips_when_template_missing(self):
        ctrl = FakeController()
        with tempfile.TemporaryDirectory() as tmp:   # ไม่มีไฟล์ tpl.png
            orig = M.templates_dir
            M.templates_dir = lambda: tmp
            try:
                status, _ = run_step(ctrl, {"type": "wait_for_image", "text": "tpl.png", "timeout": 5})
            finally:
                M.templates_dir = orig

        self.assertEqual(status, "completed")
        self.assertEqual(ctrl.calls, [])   # ไม่ควรถ่ายภาพหรือคลิกเลย

    # ---------- tap_text / wait_for_text ----------

    def test_tap_text_finds_element_and_taps_center(self):
        ctrl = FakeController()
        run_step(ctrl, {"type": "tap_text", "text": "ยืนยัน"})

        self.assertIn(("dump_ui", DEV), ctrl.calls)
        self.assertIn(("tap", DEV, 200, 450), ctrl.calls)

    def test_tap_text_substitutes_account_placeholder(self):
        ctrl = FakeController()
        ctrl.ui_xml = '<hierarchy><node text="p@e.com" resource-id="" bounds="[0,0][100,100]"/></hierarchy>'
        run_step(ctrl, {"type": "tap_text", "text": "{EMAIL}"},
                 account={"email": "p@e.com", "password": "x", "name": "n"})

        self.assertIn(("tap", DEV, 50, 50), ctrl.calls)

    def test_tap_text_skips_when_element_absent(self):
        ctrl = FakeController()
        status, _ = run_step(ctrl, {"type": "tap_text", "text": "ไม่มีปุ่มนี้"})

        self.assertNotIn(("tap", DEV, 200, 450), ctrl.calls)
        self.assertEqual(status, "completed")   # หาไม่เจอ = ข้าม ไม่ใช่ทั้งบัญชีพัง

    def test_wait_for_text_stops_when_halted(self):
        ctrl = FakeController()
        status, _ = run_step(ctrl, {"type": "wait_for_text", "text": "ยืนยัน", "timeout": 5},
                             running=False)

        self.assertEqual(status, "stopped")

    # ---------- ความครบของตาราง dispatch ----------

    def test_every_known_step_type_actually_dispatches(self):
        """ทุกชนิดที่ตัวแก้ไขเสนอให้เลือกต้องมีสาขาจริงใน _dispatch

        ถ้าขาด step นั้นจะตกไปที่ 'ไม่รู้จักชนิด → ข้าม' คือเงียบหายไปเฉยๆ ระหว่างรัน
        ซึ่งเป็นบั๊กที่หาเจอยากที่สุดแบบหนึ่ง (สคริปต์ดูเหมือนรันผ่าน แต่ขั้นนั้นไม่ได้ทำ)
        """
        expected = {
            "tap", "swipe", "text", "keyevent", "start_app", "stop_app",
            "detect_image", "wait_for_image", "tap_text", "wait_for_text",
            "screenshot", "clear_ads_loop", "fetch_otp", "sleep", "keyboard",
            "read_diamond", "find_yellow_stage", "story_auto",
        }
        import inspect
        src = inspect.getsource(M.MacroRunner._dispatch)
        for step_type in sorted(expected):
            self.assertIn(f'"{step_type}"', src, f"_dispatch ไม่มีสาขาสำหรับ step '{step_type}'")
            self.assertNotIn(step_type, M.MacroRunner._UNSUPPORTED,
                             f"step '{step_type}' ยังถูกทำเครื่องหมายว่าไม่รองรับ")


if __name__ == "__main__":
    unittest.main()
