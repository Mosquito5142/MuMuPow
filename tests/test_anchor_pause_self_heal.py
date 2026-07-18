"""เทส anchor_on_fail='pause' (ค่าเริ่มต้น): ไม่เจอภาพ -> ก่อนหยุดรอจริง ต้องลองย้อนไปทำขั้นก่อนหน้า
ซ้ำอีก 1 ครั้งแล้วเช็คใหม่ก่อนเสมอ (เผื่อกดตอนนั้นแล้วจอ/เครื่องค้าง เลยไม่ขยับมาจอนี้จริง ๆ)
ถ้าลองแล้วยังไม่เจอจริง ๆ ค่อยหยุดรอ (ผู้ใช้ยืนยันว่านี่คือสาเหตุปัญหาที่เจอบ่อยที่สุด)"""
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import macro_runner as M

B64 = base64.b64encode(b"TMPL").decode()


class RetryCtl:
    """คอนโทรลเลอร์จำลอง: match_template_bytes เจอภาพก็ต่อเมื่อถูกเรียกเกิน fail_times ครั้งแล้ว"""

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


def test_pause_self_heals_by_redoing_previous_step_once_then_succeeds():
    # พลาดแค่ครั้งแรก (match_calls=1 -> ไม่เจอ) แล้วเจอตอนเช็คซ้ำรอบ 2
    c = RetryCtl(fail_times=1)
    steps = [
        _tap(1, 1),
        _tap(2, 2, anchor_img=B64, anchor_timeout=0.001, anchor_on_fail="pause"),
        _tap(3, 3),
    ]
    r = M.MacroRunner(c, steps, log_cb=lambda t, k="info": None, anchor_poll=0.01)
    status = r.execute_one(":7555", None)
    assert status == "completed"
    # ขั้นก่อนหน้าถูกทำซ้ำ: ครั้งแรก + self-heal อีก 1 ครั้ง
    assert c.calls.count(("tap", 1, 1)) == 2
    # ขั้นที่มี anchor สำเร็จแล้วก็เดินหน้าต่อแค่ครั้งเดียว
    assert c.calls.count(("tap", 2, 2)) == 1
    assert c.calls[-1] == ("tap", 3, 3)


def test_pause_gives_up_after_one_self_heal_retry_not_infinite():
    monkeypatch_dir_used = os.path.join(os.path.dirname(__file__), "__scratch_report__")
    c = RetryCtl(fail_times=999)  # ไม่เจอเลยไม่ว่าจะลองกี่ครั้ง
    steps = [
        _tap(1, 1),
        _tap(2, 2, anchor_img=B64, anchor_timeout=0.001, anchor_on_fail="pause"),
        _tap(3, 3),
    ]
    paused_calls = []
    r = M.MacroRunner(c, steps, log_cb=lambda t, k="info": None, anchor_poll=0.01)
    r._save_failure_report = lambda *a, **k: None  # ไม่ต้องเขียนไฟล์จริงในเทสนี้
    r._pause_checkpoint = lambda device, account, step_path, step, prog: paused_calls.append(step_path)
    status = r.execute_one(":7555", None)
    assert status == "paused"
    # ทำขั้นก่อนหน้าไปแค่ 2 ครั้ง (ครั้งแรก + self-heal 1 ครั้ง) ไม่ใช่วนไม่รู้จบ
    assert c.calls.count(("tap", 1, 1)) == 2
    assert ("tap", 3, 3) not in c.calls  # ไม่มีทางไปถึงขั้นถัดไปได้เลยเพราะ anchor ไม่เจอจริง
    assert len(paused_calls) == 1


def test_pause_with_no_previous_step_pauses_immediately_no_self_heal():
    """anchor เป็นขั้นแรกสุด (idx=0) ไม่มีขั้นก่อนหน้าให้ย้อนไปทำซ้ำ -> หยุดรอทันที"""
    c = RetryCtl(fail_times=999)
    steps = [_tap(2, 2, anchor_img=B64, anchor_timeout=0.001, anchor_on_fail="pause")]
    paused_calls = []
    r = M.MacroRunner(c, steps, log_cb=lambda t, k="info": None, anchor_poll=0.01)
    r._save_failure_report = lambda *a, **k: None
    r._pause_checkpoint = lambda device, account, step_path, step, prog: paused_calls.append(step_path)
    status = r.execute_one(":7555", None)
    assert status == "paused"
    assert c.calls == []
    assert len(paused_calls) == 1


def test_pause_is_the_default_anchor_on_fail_and_also_self_heals():
    """ไม่ตั้ง anchor_on_fail เลย (ค่าเริ่มต้น) ต้องได้พฤติกรรม self-heal เดียวกับตั้ง 'pause' ชัดเจน"""
    c = RetryCtl(fail_times=1)
    steps = [_tap(1, 1), _tap(2, 2, anchor_img=B64, anchor_timeout=0.001)]  # ไม่มี anchor_on_fail
    r = M.MacroRunner(c, steps, log_cb=lambda t, k="info": None, anchor_poll=0.01)
    status = r.execute_one(":7555", None)
    assert status == "completed"
    assert c.calls.count(("tap", 1, 1)) == 2


def test_default_anchor_timeout_is_30_seconds_not_8(monkeypatch):
    """ตั้งนาฬิกาปลอมแทน time.time/time.sleep จริง กันเทสนี้ทำ pytest ค้าง ~30 วิ
    แต่ยังยืนยันค่า deadline จริงที่โค้ดใช้เมื่อไม่ได้ตั้ง anchor_timeout เอง"""
    c = RetryCtl(fail_times=999)  # ไม่เจอเลย -> ต้องรอจนครบ timeout เต็ม ๆ
    r = M.MacroRunner(c, [{"type": "tap", "x": "1", "y": "1", "anchor_img": B64}],
                      log_cb=lambda t, k="info": None, anchor_poll=1.0)

    clock = {"t": 0.0}
    monkeypatch.setattr(M.time, "time", lambda: clock["t"])
    monkeypatch.setattr(M.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))

    gate, _x, _y = r._wait_anchor(":7555", {"anchor_img": B64})  # ไม่ตั้ง anchor_timeout -> ต้องใช้ดีฟอลต์
    assert gate == "missing"
    assert 29 <= clock["t"] <= 31, f"ดีฟอลต์ควรอยู่ราว 30 วิ แต่ deadline จริงคือ {clock['t']:.2f} วิ"
