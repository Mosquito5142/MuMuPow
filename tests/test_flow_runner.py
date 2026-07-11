"""เทสเฟส 1 ของ Flow Editor: MacroRunner รองรับ if_image (กิ่ง then/else ซ้อนได้)
และสคริปต์ flat เดิมต้องทำงานเหมือนเดิมเป๊ะ"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import macro_runner as M

B64 = base64.b64encode(b"TMPL").decode()


class Ctl:
    """คอนโทรลเลอร์จำลอง — บันทึกทุกคำสั่งที่โดนเรียก"""

    def __init__(self, found=True):
        self.found = found
        self.calls = []

    def capture_screenshot_bytes(self, d):
        return True, b"SCREEN"

    def match_template_bytes(self, data, tmpl, thr):
        return (self.found, 5, 6, "m")

    def find_image_in_bytes(self, data, path, threshold=0.8):
        return (self.found, 7, 8, "m")

    def tap(self, d, x, y):
        self.calls.append(("tap", int(float(x)), int(float(y))))

    def keyevent(self, d, c):
        self.calls.append(("key", c))


def _run(steps, found=True, running_check=None):
    c = Ctl(found)
    r = M.MacroRunner(c, steps, log_cb=lambda t, k="info": None,
                      running_check=running_check or (lambda: True))
    status = r.execute_one(":7555", {"email": "a@b.c"})
    return c, status


def _tap(x, y):
    return {"type": "tap", "x": str(x), "y": str(y)}


def _if(then=None, els=None, **kw):
    step = {"type": "if_image", "anchor_img": B64, "timeout": 0}
    if then is not None:
        step["then"] = then
    if els is not None:
        step["else"] = els
    step.update(kw)
    return step


def test_flat_script_unchanged():
    c, status = _run([_tap(1, 1), {"type": "keyevent", "code": 4}])
    assert status == "completed"
    assert c.calls == [("tap", 1, 1), ("key", 4)]


def test_if_then_runs_and_rejoins_main():
    c, status = _run([_tap(1, 1), _if(then=[_tap(2, 2)]), _tap(3, 3)], found=True)
    assert status == "completed"
    assert c.calls == [("tap", 1, 1), ("tap", 2, 2), ("tap", 3, 3)]


def test_if_not_found_runs_else_then_rejoins():
    c, status = _run([_if(then=[_tap(2, 2)], els=[_tap(9, 9)]), _tap(3, 3)], found=False)
    assert status == "completed"
    assert c.calls == [("tap", 9, 9), ("tap", 3, 3)]


def test_if_not_found_no_else_just_continues():
    c, status = _run([_if(then=[_tap(2, 2)]), _tap(3, 3)], found=False)
    assert status == "completed"
    assert c.calls == [("tap", 3, 3)]


def test_nested_two_levels():
    inner = _if(then=[_tap(5, 5)])
    c, status = _run([_if(then=[inner, _tap(6, 6)]), _tap(7, 7)], found=True)
    assert status == "completed"
    assert c.calls == [("tap", 5, 5), ("tap", 6, 6), ("tap", 7, 7)]


def test_depth_limit_skips_too_deep():
    # ซ้อน 7 ชั้น — ชั้นที่เกิน MAX_BRANCH_DEPTH ต้องถูกข้าม (tap ในสุดไม่โดนกด)
    step = _tap(99, 99)
    for _ in range(7):
        step = _if(then=[step])
    c, status = _run([step], found=True)
    assert status == "completed"
    assert ("tap", 99, 99) not in c.calls


def test_stop_mid_branch():
    c = Ctl(found=True)
    flag = {"run": True}

    class StopCtl(Ctl):
        def tap(self, d, x, y):
            super().tap(d, x, y)
            flag["run"] = False  # สั่งหยุดหลังกดครั้งแรก

    c = StopCtl(found=True)
    r = M.MacroRunner(c, [_if(then=[_tap(1, 1), _tap(2, 2)]), _tap(3, 3)],
                      log_cb=lambda t, k="info": None,
                      running_check=lambda: flag["run"])
    status = r.execute_one(":7555", None)
    assert status == "stopped"
    assert c.calls == [("tap", 1, 1)]  # หยุดก่อนกดตัวที่ 2 และไม่วกกลับเส้นหลัก


def test_run_set_expands_inside_branch(tmp_path, monkeypatch):
    # ชี้ base_dir ไปโฟลเดอร์ชั่วคราว แล้ววางชุดคำสั่งไว้ใน script_sets/
    ssdir = tmp_path / "script_sets"
    ssdir.mkdir()
    (ssdir / "myset.json").write_text(
        json.dumps({"name": "MYSET", "steps": [_tap(4, 4)]}), encoding="utf-8")
    monkeypatch.setattr(M, "base_dir", lambda: str(tmp_path))

    steps = [_if(then=[{"type": "run_set", "set": "MYSET"}]), _tap(3, 3)]
    c, status = _run(steps, found=True)
    assert status == "completed"
    assert c.calls == [("tap", 4, 4), ("tap", 3, 3)]


def test_progress_reports_branch_path():
    paths = []
    c = Ctl(found=True)
    r = M.MacroRunner(c, [_tap(1, 1), _if(then=[_tap(2, 2)])],
                      log_cb=lambda t, k="info": None,
                      progress_cb=lambda dev, **kw: paths.append(kw.get("step_path")))
    r.execute_one(":7555", None)
    assert "1.then.0" in paths  # กิ่งรายงาน path ถูก (ให้เฟส 5 ใช้ไฮไลต์)
