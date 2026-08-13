"""เทส: 'รอรูป' / 'เจอรูปกด' ตั้งภาพด้วยการลากกรอบจากจอจริงได้ (ไม่ต้องพิมพ์ชื่อไฟล์เอง)

เดิมสองชนิดนี้รับได้แต่ชื่อไฟล์ใน templates/ ผู้ใช้ต้องไปครอปรูปเก็บเป็นไฟล์เองก่อน
ทั้งที่ if_image ลากกรอบจากจอได้อยู่แล้ว

จุดที่ต้องระวังที่สุด: ห้ามใช้ฟิลด์ anchor_img ร่วมกัน เพราะ step พวกนี้ยังมี 'ด่าน anchor'
ของตัวเองได้ (anchor_img = รอเห็นภาพนี้ก่อนค่อยเริ่มทำ step) ถ้าเขียนทับกันจะเปลี่ยน
พฤติกรรมสคริปต์โดยผู้ใช้ไม่ได้สั่ง จึงแยกเป็น wait_img
"""
import base64
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import macro_runner as M
import web_app

B64 = base64.b64encode(b"TEMPLATE-BYTES").decode()


class Ctl:
    def __init__(self, found=True):
        self.found = found
        self.calls = []

    def capture_screenshot_bytes(self, d):
        return True, b"SCREEN"

    def match_template_bytes(self, data, tmpl, thr=0.8):
        self.calls.append(("match_bytes", tmpl, thr))
        return (self.found, 40, 50, "m")

    def find_image_in_bytes(self, data, path, threshold=0.8):
        self.calls.append(("match_file", path, threshold))
        return (self.found, 11, 22, "m")

    def tap(self, d, x, y):
        self.calls.append(("tap", int(float(x)), int(float(y))))
        return True, ""


def run(step, found=True):
    step = dict(step)
    step.setdefault("delay", 0)
    r = M.MacroRunner(Ctl(found), [step], log_cb=lambda t, k="info": None,
                      running_check=lambda: True)
    status = r._run_steps(":7555", None, r.steps, lambda **kw: None)
    return r.controller, status


def api(steps):
    a = web_app.Api.__new__(web_app.Api)
    a.macro_steps = steps
    a.current_profile = "t"
    a._push_log = lambda *a_, **k_: None
    return a


# ---------- เลือกแหล่งภาพ ----------

def test_dragged_image_is_used_when_present():
    ctl, status = run({"type": "wait_for_image", "wait_img": B64, "timeout": 2})
    assert ("match_bytes", b"TEMPLATE-BYTES", 0.8) in ctl.calls
    assert status == "completed"


def test_taps_the_centre_of_what_it_found():
    ctl, _ = run({"type": "wait_for_image", "wait_img": B64, "timeout": 2})
    assert ("tap", 40, 50) in ctl.calls


def test_click_false_waits_without_tapping():
    ctl, _ = run({"type": "wait_for_image", "wait_img": B64, "timeout": 2, "click": False})
    assert not any(c[0] == "tap" for c in ctl.calls)


def test_threshold_is_passed_through():
    ctl, _ = run({"type": "wait_for_image", "wait_img": B64, "timeout": 2, "threshold": 0.93})
    assert ("match_bytes", b"TEMPLATE-BYTES", 0.93) in ctl.calls


def test_old_scripts_using_a_template_file_still_work(tmp_path, monkeypatch):
    """สคริปต์เดิมที่อ้างชื่อไฟล์ต้องทำงานเหมือนเดิมเป๊ะ"""
    (tmp_path / "btn.png").write_bytes(b"png")
    monkeypatch.setattr(M, "templates_dir", lambda: str(tmp_path))
    ctl, _ = run({"type": "wait_for_image", "text": "btn.png", "timeout": 2})
    assert any(c[0] == "match_file" for c in ctl.calls)
    assert ("tap", 11, 22) in ctl.calls


def test_dragged_image_wins_over_filename(tmp_path, monkeypatch):
    (tmp_path / "btn.png").write_bytes(b"png")
    monkeypatch.setattr(M, "templates_dir", lambda: str(tmp_path))
    ctl, _ = run({"type": "wait_for_image", "text": "btn.png", "wait_img": B64, "timeout": 2})
    assert any(c[0] == "match_bytes" for c in ctl.calls)
    assert not any(c[0] == "match_file" for c in ctl.calls)


def test_step_without_any_image_is_skipped_not_fatal():
    ctl, status = run({"type": "wait_for_image", "timeout": 2})
    assert status == "completed"          # ข้ามไป ไม่ล้มทั้งบัญชี
    assert ctl.calls == []


def test_missing_template_file_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "templates_dir", lambda: str(tmp_path))
    ctl, status = run({"type": "wait_for_image", "text": "ไม่มีไฟล์นี้.png", "timeout": 2})
    assert status == "completed"
    assert ctl.calls == []


def test_detect_image_also_accepts_a_dragged_image():
    ctl, _ = run({"type": "detect_image", "wait_img": B64})
    assert any(c[0] == "match_bytes" for c in ctl.calls)
    assert ("tap", 40, 50) in ctl.calls


def test_detect_image_does_not_tap_when_not_found():
    ctl, _ = run({"type": "detect_image", "wait_img": B64}, found=False)
    assert not any(c[0] == "tap" for c in ctl.calls)


# ---------- ห้ามชนกับด่าน anchor ----------

def test_wait_image_and_anchor_gate_stay_independent():
    """ขั้นเดียวกันมีได้ทั้ง 2 อย่าง: anchor_img = รอเห็นก่อนเริ่ม, wait_img = ภาพที่จะรอ/กด
    ถ้าโค้ดสับสนสองฟิลด์นี้ สคริปต์จะเปลี่ยนพฤติกรรมเงียบ ๆ"""
    anchor = base64.b64encode(b"GATE").decode()
    ctl, status = run({"type": "wait_for_image", "wait_img": B64, "timeout": 2,
                       "anchor_img": anchor, "anchor_timeout": 1})

    used = [c[1] for c in ctl.calls if c[0] == "match_bytes"]
    assert b"GATE" in used            # ด่าน anchor ถูกเช็ค
    assert b"TEMPLATE-BYTES" in used  # และภาพที่ต้องรอก็ถูกเช็ค
    assert status == "completed"


# ---------- ฝั่งตัวแก้ไข ----------

def test_set_image_wait_mode_writes_its_own_field():
    a = api([{"type": "wait_for_image", "desc": "รอปุ่ม"}])
    a.flow_set_image([0], B64, {"x": 1, "y": 2, "w": 30, "h": 40}, mode="wait")

    s = a.macro_steps[0]
    assert s["wait_img"] == B64
    assert s["wait_region"] == {"x": 1, "y": 2, "w": 30, "h": 40}
    assert "anchor_img" not in s          # ต้องไม่ไปแตะด่าน anchor


def test_set_image_cond_mode_still_writes_anchor_img():
    a = api([{"type": "if_image", "then": [], "else": []}])
    a.flow_set_image([0], B64, None, mode="cond")
    assert a.macro_steps[0]["anchor_img"] == B64
    assert "wait_img" not in a.macro_steps[0]


def test_wait_image_survives_changing_step_type():
    a = api([{"type": "wait_for_image"}])
    out = a._canonical_step("detect_image", {"text": ""},
                            {"type": "wait_for_image", "wait_img": B64,
                             "wait_region": {"x": 0, "y": 0, "w": 5, "h": 5}})
    assert out["wait_img"] == B64
    assert out["wait_region"] == {"x": 0, "y": 0, "w": 5, "h": 5}
