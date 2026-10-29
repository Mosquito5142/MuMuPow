"""เทสชนิดขั้นใหม่ 'กดที่รูป' (tap_image)

ที่มา: มีคำสั่งกดรัว/รอภาพหลายแบบแล้ว แต่ยังไม่มีคำสั่งที่ 'หาภาพแล้วกดตรงภาพนั้นครั้งเดียว'
โดยรอภาพขึ้นได้ (detect_image เช็ครอบเดียวแล้วจบ, tap_until_image กดพิกัดอื่นรัวระหว่างรอ)

ขั้นนี้: เช็คจอทุก ~0.5 วิ จนเจอภาพ → แตะกึ่งกลางภาพ 1 ครั้ง → ไปต่อ
ครบ timeout ยังไม่เจอ → on_fail="skip" เตือนแล้วไปต่อ / on_fail="fail" นับว่าบัญชีล้ม
(จำลอง screenshot/tap ทั้งหมด ไม่ต้องมีอีมูเลเตอร์จริง)
"""
import base64
import inspect
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import macro_runner as M
import web_app

B64 = base64.b64encode(b"TARGET").decode()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Ctl:
    """เจอภาพเป้าหมายหลังถูกเช็คครบ find_after ครั้ง (กึ่งกลางภาพอยู่ที่ 70,80)"""

    def __init__(self, find_after=0, tap_ok=True):
        self.find_after = find_after
        self.checks = 0
        self.thresholds = []
        self.taps = []
        self.tap_ok = tap_ok

    def capture_screenshot_bytes(self, d):
        return True, b"SCREEN"

    def match_template_bytes(self, data, tmpl, thr=0.8):
        self.checks += 1
        self.thresholds.append(thr)
        return (self.checks > self.find_after, 70, 80, "m")

    def find_image_in_bytes(self, data, path, threshold=0.8):
        self.checks += 1
        self.thresholds.append(threshold)
        return (self.checks > self.find_after, 70, 80, "m")

    def tap(self, d, x, y):
        self.taps.append((int(float(x)), int(float(y))))
        return (True, "") if self.tap_ok else (False, "device offline")


def make(step, find_after=0, tap_ok=True, running=lambda: True):
    step = dict(step)
    step.setdefault("delay", 0)
    logs = []
    r = M.MacroRunner(Ctl(find_after, tap_ok), [step],
                      log_cb=lambda t, k="info": logs.append((k, t)), running_check=running)
    r._interruptible_sleep = lambda s: running()      # ไม่ต้องรอจริงตอนเทส
    return r, logs


def run(step, **kw):
    r, logs = make(step, **kw)
    status = r._run_steps(":7555", None, r.steps, lambda **k: None)
    return r.controller, status, logs


BASE = {"type": "tap_image", "wait_img": B64, "timeout": 30}


# ---------- พฤติกรรมหลัก ----------

def test_taps_the_center_of_the_image_once_when_found():
    ctl, status, _ = run(BASE, find_after=0)
    assert ctl.taps == [(70, 80)]
    assert status == "completed"


def test_waits_for_the_image_then_taps_only_once():
    """ระหว่างรอต้องไม่กดอะไรเลย (ต่างจาก tap_until_image) เจอแล้วกดครั้งเดียว"""
    ctl, _, _ = run(BASE, find_after=4)
    assert ctl.checks == 5
    assert ctl.taps == [(70, 80)]


def test_threshold_is_passed_to_the_matcher():
    ctl, _, _ = run(dict(BASE, threshold=0.93))
    assert ctl.thresholds == [0.93]


def test_default_threshold_is_08():
    ctl, _, _ = run(BASE)
    assert ctl.thresholds == [0.8]


def test_accepts_a_template_file_too(tmp_path, monkeypatch):
    (tmp_path / "btn.png").write_bytes(b"png")
    monkeypatch.setattr(M, "templates_dir", lambda: str(tmp_path))
    ctl, _, _ = run({"type": "tap_image", "text": "btn.png", "timeout": 5}, find_after=1)
    assert ctl.taps == [(70, 80)]


# ---------- ไม่เจอภาพ ----------

def test_not_found_skips_by_default_and_keeps_the_run_going():
    ctl, status, logs = run(dict(BASE, timeout=0), find_after=9999)
    assert ctl.taps == []
    assert status == "completed"
    assert any(k == "warn" and "ยังไม่เจอ" in t for k, t in logs)


def test_timeout_zero_checks_exactly_once():
    ctl, _, _ = run(dict(BASE, timeout=0), find_after=9999)
    assert ctl.checks == 1


def test_not_found_with_on_fail_fail_marks_the_account_failed():
    ctl, status, _ = run(dict(BASE, timeout=0, on_fail="fail"), find_after=9999)
    assert ctl.taps == []
    assert status != "completed"


def test_keeps_checking_until_timeout(monkeypatch):
    """จำลองนาฬิกา: ทุกครั้งที่นอนให้เวลาเดิน 0.5 วิ — timeout 2 วิ ต้องเช็คหลายรอบแล้วค่อยยอม"""
    clock = {"t": 1000.0}
    monkeypatch.setattr(M.time, "time", lambda: clock["t"])
    r, _ = make(dict(BASE, timeout=2), find_after=9999)

    def fake_sleep(s):
        clock["t"] += s
        return True
    r._interruptible_sleep = fake_sleep
    r._run_steps(":7555", None, r.steps, lambda **k: None)
    assert r.controller.checks == 5          # t=0, 0.5, 1.0, 1.5, 2.0
    assert r.controller.taps == []


def test_adb_tap_failure_is_not_silent():
    """เจอภาพแล้วแต่ ADB กดไม่ได้ = ขั้นนี้ล้มจริง ต้องไม่เดินหน้าเงียบ ๆ"""
    _, status, _ = run(BASE, tap_ok=False)
    assert status != "completed"


def test_stop_button_ends_the_wait_immediately():
    flag = {"on": True}

    def running():
        return flag["on"]
    r, _ = make(BASE, find_after=9999, running=running)
    orig = r.controller.capture_screenshot_bytes

    def shot_then_stop(d):
        flag["on"] = False
        return orig(d)
    r.controller.capture_screenshot_bytes = shot_then_stop
    r._run_steps(":7555", None, r.steps, lambda **k: None)
    assert r.controller.checks == 1 and r.controller.taps == []


# ---------- ตั้งค่าไม่ครบ ----------

def test_skips_when_no_target_image_is_set():
    ctl, status, _ = run({"type": "tap_image", "timeout": 1})
    assert ctl.taps == [] and ctl.checks == 0 and status == "completed"


def test_bad_numbers_fall_back_to_defaults():
    ctl, _, _ = run(dict(BASE, timeout="abc", threshold="x"))
    assert ctl.taps == [(70, 80)] and ctl.thresholds == [0.8]


# ---------- ลงทะเบียนในตัวแก้ไขครบ ----------

def test_registered_everywhere_the_editor_needs_it():
    api = web_app.Api.__new__(web_app.Api)
    t = "tap_image"
    assert t in {o["value"] for o in web_app.Api._step_type_options(api)}
    assert web_app.Api._STEP_TH[t] == "กดที่รูป"
    assert web_app.Api._STEP_ICON[t] == "target"
    for f in ("text", "timeout", "threshold", "on_fail", "delay"):
        assert f in web_app.Api.STEP_FIELDS[t]
    d = web_app.Api.STEP_DEFAULTS[t]
    assert d["on_fail"] == "skip" and d["threshold"] == 0.8 and d["timeout"] == 10


def test_canonical_step_keeps_on_fail_and_drops_stale_fields():
    api = web_app.Api.__new__(web_app.Api)
    st = web_app.Api._canonical_step(api, "tap_image",
                                     {"text": "a.png", "on_fail": "fail", "x": "5", "interval": 1})
    assert st["on_fail"] == "fail" and st["text"] == "a.png"
    assert "x" not in st and "interval" not in st


def test_dispatch_has_a_real_branch_for_it():
    assert '"tap_image"' in inspect.getsource(M.MacroRunner._dispatch)
    assert "tap_image" not in M.MacroRunner._UNSUPPORTED


def test_form_wires_the_on_fail_field():
    js = io.open(os.path.join(ROOT, "webui", "app.js"), encoding="utf-8").read()
    html = io.open(os.path.join(ROOT, "webui", "index.html"), encoding="utf-8").read()
    flow = io.open(os.path.join(ROOT, "webui", "flow.js"), encoding="utf-8").read()
    assert 'id="sfOnFail"' in html and 'id="fldOnFail"' in html
    assert "p.on_fail=g('sfOnFail')" in js
    assert "tap_image:['Text','Timeout','Threshold','OnFail','Delay']" in js
    assert "tap_image:'target'" in flow
