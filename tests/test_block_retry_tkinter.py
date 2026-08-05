"""เทส 'บล็อกกันพัง' ผ่านหน้า Tkinter: run_set + block_on_fail='home_retry'
→ ถ้า set พัง กลับหน้าแรกแล้วเริ่ม set ใหม่ จำกัดรอบ

ตรรกะจริงอยู่ใน macro_runner (เทสตรงที่ test_block_retry.py) ไฟล์นี้เทส 'สายไฟ' ว่า
MuMuGUI.execute_device_macro ต่อเข้าตัวรันร่วมถูกต้อง — ผลที่ได้ต้องเหมือนกันเป๊ะทั้งสองทาง

Tk root มาจาก session fixture ตัวเดียว (tests/conftest.py) ห้ามสร้างใหม่ที่นี่:
สร้าง tk.Tk() แล้ว destroy หลายรอบบน Windows ทำให้ Tcl หมดทรัพยากรแล้วเทสล้มแบบสุ่ม"""
import base64
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

B64 = base64.b64encode(b"TMPL").decode()

WORK_SET = [{"type": "tap", "x": "10", "y": "20", "anchor_img": B64,
             "anchor_timeout": 0.001, "desc": "กดปุ่มในเกม"}]
HOME_SET = [{"type": "keyevent", "code": 4, "desc": "back1"},
            {"type": "keyevent", "code": 4, "desc": "back2"},
            {"type": "tap", "x": "441", "y": "361", "desc": "แตะกลาง"}]


class FakeController:
    """anchor เจอก็ต่อเมื่อ match ถูกเรียกเกิน fail_times ครั้ง — บันทึก tap/keyevent เพื่อตรวจ 'กลับหน้าแรก'"""

    def __init__(self, fail_times):
        self.fail_times = fail_times
        self.match_calls = 0
        self.calls = []

    def capture_screenshot_bytes(self, d):
        return True, b"SCREEN"

    def match_template_bytes(self, screen_bytes, tmpl_bytes, threshold=0.8):
        self.match_calls += 1
        return (self.match_calls > self.fail_times, 5, 6, "m")

    def find_image_in_bytes(self, screen_bytes, template_path, threshold=0.8):
        return (False, 0, 0, "m")

    def tap(self, d, x, y):
        self.calls.append(("tap", int(float(x)), int(float(y))))
        return True, ""

    def keyevent(self, d, code):
        self.calls.append(("key", int(code)))
        return True, ""


@pytest.fixture
def app(gui_app):
    """ยืม Tk root ตัวเดียวของทั้ง session (ดู tests/conftest.py) แล้วตั้งค่าที่ไฟล์นี้ต้องใช้"""
    gui_app.macro_running = True
    gui_app.script_sets = {"work": WORK_SET, "home": HOME_SET}
    gui_app._anchor_poll_interval = 0.01
    return gui_app


def _run(app, fail_times, retries=2):
    """ตั้ง controller ใหม่ + รันบล็อก คืน (result, controller.calls)"""
    app.controller = FakeController(fail_times)
    app.macro_running = True
    app.macro_steps = [{"type": "run_set", "set": "work", "block_on_fail": "home_retry",
                        "block_home": "home", "block_retries": retries, "desc": "ทำงานหลัก"}]
    result = app.execute_device_macro(":7555", {"email": "a@b.c"}, highlight=False)
    return result, app.controller.calls


def test_block_succeeds_first_try_home_not_run(app):
    result, calls = _run(app, fail_times=0)
    assert result["status"] == "completed"
    assert ("tap", 10, 20) in calls
    assert ("key", 4) not in calls


def test_block_fails_then_goes_home_and_succeeds(app):
    result, calls = _run(app, fail_times=1)
    assert result["status"] == "completed"
    assert calls.count(("key", 4)) == 2       # กลับหน้าแรก 1 รอบ (back x2)
    assert calls.count(("tap", 441, 361)) == 1
    assert calls.count(("tap", 10, 20)) == 1  # set สำเร็จรอบสอง


def test_block_exhausts_retries_then_device_error(app):
    result, calls = _run(app, fail_times=999, retries=2)
    assert result["status"] == "device_error"
    # retries=2 → total_rounds=3 → กลับหน้าแรก 2 รอบ = back x4
    assert calls.count(("key", 4)) == 4
    assert calls.count(("tap", 441, 361)) == 2
    assert ("tap", 10, 20) not in calls
