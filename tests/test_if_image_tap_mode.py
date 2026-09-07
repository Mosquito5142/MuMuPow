"""เทส if_image ที่ 'กดไปด้วยระหว่างรอภาพ' (tap_mode)

เคสจริง: ในสคริปต์รับของ ต้องกดรอบ ๆ การ์ดในเวลาที่กำหนด
 - ถ้า modal ขึ้น  -> ทำกิ่ง 'เจอ'
 - ถ้าครบเวลาแล้วไม่ขึ้น -> ทำกิ่ง 'ไม่เจอ' (อีกแบบหนึ่ง)

ต่างจากขั้น tap_around_until_image ที่ครบเวลาแล้วเตือนเฉย ๆ แล้วไหลไปขั้นถัดไป

กติกาที่เทสนี้ล็อกไว้:
1. ไม่ตั้ง tap_mode = ต้องไม่กดอะไรเลย และจังหวะ poll ต้องเป็น 0.4 วิเท่าเดิม
   (สคริปต์เก่าทั้งหมดใช้ if_image แบบรอเฉย ๆ อยู่ ห้ามเปลี่ยนพฤติกรรม)
2. ตั้งโหมดกดแต่ตั้งค่าไม่ครบ = ถอยไป 'รอเฉย ๆ' + เตือน ไม่ใช่กดมั่วที่ (0,0)
3. เช็คภาพก่อนกดเสมอ — ถ้า modal เปิดอยู่แล้วต้องไม่กดทับ
"""
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

import macro_runner as M

COND = base64.b64encode(b"MODAL").decode()      # ภาพเงื่อนไข (modal ที่รอให้ขึ้น)


def card_png(w=120, h=90):
    img = np.zeros((h, w, 3), np.uint8)
    img[:, :, 1] = 200
    return base64.b64encode(cv2.imencode(".png", img)[1].tobytes()).decode()


CARD = card_png()


class FakeTime:
    """นาฬิกาปลอม — เดินหน้าเฉพาะตอน sleep ทำให้เทสหมดเวลาได้ทันทีโดยไม่ต้องรอจริง"""

    def __init__(self):
        self.t = 1000.0

    def time(self):
        return self.t

    def sleep(self, s):
        self.t += float(s or 0)


class Ctl:
    """เจอ modal หลังถูกกดครบ open_after ครั้ง (open_after=0 = เปิดอยู่แล้วตั้งแต่ต้น)"""

    def __init__(self, open_after=3, card_at=(500, 300), card_found=True):
        self.open_after = open_after
        self.card_at = card_at
        self.card_found = card_found
        self.taps = []

    def capture_screenshot_bytes(self, d):
        return True, b"SCREEN"

    def match_template_bytes(self, data, tmpl, thr=0.8):
        if tmpl == b"MODAL":
            return (len(self.taps) >= self.open_after, 1, 2, "m")
        return (self.card_found, self.card_at[0], self.card_at[1], "m")

    def find_image_in_bytes(self, *a, **k):
        return (False, 0, 0, "no")

    def tap(self, d, x, y):
        self.taps.append((int(float(x)), int(float(y))))
        return True, ""


def _runner(steps, ctl, running=True):
    logs = []
    ft = FakeTime()
    r = M.MacroRunner(ctl, steps, log_cb=lambda t, k="info": logs.append((k, t)),
                      running_check=(running if callable(running) else (lambda: running)))
    r._time = ft
    naps = []

    def nap(s):
        naps.append(float(s))
        ft.sleep(s)
        return r.running()

    r._interruptible_sleep = nap
    r._naps = naps
    r._logs = logs
    r._ft = ft
    return r


def ev(step, ctl=None, running=True, monkeypatch=None):
    """เรียก _eval_if_image ตรง ๆ พร้อมนาฬิกาปลอม — คืน (branch, controller, runner)"""
    ctl = ctl or Ctl()
    r = _runner([dict(step)], ctl, running)
    old = M.time
    M.time = r._ft
    try:
        branch = r._eval_if_image(":7555", dict(step))
    finally:
        M.time = old
    return branch, ctl, r


BASE = {"type": "if_image", "anchor_img": COND, "timeout": 5.0, "threshold": 0.8,
        "then": [], "else": []}


# ---------- พฤติกรรมเดิมต้องไม่เปลี่ยน ----------

def test_without_tap_mode_nothing_is_tapped():
    branch, ctl, _ = ev(BASE, Ctl(open_after=99))
    assert branch == "else"
    assert ctl.taps == [], "if_image แบบเดิมต้องไม่แตะจอเลย"


def test_without_tap_mode_polls_every_04s_as_before():
    _b, _c, r = ev(BASE, Ctl(open_after=99))
    assert set(r._naps) == {0.4}, f"จังหวะ poll เปลี่ยนไป: {set(r._naps)}"


def test_without_tap_mode_still_finds_the_image():
    branch, ctl, _ = ev(BASE, Ctl(open_after=0))
    assert branch == "then"
    assert ctl.taps == []


# ---------- โหมดกดพิกัดซ้ำ ๆ ----------

def test_point_mode_taps_the_same_spot_until_found():
    step = dict(BASE, tap_mode="point", x="640", y="480", interval=0.5)
    branch, ctl, _ = ev(step, Ctl(open_after=3))
    assert branch == "then"
    assert ctl.taps == [(640, 480)] * 3


def test_point_mode_uses_interval_not_04():
    step = dict(BASE, tap_mode="point", x="640", y="480", interval=0.2)
    _b, _c, r = ev(step, Ctl(open_after=3))
    assert set(r._naps) == {0.2}


def test_point_mode_falls_to_else_when_time_runs_out():
    step = dict(BASE, tap_mode="point", x="640", y="480", interval=0.5, timeout=2.0)
    branch, ctl, _ = ev(step, Ctl(open_after=99))
    assert branch == "else"
    assert len(ctl.taps) >= 3, "หมดเวลาแล้วควรได้กดไปหลายครั้ง"


def test_modal_already_open_is_not_tapped_over():
    """เช็คภาพก่อนกด — ถ้า modal เปิดอยู่แล้วต้องไม่กดทับจนหลุดหน้า"""
    step = dict(BASE, tap_mode="point", x="640", y="480")
    branch, ctl, _ = ev(step, Ctl(open_after=0))
    assert branch == "then"
    assert ctl.taps == []


# ---------- โหมดไล่กดรอบๆ การ์ด ----------

def test_around_mode_spreads_taps_over_the_card():
    step = dict(BASE, tap_mode="around", find_img=CARD, interval=0.5)
    branch, ctl, _ = ev(step, Ctl(open_after=4))
    assert branch == "then"
    assert len(set(ctl.taps)) >= 3, f"กดจุดเดิมซ้ำตลอด: {ctl.taps}"


def test_around_mode_taps_land_inside_the_card_box():
    step = dict(BASE, tap_mode="around", find_img=CARD, interval=0.5)
    _b, ctl, _ = ev(step, Ctl(open_after=6, card_at=(500, 300)))
    for x, y in ctl.taps:                     # การ์ด 120x90 รอบจุด (500,300)
        assert 440 <= x <= 560, (x, y)
        assert 255 <= y <= 345, (x, y)


def test_around_mode_without_card_image_uses_xy_and_radius():
    step = dict(BASE, tap_mode="around", x="500", y="300", radius=40, interval=0.5)
    _b, ctl, _ = ev(step, Ctl(open_after=6))
    assert ctl.taps, "ต้องกดได้แม้ไม่ได้ตั้งภาพการ์ด"
    for x, y in ctl.taps:
        assert 460 <= x <= 540, (x, y)
        assert 260 <= y <= 340, (x, y)


def test_around_mode_waits_when_card_not_on_screen_yet():
    step = dict(BASE, tap_mode="around", find_img=CARD, interval=0.5, timeout=2.0)
    branch, ctl, r = ev(step, Ctl(open_after=99, card_found=False))
    assert branch == "else"
    assert ctl.taps == [], "หาการ์ดไม่เจอต้องไม่กดมั่ว"
    assert any("ยังไม่เจอการ์ด" in t for _k, t in r._logs)


# ---------- ตั้งค่าไม่ครบ = ถอยไปรอเฉย ๆ ไม่ใช่กดมั่ว ----------

def test_around_mode_without_card_or_xy_falls_back_to_waiting():
    step = dict(BASE, tap_mode="around", timeout=2.0)
    branch, ctl, r = ev(step, Ctl(open_after=99))
    assert branch == "else"
    assert ctl.taps == [], "ไม่มีทั้งภาพการ์ดและพิกัด ต้องไม่กดที่ (0,0)"
    assert any("รอเฉย ๆ แทน" in t for _k, t in r._logs)


def test_point_mode_without_xy_falls_back_to_waiting():
    step = dict(BASE, tap_mode="point", timeout=2.0)
    branch, ctl, r = ev(step, Ctl(open_after=99))
    assert branch == "else"
    assert ctl.taps == []
    assert any("รอเฉย ๆ แทน" in t for _k, t in r._logs)


def test_unknown_tap_mode_is_treated_as_none():
    step = dict(BASE, tap_mode="อะไรไม่รู้", x="1", y="2", timeout=2.0)
    _b, ctl, _ = ev(step, Ctl(open_after=99))
    assert ctl.taps == []


def test_stop_pressed_mid_wait_returns_stopped():
    step = dict(BASE, tap_mode="point", x="640", y="480", timeout=5.0)
    branch, _ctl, _r = ev(step, Ctl(open_after=99), running=lambda: False)
    assert branch == "stopped"


# ---------- ต่อกับกิ่ง then/else จริง ----------

def _branch_taken(open_after, timeout=3.0):
    """รันผ่าน _run_steps จริง แล้วดูว่าเข้ากิ่งไหน (กิ่งละ 1 ขั้น tap ที่พิกัดต่างกัน)"""
    step = {"type": "if_image", "anchor_img": COND, "tap_mode": "around",
            "find_img": CARD, "interval": 0.5, "timeout": timeout, "delay": 0,
            "then": [{"type": "tap", "x": "11", "y": "11", "delay": 0}],
            "else": [{"type": "tap", "x": "99", "y": "99", "delay": 0}]}
    ctl = Ctl(open_after=open_after)
    r = _runner([step], ctl)
    old = M.time
    M.time = r._ft
    try:
        status = r._run_steps(":7555", None, r.steps, lambda **kw: None)
    finally:
        M.time = old
    return status, ctl


def test_found_runs_the_then_branch():
    status, ctl = _branch_taken(open_after=3)
    assert status == "completed"
    assert ctl.taps[-1] == (11, 11), f"ควรจบด้วยกิ่ง 'เจอ': {ctl.taps}"


def test_not_found_runs_the_else_branch():
    status, ctl = _branch_taken(open_after=999, timeout=2.0)
    assert status == "completed"
    assert ctl.taps[-1] == (99, 99), f"ควรจบด้วยกิ่ง 'ไม่เจอ': {ctl.taps}"


def test_old_flat_if_image_scripts_still_pick_branches():
    """ground rule #1: สคริปต์เก่าที่ไม่มี tap_mode ต้องทำงานเหมือนเดิมเป๊ะ"""
    step = {"type": "if_image", "anchor_img": COND, "timeout": 2.0, "delay": 0,
            "then": [{"type": "tap", "x": "11", "y": "11", "delay": 0}],
            "else": [{"type": "tap", "x": "99", "y": "99", "delay": 0}]}
    for open_after, expect in ((0, (11, 11)), (999, (99, 99))):
        ctl = Ctl(open_after=open_after)
        r = _runner([dict(step)], ctl)
        old = M.time
        M.time = r._ft
        try:
            r._run_steps(":7555", None, r.steps, lambda **kw: None)
        finally:
            M.time = old
        assert ctl.taps == [expect], f"open_after={open_after}: {ctl.taps}"
