"""เทสปุ่ม 'ตัดช่วง→ทำเป็นบล็อก' (web_app.extract_range_to_block):
ตัดช่วงขั้นในสคริปต์ยาว ๆ ที่ทำไว้แล้ว ออกไปเก็บเป็นชุดใหม่ แล้วแทนที่ด้วย run_set-block
เพื่อให้แบ่งบล็อกทีหลังได้โดยไม่ต้องสร้างสคริปต์ใหม่"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web_app


@pytest.fixture
def api(tmp_path, monkeypatch):
    """Api ที่ชี้ base_dir ไปโฟลเดอร์ชั่วคราว (กันเขียนทับ script_sets จริง) + 10 ขั้นตัวอย่าง"""
    (tmp_path / "script_sets").mkdir()
    monkeypatch.setattr(web_app, "base_dir", lambda: str(tmp_path))
    a = web_app.Api()
    a.macro_steps = [{"type": "tap", "x": str(i), "y": "0", "desc": f"ขั้น{i}"} for i in range(1, 11)]
    a._tmp = str(tmp_path)
    return a


def test_extract_creates_set_and_replaces_range_with_block(api):
    api.extract_range_to_block(3, 6, "เก็บของ", "กลับหน้าแรก", "2", True)

    ms = api.macro_steps
    assert len(ms) == 7                       # 10 - 4 + 1
    blk = ms[2]
    assert blk["type"] == "run_set" and blk["set"] == "เก็บของ"
    assert blk["block_on_fail"] == "home_retry"
    assert blk["block_home"] == "กลับหน้าแรก" and blk["block_retries"] == "2"
    assert ms[1]["desc"] == "ขั้น2" and ms[3]["desc"] == "ขั้น7"   # ขั้นรอบ ๆ ไม่ขยับผิด

    saved = json.load(open(os.path.join(api._tmp, "script_sets", "เก็บของ.json"), encoding="utf-8"))
    assert saved["name"] == "เก็บของ"
    assert [s["desc"] for s in saved["steps"]] == ["ขั้น3", "ขั้น4", "ขั้น5", "ขั้น6"]


def test_extract_without_block_makes_plain_run_set(api):
    api.extract_range_to_block(1, 3, "ล็อกอิน", make_block=False)
    blk = api.macro_steps[0]
    assert blk["type"] == "run_set" and blk["set"] == "ล็อกอิน"
    assert "block_on_fail" not in blk         # run_set ธรรมดา ไม่ใช่บล็อก


def test_extract_swaps_reversed_range_and_clamps(api):
    # ใส่กลับด้าน (6→3) ต้องสลับให้ถูก และปลายเกินก็ clamp
    api.extract_range_to_block(6, 3, "ก", "", "", True)
    saved = json.load(open(os.path.join(api._tmp, "script_sets", "ก.json"), encoding="utf-8"))
    assert [s["desc"] for s in saved["steps"]] == ["ขั้น3", "ขั้น4", "ขั้น5", "ขั้น6"]


def test_extract_rejects_bad_input_without_changing_steps(api):
    before = list(api.macro_steps)
    api.extract_range_to_block(3, 6, "", "", "", True)      # ไม่มีชื่อ
    assert api.macro_steps == before
    api.extract_range_to_block("x", "y", "ชื่อ", "", "", True)  # ช่วงไม่ใช่ตัวเลข
    assert api.macro_steps == before


def test_get_load_save_script_set_api(api):
    # ทดสอบ save_script_set_steps -> get_script_set -> load_set_to_editor
    new_steps = [{"type": "tap", "x": "100", "y": "200", "desc": "สุ่มวงล้อ"}]
    res_save = api.save_script_set_steps("สุ่มวงล้อ", new_steps)
    assert res_save["ok"] is True

    res_get = api.get_script_set("สุ่มวงล้อ")
    assert res_get["ok"] is True
    assert res_get["name"] == "สุ่มวงล้อ"
    assert res_get["steps"] == new_steps

    res_load = api.load_set_to_editor("สุ่มวงล้อ")
    assert res_load["ok"] is True
    assert api.macro_steps == new_steps

