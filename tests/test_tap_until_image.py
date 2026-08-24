"""เทสชนิดขั้นใหม่ 'กดรัวจนเจอรูป' (tap_until_image)

ที่มา: หน้าโฆษณา/คัตซีนต้องกดข้ามหลายครั้งติดกันโดยไม่รู้ว่ากี่ครั้ง เดิมต้องใส่ tap ซ้ำ ๆ
เป็นสิบขั้นแล้วเดาจำนวนเอา ซึ่งพังทันทีที่โฆษณายาว/สั้นกว่าที่เดาไว้

ขั้นนี้กดพิกัดเดิมซ้ำทุก interval วินาที จนกว่าจะเจอ 'ภาพเป้าหมาย' แล้วค่อยไปขั้นต่อไป
"""
import base64
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import macro_runner as M
import web_app

B64 = base64.b64encode(b"TARGET").decode()


class Ctl:
    """เจอภาพเป้าหมายหลังถูกเช็คครบ find_after ครั้ง"""

    def __init__(self, find_after=3):
        self.find_after = find_after
        self.checks = 0
        self.taps = []

    def capture_screenshot_bytes(self, d):
        return True, b"SCREEN"

    def match_template_bytes(self, data, tmpl, thr=0.8):
        self.checks += 1
        return (self.checks > self.find_after, 70, 80, "m")

    def find_image_in_bytes(self, data, path, threshold=0.8):
        self.checks += 1
        return (self.checks > self.find_after, 70, 80, "m")

    def tap(self, d, x, y):
        self.taps.append((int(float(x)), int(float(y))))
        return True, ""


def run(step, find_after=3, running=True):
    step = dict(step)
    step.setdefault("delay", 0)
    r = M.MacroRunner(Ctl(find_after), [step], log_cb=lambda t, k="info": None,
                      running_check=(running if callable(running) else (lambda: running)))
    r._interruptible_sleep = lambda s: True      # ไม่ต้องรอจริงตอนเทส
    status = r._run_steps(":7555", None, r.steps, lambda **kw: None)
    return r.controller, status


BASE = {"type": "tap_until_image", "x": "880", "y": "40", "wait_img": B64,
        "interval": 0.5, "timeout": 30}


# ---------- พฤติกรรมหลัก ----------

def test_taps_repeatedly_until_the_target_appears():
    ctl, status = run(BASE, find_after=3)
    assert ctl.taps == [(880, 40)] * 3       # กด 3 ครั้ง แล้วรอบที่ 4 เจอภาพ
    assert status == "completed"


def test_does_not_tap_at_all_if_already_on_the_target_screen():
    """เช็คภาพก่อนกดเสมอ — ถ้าถึงหน้าที่ต้องการอยู่แล้วต้องไม่กดเกินไปอีกที"""
    ctl, _ = run(BASE, find_after=0)
    assert ctl.taps == []


def test_moves_on_without_tapping_the_target_by_default():
    """ค่าเริ่มต้น: เจอแล้วไปขั้นต่อไปเฉย ๆ ไม่กดที่ภาพ (ภาพมักเป็นแค่ตัวบอกว่ามาถึงแล้ว)"""
    ctl, _ = run(BASE, find_after=2)
    assert (70, 80) not in ctl.taps


def test_can_also_tap_the_target_when_asked():
    ctl, _ = run(dict(BASE, click=True), find_after=2)
    assert ctl.taps[-1] == (70, 80)


def test_gives_up_after_timeout_but_keeps_the_run_going():
    """ครบเวลาแล้วยังไม่เจอ = เตือนแล้วไปต่อ ไม่ล้มทั้งบัญชี
    (ปล่อยให้ด่าน anchor ของขั้นถัดไปเป็นคนตัดสินว่าจอผิดจริงไหม)"""
    ctl, status = run(dict(BASE, timeout=0.0001), find_after=9999)
    assert status == "completed"


def test_stop_button_ends_the_spam_immediately():
    flag = {"on": True}
    r = M.MacroRunner(Ctl(9999), [dict(BASE, delay=0)],
                      log_cb=lambda t, k="info": None, running_check=lambda: flag["on"])
    r._interruptible_sleep = lambda s: flag["on"]

    real_tap = r.controller.tap
    def tap_then_stop(d, x, y):
        flag["on"] = False
        return real_tap(d, x, y)
    r.controller.tap = tap_then_stop

    r._run_steps(":7555", None, r.steps, lambda **kw: None)
    assert len(r.controller.taps) == 1


# ---------- ตั้งค่าไม่ครบ ----------

def test_skips_when_no_target_image_is_set():
    ctl, status = run({"type": "tap_until_image", "x": "1", "y": "2", "timeout": 1})
    assert ctl.taps == [] and status == "completed"


def test_skips_when_no_coordinate_is_set():
    ctl, status = run({"type": "tap_until_image", "wait_img": B64, "timeout": 1})
    assert ctl.taps == [] and status == "completed"


def test_accepts_a_template_file_too(tmp_path, monkeypatch):
    """ตั้งภาพด้วยชื่อไฟล์ใน templates/ ก็ได้ เหมือนชนิดอื่น"""
    (tmp_path / "lobby.png").write_bytes(b"png")
    monkeypatch.setattr(M, "templates_dir", lambda: str(tmp_path))
    ctl, _ = run({"type": "tap_until_image", "x": "5", "y": "6",
                  "text": "lobby.png", "timeout": 30}, find_after=2)
    assert ctl.taps == [(5, 6)] * 2


def test_interval_cannot_be_zero():
    """interval 0 จะกลายเป็นกดรัวไม่หยุดจนกิน CPU/ADB — ต้องมีพื้นขั้นต่ำเสมอ
    (บทเรียนเดียวกับ anchor_poll ที่เคยทำให้ทั้งเครื่องค้าง)"""
    captured = []
    r = M.MacroRunner(Ctl(2), [dict(BASE, interval=0, delay=0)],
                      log_cb=lambda t, k="info": None, running_check=lambda: True)
    r._interruptible_sleep = lambda s: (captured.append(s), True)[1]
    r._run_steps(":7555", None, r.steps, lambda **kw: None)
    assert captured and min(captured) >= 0.05


# ---------- ต้องลงทะเบียนในตัวแก้ไขครบ ----------

def test_registered_everywhere_the_editor_needs_it():
    """ชนิดที่ตัวรันทำได้แต่ตัวแก้ไขไม่รู้จัก = ผู้ใช้สร้างไม่ได้ และฟิลด์จะโดนล้างตอนแก้"""
    api = web_app.Api.__new__(web_app.Api)
    t = "tap_until_image"
    assert t in {o["value"] for o in web_app.Api._step_type_options(api)}
    assert t in web_app.Api.STEP_FIELDS
    assert t in web_app.Api.STEP_DEFAULTS
    assert t in web_app.Api._STEP_TH
    for f in ("x", "y", "interval", "timeout", "threshold"):
        assert f in web_app.Api.STEP_FIELDS[t]


def test_dispatch_has_a_real_branch_for_it():
    import inspect
    assert '"tap_until_image"' in inspect.getsource(M.MacroRunner._dispatch)
    assert "tap_until_image" not in M.MacroRunner._UNSUPPORTED


def test_interval_and_radius_fields_are_wired_into_the_form():
    """บั๊กที่เจอ: ช่อง 'กดซ้ำทุกกี่วินาที' ถูกเพิ่มใน index.html และ STEP_FIELD_MAP แล้ว
    แต่ไม่เคยถูกผูกเข้า fillStepForm/collectStepPatch — ช่องโชว์ได้แต่ค่าไม่โหลดและไม่เซฟ
    ผู้ใช้จึงปรับจังหวะกดไม่ได้เลยทั้งที่เห็นช่องอยู่ตรงหน้า"""
    import io
    import os
    js = io.open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "webui", "app.js"), encoding="utf-8").read()
    for fld in ("sfInterval", "sfRadius"):
        assert js.count(fld) >= 2, f"{fld} ยังไม่ถูกผูกครบทั้งตอนโหลดและตอนบันทึก"
    assert "p.interval=g('sfInterval')" in js
    assert "p.radius=g('sfRadius')" in js
