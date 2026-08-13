"""เทสโหมด 'รันทีละจอ' (sequential) — โหมดกันแคปช่า

ที่มา: สคริปต์สมัครไอดี พอยิงพร้อมกันหลายจอ เว็บจับได้ว่าเป็นบอทแล้วเด้งแคปช่า
(ผู้ใช้เจอว่าพอถึงจอที่ 5 ติดทุกครั้ง) โหมดนี้ยิงทีละเครื่องแล้วเว้นจังหวะสุ่มระหว่างบัญชี

หัวใจของโหมดนี้คือ 'ต้องไม่ขนานกันจริง ๆ' — ถ้าเผลอไปเรียก run_queue ก็จะกลับไปโดนแคปช่าเหมือนเดิม
"""
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import macro_runner as M


class Ctl:
    """บันทึกลำดับ + เวลาที่แต่ละคำสั่งถูกยิง เพื่อพิสูจน์ว่าไม่ทับซ้อนกัน"""

    def __init__(self):
        self.calls = []
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def capture_screenshot_bytes(self, d):
        return True, b"S"

    def match_template_bytes(self, *a, **k):
        return False, 0, 0, "no"

    def find_image_in_bytes(self, *a, **k):
        return False, 0, 0, "no"

    def tap(self, d, x, y):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        self.calls.append(("tap", d))
        with self._lock:
            self.active -= 1
        return True, ""


def runner(steps=None, **kw):
    return M.MacroRunner(Ctl(), steps or [{"type": "tap", "x": "1", "y": "2", "delay": 0}],
                         log_cb=lambda t, k="info": None, running_check=lambda: True, **kw)


def accounts(n):
    return [{"email": f"a{i}@x.com", "name": f"acc{i}"} for i in range(n)]


# ---------- การจับคู่จอ/บัญชี ----------

def test_pairs_cycle_through_devices():
    pairs = M.build_sequential_macro_pairs(["d1", "d2", "d3"], accounts(5))
    assert [p[0] for p in pairs] == ["d1", "d2", "d3", "d1", "d2"]
    assert [p[2] for p in pairs] == [0, 1, 2, 3, 4]
    assert all(p[3] == 5 for p in pairs)


def test_pairs_without_accounts_is_one_run_per_device():
    pairs = M.build_sequential_macro_pairs(["d1", "d2"], [])
    assert [(p[0], p[1]) for p in pairs] == [("d1", None), ("d2", None)]


def test_pairs_without_devices_is_empty():
    assert M.build_sequential_macro_pairs([], accounts(3)) == []


def test_gui_reuses_the_same_pairing_helper():
    """ห้ามมีสำเนาแยกใน gui.py ไม่งั้นสองแอปจับคู่ไม่เหมือนกัน"""
    import gui
    assert gui.build_sequential_macro_pairs is M.build_sequential_macro_pairs


# ---------- พฤติกรรมตอนรันจริง ----------

def test_sequential_never_runs_two_devices_at_once():
    """จุดสำคัญที่สุดของโหมดนี้ — ถ้าขนานเมื่อไหร่ก็กลับไปโดนแคปช่า"""
    r = runner()
    r.run_sequential([":1", ":2", ":3"], accounts(6), gap=None)
    assert r.controller.max_active == 1


def test_sequential_covers_every_account_in_order():
    r = runner()
    r.run_sequential([":1", ":2"], accounts(4), gap=None)
    assert [c[1] for c in r.controller.calls] == [":1", ":2", ":1", ":2"]


def test_sequential_runs_once_per_device_when_no_accounts():
    r = runner()
    r.run_sequential([":1", ":2"], [], gap=None)
    assert [c[1] for c in r.controller.calls] == [":1", ":2"]


def test_stop_button_ends_the_queue_immediately():
    flag = {"on": True}
    r = M.MacroRunner(Ctl(), [{"type": "tap", "x": "1", "y": "2", "delay": 0}],
                      log_cb=lambda t, k="info": None, running_check=lambda: flag["on"])
    orig = r.execute_one

    def stop_after_first(dev, acc):
        out = orig(dev, acc)
        flag["on"] = False
        return out

    r.execute_one = stop_after_first
    r.run_sequential([":1", ":2"], accounts(5), gap=None)
    assert len(r.controller.calls) == 1


def test_paused_device_is_skipped_but_others_keep_going():
    """จอที่รอผู้ใช้แก้ไขต้องไม่ถูกหยิบมาใช้อีก แต่บัญชีที่เหลือยังเดินต่อบนจออื่นได้"""
    r = runner()
    seen = []

    def fake(dev, acc):
        seen.append(dev)
        return "paused" if dev == ":1" else "completed"

    r.execute_one = fake
    r.run_sequential([":1", ":2"], accounts(6), gap=None)

    assert seen.count(":1") == 1          # เจอ paused ครั้งเดียวแล้วเลิกใช้จอนี้
    assert seen.count(":2") == 3          # จอที่เหลือรับงานต่อครบ


def test_stops_when_every_device_is_paused():
    r = runner()
    seen = []

    def fake(dev, acc):
        seen.append(dev)
        return "paused"

    r.execute_one = fake
    r.run_sequential([":1", ":2"], accounts(8), gap=None)
    assert len(seen) == 2                 # จอละครั้ง แล้วหยุด ไม่ไล่จนครบ 8 บัญชี


def test_gap_waits_between_accounts_but_not_after_the_last():
    slept = []
    r = runner()
    r._interruptible_sleep = lambda s: (slept.append(s), True)[1]
    r.run_sequential([":1"], accounts(3), gap=(0.4, 0.4))

    assert len(slept) == 2                # 3 บัญชี = พัก 2 ครั้ง ไม่พักหลังตัวสุดท้าย
    assert all(abs(s - 0.4) < 1e-9 for s in slept)


def test_gap_is_randomised_within_range():
    slept = []
    r = runner()
    r._interruptible_sleep = lambda s: (slept.append(s), True)[1]
    r.run_sequential([":1"], accounts(12), gap=(8.0, 20.0))

    assert all(8.0 <= s <= 20.0 for s in slept)
    assert len(set(slept)) > 1            # สุ่มจริง ไม่ใช่ค่าคงที่ (ค่าคงที่ก็ถูกจับได้ง่าย)


def test_stopping_during_the_gap_ends_the_run():
    r = runner()
    r._interruptible_sleep = lambda s: False      # จำลองผู้ใช้กดหยุดระหว่างพัก
    r.run_sequential([":1"], accounts(5), gap=(1.0, 1.0))
    assert len(r.controller.calls) == 1
