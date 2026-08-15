"""เทส: แทรก 'ชุดคำสั่งย่อย' ลงผังตรงตำแหน่งที่ต้องการ

เดิมต้องเพิ่มบล็อก run_set เปล่าแล้วพิมพ์ชื่อชุดเองให้ตรงเป๊ะ — พิมพ์ผิดตัวเดียว
ตอนรันจะเจอ 'ไม่พบชุดคำสั่ง' แล้วขั้นนั้นถูกข้ามไปเงียบ ๆ
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web_app

SETS = [{"name": "กลับหน้าแรก", "count": 7},
        {"name": "ส่งรถบัส", "count": 7},
        {"name": "ข้ามhotzone", "count": 7}]


def api(steps):
    a = web_app.Api.__new__(web_app.Api)
    a.macro_steps = steps
    a.current_profile = "t"
    a._push_log = lambda *a_, **k_: None
    a.list_script_sets = lambda: {"sets": SETS}
    return a


def tap(desc):
    return {"type": "tap", "x": "1", "y": "2", "desc": desc}


def iff(desc):
    return {"type": "if_image", "desc": desc, "then": [], "else": []}


def descs(lst):
    return [s.get("desc") for s in lst]


# ---------- แทรกแบบธรรมดา ----------

def test_insert_set_in_the_middle():
    a = api([tap("A"), tap("B")])
    r = a.flow_add_set([1], "ส่งรถบัส")

    assert r["ok"] is True
    s = a.macro_steps[1]
    assert s["type"] == "run_set" and s["set"] == "ส่งรถบัส"
    assert descs(a.macro_steps) == ["A", "ใช้ชุด: ส่งรถบัส", "B"]


def test_insert_set_into_a_branch():
    a = api([iff("ถ้าเจอ")])
    r = a.flow_add_set([0, "then", 0], "ข้ามhotzone")
    assert r["ok"] is True
    assert a.macro_steps[0]["then"][0]["set"] == "ข้ามhotzone"


def test_plain_insert_is_not_a_block():
    a = api([])
    a.flow_add_set([0], "ส่งรถบัส")
    assert "block_on_fail" not in a.macro_steps[0]


# ---------- แทรกเป็นบล็อกกันพัง ----------

def test_insert_as_crash_proof_block():
    a = api([])
    a.flow_add_set([0], "ส่งรถบัส", as_block=True, block_home="กลับหน้าแรก")

    s = a.macro_steps[0]
    assert s["block_on_fail"] == "home_retry"
    assert s["block_home"] == "กลับหน้าแรก"
    assert s["desc"] == "บล็อก: ส่งรถบัส"


def test_block_retries_can_be_set():
    a = api([])
    a.flow_add_set([0], "ส่งรถบัส", as_block=True, block_retries=5)
    assert a.macro_steps[0]["block_retries"] == 5


def test_blank_retries_falls_back_to_runner_default():
    """เว้นว่าง = ไม่เขียนคีย์ลงไฟล์ ให้ตัวรันใช้ค่าเริ่มต้น (3) เอง
    ถ้าเผลอเขียน null/ว่างลงไป ตัวรันจะตีเป็น 0 รอบ = ไม่ลองใหม่เลย"""
    a = api([])
    a.flow_add_set([0], "ส่งรถบัส", as_block=True, block_retries="")
    assert "block_retries" not in a.macro_steps[0]


def test_block_without_home_set_is_still_valid():
    a = api([])
    a.flow_add_set([0], "ส่งรถบัส", as_block=True, block_home="")
    assert "block_home" not in a.macro_steps[0]
    assert a.macro_steps[0]["block_on_fail"] == "home_retry"


# ---------- กันพิมพ์ผิด ----------

def test_unknown_set_is_refused():
    """จุดสำคัญ: ชื่อที่ไม่มีจริงต้องไม่ถูกแทรก ไม่งั้นตอนรันจะข้ามขั้นนั้นเงียบ ๆ"""
    a = api([tap("A")])
    r = a.flow_add_set([0], "ชุดที่ไม่มีอยู่")
    assert r["ok"] is False
    assert descs(a.macro_steps) == ["A"]


def test_blank_name_is_refused():
    a = api([tap("A")])
    assert a.flow_add_set([0], "   ")["ok"] is False
    assert len(a.macro_steps) == 1


def test_bad_path_does_not_corrupt_the_script():
    a = api([tap("A")])
    r = a.flow_add_set([9, "then", 0], "ส่งรถบัส")
    assert r["ok"] is False
    assert descs(a.macro_steps) == ["A"]


def test_returns_path_for_the_editor_to_select():
    a = api([tap("A"), tap("B")])
    assert a.flow_add_set([2], "ส่งรถบัส")["path"] == [2]


# ---------- ตัวรันต้องรู้จักชุดที่แทรกเข้าไป ----------

def test_inserted_set_actually_expands_at_run_time():
    """แทรกแล้วต้องคลี่เป็นขั้นจริงตอนรัน ไม่ใช่แค่ดูดีบนผัง"""
    import macro_runner as M

    a = api([])
    a.flow_add_set([0], "ส่งรถบัส")

    sets = {"ส่งรถบัส": [{"type": "tap", "x": "9", "y": "9", "delay": 0}]}
    r = M.MacroRunner(None, a.macro_steps, log_cb=lambda t, k="info": None, script_sets=sets)

    assert [s["type"] for s in r.steps] == ["tap"]      # run_set ถูกคลี่แบนแล้ว
    assert r.steps[0]["x"] == "9"


def test_inserted_block_is_kept_as_a_block_at_run_time():
    import macro_runner as M

    a = api([])
    a.flow_add_set([0], "ส่งรถบัส", as_block=True, block_home="กลับหน้าแรก")

    sets = {"ส่งรถบัส": [{"type": "tap", "x": "9", "y": "9", "delay": 0}],
            "กลับหน้าแรก": [{"type": "keyevent", "code": 4, "delay": 0}]}
    r = M.MacroRunner(None, a.macro_steps, log_cb=lambda t, k="info": None, script_sets=sets)

    blk = r.steps[0]
    assert M.MacroRunner._is_block(blk)                # ไม่โดนคลี่แบน
    assert len(blk["_block_steps"]) == 1
    assert len(blk["_home_steps"]) == 1                # ชุดกู้ถูก resolve ไว้แล้ว
