import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import save_web_game_import as swg
from save_web_game_import import (
    SAVE_WEB_GAME_EXPORT_SCHEMA,
    import_save_web_game_accounts,
    match_accounts_to_web,
    merge_save_web_game_accounts,
    push_diamonds_to_web,
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


class _FakeResp:
    def __init__(self, data=b'{"success": true}'):
        self._data = data

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class PushDiamondsToWebTests(unittest.TestCase):
    """ทดสอบการยิงอัปเดตเพชรเข้าเว็บ (PUT /api/accounts) โดย stub urllib.request.urlopen"""

    def test_puts_each_account_with_correct_url_method_and_body(self):
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append({
                "url": req.full_url,
                "method": req.get_method(),
                "body": json.loads(req.data.decode("utf-8")),
            })
            return _FakeResp()

        updates = [
            {"id": "necfaaroh", "diamonds": 3631, "lastFarmDate": "2026-06-21"},
            {"id": "abc123", "diamonds": 100, "lastFarmDate": "2026-06-21"},
        ]
        with mock.patch.object(swg.urllib.request, "urlopen", fake_urlopen):
            results, stats = push_diamonds_to_web("https://app.vercel.app/", updates)

        self.assertEqual(stats, {"sent": 2, "failed": 0})
        self.assertTrue(all(ok for ok, _ in results.values()))
        # trailing slash stripped, endpoint appended
        self.assertEqual({c["url"] for c in calls}, {"https://app.vercel.app/api/accounts"})
        self.assertEqual({c["method"] for c in calls}, {"PUT"})
        bodies = {c["body"]["id"]: c["body"] for c in calls}
        self.assertEqual(
            bodies["necfaaroh"],
            {"id": "necfaaroh", "diamonds": 3631, "lastFarmDate": "2026-06-21"},
        )

    def test_no_base_url_sends_nothing(self):
        results, stats = push_diamonds_to_web("", [{"id": "x", "diamonds": 1}])
        self.assertEqual(results, {})
        self.assertEqual(stats, {"sent": 0, "failed": 0})

    def test_updates_without_id_are_not_sent(self):
        def boom(*a, **k):
            raise AssertionError("urlopen should not be called when no valid ids")

        with mock.patch.object(swg.urllib.request, "urlopen", boom):
            results, stats = push_diamonds_to_web("https://x", [{"diamonds": 5}])
        self.assertEqual(stats, {"sent": 0, "failed": 0})

    def test_http_error_is_reported_as_failed(self):
        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 500, "Server Error", {}, None)

        with mock.patch.object(swg.urllib.request, "urlopen", fake_urlopen):
            results, stats = push_diamonds_to_web("https://x", [{"id": "id1", "diamonds": 7}])

        self.assertEqual(stats, {"sent": 0, "failed": 1})
        self.assertFalse(results["id1"][0])
        self.assertIn("HTTP 500", results["id1"][1])


class MatchAccountsToWebTests(unittest.TestCase):
    """ทดสอบการจับคู่บัญชี MuMuPow กับเว็บด้วยชื่อ เพื่อ backfill save_web_game_id"""

    def test_matches_by_title_then_ingamename_and_skips_existing(self):
        web = [
            {"id": "necfaaroh", "title": "คิเสะ&อาคาชิ ปลุก6 มอส", "ingamename": "101312319"},
            {"id": "muxxyufce", "title": "ไก่อาคาชิ 10312140122 มอส", "ingamename": "10312140122"},
            {"id": "wid3", "title": "Some Title", "ingamename": "Daikisan"},
        ]
        mumupow = [
            {"email": "a@x.com", "name": "คิเสะ&อาคาชิ ปลุก6 มอส"},  # match by title
            {"email": "b@x.com", "name": "Daikisan"},                # match by ingamename
            {"email": "c@x.com", "name": "ไก่อาคาชิ 10312140122 มอส", "save_web_game_id": "already"},  # skip
            {"email": "d@x.com", "name": "ไม่มีในเว็บ"},              # no match
        ]
        proposals = match_accounts_to_web(mumupow, web)
        by_email = {p["email"]: p for p in proposals}
        self.assertEqual(set(by_email), {"a@x.com", "b@x.com"})
        self.assertEqual(by_email["a@x.com"]["web_id"], "necfaaroh")
        self.assertEqual(by_email["a@x.com"]["by"], "title")
        self.assertEqual(by_email["b@x.com"]["web_id"], "wid3")
        self.assertEqual(by_email["b@x.com"]["by"], "ingamename")

    def test_one_to_one_does_not_reuse_a_web_id(self):
        web = [{"id": "only1", "title": "Dup", "ingamename": ""}]
        mumupow = [{"email": "a@x.com", "name": "Dup"}, {"email": "b@x.com", "name": "Dup"}]
        proposals = match_accounts_to_web(mumupow, web)
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["email"], "a@x.com")

    def test_normalizes_whitespace_and_case(self):
        web = [{"id": "w", "title": "  Hello   World ", "ingamename": ""}]
        proposals = match_accounts_to_web([{"email": "a@x.com", "name": "hello world"}], web)
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["web_id"], "w")


if __name__ == "__main__":
    unittest.main()
