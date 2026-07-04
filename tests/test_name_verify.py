"""ทดสอบการยืนยันตัวตนก่อนเขียนเพชร (ชั้น A): เทียบ ingamename ที่บันทึกไว้ vs ที่ OCR อ่านจากจอ

หลักการ: ทน OCR เพี้ยนเล็กน้อย (O↔0, l↔i, ขยะปนท้าย) แต่ต้องกัน 'สลับบัญชี' ได้
โดยเฉพาะ player ID ที่เป็นตัวเลขล้วนและต่างกันแค่หลักเดียว ต้องไม่ถือว่าตรง
"""
from mumu_controller import names_match, normalize_ingame_name


def test_exact_match():
    assert names_match("EgoEat", "EgoEat")
    assert names_match("10360117809", "10360117809")


def test_tolerates_ocr_noise_and_spaces():
    assert names_match("EgoEat", "Ego Eat")      # ช่องว่างแทรก
    assert names_match("EgoEat", "EgoEat)")       # ขยะปนท้าย
    assert names_match("Daikisan", "Daiklsan")    # l แทน i
    assert names_match("EgoEat", "EgoEot")        # a↔o (fuzzy)


def test_numeric_id_tolerates_letter_digit_confusion():
    assert names_match("10360117809", "1036O117809")    # O แทน 0
    assert names_match("10360117809", "10360117809x")   # ขยะท้าย


def test_numeric_id_rejects_different_id():
    # ID ต่างกันแค่หลักสุดท้าย = คนละบัญชี ต้องไม่ตรง (กันเขียนเพชรผิดบัญชี)
    assert not names_match("10360117809", "10360117810")
    assert not names_match("10360117809", "20360117809")


def test_rejects_different_name():
    assert not names_match("EgoEat", "Kuroko")


def test_rejects_empty_or_garbage():
    assert not names_match("EgoEat", "")
    assert not names_match("", "EgoEat")
    assert not names_match("EgoEat", "|")


def test_short_name_not_matched_by_containment():
    # ชื่อสั้น 2-3 ตัว ไม่ควรตรงเพราะบังเอิญเป็นสับสตริงของข้อความยาว
    assert not names_match("ab", "abcdefghij")


def test_normalize_strips_case_space_punct():
    assert normalize_ingame_name("  Ego_Eat! ") == "egoeat"
    assert normalize_ingame_name("D-Rose") == "drose"
