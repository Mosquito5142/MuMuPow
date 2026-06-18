import json
import tempfile
import unittest
from pathlib import Path

from save_web_game_import import (
    SAVE_WEB_GAME_EXPORT_SCHEMA,
    import_save_web_game_accounts,
    merge_save_web_game_accounts,
)


def make_export(accounts):
    return {
        "schema": SAVE_WEB_GAME_EXPORT_SCHEMA,
        "version": 1,
        "exportedAt": "2026-06-18T00:00:00.000Z",
        "source": {"app": "Save_Web_Game"},
        "accounts": accounts,
    }


class SaveWebGameImportTests(unittest.TestCase):
    def test_merge_adds_new_accounts_with_character_metadata(self):
        payload = make_export(
            [
                {
                    "gameAccountId": "acc-1",
                    "title": "Slot 1",
                    "email": "player@example.com",
                    "password": "secret",
                    "ownerName": "Owner A",
                    "ingamename": "Ace",
                    "group": "Owner A",
                    "cards": [
                        {"key": "kise", "label": "Kise", "qty": 2, "category": "normal"},
                        {"key": "akashiSP", "label": "Akashi SP", "qty": 1, "category": "special"},
                    ],
                }
            ]
        )

        merged, stats = merge_save_web_game_accounts([], payload)

        self.assertEqual(stats["imported"], 1)
        self.assertEqual(stats["updated"], 0)
        self.assertEqual(stats["skipped"], 0)
        self.assertEqual(merged[0]["email"], "player@example.com")
        self.assertEqual(merged[0]["password"], "secret")
        self.assertEqual(merged[0]["name"], "Ace")
        self.assertEqual(merged[0]["group"], "Owner A")
        self.assertEqual(merged[0]["save_web_game_id"], "acc-1")
        self.assertEqual(merged[0]["save_web_game_title"], "Slot 1")
        self.assertEqual(merged[0]["ownerName"], "Owner A")
        self.assertEqual(merged[0]["card_count"], 3)
        self.assertEqual(merged[0]["cards"][0]["key"], "kise")

    def test_merge_updates_existing_account_by_email_case_insensitive(self):
        existing = [
            {
                "email": "PLAYER@example.com",
                "password": "old",
                "name": "Old",
                "checked": False,
                "group": "Old Group",
            }
        ]
        payload = make_export(
            [
                {
                    "gameAccountId": "acc-2",
                    "title": "Updated Slot",
                    "email": "player@example.com",
                    "password": "new",
                    "ownerName": "Owner B",
                    "ingamename": "Hero",
                    "group": "Owner B",
                    "cards": [{"key": "midorima", "label": "Midorima", "qty": 5, "category": "normal"}],
                }
            ]
        )

        merged, stats = merge_save_web_game_accounts(existing, payload)

        self.assertEqual(len(merged), 1)
        self.assertEqual(stats["imported"], 0)
        self.assertEqual(stats["updated"], 1)
        self.assertFalse(merged[0]["checked"])
        self.assertEqual(merged[0]["email"], "PLAYER@example.com")
        self.assertEqual(merged[0]["password"], "new")
        self.assertEqual(merged[0]["name"], "Hero")
        self.assertEqual(merged[0]["card_count"], 5)

    def test_merge_skips_invalid_export_accounts(self):
        payload = make_export(
            [
                {"email": "", "password": "secret", "cards": []},
                {"email": "missing-password@example.com", "password": "", "cards": []},
            ]
        )

        merged, stats = merge_save_web_game_accounts([], payload)

        self.assertEqual(merged, [])
        self.assertEqual(stats["skipped"], 2)

    def test_import_save_web_game_accounts_persists_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            export_path = tmp_path / "export.json"
            accounts_path = tmp_path / "accounts.json"
            export_path.write_text(
                json.dumps(
                    make_export(
                        [
                            {
                                "gameAccountId": "acc-1",
                                "title": "Slot 1",
                                "email": "player@example.com",
                                "password": "secret",
                                "ownerName": "",
                                "ingamename": "",
                                "group": "Save_Web_Game",
                                "cards": [],
                            }
                        ]
                    )
                ),
                encoding="utf-8",
            )
            accounts_path.write_text("[]", encoding="utf-8")

            stats = import_save_web_game_accounts(export_path, accounts_path)
            saved = json.loads(accounts_path.read_text(encoding="utf-8"))

        self.assertEqual(stats["imported"], 1)
        self.assertEqual(saved[0]["email"], "player@example.com")


if __name__ == "__main__":
    unittest.main()
