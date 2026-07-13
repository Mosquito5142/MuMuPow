"""เทส anchor_on_fail='retry': ไม่เจอภาพ -> วนกลับไปทำขั้นก่อนหน้าใหม่ (จำกัดรอบ) แทนที่จะหยุดจอทันที"""
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import macro_runner as M

B64 = base64.b64encode(b"TMPL").decode()


class RetryCtl:
    """คอนโทรลเลอร์จำลอง: match_template_bytes เจอภาพก็ต่อเมื่อถูกเรียกเกิน fail_times ครั้งแล้ว
    (จำลองว่าจอค่อยๆ เข้าที่หลังวนทำซ้ำ) — ตั้ง fail_times สูงมากถ้าอยากให้ไม่เจอตลอด"""

    def __init__(self, fail_times):
        self.fail_times = fail_times
        self.match_calls = 0
        self.calls = []

    def capture_screenshot_bytes(self, d):
        return True, b"SCREEN"

    def match_template_bytes(self, data, tmpl, thr):
        self.match_calls += 1
        return (self.match_calls > self.fail_times, 5, 6, "m")

    def tap(self, d, x, y):
        self.calls.append(("tap", int(float(x)), int(float(y))))


def _tap(x, y, **extra):
    step = {"type": "tap", "x": str(x), "y": str(y)}
    step.update(extra)
    return step


def test_anchor_retry_jumps_back_and_eventually_succeeds():
    c = RetryCtl(fail_times=2)  # เจอจริงตอนแคปครั้งที่ 3 (หลังวนไป 2 รอบ)
    steps = [
        _tap(1, 1),
        _tap(2, 2, anchor_img=B64, anchor_timeout=0.001, anchor_on_fail="retry",
             anchor_retry_target=0, anchor_retry_limit=5),
        _tap(3, 3),
    ]
    r = M.MacroRunner(c, steps, log_cb=lambda t, k="info": None, anchor_poll=0.01)
    status = r.execute_one(":7555", None)
    assert status == "completed"
    # ขั้น 1 (เป้าหมายวนกลับ) ถูกทำซ้ำ 3 ครั้ง = ครั้งแรก + วน 2 รอบ
    assert c.calls.count(("tap", 1, 1)) == 3
    # ขั้นที่มี anchor สำเร็จแค่ครั้งเดียว (พอเจอภาพแล้วก็เดินหน้าต่อ ไม่วนซ้ำอีก)
    assert c.calls.count(("tap", 2, 2)) == 1
    # ไปถึงขั้นสุดท้ายได้ตามลำดับ
    assert c.calls[-1] == ("tap", 3, 3)


def test_anchor_retry_exhausts_limit_then_aborts():
    c = RetryCtl(fail_times=999)  # ไม่เจอเลยไม่ว่าจะวนกี่รอบ
    steps = [
        _tap(1, 1),
        _tap(2, 2, anchor_img=B64, anchor_timeout=0.001, anchor_on_fail="retry",
             anchor_retry_target=0, anchor_retry_limit=2),
    ]
    r = M.MacroRunner(c, steps, log_cb=lambda t, k="info": None, anchor_poll=0.01, reset_cfg={})
    status = r.execute_one(":7555", None)
    assert status == "device_error"
    # ครั้งแรก + วนครบ 2 รอบ = ทำขั้น 1 ไป 3 ครั้ง แล้วยอมแพ้ (ไม่เคยไปถึงขั้น 2 เพราะไม่เจอภาพตลอด)
    assert c.calls.count(("tap", 1, 1)) == 3
    assert ("tap", 2, 2) not in c.calls


def test_anchor_retry_without_target_falls_back_to_abort():
    c = RetryCtl(fail_times=999)
    steps = [_tap(2, 2, anchor_img=B64, anchor_timeout=0.001, anchor_on_fail="retry")]  # ไม่ได้ตั้ง target
    r = M.MacroRunner(c, steps, log_cb=lambda t, k="info": None, anchor_poll=0.01)
    status = r.execute_one(":7555", None)
    assert status == "device_error"
    assert c.calls == []


def test_flat_scripts_without_retry_are_unaffected():
    """สคริปต์เดิมที่ไม่มี anchor_on_fail='retry' เลย ต้องรันเหมือนเดิมทุกประการ (no regression)"""
    c = RetryCtl(fail_times=-1)  # เจอภาพเสมอ
    steps = [_tap(1, 1), _tap(2, 2, anchor_img=B64, anchor_timeout=0.001), _tap(3, 3)]
    r = M.MacroRunner(c, steps, log_cb=lambda t, k="info": None, anchor_poll=0.01)
    status = r.execute_one(":7555", None)
    assert status == "completed"
    assert c.calls == [("tap", 1, 1), ("tap", 2, 2), ("tap", 3, 3)]
