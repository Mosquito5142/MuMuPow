import os
import tempfile
import unittest

import cv2
import numpy as np

from mumu_controller import (
    MuMuController,
    escape_adb_text,
    find_element_center,
    list_ui_elements,
)


SAMPLE_UI = """<?xml version='1.0'?>
<hierarchy>
  <node text="" resource-id="com.game:id/root" bounds="[0,0][1080,1920]">
    <node text="Email" resource-id="com.game:id/email" bounds="[40,200][1040,300]"/>
    <node text="ยืนยัน" resource-id="com.game:id/confirm" content-desc="confirm-btn" bounds="[100,400][300,500]" clickable="true"/>
    <node text="Login Now" resource-id="" bounds="[100,600][500,700]"/>
  </node>
</hierarchy>"""


class EscapeAdbTextTests(unittest.TestCase):
    def test_plain_text_is_unchanged(self):
        self.assertEqual(escape_adb_text("player@example.com"), "player@example.com")

    def test_space_becomes_percent_s_token(self):
        self.assertEqual(escape_adb_text("hello world"), "hello%sworld")

    def test_shell_metacharacters_are_backslash_escaped(self):
        self.assertEqual(escape_adb_text("P@ss&w(rd)!"), "P@ss\\&w\\(rd\\)\\!")

    def test_quotes_and_dollar_and_backtick_are_escaped(self):
        self.assertEqual(escape_adb_text("a\"b'c$d`e"), "a\\\"b\\'c\\$d\\`e")

    def test_pipe_semicolon_redirect_are_escaped(self):
        self.assertEqual(escape_adb_text("a|b;c<d>e"), "a\\|b\\;c\\<d\\>e")

    def test_backslash_itself_is_escaped(self):
        self.assertEqual(escape_adb_text("a\\b"), "a\\\\b")

    def test_non_string_input_is_coerced(self):
        self.assertEqual(escape_adb_text(12345), "12345")


class FindImageInBytesTests(unittest.TestCase):
    def _controller(self):
        # __new__ หลีกเลี่ยง __init__ (ซึ่งไปค้นหา adb) — เมธอดจับภาพไม่พึ่ง adb_path
        return MuMuController.__new__(MuMuController)

    def test_locates_template_inside_screenshot_bytes(self):
        ctrl = self._controller()
        rng = np.random.default_rng(0)
        patch = rng.integers(0, 255, (16, 16, 3), dtype=np.uint8)  # ลายไม่ซ้ำ จับง่าย
        screen = np.zeros((120, 160, 3), dtype=np.uint8)
        x0, y0 = 40, 30
        screen[y0:y0 + 16, x0:x0 + 16] = patch
        ok, png = cv2.imencode(".png", screen)
        self.assertTrue(ok)

        with tempfile.TemporaryDirectory() as d:
            tpl = os.path.join(d, "t.png")
            cv2.imwrite(tpl, patch)
            found, mx, my, msg = ctrl.find_image_in_bytes(png.tobytes(), tpl, threshold=0.9)

        self.assertTrue(found, msg)
        self.assertLessEqual(abs(mx - (x0 + 8)), 2)
        self.assertLessEqual(abs(my - (y0 + 8)), 2)

    def test_missing_template_returns_not_found(self):
        ctrl = self._controller()
        found, mx, my, msg = ctrl.find_image_in_bytes(b"PNG", "does_not_exist.png")
        self.assertFalse(found)

    def test_empty_bytes_returns_not_found(self):
        ctrl = self._controller()
        with tempfile.TemporaryDirectory() as d:
            tpl = os.path.join(d, "t.png")
            cv2.imwrite(tpl, np.zeros((8, 8, 3), dtype=np.uint8))
            found, mx, my, msg = ctrl.find_image_in_bytes(b"", tpl)
        self.assertFalse(found)


class InputTextUnicodeTests(unittest.TestCase):
    def _ctrl(self):
        c = MuMuController.__new__(MuMuController)  # ไม่เรียก __init__ (ไม่ค้นหา adb)
        c.adb_path = "adb"
        c._calls = []

        def fake_run(args, timeout=10):
            c._calls.append(list(args))
            return True, ""

        c.run_adb_cmd = fake_run
        return c

    def test_ascii_text_uses_plain_input_text(self):
        c = self._ctrl()
        ok, out = c.input_text_unicode("dev", "Hello")
        self.assertTrue(ok)
        self.assertEqual(c._calls[-1][:5], ["-s", "dev", "shell", "input", "text"])

    def test_thai_text_requires_adbkeyboard(self):
        c = self._ctrl()
        c.current_ime = lambda dev: (True, "com.other.ime/.IME")
        ok, msg = c.input_text_unicode("dev", "สวัสดี")
        self.assertFalse(ok)
        self.assertIn("ADBKeyboard", msg)

    def test_thai_text_with_adbkeyboard_sends_base64_broadcast(self):
        c = self._ctrl()
        c.current_ime = lambda dev: (True, "com.android.adbkeyboard/.AdbIME")
        ok, out = c.input_text_unicode("dev", "สวัสดี")
        args = c._calls[-1]
        self.assertIn("ADB_INPUT_B64", args)
        expected_b64 = __import__("base64").b64encode("สวัสดี".encode("utf-8")).decode("ascii")
        self.assertIn(expected_b64, args)


class FindElementCenterTests(unittest.TestCase):
    def test_finds_element_by_exact_text_and_returns_center(self):
        found, x, y, info = find_element_center(SAMPLE_UI, text="ยืนยัน")
        self.assertTrue(found, info)
        self.assertEqual((x, y), (200, 450))  # center of [100,400][300,500]

    def test_finds_element_by_partial_text(self):
        found, x, y, info = find_element_center(SAMPLE_UI, text="Login")
        self.assertTrue(found, info)
        self.assertEqual((x, y), (300, 650))  # center of [100,600][500,700]

    def test_finds_element_by_resource_id_substring(self):
        found, x, y, info = find_element_center(SAMPLE_UI, resource_id="id/email")
        self.assertTrue(found, info)
        self.assertEqual((x, y), (540, 250))  # center of [40,200][1040,300]

    def test_matches_content_desc(self):
        found, x, y, info = find_element_center(SAMPLE_UI, text="confirm-btn")
        self.assertTrue(found, info)
        self.assertEqual((x, y), (200, 450))

    def test_returns_not_found_for_missing_text(self):
        found, x, y, info = find_element_center(SAMPLE_UI, text="ไม่มีปุ่มนี้")
        self.assertFalse(found)

    def test_handles_malformed_xml_gracefully(self):
        found, x, y, info = find_element_center("<not-closed", text="x")
        self.assertFalse(found)

    def test_list_ui_elements_skips_empty_nodes(self):
        items = list_ui_elements(SAMPLE_UI)
        texts = [it["text"] for it in items]
        # โหนด root (text ว่าง แต่มี id) ติดมาด้วย แต่โหนดที่ไม่มีทั้ง text/id/desc ถูกตัด
        self.assertIn("ยืนยัน", texts)
        self.assertIn("Login Now", texts)
        confirm = next(it for it in items if it["text"] == "ยืนยัน")
        self.assertTrue(confirm["clickable"])
        self.assertEqual(confirm["center"], (200, 450))


class ReadNumberInRegionTests(unittest.TestCase):
    """ทดสอบ OCR เลขแบบเทมเพลตต่อหลัก (per-digit template matching) ของระบบอ่านเพชร"""

    def _controller(self):
        return MuMuController.__new__(MuMuController)

    def _render_digit(self, d):
        """วาดเลข d เป็นภาพเล็ก (BGR) ด้วยฟอนต์คงที่ ใช้เป็นทั้งเทมเพลตและชิ้นส่วนของเลขเป้าหมาย"""
        font, scale, thick = cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2
        (w, h), base = cv2.getTextSize(str(d), font, scale, thick)
        img = np.zeros((h + base + 4, w + 4, 3), dtype=np.uint8)
        cv2.putText(img, str(d), (2, h + 2), font, scale, (255, 255, 255), thick, cv2.LINE_AA)
        return img

    def _build_scene(self, digits_dir, number_str, rx=200, ry=40, gap=8):
        """สร้างภาพหน้าจอจำลองโดย 'วาง' ภาพเลขแต่ละหลักลงไปจริง ๆ (paste) เพื่อให้ match ตรงเป๊ะ
        พร้อมบันทึกเทมเพลตเลข 0-9 ลง digits_dir แล้วคืน (png_bytes, region)"""
        digit_imgs = {d: self._render_digit(d) for d in range(10)}
        for d, im in digit_imgs.items():
            cv2.imwrite(os.path.join(digits_dir, f"{d}.png"), im)

        cell_h = max(im.shape[0] for im in digit_imgs.values())
        screen = np.zeros((ry + cell_h + 40, 500, 3), dtype=np.uint8)
        x = rx
        for ch in number_str:
            im = digit_imgs[int(ch)]
            hi, wi = im.shape[:2]
            screen[ry:ry + hi, x:x + wi] = im
            x += wi + gap
        region = {"x": rx - 2, "y": ry - 2, "w": (x - rx) + 4, "h": cell_h + 4}
        ok, png = cv2.imencode(".png", screen)
        self.assertTrue(ok)
        return png.tobytes(), region

    def test_reads_multi_digit_number_with_repeats(self):
        ctrl = self._controller()
        with tempfile.TemporaryDirectory() as d:
            png_bytes, region = self._build_scene(d, "3631")  # มีเลขซ้ำ (3) และเลขแคบ (1)
            ok, number, raw = ctrl.read_number_in_region(png_bytes, region, d, threshold=0.85)
        self.assertTrue(ok, raw)
        self.assertEqual(number, 3631)

    def test_reads_single_digit(self):
        ctrl = self._controller()
        with tempfile.TemporaryDirectory() as d:
            png_bytes, region = self._build_scene(d, "7")
            ok, number, raw = ctrl.read_number_in_region(png_bytes, region, d, threshold=0.85)
        self.assertTrue(ok, raw)
        self.assertEqual(number, 7)

    def test_zero_size_region_returns_not_found(self):
        ctrl = self._controller()
        with tempfile.TemporaryDirectory() as d:
            png_bytes, _region = self._build_scene(d, "42")
            ok, number, raw = ctrl.read_number_in_region(png_bytes, {"x": 0, "y": 0, "w": 0, "h": 0}, d)
        self.assertFalse(ok)
        self.assertIsNone(number)

    def test_no_digit_templates_returns_not_found(self):
        ctrl = self._controller()
        screen = np.zeros((80, 200, 3), dtype=np.uint8)
        ok_enc, png = cv2.imencode(".png", screen)
        self.assertTrue(ok_enc)
        with tempfile.TemporaryDirectory() as empty_dir:  # ไม่มีไฟล์เลขเลย
            ok, number, raw = ctrl.read_number_in_region(
                png.tobytes(), {"x": 0, "y": 0, "w": 50, "h": 30}, empty_dir)
        self.assertFalse(ok)
        self.assertIsNone(number)

    def test_empty_bytes_returns_not_found(self):
        ctrl = self._controller()
        with tempfile.TemporaryDirectory() as d:
            ok, number, raw = ctrl.read_number_in_region(b"", {"x": 0, "y": 0, "w": 10, "h": 10}, d)
        self.assertFalse(ok)
        self.assertIsNone(number)


if __name__ == "__main__":
    unittest.main()
