import unittest

from quick_builder import (
    DEFAULT_COORDINATE_PRESETS,
    build_key_step,
    build_sleep_step,
    build_swipe_step,
    build_tap_step_from_preset,
    build_text_step,
    normalize_coordinate_preset,
)


class QuickBuilderTests(unittest.TestCase):
    def test_default_presets_include_common_login_targets(self):
        names = [preset["name"] for preset in DEFAULT_COORDINATE_PRESETS]

        self.assertIn("สมัคร: ช่อง Email", names)
        self.assertIn("สมัคร: ปุ่มส่ง OTP", names)
        self.assertIn("Login: ปุ่ม Login", names)

    def test_normalize_coordinate_preset_accepts_numeric_strings(self):
        preset = normalize_coordinate_preset({"name": "ปุ่ม Login", "x": "451", "y": "293"})

        self.assertEqual(preset, {"name": "ปุ่ม Login", "x": 451, "y": 293})

    def test_normalize_coordinate_preset_accepts_decimal_coordinates(self):
        preset = normalize_coordinate_preset({"name": "ส่ง OTP", "x": "611.4", "y": "322.3"})

        self.assertEqual(preset, {"name": "ส่ง OTP", "x": 611.4, "y": 322.3})

    def test_tap_step_uses_preset_coordinates_and_default_delay(self):
        step = build_tap_step_from_preset({"name": "ปุ่ม Login", "x": 451, "y": 293})

        self.assertEqual(step["type"], "tap")
        self.assertEqual(step["x"], "451")
        self.assertEqual(step["y"], "293")
        self.assertEqual(step["delay"], 0.5)
        self.assertEqual(step["desc"], "คลิก ปุ่ม Login")

    def test_quick_builder_creates_text_sleep_key_and_swipe_steps(self):
        self.assertEqual(build_text_step("{EMAIL}")["text"], "{EMAIL}")
        self.assertEqual(build_sleep_step(1)["seconds"], 1.0)
        self.assertEqual(build_key_step("BACK"), {"type": "keyevent", "code": "4", "delay": 0.3, "desc": "กด BACK"})
        self.assertEqual(
            build_swipe_step("up"),
            {
                "type": "swipe",
                "x": "450",
                "y": "420",
                "x2": "450",
                "y2": "160",
                "delay": 0.5,
                "desc": "เลื่อนขึ้น",
            },
        )


if __name__ == "__main__":
    unittest.main()
