"""อ่านเพชร (read_diamond) ไม่มีการยืนยันชื่อในเกมก่อนบันทึกอีกต่อไป

เดิมมีชั้นยืนยันตัวตน (OCR ชื่อในเกม เทียบกับ ingamename) ก่อนเขียนเพชร กันกรณีจอ/บัญชีสลับกัน
แต่ทำให้เกิด false positive บ่อย: OCR อ่านเลขในชื่อ (เช่น player ID ตัวเลขล้วน) พลาดไปตัวเดียว
ก็ถูกตีว่า 'ไม่ตรงบัญชี' ทั้งที่จริงเป็นบัญชีถูกต้อง — ตัดสินใจเอาชั้นนี้ออก เพราะ anchor ของสคริปต์
ที่รันมาก่อนหน้า read_diamond ยืนยันจอ/บัญชีที่ถูกต้องอยู่แล้วในตัว

ผลคือ: read_diamond ควรอ่านค่าจาก OCR ตัวเลขแล้วบันทึกตรง ๆ โดยไม่สนใจว่าชื่อในเกม/ingamename
จะตรงกันหรือไม่ (ไม่มีการเรียก OCR ชื่อ / ไม่มีการเปรียบเทียบใด ๆ อีก)"""
import os
import sys
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import macro_runner


class FakeController:
    def __init__(self):
        self.name_ocr_calls = 0

    def capture_screenshot_bytes(self, device):
        return True, b"fake-screenshot-bytes"

    def read_number_tesseract(self, data, region):
        return True, 3631, "3631"


def _runner(controller, logs=None):
    logs = logs if logs is not None else []
    return macro_runner.MacroRunner(
        controller, steps=[],
        log_cb=lambda t, k="info": logs.append((k, t)),
        diamond_cfg={"region": {"x": 0, "y": 0, "w": 40, "h": 20}},
    ), logs


def test_diamond_written_even_when_ingamename_would_not_match_screen():
    """ไม่มี OCR ชื่อเรียกเลย ต่อให้ ingamename ต่างจากที่ควรเห็นบนจอ ก็บันทึกเพชรตรง ๆ"""
    controller = FakeController()
    r, logs = _runner(controller)
    account = {"email": "a@x.com", "ingamename": "10284914478", "name": "หัวจ่าย คางามิ 60 บาท"}

    with unittest.mock.patch.object(macro_runner, "find_tesseract", lambda: "tesseract.exe"), \
         unittest.mock.patch.object(macro_runner, "ocr_text_tesseract") as mock_ocr:
        r._read_diamond(":16384", account)
        mock_ocr.assert_not_called()  # ไม่มีการ OCR ชื่อในเกมอีกต่อไป

    assert len(r.diamond_rows) == 1
    assert r.diamond_rows[0]["diamonds"] == 3631
    assert r.diamond_rows[0]["email"] == "a@x.com"
    assert not any("ไม่เขียนเพชร" in t or "ไม่ตรง" in t for _, t in logs)


def test_diamond_written_when_account_has_no_ingamename_at_all():
    controller = FakeController()
    r, logs = _runner(controller)
    account = {"email": "b@x.com"}  # ไม่มี ingamename/name เลย

    with unittest.mock.patch.object(macro_runner, "find_tesseract", lambda: "tesseract.exe"):
        r._read_diamond(":16385", account)

    assert len(r.diamond_rows) == 1
    assert r.diamond_rows[0]["diamonds"] == 3631


def test_no_region_configured_still_skips_cleanly():
    controller = FakeController()
    r, logs = _runner(controller)
    r.diamond_cfg = {"region": {"x": 0, "y": 0, "w": 0, "h": 0}}

    r._read_diamond(":16384", {"email": "a@x.com"})

    assert r.diamond_rows == []
    assert any("ยังไม่ได้ตั้งพื้นที่" in t for _, t in logs)
