"""เทสว่า 'แคปเพชรแมนนวล' บน webui จับคู่จอ↔บัญชีก่อนอ่าน แล้วส่งเข้าเว็บทันที (เหมือน Tkinter)

บั๊กเดิม: read_diamond_manual เรียก _read_diamond(dev, None) → row ไม่มี save_web_game_id →
_auto_push_diamonds กรองทิ้งหมด → ไม่ส่งเข้าเว็บเลย (ต่างจาก Tkinter ที่จับคู่บัญชีแล้ว push ทันที)
"""
import json
import os
import sys
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web_app


class FakeController:
    def capture_screenshot_bytes(self, device):
        return True, b"SCREEN"

    def read_number_tesseract(self, data, region):
        return True, 4200, "4200"   # อ่านได้ 4200 เพชรเสมอ


def _api(tmp, accounts):
    api = web_app.Api()
    path = os.path.join(tmp, "accounts.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(accounts, f, ensure_ascii=False)
    api._accounts_path = lambda: path
    api.controller = FakeController()
    api.devices = [":16384", ":16416"]
    api.selected = {":16384", ":16416"}
    return api


CFG = {"region": {"x": 0, "y": 0, "w": 40, "h": 20}, "verify_name": False,
       "export_path": "diamond_export.json", "web_base_url": "https://web.test/", "auto_push": True}


def test_manual_capture_pairs_accounts_and_pushes_to_web(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "base_dir", lambda: str(tmp_path))
    monkeypatch.setattr(web_app, "find_tesseract", lambda: "tesseract.exe", raising=False)
    # จอ :16384 เคยรันบัญชี a (มี id เว็บ), :16416 เคยรันบัญชี b
    accounts = [
        {"email": "a@x.com", "save_web_game_id": "web-a", "last_device": ":16384", "checked": True},
        {"email": "b@x.com", "save_web_game_id": "web-b", "last_device": ":16416", "checked": True},
    ]
    api = _api(str(tmp_path), accounts)
    api._load_diamond_cfg = lambda: CFG

    captured = {}

    def fake_push(url, updates, **kw):
        captured["url"] = url
        captured["updates"] = updates
        return {u["id"]: (True, "ok") for u in updates}, {"sent": len(updates), "failed": 0}

    import macro_runner
    monkeypatch.setattr(macro_runner, "find_tesseract", lambda: "tesseract.exe")
    with unittest.mock.patch("save_web_game_import.push_diamonds_to_web", side_effect=fake_push):
        res = api.read_diamond_manual()

    assert res["ok"] and len(res["rows"]) == 2
    # ทุกแถวต้องมี save_web_game_id (จับคู่บัญชีสำเร็จ) — ไม่ใช่ค่าว่างเหมือนตอนส่ง account=None
    assert all(r["save_web_game_id"] for r in res["rows"])
    # ต้อง push เข้าเว็บทั้ง 2 บัญชี
    assert captured.get("url") == "https://web.test/"
    ids = sorted(u["id"] for u in captured["updates"])
    assert ids == ["web-a", "web-b"]
    assert all(u["diamonds"] == 4200 for u in captured["updates"])


def test_manual_capture_falls_back_to_checked_accounts_by_index(tmp_path, monkeypatch):
    """ไม่เคยรัน (ไม่มี last_device) → ใช้บัญชีที่ติ๊กไว้ตามลำดับจอ (เหมือน fallback ของ Tkinter)"""
    monkeypatch.setattr(web_app, "base_dir", lambda: str(tmp_path))
    accounts = [
        {"email": "a@x.com", "save_web_game_id": "web-a", "checked": True},
        {"email": "b@x.com", "save_web_game_id": "web-b", "checked": True},
    ]
    api = _api(str(tmp_path), accounts)
    api._load_diamond_cfg = lambda: CFG
    import macro_runner
    monkeypatch.setattr(macro_runner, "find_tesseract", lambda: "tesseract.exe")

    captured = {}
    with unittest.mock.patch("save_web_game_import.push_diamonds_to_web",
                             side_effect=lambda url, updates, **k: (captured.update(updates=updates) or ({}, {"sent": len(updates), "failed": 0}))):
        api.read_diamond_manual()
    assert sorted(u["id"] for u in captured["updates"]) == ["web-a", "web-b"]
