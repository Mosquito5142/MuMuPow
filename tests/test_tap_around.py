"""เทสชนิดขั้น 'กดรอบๆ การ์ดจนเจอรูป' (tap_around_until_image)

เคสจริง: การ์ดร้านค้าในเกม กดตรงรูปไอเทมแล้วเกมไม่รับ ต้องกดโดนพื้นการ์ดส่วนอื่น
และการ์ดก็ไม่ได้อยู่ตำแหน่งเดิมทุกครั้ง (รายการเลื่อน/สลับที่)

ขั้นนี้: หาการ์ดใหม่ทุกรอบ -> ไล่กดหลายจุดในการ์ด -> ภาพเป้าหมาย (modal) ขึ้นแล้วไปต่อ
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

TARGET = base64.b64encode(b"MODAL").decode()


def card_png(w=120, h=90):
    """ภาพการ์ดจริง ๆ (ต้องถอดรหัสได้ เพราะโค้ดอ่านขนาดจากภาพเพื่อคำนวณกรอบ)"""
    img = np.zeros((h, w, 3), np.uint8)
    img[:, :, 1] = 200
    return base64.b64encode(cv2.imencode(".png", img)[1].tobytes()).decode()


CARD = card_png()


class Ctl:
    """เจอ modal หลังถูกกดครบ open_after ครั้ง — จำลองเกมที่ต้องกดหลายจุดกว่าจะติด"""

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
        return (self.card_found, self.card_at[0], self.card_at[1], "m")   # ภาพการ์ด

    def find_image_in_bytes(self, *a, **k):
        return (False, 0, 0, "no")

    def tap(self, d, x, y):
        self.taps.append((int(float(x)), int(float(y))))
        return True, ""


def run(step, ctl=None):
    step = dict(step)
    step.setdefault("delay", 0)
    r = M.MacroRunner(ctl or Ctl(), [step], log_cb=lambda t, k="info": None,
                      running_check=lambda: True)
    r._interruptible_sleep = lambda s: True
    status = r._run_steps(":7555", None, r.steps, lambda **kw: None)
    return r.controller, status


BASE = {"type": "tap_around_until_image", "find_img": CARD, "wait_img": TARGET,
        "interval": 0.5, "timeout": 30, "threshold": 0.8}


# ---------- พฤติกรรมหลัก ----------

def test_taps_several_different_spots_not_the_same_one():
    """หัวใจของปัญหา: กดจุดเดิมซ้ำไม่ช่วย ต้องกระจายจุดกดในการ์ด"""
    ctl, status = run(BASE, Ctl(open_after=4))
    assert status == "completed"
    assert len(set(ctl.taps)) >= 3, f"กดจุดซ้ำเดิมตลอด: {ctl.taps}"


def test_does_not_start_at_the_centre_of_the_card():
    """กลางการ์ดคือรูปไอเทมที่เกมไม่รับการกด — ต้องไม่ใช่จุดแรกที่ลอง"""
    ctl, _ = run(BASE, Ctl(open_after=9))
    assert ctl.taps[0] != (500, 300)


def test_all_taps_land_inside_the_card_box():
    """การ์ด 120x90 อยู่กึ่งกลาง (500,300) -> ทุกจุดต้องอยู่ในกรอบนั้น ไม่หลุดไปโดนการ์ดข้าง ๆ"""
    ctl, _ = run(BASE, Ctl(open_after=99))
    for x, y in ctl.taps:
        assert 500 - 60 <= x <= 500 + 60, f"x={x} หลุดกรอบการ์ด"
        assert 300 - 45 <= y <= 300 + 45, f"y={y} หลุดกรอบการ์ด"


def test_stops_as_soon_as_the_modal_appears():
    ctl, _ = run(BASE, Ctl(open_after=2))
    assert len(ctl.taps) == 2, "เจอ modal แล้วต้องหยุดกดทันที"


def test_does_not_tap_at_all_if_modal_is_already_open():
    ctl, _ = run(BASE, Ctl(open_after=0))
    assert ctl.taps == []


def test_relocates_the_card_every_round():
    """รายการร้านค้าเลื่อนได้ระหว่างกด — ต้องหาการ์ดใหม่ทุกรอบ ไม่ใช่จำตำแหน่งครั้งแรก"""
    ctl = Ctl(open_after=3)
    calls = []
    orig = ctl.match_template_bytes

    def spy(data, tmpl, thr=0.8):
        if tmpl != b"MODAL":
            calls.append(1)
        return orig(data, tmpl, thr)

    ctl.match_template_bytes = spy
    run(BASE, ctl)
    assert len(calls) >= 3, "ต้องหาการ์ดใหม่ทุกรอบที่กด"


def test_waits_when_the_card_is_not_on_screen_yet():
    ctl, status = run(dict(BASE, timeout=0.0001), Ctl(open_after=99, card_found=False))
    assert ctl.taps == []            # ไม่เจอการ์ด = ไม่กดมั่ว
    assert status == "completed"     # แต่ไม่ล้มทั้งบัญชี


def test_falls_back_to_a_fixed_point_when_no_card_image():
    ctl, _ = run({"type": "tap_around_until_image", "wait_img": TARGET,
                  "x": "400", "y": "250", "radius": 40, "timeout": 30, "delay": 0},
                 Ctl(open_after=3))
    for x, y in ctl.taps:
        assert 360 <= x <= 440 and 210 <= y <= 290


def test_gives_up_after_timeout_without_failing_the_account():
    ctl, status = run(dict(BASE, timeout=0.0001), Ctl(open_after=999))
    assert status == "completed"


def test_skips_when_target_image_missing():
    ctl, status = run({"type": "tap_around_until_image", "find_img": CARD, "timeout": 1})
    assert ctl.taps == [] and status == "completed"


def test_skips_when_neither_card_image_nor_coordinate():
    ctl, status = run({"type": "tap_around_until_image", "wait_img": TARGET, "timeout": 1})
    assert ctl.taps == [] and status == "completed"


def test_stop_button_ends_it_immediately():
    flag = {"on": True}
    ctl = Ctl(open_after=999)
    r = M.MacroRunner(ctl, [dict(BASE, delay=0)], log_cb=lambda t, k="info": None,
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
    t = "tap_around_until_image"
    assert t in {o["value"] for o in web_app.Api._step_type_options(api)}
    for f in ("x", "y", "radius", "interval", "timeout", "threshold"):
        assert f in web_app.Api.STEP_FIELDS[t]
    assert t in web_app.Api._STEP_TH


def test_find_image_is_stored_separately_from_target():
    """ภาพการ์ดกับภาพเป้าหมายต้องคนละฟิลด์ ไม่งั้นทับกันแล้วขั้นนี้ทำงานไม่ได้"""
    a = web_app.Api.__new__(web_app.Api)
    a.macro_steps = [{"type": "tap_around_until_image"}]
    a.current_profile = "t"
    a._push_log = lambda *x, **k: None

    a.flow_set_image([0], CARD, {"x": 1, "y": 2, "w": 3, "h": 4}, mode="find")
    a.flow_set_image([0], TARGET, None, mode="wait")

    s = a.macro_steps[0]
    assert s["find_img"] == CARD and s["wait_img"] == TARGET
    assert "anchor_img" not in s


def test_both_images_survive_editing_the_step():
    a = web_app.Api.__new__(web_app.Api)
    a._push_log = lambda *x, **k: None
    out = a._canonical_step("tap_around_until_image", {"timeout": 20},
                            {"find_img": CARD, "wait_img": TARGET,
                             "find_region": {"x": 0, "y": 0, "w": 1, "h": 1}})
    assert out["find_img"] == CARD and out["wait_img"] == TARGET
    assert out["find_region"] == {"x": 0, "y": 0, "w": 1, "h": 1}
