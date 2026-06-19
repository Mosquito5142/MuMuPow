import os
import tempfile
import types
import unittest

import gui


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

    def find_image_on_screen(self, screen_path, template_path, threshold=0.8):
        if self.found_image:
            return (True, self.match_point[0], self.match_point[1], "match")
        return (False, 0, 0, "no match")

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


def make_stub(controller):
    stub = types.SimpleNamespace()
    stub.controller = controller
    stub.macro_running = True
    stub.templates_dir = "templates"
    stub._logs = []
    stub.write_log = lambda msg, t="info": stub._logs.append((t, msg))
    # static helper บน MuMuGUI ที่ handler เรียกผ่าน self
    stub._substitute_account = gui.MuMuGUI._substitute_account
    stub._parse_ui_query = gui.MuMuGUI._parse_ui_query
    return stub


def make_ctx(device="127.0.0.1:5555", account=None):
    result = {"errors": 0, "error": ""}

    def record(ret, label):
        try:
            ok, out = ret
        except (TypeError, ValueError):
            ok, out = True, ""
        if not ok:
            result["errors"] += 1
            if not result["error"]:
                result["error"] = f"{label}: {out}"
        return ok

    ctx = types.SimpleNamespace(device=device, account=account, record=record, step_delay=0.0)
    ctx.result = result
    return ctx


class StepHandlerTests(unittest.TestCase):
    def test_tap_sends_command_and_records_no_error_on_success(self):
        ctrl = FakeController()
        ctx = make_ctx()
        gui.MuMuGUI._step_tap(make_stub(ctrl), ctx, {"x": "10", "y": "20"})

        self.assertEqual(ctrl.calls, [("tap", "127.0.0.1:5555", "10", "20")])
        self.assertEqual(ctx.result["errors"], 0)

    def test_tap_records_error_when_adb_fails(self):
        ctrl = FakeController(fail=True)
        ctx = make_ctx()
        gui.MuMuGUI._step_tap(make_stub(ctrl), ctx, {"x": "10", "y": "20"})

        self.assertEqual(ctx.result["errors"], 1)
        self.assertTrue(ctx.result["error"].startswith("tap:"))

    def test_text_substitutes_account_placeholders(self):
        ctrl = FakeController()
        account = {"email": "p@e.com", "password": "secret", "name": "Ace"}
        ctx = make_ctx(account=account)
        gui.MuMuGUI._step_text(make_stub(ctrl), ctx, {"text": "{EMAIL}/{PASSWORD}/{NAME}"})

        self.assertEqual(ctrl.calls, [("text", "127.0.0.1:5555", "p@e.com/secret/Ace")])

    def test_text_without_account_sends_literal(self):
        ctrl = FakeController()
        ctx = make_ctx(account=None)
        gui.MuMuGUI._step_text(make_stub(ctrl), ctx, {"text": "{EMAIL}"})

        self.assertEqual(ctrl.calls, [("text", "127.0.0.1:5555", "{EMAIL}")])

    def test_thai_text_routes_to_unicode_input(self):
        ctrl = FakeController()
        account = {"email": "p@e.com", "password": "x", "name": "บอส"}
        ctx = make_ctx(account=account)
        gui.MuMuGUI._step_text(make_stub(ctrl), ctx, {"text": "{NAME}"})

        self.assertEqual(ctrl.calls, [("text_unicode", "127.0.0.1:5555", "บอส")])

    def test_keyevent_passes_code(self):
        ctrl = FakeController()
        ctx = make_ctx()
        gui.MuMuGUI._step_keyevent(make_stub(ctrl), ctx, {"code": "4"})

        self.assertEqual(ctrl.calls, [("keyevent", "127.0.0.1:5555", "4")])

    def test_sleep_returns_stop_when_macro_halted(self):
        stub = make_stub(FakeController())
        stub.macro_running = False
        ctx = make_ctx()
        signal = gui.MuMuGUI._step_sleep(stub, ctx, {"seconds": 1})

        self.assertEqual(signal, "stop")

    def test_sleep_completes_when_running(self):
        stub = make_stub(FakeController())
        ctx = make_ctx()
        signal = gui.MuMuGUI._step_sleep(stub, ctx, {"seconds": 0})

        self.assertIsNone(signal)

    def test_wait_for_image_taps_when_image_appears(self):
        ctrl = FakeController()
        ctrl.found_image = True
        ctrl.match_point = (123, 456)
        stub = make_stub(ctrl)
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "tpl.png"), "wb").close()
            stub.templates_dir = tmp
            ctx = make_ctx()
            signal = gui.MuMuGUI._step_wait_for_image(
                stub, ctx, {"text": "tpl.png", "timeout": 5, "interval": 0.1, "click": True}
            )

        self.assertIsNone(signal)
        self.assertIn(("tap", "127.0.0.1:5555", 123, 456), ctrl.calls)

    def test_wait_for_image_skips_when_template_missing(self):
        ctrl = FakeController()
        stub = make_stub(ctrl)
        with tempfile.TemporaryDirectory() as tmp:
            stub.templates_dir = tmp  # ไม่มีไฟล์ tpl.png
            ctx = make_ctx()
            signal = gui.MuMuGUI._step_wait_for_image(
                stub, ctx, {"text": "tpl.png", "timeout": 5}
            )

        self.assertIsNone(signal)
        self.assertEqual(ctrl.calls, [])  # ไม่ควรถ่ายภาพหรือคลิกเลย

    def test_tap_text_finds_element_and_taps_center(self):
        ctrl = FakeController()
        ctx = make_ctx()
        gui.MuMuGUI._step_tap_text(make_stub(ctrl), ctx, {"text": "ยืนยัน"})

        self.assertIn(("dump_ui", "127.0.0.1:5555"), ctrl.calls)
        self.assertIn(("tap", "127.0.0.1:5555", 200, 450), ctrl.calls)

    def test_tap_text_substitutes_account_placeholder(self):
        ctrl = FakeController()
        ctrl.ui_xml = '<hierarchy><node text="p@e.com" resource-id="" bounds="[0,0][100,100]"/></hierarchy>'
        ctx = make_ctx(account={"email": "p@e.com", "password": "x", "name": "n"})
        gui.MuMuGUI._step_tap_text(make_stub(ctrl), ctx, {"text": "{EMAIL}"})

        self.assertIn(("tap", "127.0.0.1:5555", 50, 50), ctrl.calls)

    def test_tap_text_skips_when_element_absent(self):
        ctrl = FakeController()
        ctx = make_ctx()
        gui.MuMuGUI._step_tap_text(make_stub(ctrl), ctx, {"text": "ไม่มีปุ่มนี้"})

        self.assertNotIn(("tap", "127.0.0.1:5555", 200, 450), ctrl.calls)

    def test_wait_for_text_returns_stop_when_halted(self):
        stub = make_stub(FakeController())
        stub.macro_running = False
        ctx = make_ctx()
        signal = gui.MuMuGUI._step_wait_for_text(stub, ctx, {"text": "ยืนยัน", "timeout": 5})

        self.assertEqual(signal, "stop")

    def test_every_known_step_type_has_a_handler_method(self):
        # ทุกชนิด step ที่ระบบรองรับต้องมีเมธอด handler _step_<type> รองรับ
        expected = {
            "tap", "swipe", "text", "keyevent", "start_app", "stop_app",
            "detect_image", "wait_for_image", "tap_text", "wait_for_text",
            "screenshot", "clear_ads_loop", "fetch_otp", "sleep", "keyboard",
        }
        for step_type in expected:
            self.assertTrue(
                callable(getattr(gui.MuMuGUI, f"_step_{step_type}", None)),
                f"ขาด handler สำหรับ step '{step_type}'",
            )


if __name__ == "__main__":
    unittest.main()
