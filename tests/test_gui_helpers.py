import unittest

from gui import (
    BUTTON_VARIANTS,
    build_account_summary,
    build_macro_step_summary,
    build_sequential_macro_pairs,
    build_status_summary,
    get_button_colors,
)


class GuiHelperTests(unittest.TestCase):
    def test_status_summary_counts_selected_items_and_profile(self):
        summary = build_status_summary(
            total_devices=3,
            selected_devices=2,
            total_accounts=8,
            selected_accounts=5,
            macro_steps=12,
            profile_name="Default Login",
            is_running=False,
        )

        self.assertIn("Emulator: 2/3", summary)
        self.assertIn("Accounts: 5/8", summary)
        self.assertIn("Steps: 12", summary)
        self.assertIn("Profile: Default Login", summary)
        self.assertIn("Ready", summary)

    def test_status_summary_reports_running_state(self):
        summary = build_status_summary(
            total_devices=1,
            selected_devices=1,
            total_accounts=0,
            selected_accounts=0,
            macro_steps=4,
            profile_name="",
            is_running=True,
        )

        self.assertIn("Running", summary)
        self.assertIn("Profile: Custom", summary)

    def test_button_variants_define_operational_console_hierarchy(self):
        self.assertIn("neutral", BUTTON_VARIANTS)
        self.assertEqual(get_button_colors("primary")["bg"], "#0F766E")
        self.assertEqual(get_button_colors("danger")["bg"], "#7F1D1D")
        self.assertEqual(get_button_colors("unknown"), get_button_colors("neutral"))

    def test_macro_step_summary_formats_tap_as_columns(self):
        summary = build_macro_step_summary(
            3,
            {"type": "tap", "x": 450, "y": 320, "delay": 0.5, "desc": "click email"},
        )

        self.assertIn("04", summary)
        self.assertIn("Tap", summary)
        self.assertIn("450, 320", summary)
        self.assertIn("0.5s", summary)
        self.assertIn("click email", summary)

    def test_macro_step_summary_formats_token_text(self):
        summary = build_macro_step_summary(
            1,
            {"type": "text", "text": "{EMAIL}", "delay": 0.5, "desc": "email"},
        )

        self.assertIn("02", summary)
        self.assertIn("Text", summary)
        self.assertIn("{EMAIL}", summary)
        self.assertIn("0.5s", summary)

    def test_macro_step_summary_formats_sleep_seconds(self):
        summary = build_macro_step_summary(
            4,
            {"type": "sleep", "seconds": 3, "delay": 0.25, "desc": "wait after login"},
        )

        self.assertIn("05", summary)
        self.assertIn("Sleep", summary)
        self.assertIn("wait 3", summary)
        self.assertIn("0.25s", summary)
        self.assertIn("wait after login", summary)

    def test_macro_step_summary_formats_run_set_name(self):
        summary = build_macro_step_summary(
            5,
            {"type": "run_set", "set": "Daily Quest", "delay": 1, "desc": "nested set"},
        )

        self.assertIn("06", summary)
        self.assertIn("Run Set", summary)
        self.assertIn("Daily Quest", summary)
        self.assertIn("1s", summary)

    def test_macro_step_summary_formats_keyboard_action(self):
        summary = build_macro_step_summary(
            6,
            {"type": "keyboard", "key": "enter", "action": "press", "delay": 0.1},
        )

        self.assertIn("07", summary)
        self.assertIn("Keyboard", summary)
        self.assertIn("press enter", summary)
        self.assertIn("0.1s", summary)

    def test_macro_step_summary_formats_swipe_coordinates(self):
        summary = build_macro_step_summary(
            7,
            {"type": "swipe", "x": 10, "y": 20, "x2": 300, "y2": 400, "delay": 0.75},
        )

        self.assertIn("08", summary)
        self.assertIn("Swipe", summary)
        self.assertIn("10,20 -> 300,400", summary)
        self.assertIn("0.75s", summary)

    def test_macro_step_summary_formats_keyevent_code(self):
        summary = build_macro_step_summary(
            8,
            {"type": "keyevent", "code": 4, "delay": 0.2, "desc": "back"},
        )

        self.assertIn("09", summary)
        self.assertIn("Key", summary)
        self.assertIn("4", summary)
        self.assertIn("0.2s", summary)
        self.assertIn("back", summary)

    def test_account_summary_keeps_group_and_otp_signal(self):
        summary = build_account_summary(
            {"email": "player@example.com", "name": "Main", "group": "A", "refresh_token": "token"}
        )

        self.assertIn("Main", summary)
        self.assertIn("player@example.com", summary)
        self.assertIn("A", summary)
        self.assertIn("OTP", summary)

    def test_account_summary_omits_otp_without_refresh_token(self):
        summary = build_account_summary(
            {"email": "player@example.com", "name": "Main", "group": "A", "client_id": "client"}
        )

        self.assertNotIn("OTP", summary)

    def test_sequential_pairs_cycle_devices_for_accounts(self):
        accounts = [
            {"email": "a1@example.com"},
            {"email": "a2@example.com"},
            {"email": "a3@example.com"},
            {"email": "a4@example.com"},
        ]

        pairs = build_sequential_macro_pairs(["dev1", "dev2", "dev3"], accounts)

        self.assertEqual(
            pairs,
            [
                ("dev1", accounts[0], 0, 4),
                ("dev2", accounts[1], 1, 4),
                ("dev3", accounts[2], 2, 4),
                ("dev1", accounts[3], 3, 4),
            ],
        )

    def test_sequential_pairs_run_each_device_without_accounts(self):
        pairs = build_sequential_macro_pairs(["dev1", "dev2"], [])

        self.assertEqual(
            pairs,
            [
                ("dev1", None, 0, 2),
                ("dev2", None, 1, 2),
            ],
        )

    def test_sequential_pairs_return_empty_without_devices(self):
        self.assertEqual(build_sequential_macro_pairs([], [{"email": "a1@example.com"}]), [])


if __name__ == "__main__":
    unittest.main()
