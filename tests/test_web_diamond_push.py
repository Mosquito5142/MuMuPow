"""เทสว่า webui ส่งเพชรเข้าเว็บ Save Web Game อัตโนมัติตอนจบรัน เหมือน Tkinter
(บั๊กเดิม: _persist_diamonds เขียนแค่ไฟล์+accounts.json ไม่เคยยิงเข้าเว็บเลย ทั้งที่ diamond_ocr.json
ตั้ง auto_push=true + web_base_url ไว้แล้ว — ต้องไปกดปุ่ม 'ส่งเพชรขึ้นเว็บ' เองทุกครั้ง)
และชื่อไฟล์ export ต้องอ่านจาก cfg['export_path'] ให้ตรงกับ Tkinter (เดิม hardcode 'diamonds_export.json')"""
import json
import os
import shutil
import sys
import tempfile
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web_app


def _api(tmp, cfg):
    api = web_app.Api()
    tmp_acc = os.path.join(tmp, "accounts.json")
    json.dump([{"email": "a@x.com", "checked": True, "name": "acc0"}], open(tmp_acc, "w", encoding="utf-8"))
    api._accounts_path = lambda: tmp_acc
    api._load_diamond_cfg = lambda: cfg
    return api


ROWS = [
    {"email": "a@x.com", "name": "acc0", "save_web_game_id": "web-1", "diamonds": 3631,
     "device": ":7555", "time": "2026-07-15 10:00:00"},
    {"email": "b@x.com", "name": "acc1", "save_web_game_id": "", "diamonds": 100,
     "device": ":7556", "time": "2026-07-15 10:00:01"},  # ไม่มี id เว็บ -> ต้องไม่ถูกส่ง
]


def test_persist_diamonds_pushes_to_web_when_configured():
    tmp = tempfile.mkdtemp()
    try:
        cfg = {"export_path": "diamond_export.json", "web_base_url": "https://web.test/", "auto_push": True}
        api = _api(tmp, cfg)
        logs = []
        captured = {}

        def fake_push(url, updates, **kw):
            captured["url"] = url
            captured["updates"] = updates
            return {"web-1": (True, "ok")}, {"sent": 1, "failed": 0}

        with unittest.mock.patch.object(web_app, "base_dir", lambda: tmp), \
             unittest.mock.patch("save_web_game_import.push_diamonds_to_web", side_effect=fake_push):
            api._persist_diamonds(ROWS, lambda t, k="info": logs.append((k, t)))

        assert captured.get("url") == "https://web.test/"
        # ส่งเฉพาะแถวที่มี save_web_game_id — แถวที่ไม่มี id ต้องไม่หลุดไป
        assert len(captured["updates"]) == 1
        u = captured["updates"][0]
        assert u["id"] == "web-1"
        assert u["diamonds"] == 3631
        assert u["lastFarmDate"]   # ต้องส่งวันที่ฟาร์มไปด้วย เหมือน Tkinter
    finally:
        shutil.rmtree(tmp)


def test_export_filename_comes_from_config_not_hardcoded():
    tmp = tempfile.mkdtemp()
    try:
        cfg = {"export_path": "diamond_export.json", "web_base_url": "", "auto_push": False}
        api = _api(tmp, cfg)
        with unittest.mock.patch.object(web_app, "base_dir", lambda: tmp):
            api._persist_diamonds(ROWS, lambda t, k="info": None)
        assert os.path.exists(os.path.join(tmp, "diamond_export.json"))
        # ชื่อเดิมที่ hardcode ไว้ (มี s เกิน) ต้องไม่ถูกสร้างอีก
        assert not os.path.exists(os.path.join(tmp, "diamonds_export.json"))
    finally:
        shutil.rmtree(tmp)


def test_no_push_when_auto_push_disabled():
    tmp = tempfile.mkdtemp()
    try:
        cfg = {"export_path": "diamond_export.json", "web_base_url": "https://web.test/", "auto_push": False}
        api = _api(tmp, cfg)
        called = []
        with unittest.mock.patch.object(web_app, "base_dir", lambda: tmp), \
             unittest.mock.patch("save_web_game_import.push_diamonds_to_web",
                                 side_effect=lambda *a, **k: called.append(1)):
            api._persist_diamonds(ROWS, lambda t, k="info": None)
        assert called == []
    finally:
        shutil.rmtree(tmp)


def test_no_push_when_url_missing_but_still_writes_file_and_accounts():
    tmp = tempfile.mkdtemp()
    try:
        cfg = {"export_path": "diamond_export.json", "web_base_url": "", "auto_push": True}
        api = _api(tmp, cfg)
        called = []
        with unittest.mock.patch.object(web_app, "base_dir", lambda: tmp), \
             unittest.mock.patch("save_web_game_import.push_diamonds_to_web",
                                 side_effect=lambda *a, **k: called.append(1)):
            api._persist_diamonds(ROWS, lambda t, k="info": None)
        assert called == []                                   # ไม่ยิงเน็ตเวิร์กตอนไม่มี URL
        assert os.path.exists(os.path.join(tmp, "diamond_export.json"))  # แต่ยังเขียนไฟล์ปกติ
        accts = json.load(open(api._accounts_path(), encoding="utf-8"))
        assert accts[0]["diamonds"] == 3631                   # และยังอัปเดตบัญชีปกติ
    finally:
        shutil.rmtree(tmp)


def test_push_failure_does_not_break_run():
    """เว็บล่ม/เน็ตพัง ต้องไม่ทำให้ทั้งรอบรันพัง — แค่ log ไว้ (ไฟล์+บัญชีต้องเขียนสำเร็จไปแล้วก่อนหน้า)"""
    tmp = tempfile.mkdtemp()
    try:
        cfg = {"export_path": "diamond_export.json", "web_base_url": "https://web.test/", "auto_push": True}
        api = _api(tmp, cfg)
        logs = []

        def boom(*a, **k):
            raise RuntimeError("connection refused")

        with unittest.mock.patch.object(web_app, "base_dir", lambda: tmp), \
             unittest.mock.patch("save_web_game_import.push_diamonds_to_web", side_effect=boom):
            api._persist_diamonds(ROWS, lambda t, k="info": logs.append((k, t)))

        assert os.path.exists(os.path.join(tmp, "diamond_export.json"))
        accts = json.load(open(api._accounts_path(), encoding="utf-8"))
        assert accts[0]["diamonds"] == 3631
        assert any(k == "err" and "connection refused" in t for k, t in logs)
    finally:
        shutil.rmtree(tmp)
