import unittest

from gui import build_status_summary


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


if __name__ == "__main__":
    unittest.main()
