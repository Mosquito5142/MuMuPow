"""เทสชนิดขั้น 'ตอบคำถามอัตโนมัติ' (answer_quiz)

เคสจริง: ควิซชื่อเสียงในเกม ต้องตอบทีละข้อไปเรื่อย ๆ จนครบถึงจะได้รางวัล ซึ่งนานมาก
ผู้ใช้อยากให้เลือกเองแล้วหยุดทันทีที่ป๊อปอัพรับรางวัลขึ้น

โหมด longest ใช้สูตร 'ข้อที่ข้อความยาวสุดมักเป็นข้อถูก' — วัดความยาวด้วยการนับพิกเซล
ตัวอักษรในกล่อง ไม่ใช่ OCR เพราะข้อความเป็นภาษาไทย และเครื่องนี้ tesseract เห็นแค่ eng/osd
(ต่อให้อ่านได้ก็อ่านผิดบ่อยจนนับตัวอักษรไม่น่าเชื่อถือ) การนับพิกเซลไม่ขึ้นกับภาษาเลย
"""
import base64
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

import macro_runner as M
import web_app

DONE = base64.b64encode(b"REWARD").decode()


def quiz_screen(char_counts, box_w=220, box_h=50, origin=(100, 100), gap=(300, 120)):
    """สร้างภาพจอควิซปลอม: กล่องตัวเลือกเรียง 2 คอลัมน์ ข้อความยาวไม่เท่ากัน
    คืน (png_bytes, [จุดกึ่งกลางของแต่ละกล่อง])"""
    img = np.full((540, 960, 3), 245, np.uint8)
    pts = []
    for i, n in enumerate(char_counts):
        cx = origin[0] + (i % 2) * gap[0] + box_w // 2
        cy = origin[1] + (i // 2) * gap[1] + box_h // 2
        x0, y0 = cx - box_w // 2, cy - box_h // 2
        cv2.rectangle(img, (x0, y0), (x0 + box_w, y0 + box_h), (235, 225, 210), -1)
        for c in range(n):                       # ตัวอักษรจำลอง
            tx = x0 + 10 + c * 11
            if tx < x0 + box_w - 12:
                cv2.rectangle(img, (tx, y0 + 18), (tx + 7, y0 + 34), (60, 60, 60), -1)
        pts.append((cx, cy))
    return cv2.imencode(".png", img)[1].tobytes(), pts


class Ctl:
    """เจอภาพ 'ตอบครบแล้ว' หลังตอบครบ answer_after ข้อ

    นับจาก 'จำนวนครั้งที่กดโดนจุดตัวเลือก' — ต้องส่ง choice_pts เข้ามาให้รู้ว่าจุดไหนคือตัวเลือก
    (ถ้าไม่นับ ลูปจะไม่มีวันจบแล้วเทสค้างจนหมด timeout)"""

    def __init__(self, screen, answer_after=3, choice_pts=()):
        self.screen = screen
        self.answer_after = answer_after
        self.choice_pts = set(choice_pts)
        self.answers = 0
        self.taps = []

    def capture_screenshot_bytes(self, d):
        return True, self.screen

    def match_template_bytes(self, data, tmpl, thr=0.8):
        return (self.answers >= self.answer_after, 1, 2, "m")

    def find_image_in_bytes(self, *a, **k):
        return (False, 0, 0, "no")

    def tap(self, d, x, y):
        pt = (int(float(x)), int(float(y)))
        self.taps.append(pt)
        if pt in self.choice_pts:
            self.answers += 1
        return True, ""


def run(step, ctl):
    step = dict(step)
    step.setdefault("delay", 0)
    r = M.MacroRunner(ctl, [step], log_cb=lambda t, k="info": None, running_check=lambda: True)
    r._interruptible_sleep = lambda s: True
    status = r._run_steps(":7555", None, r.steps, lambda **kw: None)
    return ctl, status


def base(pts, **kw):
    step = {"type": "answer_quiz", "wait_img": DONE, "box": "220,50",
            "points": " | ".join(f"{x},{y}" for x, y in pts),
            "submit": "790,425", "timeout": 8, "interval": 1.0}
    step.update(kw)
    return step


# ---------- แปลงพิกัดจากข้อความ ----------

def test_parses_points_in_several_formats():
    assert M.MacroRunner.parse_points("417,257 | 699,257") == [(417, 257), (699, 257)]
    assert M.MacroRunner.parse_points("1,2;3,4") == [(1, 2), (3, 4)]
    assert M.MacroRunner.parse_points("5,6" + chr(10) + "7,8") == [(5, 6), (7, 8)]
    assert M.MacroRunner.parse_points("") == []
    assert M.MacroRunner.parse_points("ขยะ|9,9") == [(9, 9)]


# ---------- โหมดข้อยาวสุด ----------

def test_picks_the_choice_with_the_longest_text():
    """ข้อ 3 ยาวสุด -> ต้องกดข้อ 3 ไม่ใช่ข้ออื่น"""
    screen, pts = quiz_screen([3, 6, 17, 8])
    ctl, _ = run(base(pts), Ctl(screen, answer_after=1, choice_pts=pts))
    assert ctl.taps[0] == pts[2]


def test_longest_choice_works_wherever_it_sits():
    for longest_at in range(4):
        counts = [4, 4, 4, 4]
        counts[longest_at] = 18
        screen, pts = quiz_screen(counts)
        ctl, _ = run(base(pts), Ctl(screen, answer_after=1, choice_pts=pts))
        assert ctl.taps[0] == pts[longest_at], f"เลือกผิดเมื่อข้อยาวอยู่ตำแหน่ง {longest_at}"


def test_presses_submit_after_choosing():
    screen, pts = quiz_screen([3, 9])
    ctl, _ = run(base(pts), Ctl(screen, answer_after=1, choice_pts=pts))
    assert (790, 425) in ctl.taps


def test_works_without_a_submit_button():
    screen, pts = quiz_screen([3, 9])
    ctl, _ = run(base(pts, submit=""), Ctl(screen, answer_after=1, choice_pts=pts))
    assert ctl.taps == [pts[1]]           # กดแต่ข้อ ไม่มีการกดปุ่มส่ง


def test_stops_as_soon_as_the_reward_appears():
    screen, pts = quiz_screen([3, 9])
    ctl, status = run(base(pts), Ctl(screen, answer_after=2, choice_pts=pts))
    assert status == "completed"
    assert ctl.answers == 2               # ตอบ 2 ข้อแล้วเจอรางวัล -> หยุด


def test_does_nothing_when_already_finished():
    screen, pts = quiz_screen([3, 9])
    ctl, _ = run(base(pts), Ctl(screen, answer_after=0, choice_pts=pts))
    assert ctl.taps == []


# ---------- โหมดไล่ทีละข้อ ----------

def test_cycle_mode_tries_each_choice_in_turn():
    screen, pts = quiz_screen([5, 5, 5, 5])
    ctl, _ = run(base(pts, mode="cycle"), Ctl(screen, answer_after=3, choice_pts=pts))
    picked = [t for t in ctl.taps if t in pts]
    assert picked == [pts[0], pts[1], pts[2]]


def test_cycle_mode_wraps_around():
    screen, pts = quiz_screen([5, 5])
    ctl, _ = run(base(pts, mode="cycle"), Ctl(screen, answer_after=3, choice_pts=pts))
    picked = [t for t in ctl.taps if t in pts]
    assert picked == [pts[0], pts[1], pts[0]]


# ---------- ตั้งค่าไม่ครบ / กันพัง ----------

def test_skips_without_choice_points():
    screen, _ = quiz_screen([5])
    ctl, status = run({"type": "answer_quiz", "wait_img": DONE, "timeout": 1}, Ctl(screen, 99))
    assert ctl.taps == [] and status == "completed"


def test_skips_without_a_target_image():
    screen, pts = quiz_screen([5, 5])
    ctl, status = run({"type": "answer_quiz", "points": "1,2|3,4", "timeout": 1}, Ctl(screen, 99))
    assert ctl.taps == [] and status == "completed"


def test_timeout_does_not_fail_the_account():
    screen, pts = quiz_screen([3, 9])
    ctl, status = run(base(pts, timeout=0.0001), Ctl(screen, answer_after=999, choice_pts=pts))
    assert status == "completed"


def test_stop_button_ends_it():
    screen, pts = quiz_screen([3, 9])
    ctl = Ctl(screen, answer_after=999, choice_pts=pts)
    flag = {"on": True}
    r = M.MacroRunner(ctl, [dict(base(pts), delay=0)], log_cb=lambda t, k="info": None,
                      running_check=lambda: flag["on"])
    r._interruptible_sleep = lambda s: flag["on"]
    real = ctl.tap

    def tap_then_stop(d, x, y):
        flag["on"] = False
        return real(d, x, y)

    ctl.tap = tap_then_stop
    r._run_steps(":7555", None, r.steps, lambda **kw: None)
    assert len(ctl.taps) == 1


# ---------- ลงทะเบียนในตัวแก้ไข ----------

def test_registered_in_every_editor_table():
    api = web_app.Api.__new__(web_app.Api)
    t = "answer_quiz"
    assert t in {o["value"] for o in web_app.Api._step_type_options(api)}
    for f in ("points", "submit", "box", "mode", "timeout", "threshold"):
        assert f in web_app.Api.STEP_FIELDS[t]
    assert web_app.Api.STEP_DEFAULTS[t]["mode"] == "longest"
    assert t in web_app.Api._STEP_TH


def test_form_fields_are_wired_both_ways():
    import io as _io
    js = _io.open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "webui", "app.js"), encoding="utf-8").read()
    for fld in ("sfPoints", "sfSubmit", "sfBox", "sfMode"):
        assert js.count(fld) >= 2, f"{fld} ยังไม่ถูกผูกครบทั้งตอนโหลดและตอนบันทึก"
