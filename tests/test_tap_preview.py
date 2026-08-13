"""เทส 'ภาพช่วยจำจุดที่กด' (preview_img)

ตอนกลับมาแก้สคริปต์ยาว ๆ ทีหลัง แถวที่เขียนว่า "แตะ (791, 465)" อ่านไม่ออกว่าปุ่มอะไร
ฟีเจอร์นี้เก็บภาพย่อรอบจุดที่กดไว้ให้ดู

ข้อกำหนดที่ห้ามพลาด:
  1. ต้องไม่ยุ่งกับการทำงานของตัวรัน — ต่างจาก anchor_img ที่ทำให้ 'รอจนเจอภาพ' ก่อนกด
  2. ต้องไม่ทำให้ไฟล์สคริปต์บวมจนใช้งานไม่ไหว (สคริปต์จริงมี 100+ ขั้น)
"""
import base64
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2

import macro_runner as M
import web_app


def api(steps=None):
    a = web_app.Api.__new__(web_app.Api)
    a.macro_steps = steps if steps is not None else [{"type": "tap", "x": "0", "y": "0", "desc": "ปุ่ม"}]
    a.current_profile = "t"
    a._push_log = lambda *a_, **k_: None
    return a


def fake_screen(w=960, h=540):
    """ภาพจอปลอมที่มีลวดลาย (ไล่สี) — ถ้าใช้ภาพสีเดียว JPEG จะเล็กผิดปกติจนวัดขนาดไม่มีความหมาย"""
    img = np.zeros((h, w, 3), np.uint8)
    img[:, :, 0] = np.linspace(0, 255, w, dtype=np.uint8)[None, :]
    img[:, :, 1] = np.linspace(0, 255, h, dtype=np.uint8)[:, None]
    img[:, :, 2] = ((np.arange(w)[None, :] // 7 + np.arange(h)[:, None] // 5) % 256).astype(np.uint8)
    raw = cv2.imencode(".png", img)[1].tobytes()
    return "data:image/png;base64," + base64.b64encode(raw).decode()


def decode(b64):
    return cv2.imdecode(np.frombuffer(base64.b64decode(b64), np.uint8), cv2.IMREAD_COLOR)


# ---------- สร้างภาพ ----------

def test_preview_is_saved_when_screen_image_is_supplied():
    a = api()
    a.flow_set_xy([0], 480, 270, None, None, fake_screen())
    assert a.macro_steps[0].get("preview_img")


def test_no_preview_when_no_screen_image():
    """ตั้งพิกัดด้วยการพิมพ์เลขเองต้องไม่พังและไม่ยัดภาพเปล่า ๆ ให้"""
    a = api()
    a.flow_set_xy([0], 100, 200)
    assert "preview_img" not in a.macro_steps[0]
    assert a.macro_steps[0]["x"] == "100"


def test_preview_is_capped_to_thumbnail_size():
    a = api()
    img = decode(a._tap_preview_b64(fake_screen(), 480, 270))
    assert max(img.shape[:2]) <= web_app.Api.PREVIEW_MAX


def test_preview_stays_small_enough_for_long_scripts():
    """สคริปต์จริงมี 100+ ขั้น ถ้าภาพละ 20 KB ไฟล์จะโตเป็นหลาย MB จนเปิด/เซฟช้า"""
    a = api()
    sizes = [len(a._tap_preview_b64(fake_screen(), x, y))
             for x, y in [(100, 100), (480, 270), (700, 200), (300, 400)]]
    assert max(sizes) < 12 * 1024, f"ภาพใหญ่เกินไป: {max(sizes)} ไบต์/ขั้น"


def test_preview_marks_the_exact_tap_point_in_red():
    """กากบาทแดงตรงกลางกรอบ = จุดที่กดจริง (เผื่อปุ่มใหญ่กว่ากรอบจะได้รู้ว่ากดตรงไหน)"""
    a = api()
    img = decode(a._tap_preview_b64(fake_screen(), 480, 270))
    h, w = img.shape[:2]
    centre = img[h // 2 - 4:h // 2 + 5, w // 2 - 4:w // 2 + 5]
    reddest = centre[:, :, 2].astype(int) - centre[:, :, 1].astype(int)
    assert reddest.max() > 40      # มีพิกเซลแดงชัดกลางภาพ


def test_preview_handles_taps_at_the_screen_edge():
    """จุดกดชิดขอบจอ กรอบจะโดนตัด ต้องไม่พังและยังได้ภาพ"""
    a = api()
    for x, y in [(0, 0), (959, 539), (0, 539), (959, 0)]:
        out = a._tap_preview_b64(fake_screen(), x, y)
        assert out and decode(out) is not None


def test_bad_image_input_returns_empty_not_crash():
    a = api()
    assert a._tap_preview_b64("ไม่ใช่ภาพ", 10, 10) == ""
    assert a._tap_preview_b64("", 10, 10) == ""


# ---------- ต้องไม่กระทบการทำงาน ----------

def test_runner_ignores_preview_image_completely():
    """ข้อสำคัญที่สุด: preview_img ต้องไม่ทำให้ตัวรัน 'รอภาพ' เหมือน anchor_img
    ถ้าเผลอไปใช้ชื่อฟิลด์เดียวกัน สคริปต์จะเปลี่ยนพฤติกรรมโดยผู้ใช้ไม่ได้สั่ง"""
    calls = []

    class Ctl:
        def capture_screenshot_bytes(self, d):
            calls.append("shot")
            return True, b"S"

        def match_template_bytes(self, *a, **k):
            calls.append("match")
            return False, 0, 0, ""

        def tap(self, d, x, y):
            calls.append(("tap", int(float(x)), int(float(y))))
            return True, ""

    step = {"type": "tap", "x": "5", "y": "6", "delay": 0,
            "preview_img": base64.b64encode(b"whatever").decode()}
    r = M.MacroRunner(Ctl(), [step], log_cb=lambda t, k="info": None, running_check=lambda: True)
    assert r._run_steps(":7555", None, r.steps, lambda **kw: None) == "completed"
    assert ("tap", 5, 6) in calls
    assert "match" not in calls          # ไม่มีการเทียบภาพเลย


def test_preview_survives_changing_step_type():
    """เปลี่ยนชนิดขั้นแล้วภาพต้องไม่หาย (เหมือนที่ค่า anchor_* ถูกคงไว้)"""
    a = api()
    existing = {"type": "tap", "x": "1", "y": "2", "preview_img": "ZZZ", "anchor_img": "AAA"}
    out = a._canonical_step("swipe", {"x": "1", "y": "2", "x2": "3", "y2": "4"}, existing)
    assert out["preview_img"] == "ZZZ"
    assert out["anchor_img"] == "AAA"


def test_clear_preview_removes_only_the_image():
    a = api([{"type": "tap", "x": "1", "y": "2", "desc": "ปุ่ม", "preview_img": "ZZZ"}])
    a.flow_clear_preview([0])
    assert "preview_img" not in a.macro_steps[0]
    assert a.macro_steps[0]["x"] == "1" and a.macro_steps[0]["desc"] == "ปุ่ม"


def test_swipe_preview_marks_the_start_point():
    a = api([{"type": "swipe", "x": "0", "y": "0", "x2": "0", "y2": "0"}])
    a.flow_set_xy([0], 300, 200, 500, 400, fake_screen())
    assert a.macro_steps[0]["preview_img"]
    assert (a.macro_steps[0]["x"], a.macro_steps[0]["x2"]) == ("300", "500")
