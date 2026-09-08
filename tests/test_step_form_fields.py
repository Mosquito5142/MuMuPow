"""เทสฟอร์มแก้ขั้นตอน: ค่าต้องไม่หาย + ทุกช่องพิกัดต้องเลือกจากจอได้

บั๊กที่เคยเกิด (และเทสนี้กันไม่ให้กลับมา):
flowSelect() ไล่พิมพ์ชื่อฟิลด์เองทีละตัวตอนส่งเข้า fillStepForm แล้วรายการนั้นตกหล่นไป 9 ตัว
(points/submit/refresh/box/mode/tap_mode/interval/radius/click) ผลคือในโหมดผังงาน
ช่องพวกนั้นขึ้นว่างเสมอ แล้วพอกด "อัปเดตขั้นตอน" -> collectStepPatch อ่านช่องว่าง
-> เขียนทับค่าจริงหายหมด (ปุ่ม "เก็บพิกัดตัวเลือกจากจอ" เลยดูเหมือนไม่ทำงาน)

วิธีกัน: ห้ามมีรายการฟิลด์ที่ต้องดูแลคู่ขนานอีก — ต้องส่งทั้งอ็อบเจกต์ไปเลย
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web_app

WEBUI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "webui")


def _read(name):
    with open(os.path.join(WEBUI, name), encoding="utf-8") as f:
        return f.read()


def _code_only(src):
    """ตัดคอมเมนต์ // ออก — กันเทสไปแมตช์ข้อความในคอมเมนต์แทนโค้ดจริง"""
    return "\n".join(l for l in src.split("\n") if not l.strip().startswith("//"))


APP = _code_only(_read("app.js"))
FLOW = _code_only(_read("flow.js"))
HTML = _read("index.html")

# ช่องพิกัด/ขนาด -> ฟังก์ชันเลือกจากจอที่ต้องผูกไว้
PICKERS = {
    "sfX": "pickXY(", "sfY": "pickXY(",
    "sfX2": "pickXY(", "sfY2": "pickXY(",
    "sfPoints": "pickPoints(",
    "sfSubmit": "pickPoint(",
    "sfRefresh": "pickPoint(",
    "sfBox": "pickSize(",
    "sfRadius": "pickRadius(",
}


# ---------- บั๊กค่าหาย ----------

def test_flow_select_passes_the_whole_step_not_a_hand_written_list():
    """หัวใจ: flowSelect ต้องไม่ไล่พิมพ์ชื่อฟิลด์เอง"""
    m = re.search(r"fillStepForm\(([^;]*)\)", FLOW)
    assert m, "ไม่เจอการเรียก fillStepForm ใน flow.js"
    arg = m.group(1)
    assert "Object.assign" in arg, f"flowSelect ต้องส่งทั้งอ็อบเจกต์ ไม่ใช่ literal: {arg[:120]}"
    # ห้ามมี object literal ที่ไล่จับคู่ฟิลด์ทีละตัว เช่น  x:s.x, y:s.y
    assert not re.search(r"\w+\s*:\s*s\.\w+", arg), \
        f"เจอการไล่พิมพ์ชื่อฟิลด์เองใน flowSelect — บั๊กเดิมกลับมาแล้ว: {arg[:160]}"


def test_list_view_also_passes_the_whole_step():
    assert re.search(r"fillStepForm\(st\.raw\s*\|\|\s*st\)", APP), \
        "selectStep ต้องส่งอ็อบเจกต์ขั้นตอนทั้งก้อนเข้า fillStepForm"


def test_every_field_the_form_reads_survives_a_round_trip():
    """ทุกช่องที่ fillStepForm อ่าน ต้องถูก collectStepPatch ส่งกลับได้ ไม่มีตัวไหนอ่านได้อย่างเดียว"""
    read_ids = set(re.findall(r"g\('(sf[A-Za-z0-9]+)'\)", APP))
    patch_src = APP[APP.find("function collectStepPatch"):]
    written_ids = set(re.findall(r"g\('(sf[A-Za-z0-9]+)'\)", patch_src))
    # sfBlockOn/sfBlockOpts/sfClick อ่านผ่าน checkbox ไม่ใช่ g() — ยกเว้นให้
    skip = {"sfType", "sfTextLabel", "sfBlockOn", "sfBlockOpts", "sfClick"}
    missing = (read_ids - written_ids) - skip
    assert not missing, f"ช่องพวกนี้เติมค่าได้แต่บันทึกกลับไม่ได้: {sorted(missing)}"


def test_the_nine_fields_that_used_to_vanish_are_in_the_form():
    """ฟิลด์ที่เคยตกหล่น — ต้องยังมีช่องอยู่จริงในฟอร์ม"""
    for fid in ("sfPoints", "sfSubmit", "sfRefresh", "sfBox", "sfMode",
                "sfTapMode", "sfInterval", "sfRadius", "sfClick"):
        assert 'id="%s"' % fid in HTML, f"ไม่มีช่อง {fid} ในฟอร์ม"
        assert "g('%s')" % fid in APP or "getElementById('%s')" % fid in APP, \
            f"{fid} ไม่ถูกอ่าน/เขียนใน app.js"


# ---------- ตัวเลือกพิกัดจากจอ ----------

def test_every_coordinate_field_has_a_screen_picker():
    """ทุกช่องพิกัด/ขนาดต้องกดเลือกจากจอได้ ไม่ต้องพิมพ์เลข"""
    for fid, fn in PICKERS.items():
        assert fn in HTML, f"ช่อง {fid} ยังไม่มีปุ่มเลือกจากจอ (ต้องเรียก {fn})"


def test_pickers_are_wired_to_the_right_inputs():
    for call in ("pickXY('sfX','sfY')", "pickXY('sfX2','sfY2')",
                 "pickPoints('sfPoints')", "pickSize('sfBox')", "pickRadius('sfRadius')"):
        assert call in HTML, f"ไม่เจอปุ่มที่เรียก {call}"
    assert "pickPoint('sfSubmit'" in HTML
    assert "pickPoint('sfRefresh'" in HTML


def test_every_picker_the_html_calls_actually_exists():
    """กันปุ่มตายเงียบ — กดแล้วไม่มีอะไรเกิดขึ้นเพราะฟังก์ชันไม่มีจริง"""
    called = set(re.findall(r'onclick="(pick[A-Za-z]+)\(', HTML))
    assert called, "ไม่เจอปุ่มเลือกพิกัดใน index.html เลย"
    for fn in sorted(called):
        assert re.search(r"(async\s+)?function\s+%s\s*\(" % fn, FLOW), \
            f"index.html เรียก {fn}() แต่ flow.js ไม่มีฟังก์ชันนี้"


def test_pickers_save_through_the_shared_update_path():
    """ต้องบันทึกผ่าน updateStep() ซึ่งแยกทางให้ 2 โหมดเอง ไม่ใช่ยิง API ตรง"""
    assert "async function _pickCommit()" in FLOW
    block = FLOW[FLOW.find("async function _pickCommit()"):][:400]
    assert "updateStep()" in block, "_pickCommit ต้องเรียก updateStep() (ตัวแยกทางบันทึก 2 โหมด)"


def test_pickers_live_outside_the_flow_only_panel():
    """ปุ่มต้องอยู่ในฟอร์ม (ใช้ได้ทั้ง 2 โหมด) ไม่ใช่ใน #flowActions ที่โผล่เฉพาะโหมดผังงาน"""
    i = HTML.find('id="flowActions"')
    assert i > 0
    for call in ("pickXY(", "pickPoints(", "pickSize(", "pickRadius("):
        j = HTML.find(call)
        assert j >= 0 and j < i, f"{call} ต้องอยู่ในฟอร์มก่อน #flowActions ไม่งั้นโหมดลิสต์จะไม่เห็นปุ่ม"


# ---------- ฟิลด์ของ answer_quiz ต้องครบทั้ง 2 ฝั่ง ----------

def test_fallback_type_list_covers_every_step_type():
    """ลิสต์ชนิดขั้นสำรอง (ใช้ตอนเปิดในเบราว์เซอร์ธรรมดา) ต้องครบเท่า backend

    เป็นบั๊กคลาสเดียวกับ flowSelect: มีรายการที่ต้องดูแลคู่ขนานแล้วลืมมาต่อ
    เคยตกหล่น answer_quiz/story_auto/tap_until_image/tap_around_until_image
    """
    blk = APP[APP.find("FALLBACK_TYPE_OPTIONS"):]
    blk = blk[:blk.find("];")]
    fe = set(re.findall(r"value:'(\w+)'", blk))
    be = set(web_app.Api.STEP_FIELDS.keys())
    assert not (be - fe), f"ลิสต์สำรองขาดชนิดขั้น: {sorted(be - fe)}"
    assert not (fe - be), f"ลิสต์สำรองมีชนิดขั้นที่ backend ไม่รู้จัก: {sorted(fe - be)}"


def test_answer_quiz_fields_match_between_backend_and_form():
    be = set(web_app.Api.STEP_FIELDS["answer_quiz"])
    for k in ("points", "submit", "refresh", "box", "mode"):
        assert k in be, f"backend STEP_FIELDS['answer_quiz'] ขาด {k}"
    m = re.search(r"answer_quiz:\[([^\]]*)\]", APP)
    assert m, "ไม่เจอ STEP_FIELD_MAP.answer_quiz ใน app.js"
    fe = m.group(1)
    for k in ("Points", "Submit", "Refresh", "Box", "Mode"):
        assert k in fe, f"STEP_FIELD_MAP.answer_quiz ขาด {k}"
