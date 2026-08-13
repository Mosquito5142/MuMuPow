"""เทสการย้ายบล็อกข้ามกิ่งบนผัง (flow_move_to)

เดิมผังย้ายบล็อกได้แค่สลับกับเพื่อนบ้านในลิสต์เดียวกัน ถ้าอยากเอาบล็อกที่ทำไว้แล้ว
ยัดเข้าเงื่อนไข if ต้องไปแก้ไฟล์ JSON เอง ซึ่งช้าและพลาดง่าย

จุดที่พลาดง่ายที่สุดคือ 'ดัชนีเลื่อน' เวลาย้ายภายในลิสต์เดียวกัน (ดึงออกก่อนแล้วค่อยแทรก
ทำให้ตำแหน่งปลายทางที่อยู่ข้างหลังเลื่อนมา 1 ช่อง) กับการย้ายบล็อกเข้าไปในกิ่งของตัวเอง
ซึ่งจะทำให้บล็อกนั้นหายไปทั้งก้อน
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web_app


def api(steps):
    a = web_app.Api.__new__(web_app.Api)
    a.macro_steps = steps
    a.current_profile = "t"
    a._run_log = []
    a._push_log = lambda *a_, **k_: None
    return a


def tap(desc):
    return {"type": "tap", "x": "1", "y": "2", "desc": desc}


def iff(desc, then=None, els=None):
    return {"type": "if_image", "desc": desc, "then": then or [], "else": els or []}


def descs(lst):
    return [s.get("desc") for s in lst]


# ---------- ย้ายเข้ากิ่ง (เคสหลักที่ผู้ใช้ต้องการ) ----------

def test_move_main_line_block_into_then_branch():
    a = api([iff("ถ้าเจอ"), tap("A"), tap("B")])
    r = a.flow_move_to([1], [0, "then", 0])

    assert r["ok"] is True
    assert descs(a.macro_steps) == ["ถ้าเจอ", "B"]
    assert descs(a.macro_steps[0]["then"]) == ["A"]


def test_move_into_else_branch():
    a = api([iff("ถ้าเจอ"), tap("A")])
    a.flow_move_to([1], [0, "else", 0])
    assert descs(a.macro_steps[0]["else"]) == ["A"]


def test_move_into_branch_that_already_has_blocks():
    a = api([iff("ถ้าเจอ", then=[tap("X"), tap("Y")]), tap("A")])
    a.flow_move_to([1], [0, "then", 1])          # แทรกกลางกิ่ง
    assert descs(a.macro_steps[0]["then"]) == ["X", "A", "Y"]


def test_move_block_out_of_branch_back_to_main_line():
    a = api([iff("ถ้าเจอ", then=[tap("A")]), tap("B")])
    a.flow_move_to([0, "then", 0], [2])
    assert descs(a.macro_steps[0]["then"]) == []
    assert descs(a.macro_steps) == ["ถ้าเจอ", "B", "A"]


def test_move_between_two_different_branches():
    a = api([iff("หนึ่ง", then=[tap("A")]), iff("สอง")])
    a.flow_move_to([0, "then", 0], [1, "else", 0])
    assert descs(a.macro_steps[0]["then"]) == []
    assert descs(a.macro_steps[1]["else"]) == ["A"]


def test_if_block_can_be_moved_with_its_children():
    """ย้ายบล็อกเงื่อนไขทั้งก้อน ลูกในกิ่งต้องติดไปด้วย"""
    a = api([tap("A"), iff("เงื่อนไข", then=[tap("ลูก1"), tap("ลูก2")])])
    a.flow_move_to([1], [0])
    assert a.macro_steps[0]["desc"] == "เงื่อนไข"
    assert descs(a.macro_steps[0]["then"]) == ["ลูก1", "ลูก2"]


# ---------- ดัชนีเลื่อนตอนย้ายในลิสต์เดียวกัน ----------

def test_move_down_within_same_list_lands_where_expected():
    a = api([tap("A"), tap("B"), tap("C")])
    a.flow_move_to([0], [2])          # เอา A ไปวางก่อน C
    assert descs(a.macro_steps) == ["B", "A", "C"]


def test_move_to_end_of_same_list():
    a = api([tap("A"), tap("B"), tap("C")])
    a.flow_move_to([0], [3])
    assert descs(a.macro_steps) == ["B", "C", "A"]


def test_move_up_within_same_list():
    a = api([tap("A"), tap("B"), tap("C")])
    a.flow_move_to([2], [0])
    assert descs(a.macro_steps) == ["C", "A", "B"]


def test_move_onto_itself_is_harmless():
    a = api([tap("A"), tap("B")])
    a.flow_move_to([0], [0])
    assert descs(a.macro_steps) == ["A", "B"]


# ---------- กันพัง ----------

def test_cannot_move_block_into_its_own_branch():
    """ถ้าปล่อยให้ทำ บล็อกจะถูกดึงออกมาแล้วไม่มีที่ให้วางกลับ = หายทั้งก้อน"""
    a = api([iff("เงื่อนไข", then=[tap("ลูก")])])
    r = a.flow_move_to([0], [0, "then", 0])

    assert r["ok"] is False
    assert descs(a.macro_steps) == ["เงื่อนไข"]          # ต้องยังอยู่ครบ
    assert descs(a.macro_steps[0]["then"]) == ["ลูก"]


def test_rejects_nesting_past_the_runtime_depth_limit():
    """ตัวรันข้ามกิ่งที่ลึกเกิน MAX_BRANCH_DEPTH — ต้องกันตั้งแต่ตอนแก้ผัง ไม่ใช่ไปเงียบตอนรัน"""
    deep = iff("ชั้นในสุด")
    for n in range(6, 0, -1):
        deep = iff(f"ชั้น{n}", then=[deep])
    a = api([deep, iff("ปลายทาง")])

    r = a.flow_move_to([0], [1, "then", 0])
    assert r["ok"] is False
    assert "เกิน" in r["error"]
    assert len(a.macro_steps) == 2                        # ไม่มีอะไรหาย
    assert a.macro_steps[0]["desc"] == "ชั้น1"            # ต้นทางยังอยู่ที่เดิม


def test_destination_index_shifts_when_source_removed_from_earlier_position():
    """ย้าย [0] เข้ากิ่งของบล็อกที่ index 1 — พอดึง [0] ออก บล็อกนั้นเลื่อนมาเป็น index 0
    ถ้าไม่ชดเชยดัชนีตรงนี้ จะไปแทรกผิดที่หรือพังทั้งคำสั่ง"""
    a = api([tap("A"), iff("เงื่อนไข"), tap("C")])
    r = a.flow_move_to([0], [1, "then", 0])

    assert r["ok"] is True
    assert descs(a.macro_steps) == ["เงื่อนไข", "C"]
    assert descs(a.macro_steps[0]["then"]) == ["A"]


def test_bad_paths_do_not_corrupt_the_script():
    a = api([tap("A"), tap("B")])
    for bad in ([], [99], [0, "then", 0]):
        a.flow_move_to(bad, [0])
    assert descs(a.macro_steps) == ["A", "B"]


def test_returns_new_path_of_the_moved_block():
    """UI ใช้ค่านี้เลือกบล็อกเดิมต่อหลังย้าย ผู้ใช้จะได้ทำงานต่อได้ทันที"""
    a = api([iff("ถ้าเจอ"), tap("A")])
    r = a.flow_move_to([1], [0, "then", 0])
    assert r["path"] == [0, "then", 0]


# ---------- ปุ่มลัด 'ย้ายเข้ากิ่ง' ----------

def test_branch_targets_lists_sibling_if_blocks():
    a = api([iff("ป๊อปอัพ"), tap("A"), iff("โฆษณา", then=[tap("x")])])
    got = a.flow_branch_targets([1])["targets"]

    paths = [t["path"] for t in got]
    assert [0, "then", 0] in paths
    assert [0, "else", 0] in paths
    assert [2, "then", 1] in paths        # ต่อท้ายของเดิมที่มี 1 ขั้น
    assert all("ป๊อปอัพ" in t["label"] or "โฆษณา" in t["label"] for t in got)


def test_branch_targets_excludes_itself():
    a = api([iff("ตัวเอง", then=[tap("x")])])
    assert a.flow_branch_targets([0])["targets"] == []


# ---------- ย้ายทีละหลายบล็อก (ช่วงต่อเนื่อง) ----------

def test_move_range_into_branch():
    """เคสจริง: สคริปต์ยาว ๆ อยากยกหลายขั้นเข้าเงื่อนไขทีเดียว"""
    a = api([iff("ถ้าเจอ"), tap("A"), tap("B"), tap("C"), tap("D")])
    r = a.flow_move_range([1], [3], [0, "then", 0])

    assert r["ok"] is True and r["count"] == 3
    assert descs(a.macro_steps) == ["ถ้าเจอ", "D"]
    assert descs(a.macro_steps[0]["then"]) == ["A", "B", "C"]


def test_move_range_keeps_original_order():
    a = api([tap("A"), tap("B"), tap("C"), iff("ปลายทาง")])
    a.flow_move_range([0], [2], [3, "then", 0])
    assert descs(a.macro_steps[0]["then"]) == ["A", "B", "C"]


def test_move_range_accepts_reversed_selection():
    """ผู้ใช้ shift+คลิกจากล่างขึ้นบนก็ต้องได้ผลเดียวกัน"""
    a = api([iff("ถ้าเจอ"), tap("A"), tap("B")])
    a.flow_move_range([2], [1], [0, "then", 0])
    assert descs(a.macro_steps[0]["then"]) == ["A", "B"]


def test_move_range_out_of_branch():
    a = api([iff("ถ้าเจอ", then=[tap("A"), tap("B"), tap("C")])])
    a.flow_move_range([0, "then", 0], [0, "then", 1], [1])
    assert descs(a.macro_steps[0]["then"]) == ["C"]
    assert descs(a.macro_steps) == ["ถ้าเจอ", "A", "B"]


def test_move_range_within_same_list_shifts_correctly():
    a = api([tap("A"), tap("B"), tap("C"), tap("D")])
    a.flow_move_range([0], [1], [4])          # ยก A,B ไปท้าย
    assert descs(a.macro_steps) == ["C", "D", "A", "B"]


def test_move_range_onto_itself_is_harmless():
    a = api([tap("A"), tap("B"), tap("C")])
    a.flow_move_range([0], [1], [1])          # ปลายทางตกกลางช่วงที่ย้าย
    assert descs(a.macro_steps) == ["A", "B", "C"]


def test_move_range_rejects_blocks_from_different_levels():
    a = api([iff("เงื่อนไข", then=[tap("ใน")]), tap("นอก")])
    r = a.flow_move_range([0, "then", 0], [1], [0])
    assert r["ok"] is False
    assert descs(a.macro_steps[0]["then"]) == ["ใน"]
    assert descs(a.macro_steps) == ["เงื่อนไข", "นอก"]


def test_move_range_cannot_drop_into_own_branch():
    a = api([tap("A"), iff("เงื่อนไข"), tap("B")])
    r = a.flow_move_range([0], [2], [1, "then", 0])
    assert r["ok"] is False
    assert len(a.macro_steps) == 3


def test_move_range_bad_input_does_not_corrupt():
    a = api([tap("A"), tap("B")])
    for s, e, d in (([], [1], [0]), ([0], [99], [0]), ([0], [1], [])):
        a.flow_move_range(s, e, d)
    assert descs(a.macro_steps) == ["A", "B"]


# ---------- เลขขั้นบนผัง ----------

def test_sibling_index_is_position_within_its_own_list():
    """ผังโชว์เลขขั้น = ตำแหน่งในลิสต์ตัวเอง +1 และ dropdown 'วนกลับไปทำขั้นไหน'
    ก็อ้างลิสต์เดียวกัน — ถ้าสองที่นี้นับคนละแบบ ผู้ใช้จะตั้งเป้าหมายวนกลับผิดขั้นโดยไม่รู้ตัว"""
    a = api([tap("A"), iff("เงื่อนไข", then=[tap("ใน1"), tap("ใน2")]), tap("C")])

    main = a.list_siblings([2])
    assert main["ok"] is True
    assert [s["idx"] for s in main["steps"]] == [0, 1, 2]
    assert [s["desc"] for s in main["steps"]] == ["A", "เงื่อนไข", "C"]
    assert main["current"] == 2

    branch = a.list_siblings([1, "then", 1])
    assert [s["idx"] for s in branch["steps"]] == [0, 1]
    assert [s["desc"] for s in branch["steps"]] == ["ใน1", "ใน2"]
    assert branch["current"] == 1


def test_retry_target_index_points_at_the_same_block_the_number_shows():
    """เป้าหมายวนกลับเก็บเป็น idx ดิบ (0-based) ส่วนที่โชว์ให้คนอ่านคือ idx+1
    เทสนี้ยึดความสัมพันธ์นั้นไว้ ไม่ให้ใครเผลอเปลี่ยนข้างใดข้างหนึ่ง"""
    a = api([tap("A"), tap("B"), tap("C")])
    steps = a.list_siblings([1])["steps"]
    shown = {s["idx"] + 1: s["desc"] for s in steps}   # เลขที่ผู้ใช้เห็นบนผัง -> บล็อกจริง
    assert shown == {1: "A", 2: "B", 3: "C"}
