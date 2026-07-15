"""เทสว่า anchor_poll ถูกจำกัดช่วง 0.1–10 วิ ในตัวรันฝั่งเว็บ (MacroRunner) เหมือน Tkinter
บั๊กเดิม: webui ไม่ clamp เลย -> พิมพ์ค่าติดลบในช่อง 'ความถี่เช็ค Anchor' ทำให้ลูปหน่วงใน
_wait_anchor ไม่ทำงาน (while waited < anchor_poll เป็นเท็จตั้งแต่แรก) กลายเป็น busy loop
แคปจอรัวสุดกำลัง (วัดได้ ~6 ล้านครั้ง/วิ) กิน CPU+ADB จนจอค้าง — Tkinter clamp ไว้อยู่แล้ว"""
import base64
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import macro_runner as M

B64 = base64.b64encode(b"TMPL").decode()


def _runner(poll):
    return M.MacroRunner(object(), [], log_cb=lambda t, k="info": None, anchor_poll=poll)


def test_normal_values_pass_through():
    assert _runner(0.5).anchor_poll == 0.5
    assert _runner(2).anchor_poll == 2.0
    assert _runner(10).anchor_poll == 10.0


def test_negative_is_clamped_to_floor_not_busy_loop():
    assert _runner(-1).anchor_poll == 0.1
    assert _runner(-999).anchor_poll == 0.1


def test_too_large_is_clamped_to_ceiling():
    assert _runner(999).anchor_poll == 10.0


def test_zero_and_none_fall_back_to_default():
    assert _runner(0).anchor_poll == 2.0
    assert _runner(None).anchor_poll == 2.0


class _CountCtl:
    """นับจำนวนครั้งที่แคปจอ — ใช้ยืนยันว่าไม่เกิด busy loop จริง"""

    def __init__(self):
        self.polls = 0

    def capture_screenshot_bytes(self, d):
        self.polls += 1
        return True, b"SCREEN"

    def match_template_bytes(self, data, tmpl, thr):
        return (False, 0, 0, "no")   # ไม่เจอเสมอ -> วนเช็คจนหมด timeout


def test_negative_poll_does_not_hammer_the_device():
    """ยืนยันผลลัพธ์จริง ไม่ใช่แค่ค่าตัวแปร: ค่าติดลบต้องไม่ทำให้แคปจอรัวเป็นพัน/ล้านครั้ง"""
    c = _CountCtl()
    r = M.MacroRunner(c, [], log_cb=lambda t, k="info": None, anchor_poll=-1)
    t0 = time.perf_counter()
    r._wait_anchor(":7555", {"anchor_img": B64, "anchor_timeout": 0.5})
    dt = time.perf_counter() - t0
    # clamp เป็น 0.1 -> ใน ~0.5 วิ ควรเช็คราวๆ ไม่กี่ครั้ง (เผื่อเครื่องช้า/เร็ว ให้ผ่านได้ถึง 30)
    assert c.polls <= 30, f"เช็คจอ {c.polls} ครั้งใน {dt:.2f} วิ — busy loop กลับมาแล้ว"
