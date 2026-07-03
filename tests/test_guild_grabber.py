"""ทดสอบ helper ดึงรายชื่อสมาชิกชมรม: รวมรูปแนวตั้ง + เทียบความเหมือนภาพ"""
import numpy as np
import cv2

from mumu_controller import (
    stitch_png_vertically, png_similarity,
    extract_guild_member_names, normalize_guild_name,
    find_yellow_frame,
)


def _png(h, w, color=(0, 0, 0)):
    img = np.full((h, w, 3), color, dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _decode(b):
    return cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)


def test_stitch_none_when_empty():
    assert stitch_png_vertically([]) is None
    assert stitch_png_vertically([None, b""]) is None


def test_stitch_stacks_heights_with_gap():
    pngs = [_png(100, 200), _png(50, 200), _png(70, 200)]
    out = stitch_png_vertically(pngs, max_width=1080, gap=8)
    assert out is not None
    img = _decode(out)
    # ความสูงรวม = 100+50+70 + gap*2 = 220 + 16 = 236
    assert img.shape[0] == 100 + 50 + 70 + 8 * 2
    assert img.shape[1] == 200


def test_stitch_downscales_wide_images():
    out = stitch_png_vertically([_png(200, 2000)], max_width=1080, gap=0)
    img = _decode(out)
    assert img.shape[1] == 1080  # ถูกย่อให้กว้าง 1080


def test_similarity_identical_is_one():
    a = _png(120, 120, (30, 60, 90))
    assert png_similarity(a, a) == 1.0


def test_similarity_very_different_is_low():
    a = _png(120, 120, (0, 0, 0))
    b = _png(120, 120, (255, 255, 255))
    assert png_similarity(a, b) < 0.1


def test_similarity_handles_size_mismatch():
    a = _png(120, 120, (10, 10, 10))
    b = _png(60, 60, (10, 10, 10))
    # ขนาดต่างกันแต่สีเดียวกัน -> resize แล้วเหมือนกันหมด
    assert png_similarity(a, b) > 0.95


def test_similarity_zero_on_bad_input():
    assert png_similarity(b"", _png(10, 10)) == 0.0


# ===== แยกชื่อ + ตัดซ้ำ =====
def test_extract_dedupes_across_pages():
    text = "Miracles\nDylanlxes\nHeal_Hee\nMiracles\nheal_hee\nDylanlxes"
    names = extract_guild_member_names(text)
    assert names == ["Miracles", "Dylanlxes", "Heal_Hee"]


def test_extract_drops_labels_and_status():
    text = "สมาชิก\nGUILD\nonline\n2 minutes ago\nDaikisan\n12\nออกจากชมรม"
    assert extract_guild_member_names(text) == ["Daikisan"]


def test_extract_keeps_pure_digit_name():
    # ชื่อตัวเลขล้วน (เช่น 10348356110) ต้องไม่ถูกตัดทิ้ง
    names = extract_guild_member_names("10348356110\n10312140122")
    assert names == ["10348356110", "10312140122"]


def test_extract_trims_trailing_level_status():
    # "Name 12 5 online" -> เหลือ "Name"
    assert extract_guild_member_names("NewDragon 12 5 online") == ["NewDragon"]


def test_normalize_collapses_case_and_space():
    assert normalize_guild_name("  Heal_Hee  ") == "heal_hee"
    assert normalize_guild_name("D Rose") == "d rose"


def test_extract_drops_too_short_or_numeric_noise():
    assert extract_guild_member_names("ab\n7\niv\n|") == []


# ===== ชื่อหลายภาษา: ไทย/ญี่ปุ่น/เกาหลี/จีน =====
def test_extract_keeps_cjk_and_thai_names():
    text = "Himaru\nสมชาย\nサクラ\n김철수\n小明"
    assert extract_guild_member_names(text) == ["Himaru", "สมชาย", "サクラ", "김철수", "小明"]


def test_extract_joins_ocr_inserted_spaces_in_thai_and_cjk():
    # Tesseract มักแทรกช่องว่างระหว่างตัวอักษรไทย/ญี่ปุ่น -> ต้องรวมกลับเป็นคำเดียว
    assert extract_guild_member_names("ม า น ะ ชั ย") == ["มานะชัย"]
    assert extract_guild_member_names("サク ラ") == ["サクラ"]


def test_extract_keeps_two_char_cjk_name():
    # ชื่อจีน/ญี่ปุ่น 2 ตัวอักษรเป็นชื่อจริง ต้องไม่ถูกตัดด้วยเกณฑ์ความยาวขั้นต่ำ
    assert extract_guild_member_names("小明") == ["小明"]


# ===== find_yellow_frame (หาด่านถัดไปบน map) =====
def _png_with_rect(h, w, rect=None, color=(0, 255, 255), thickness=6, filled=False):
    img = np.full((h, w, 3), (120, 110, 100), dtype=np.uint8)  # พื้นเทาๆ
    if rect:
        x, y, rw, rh = rect
        cv2.rectangle(img, (x, y), (x + rw, y + rh), color, -1 if filled else thickness)
    ok, buf = cv2.imencode(".png", img)
    return buf.tobytes()


def test_yellow_frame_found_center():
    png = _png_with_rect(540, 960, rect=(400, 200, 160, 160))
    found, cx, cy, box = find_yellow_frame(png)
    assert found
    assert abs(cx - 480) <= 12 and abs(cy - 280) <= 12


def test_yellow_frame_ignores_small_stars():
    # ดาวเหลืองดวงเล็กหลายดวง ไม่ควรถูกนับเป็นกรอบด่าน
    png = _png_with_rect(540, 960, rect=(50, 50, 12, 12), filled=True)
    found, *_ = find_yellow_frame(png)
    assert not found


def test_yellow_frame_none_when_no_yellow():
    png = _png_with_rect(540, 960, rect=None)
    assert find_yellow_frame(png)[0] is False


def test_yellow_frame_picks_largest():
    img = np.full((540, 960, 3), (120, 110, 100), dtype=np.uint8)
    cv2.rectangle(img, (40, 40), (110, 110), (0, 255, 255), -1)     # เล็ก
    cv2.rectangle(img, (600, 250), (820, 470), (0, 255, 255), 6)    # ใหญ่ (กรอบด่าน)
    ok, buf = cv2.imencode(".png", img)
    found, cx, cy, box = find_yellow_frame(buf.tobytes())
    assert found
    assert cx > 500  # เลือกกล่องใหญ่ฝั่งขวา


def test_yellow_frame_bad_input():
    assert find_yellow_frame(b"")[0] is False
