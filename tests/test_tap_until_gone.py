"""ชนิดขั้น 'กดรัวจนรูปหาย' (tap_until_gone) — รับของจนครบ

ที่มา: รับของซ้ำ ๆ (กดปุ่มรับ) จนไอเทม/ปุ่มรับหายหมด แล้วค่อยไปขั้นต่อไป
เป็นตรงข้ามของ tap_until_image (กดจนภาพ 'โผล่') — อันนี้กดจนภาพ 'หาย'

ใช้ handler เดียวกัน (_tap_until_image) แค่สลับเงื่อนไขหยุดด้วย gone=True
"""
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import macro_runner as M
import web_app

TARGET = base64.b64encode(b"ITEM").decode()


class Ctl:
    """ภาพเป้าหมายหายไปหลังถูกกดครบ gone_after ครั้ง (จำลอง 'ของหมดหลังกดไปหลายที')"""

    def __init__(self, gone_after=3, found=True):
        self.gone_after = gone_after
        self.found = found
        self.taps = []

    def capture_screenshot_bytes(self, d):
        return True, b"SCREEN"

    def match_template_bytes(self, data, tmpl, thr=0.8):
        # เจอภาพตราบใดที่ยังกดไม่ครบ gone_after ครั้ง
        return (self.found and len(self.taps) < self.gone_after, 5, 6, "m")

    def find_image_in_bytes(self, *a, **k):
        return (False, 0, 0, "no")

    def tap(self, d, x, y):
        self.taps.append((int(float(x)), int(float(y))))
        return True, ""


def run(step, ctl, gone):
    r = M.MacroRunner(ctl, [step], log_cb=lambda t, k="info": None, running_check=lambda: True)
    r._interruptible_sleep = lambda s: True
    r._tap_until_image(":7555", dict(step), gone=gone)
    return ctl


BASE = {"type": "tap_until_gone", "x": "400", "y": "500", "wait_img": TARGET,
        "interval": 0.5, "timeout": 30, "threshold": 0.8, "delay": 0}


def test_taps_until_image_disappears():
    ctl = run(BASE, Ctl(gone_after=3), gone=True)
    assert ctl.taps == [(400, 500)] * 3, "ต้องกดพิกัดเดิมจนภาพหาย (3 ครั้ง)"


def test_stops_immediately_if_already_gone():
    """ของหมดอยู่แล้ว (ภาพไม่เจอตั้งแต่แรก) → ไม่กดเลย ไปต่อทันที"""
    ctl = run(BASE, Ctl(found=False), gone=True)
    assert ctl.taps == []


def test_gone_mode_ignores_click_flag():
    """โหมดจนหาย กดพิกัดเดิมอย่างเดียว ไม่กดที่ตำแหน่งภาพ (click ไม่มีผล)"""
    ctl = run(dict(BASE, click=True), Ctl(gone_after=2), gone=True)
    assert set(ctl.taps) == {(400, 500)}, f"ต้องกดแค่พิกัดเดิม: {ctl.taps}"


def test_appear_mode_unchanged():
    """โหมดเดิม (gone=False) ต้องยังหยุดเมื่อ 'เจอ' — ไม่พังจากการเพิ่มโหมดใหม่"""
    # ภาพเจอตั้งแต่แรก → หยุดทันที ไม่กด
    ctl = run(dict(BASE, type="tap_until_image"), Ctl(found=True, gone_after=99), gone=False)
    assert ctl.taps == [], "โหมดจนเจอ: เจอตั้งแต่แรกต้องไม่กด"


def test_no_image_skips():
    ctl = Ctl()
    r = M.MacroRunner(ctl, [], log_cb=lambda t, k="info": None, running_check=lambda: True)
    r._tap_until_image(":7555", {"type": "tap_until_gone", "x": "1", "y": "2"}, gone=True)
    assert ctl.taps == []


def test_dispatch_routes_tap_until_gone():
    """ground rule: ชนิดที่ประกาศต้อง dispatch ได้จริง (ไม่ถูกข้ามเงียบ)"""
    ctl = Ctl(gone_after=2)
    r = M.MacroRunner(ctl, [dict(BASE)], log_cb=lambda t, k="info": None, running_check=lambda: True)
    r._interruptible_sleep = lambda s: True
    r._run_steps(":7555", None, r.steps, lambda **kw: None)
    assert ctl.taps == [(400, 500)] * 2, "ต้องเข้า _tap_until_image ผ่าน dispatch"


# ---------- ลงทะเบียนครบทุกตาราง ----------

def test_registered_in_all_backend_tables():
    for tbl in (web_app.Api._STEP_TH, web_app.Api._STEP_ICON,
                web_app.Api.STEP_FIELDS, web_app.Api.STEP_DEFAULTS):
        assert "tap_until_gone" in tbl, f"ขาดใน {tbl}"


def test_in_type_options():
    vals = [o.get("value") for o in web_app.Api()._step_type_options()]
    assert "tap_until_gone" in vals
