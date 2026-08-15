"""เทส: วางพรีเซ็ตพิกัดตรงตำแหน่งไหนก็ได้บนผัง

เดิม quick_add ใช้ macro_steps.append() คือต่อท้ายเส้นหลักอย่างเดียว ถ้าอยากได้พรีเซ็ต
ตรงกลางสคริปต์หรือในกิ่ง if ต้องไปแก้ไฟล์ JSON เอง ซึ่งเป็นเหตุผลที่ผู้ใช้ขอให้แก้
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web_app

PRESETS = [
    {"name": "Login: ช่อง Email", "x": 450, "y": 211},
    {"name": "ปุ่ม Close Ads", "x": 895, "y": 45},
]


def api(steps):
    a = web_app.Api.__new__(web_app.Api)
    a.macro_steps = steps
    a.current_profile = "t"
    a._push_log = lambda *a_, **k_: None
    a.get_presets = lambda: {"presets": PRESETS}
    return a


def tap(desc):
    return {"type": "tap", "x": "1", "y": "2", "desc": desc}


def iff(desc, then=None):
    return {"type": "if_image", "desc": desc, "then": then or [], "else": []}


def descs(lst):
    return [s.get("desc") for s in lst]


# ---------- วางตรงตำแหน่งที่ต้องการ ----------

def test_insert_preset_in_the_middle_of_the_main_line():
    a = api([tap("A"), tap("B")])
    r = a.flow_add_preset([1], "ปุ่ม Close Ads")

    assert r["ok"] is True
    assert descs(a.macro_steps) == ["A", "คลิก ปุ่ม Close Ads", "B"]
    assert (a.macro_steps[1]["x"], a.macro_steps[1]["y"]) == ("895", "45")
    assert a.macro_steps[1]["type"] == "tap"


def test_insert_preset_into_a_branch():
    """เคสที่ผู้ใช้ทำไม่ได้เลยก่อนหน้านี้"""
    a = api([iff("ถ้าเจอโฆษณา")])
    r = a.flow_add_preset([0, "then", 0], "ปุ่ม Close Ads")

    assert r["ok"] is True
    assert descs(a.macro_steps[0]["then"]) == ["คลิก ปุ่ม Close Ads"]


def test_insert_preset_at_the_front():
    a = api([tap("A")])
    a.flow_add_preset([0], "Login: ช่อง Email")
    assert descs(a.macro_steps)[0] == "คลิก Login: ช่อง Email"


def test_insert_preset_at_the_end():
    a = api([tap("A")])
    a.flow_add_preset([1], "Login: ช่อง Email")
    assert descs(a.macro_steps)[-1] == "คลิก Login: ช่อง Email"


def test_returns_path_so_the_editor_can_select_it():
    a = api([tap("A"), tap("B")])
    r = a.flow_add_preset([1], "ปุ่ม Close Ads")
    assert r["path"] == [1]


def test_unknown_preset_changes_nothing():
    a = api([tap("A")])
    r = a.flow_add_preset([0], "พรีเซ็ตที่ไม่มีอยู่")
    assert r["ok"] is False
    assert descs(a.macro_steps) == ["A"]


def test_bad_path_does_not_corrupt_the_script():
    a = api([tap("A")])
    r = a.flow_add_preset([9, "then", 0], "ปุ่ม Close Ads")
    assert r["ok"] is False
    assert descs(a.macro_steps) == ["A"]


def test_decimal_preset_coordinates_are_tappable():
    """พรีเซ็ตจริงเก็บพิกัดเป็นทศนิยม (เช่น 333.7) ส่วน ADB รับแต่จำนวนเต็ม
    ขั้นที่ได้ต้องรันแล้วกดที่พิกัดปัดเศษถูกต้อง ไม่ใช่พังเงียบ ๆ"""
    import macro_runner as M

    a = api([])
    a.get_presets = lambda: {"presets": [{"name": "ทศนิยม", "x": 333.7, "y": 201.6}]}
    a.flow_add_preset([0], "ทศนิยม")

    taps = []

    class Ctl:
        def capture_screenshot_bytes(self, d):
            return True, b"S"

        def tap(self, d, x, y):
            taps.append((x, y))
            return True, ""

    step = dict(a.macro_steps[0], delay=0)
    r = M.MacroRunner(Ctl(), [step], log_cb=lambda t, k="info": None, running_check=lambda: True)
    assert r._run_steps(":7555", None, r.steps, lambda **kw: None) == "completed"
    assert taps == [(334, 202)]


# ---------- ของเดิมต้องยังทำงาน ----------

def test_quick_add_still_appends_to_the_end():
    """มุมมองลิสต์ยังใช้ quick_add อยู่ ห้ามเปลี่ยนพฤติกรรมเดิม"""
    a = api([tap("A")])
    a.get_steps = lambda: {"steps": []}
    a.quick_add("ปุ่ม Close Ads")
    assert descs(a.macro_steps) == ["A", "คลิก ปุ่ม Close Ads"]


def test_quick_add_with_unknown_preset_is_harmless():
    a = api([tap("A")])
    a.get_steps = lambda: {"steps": []}
    a.quick_add("ไม่มีชื่อนี้")
    assert descs(a.macro_steps) == ["A"]


def test_real_presets_file_loads():
    """พรีเซ็ตจริงในเครื่องต้องอ่านได้และมีฟิลด์ครบ ไม่งั้นเมนูจะว่าง"""
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "presets.json")
    if not os.path.exists(p):
        pytest.skip("ไม่มี presets.json ในเครื่องนี้")
    data = json.load(open(p, encoding="utf-8")).get("presets", [])
    assert data, "presets.json ว่าง"
    for item in data:
        assert item.get("name") and "x" in item and "y" in item
