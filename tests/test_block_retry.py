"""เทส 'บล็อกกันพัง' (run_set + block_on_fail='home_retry'):
แบ่งงานเป็น set ถ้า set ไหนพัง (anchor ไม่เจอ) → เล่นชุด 'กลับหน้าแรก' → เริ่ม set นั้นใหม่ทั้งชุด
จำกัดจำนวนรอบ (block_retries) ครบแล้วยังพัง → device_error + บันทึกจุดที่ติด

ต่างจาก anchor_on_fail ปกติ: หน่วยการลองใหม่คือ 'ทั้ง set' (กลับสู่จุดที่รู้แน่ ๆ ก่อนเริ่มใหม่)
ไม่ใช่ย้อนทีละขั้น"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import macro_runner as M

B64 = base64.b64encode(b"TMPL").decode()


class Ctl:
    """anchor (match_template_bytes) เจอก็ต่อเมื่อถูกเรียกเกิน fail_times ครั้งแล้ว
    (จำลองว่า set พังกี่รอบแรก แล้วค่อยผ่าน) — บันทึก tap/keyevent เพื่อตรวจว่า 'กลับหน้าแรก' ถูกเล่นจริง"""

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
        return True, ""

    def keyevent(self, d, code):
        self.calls.append(("key", int(code)))
        return True, ""


def _setup_sets(tmp_path):
    """สร้าง script_sets/ ชั่วคราว: 'work' (มี anchor 1 ขั้น) + 'home' (back x2 + tap) แล้วชี้ base_dir ไปที่นี่"""
    d = tmp_path / "script_sets"
    d.mkdir()
    (d / "work.json").write_text(json.dumps({
        "name": "work",
        "steps": [{"type": "tap", "x": "10", "y": "20", "anchor_img": B64,
                   "anchor_timeout": 0.001, "desc": "กดปุ่มในเกม"}],
    }, ensure_ascii=False), encoding="utf-8")
    (d / "home.json").write_text(json.dumps({
        "name": "home",
        "steps": [{"type": "keyevent", "code": 4, "desc": "back1"},
                  {"type": "keyevent", "code": 4, "desc": "back2"},
                  {"type": "tap", "x": "441", "y": "361", "desc": "แตะกลาง"}],
    }, ensure_ascii=False), encoding="utf-8")


def _block_macro(retries=2):
    return [{"type": "run_set", "set": "work", "block_on_fail": "home_retry",
             "block_home": "home", "block_retries": retries, "desc": "ทำงานหลัก"}]


def _runner(ctl, monkeypatch, tmp_path):
    monkeypatch.setattr(M, "base_dir", lambda: str(tmp_path))
    return M.MacroRunner(ctl, _block_macro(), log_cb=lambda t, k="info": None, anchor_poll=0.01)


def test_block_succeeds_first_try_home_not_run(monkeypatch, tmp_path):
    _setup_sets(tmp_path)
    c = Ctl(fail_times=0)  # เจอ anchor ตั้งแต่ครั้งแรก → set ผ่านเลย
    r = _runner(c, monkeypatch, tmp_path)
    status = r.execute_one(":7555", {"email": "a@b.c"})
    assert status == "completed"
    assert ("tap", 10, 20) in c.calls          # ขั้นใน set ถูกกด
    assert ("key", 4) not in c.calls           # ไม่ต้องกลับหน้าแรกเลย
    assert ("tap", 441, 361) not in c.calls


def test_block_fails_then_goes_home_and_succeeds(monkeypatch, tmp_path):
    _setup_sets(tmp_path)
    c = Ctl(fail_times=1)  # รอบแรกพัง รอบสองผ่าน
    r = _runner(c, monkeypatch, tmp_path)
    status = r.execute_one(":7555", {"email": "a@b.c"})
    assert status == "completed"
    # 'กลับหน้าแรก' ถูกเล่น 1 รอบ (back x2 + tap กลาง) ก่อนเริ่ม set ใหม่
    assert c.calls.count(("key", 4)) == 2
    assert c.calls.count(("tap", 441, 361)) == 1
    # ขั้นใน set สำเร็จตอนรอบสอง
    assert c.calls.count(("tap", 10, 20)) == 1


def test_block_exhausts_retries_then_device_error_and_report(monkeypatch, tmp_path):
    _setup_sets(tmp_path)
    c = Ctl(fail_times=999)  # ไม่เคยผ่านเลย
    r = _runner(c, monkeypatch, tmp_path)
    status = r.execute_one(":7555", {"email": "a@b.c"})
    assert status == "device_error"
    # retries=2 → total_rounds=3 → กลับหน้าแรก 2 รอบ (ระหว่างรอบ) = back x2 x 2 = 4 ครั้ง
    assert c.calls.count(("key", 4)) == 4
    assert c.calls.count(("tap", 441, 361)) == 2
    # ขั้นในเกมไม่เคยกดสำเร็จ (anchor ไม่เจอตลอด)
    assert ("tap", 10, 20) not in c.calls
    # บันทึกจุดที่ติดไว้จริง
    assert (tmp_path / "error_reports" / "report.jsonl").exists()
    rec = json.loads((tmp_path / "error_reports" / "report.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert "block_failed:work" in rec["reason"]


def test_block_retries_count_is_configurable(monkeypatch, tmp_path):
    _setup_sets(tmp_path)
    c = Ctl(fail_times=999)
    monkeypatch.setattr(M, "base_dir", lambda: str(tmp_path))
    macro = [{"type": "run_set", "set": "work", "block_on_fail": "home_retry",
              "block_home": "home", "block_retries": 0, "desc": "ทำงานหลัก"}]  # ลอง 0 รอบ = ครั้งเดียวจบ
    r = M.MacroRunner(c, macro, log_cb=lambda t, k="info": None, anchor_poll=0.01)
    status = r.execute_one(":7555", {"email": "a@b.c"})
    assert status == "device_error"
    assert ("key", 4) not in c.calls  # ไม่กลับหน้าแรกเลย (ไม่มีรอบให้ลองซ้ำ)


def test_plain_run_set_without_block_marker_still_flattens(monkeypatch, tmp_path):
    """run_set ธรรมดา (ไม่มี block_on_fail) ต้องถูกคลี่แบนแล้วรันต่อเนื่องเหมือนเดิม (no regression)"""
    _setup_sets(tmp_path)
    c = Ctl(fail_times=0)
    monkeypatch.setattr(M, "base_dir", lambda: str(tmp_path))
    macro = [{"type": "run_set", "set": "home"}]  # run_set ธรรมดา ชี้ set 'home' (ไม่มี anchor)
    r = M.MacroRunner(c, macro, log_cb=lambda t, k="info": None, anchor_poll=0.01)
    status = r.execute_one(":7555", {"email": "a@b.c"})
    assert status == "completed"
    assert c.calls.count(("key", 4)) == 2
    assert ("tap", 441, 361) in c.calls
