import unittest

from gui import (
    BUTTON_VARIANTS,
    build_account_summary,
    build_macro_step_summary,
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

    def test_account_summary_keeps_group_and_otp_signal(self):
        summary = build_account_summary(
            {"email": "player@example.com", "name": "Main", "group": "A", "refresh_token": "token"}
        )

        self.assertIn("Main", summary)
        self.assertIn("player@example.com", summary)
        self.assertIn("A", summary)
        self.assertIn("OTP", summary)


if __name__ == "__main__":
    unittest.main()
