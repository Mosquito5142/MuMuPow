"""ทดสอบ find_highlighted_stage: หา 'ด่านที่ถูกไฮไลท์' บนหน้าเลือกด่านโดยไม่พึ่ง AI

หลักการที่ทดสอบ: กรอบเลือกเป็นเหลือง UI สว่างจัด (V≈254) แยกออกจากเหลืองในภาพศิลป์
(V≤243) ได้ด้วย threshold V สูง แล้วจับ 'เส้นกรอบ [' ที่สูงและบาง (ต่างจากดาว/ไอคอนกลม)
"""
import numpy as np
import cv2

from mumu_controller import find_highlighted_stage, find_swipe_glow


def _png(img):
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _base_map(w=960, h=540):
    """พื้นหลังหน้าเลือกด่านจำลอง (ฟ้าอ่อน)"""
    return np.full((h, w, 3), (230, 220, 200), dtype=np.uint8)


def _put_ui_yellow_bracket(img, x, y, bh=62, arm=25, side="left"):
    """วาดกรอบเลือกสีเหลือง UI สว่างจัด (BGR ที่ให้ HSV≈(30,150,254)) รูปตัว [ หรือ ]"""
    color = (80, 232, 255)  # BGR -> เหลืองสว่าง V สูง
    spine_x = x if side == "left" else x + arm
    cv2.rectangle(img, (spine_x, y), (spine_x + 4, y + bh), color, -1)   # แกนตั้ง
    ax = x if side == "left" else x  # แขนยื่นเข้าด้านการ์ด
    cv2.rectangle(img, (x, y), (x + arm, y + 5), color, -1)              # แขนบน
    cv2.rectangle(img, (x, y + bh - 5), (x + arm, y + bh), color, -1)    # แขนล่าง


def _put_warm_artwork(img, x, y, w=180, h=110):
    """ภาพประกอบด่านโทนส้ม/เหลือง (V ต่ำกว่ากรอบ UI) — ตัวหลอก find_yellow_frame แบบเดิม"""
    # HSV≈(26,105,238) => เหลืองอมส้ม สว่างปานกลาง (ไม่ถึงเกณฑ์ V≥246 ของกรอบ UI)
    cv2.rectangle(img, (x, y), (x + w, y + h), (70, 170, 205), -1)


def test_finds_centered_stage_between_two_brackets():
    img = _base_map()
    # การ์ดกลางจอ: กรอบซ้าย x=520, กรอบขวา x=700 (ห่าง 180) ที่ระดับ label y=250
    _put_ui_yellow_bracket(img, 520, 250, side="left")
    _put_ui_yellow_bracket(img, 700, 250, side="right")
    found, cx, cy = find_highlighted_stage(_png(img))
    assert found
    # จุดแตะควรอยู่กึ่งกลางระหว่างสองกรอบในแนวนอน
    assert 590 <= cx <= 690
    # และขยับขึ้นจาก label bar (ไม่ต่ำกว่าตำแหน่งกรอบ)
    assert cy < 250 + 62


def test_ignores_warm_artwork_only():
    """ภาพศิลป์โทนส้ม/เหลืองล้วน (ไม่มีกรอบ UI สว่าง) ต้องไม่ถูกตรวจว่าเป็นด่านไฮไลท์"""
    img = _base_map()
    _put_warm_artwork(img, 400, 300)   # ด่านที่ 'ไม่ได้' ถูกเลือก แต่ภาพเป็นโทนทอง
    found, _cx, _cy = find_highlighted_stage(_png(img))
    assert not found


def test_warm_artwork_does_not_beat_real_bracket():
    """มีทั้งภาพโทนทอง (ด่านอื่น) และกรอบ UI จริง (ด่านที่เลือก) — ต้องเลือกอันที่มีกรอบ UI"""
    img = _base_map()
    _put_warm_artwork(img, 380, 300, w=180, h=110)          # ด่าน 'หลอก' โทนทอง ฝั่งซ้าย
    _put_ui_yellow_bracket(img, 720, 250, side="left")       # ด่านจริง (กรอบ UI) ฝั่งขวา
    found, cx, cy = find_highlighted_stage(_png(img))
    assert found
    assert cx > 600  # ต้องเลือกฝั่งขวา (กรอบ UI) ไม่ใช่ฝั่งซ้าย (ภาพทอง)


def test_single_bracket_left_taps_to_the_right():
    """เจอกรอบเดียวแบบ '[' (ด่านริมจอถูกตัดขอบขวา) -> จุดแตะต้องเลื่อนไปทางขวาเข้าการ์ด"""
    img = _base_map()
    _put_ui_yellow_bracket(img, 760, 400, side="left")
    found, cx, cy = find_highlighted_stage(_png(img))
    assert found
    assert cx > 760  # เข้าหาการ์ดทางขวาของกรอบ


def test_no_yellow_returns_not_found():
    img = _base_map()
    found, cx, cy = find_highlighted_stage(_png(img))
    assert not found and cx == 0 and cy == 0


def test_bad_input():
    assert find_highlighted_stage(b"")[0] is False


def test_ignores_wide_yellow_ring_icon():
    """ไอคอน/วงแหวนเหลืองกว้าง (เช่นในจอแมตช์) ต้องไม่ถูกนับเป็นกรอบเลือก (กรอบต้องบาง)"""
    img = _base_map()
    # วงแหวนเหลืองสว่างแต่ 'กว้าง' (w≈70) — ไม่ใช่เส้นกรอบบาง
    cv2.circle(img, (850, 240), 40, (80, 232, 255), 8)
    found, _cx, _cy = find_highlighted_stage(_png(img))
    assert not found


# ===== find_swipe_glow: หาไอคอนบาสเรืองแสงของ cutscene แบบปัดนิ้ว =====
def _scene(w=960, h=540):
    """พื้นหลัง cutscene จำลอง (โทนอุ่น)"""
    return np.full((h, w, 3), (60, 120, 170), dtype=np.uint8)


def _put_glow_ball(img, cx, cy, r=30):
    """วาดไอคอนบาสเรืองแสง: ลูกบอลฟ้าสว่างจัด (glow เรืองทั่วทั้งลูก -> halo cyan สูง)"""
    cv2.circle(img, (cx, cy), r, (255, 210, 90), -1)


def _put_joystick(img, cx, cy, r=24):
    """วาด 'จอยสติ๊ก' ตอนแมตช์: ลูกบาสน้ำเงินขอบขาว ในวงแหวนเทา — ไม่มี glow ฟ้าเรือง"""
    cv2.circle(img, (cx, cy), r + 40, (150, 140, 130), 3)   # วงแหวนใหญ่โปร่ง
    cv2.circle(img, (cx, cy), r + 4, (235, 235, 235), -1)   # ขอบขาวรอบลูกบอล
    cv2.circle(img, (cx, cy), r, (235, 170, 70), -1)        # ลูกบาสน้ำเงิน (ไม่มี halo ฟ้า)


def test_swipe_glow_found_in_lower_half():
    img = _scene()
    _put_glow_ball(img, 137, 356)
    found, cx, cy = find_swipe_glow(_png(img))
    assert found
    assert abs(cx - 137) <= 15 and abs(cy - 356) <= 15


def test_swipe_glow_ignores_top_back_button():
    """ปุ่มย้อนกลับสีฟ้ามุมซ้ายบน (y เล็ก) ต้องไม่ถูกนับเป็นไอคอนปัดนิ้ว"""
    img = _scene()
    _put_glow_ball(img, 47, 40)   # ตำแหน่งปุ่ม back
    found, _cx, _cy = find_swipe_glow(_png(img))
    assert not found


def test_swipe_glow_ignores_irregular_shape():
    """ก้อนสีฟ้าไม่กลม (เช่นผมตัวละคร) ต้องไม่ถูกนับเป็นไอคอน"""
    img = _scene()
    # สี่เหลี่ยมผืนผ้าฟ้ากว้าง (ไม่กลม, w/h ผิด)
    cv2.rectangle(img, (40, 300), (130, 360), (255, 210, 90), -1)
    found, _cx, _cy = find_swipe_glow(_png(img))
    assert not found


def test_swipe_glow_ignores_match_joystick():
    """จอยสติ๊ก (ปุ่มเดิน) ตอนแมตช์ = ลูกบอลฟ้าแต่ไม่มี glow เรือง ต้องไม่ถูกปัด
    (ไม่งั้นตัวละครจะเดินเอง auto ไม่ทำงาน)"""
    img = _scene()
    _put_joystick(img, 139, 422)
    found, _cx, _cy = find_swipe_glow(_png(img))
    assert not found


def test_swipe_glow_none_on_empty():
    assert find_swipe_glow(_png(_scene()))[0] is False


def test_swipe_glow_bad_input():
    assert find_swipe_glow(b"")[0] is False
