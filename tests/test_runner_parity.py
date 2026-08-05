"""เทส 'ความเท่ากันของตัวรัน' — MacroRunner ต้องทำได้ทุกอย่างที่เอนจินใน gui.py (Tkinter) เคยทำ

เหตุผลที่ต้องมีไฟล์นี้: Tkinter ถูกเปลี่ยนไปเรียก MacroRunner แทนเอนจินสำเนาของตัวเอง
ถ้า MacroRunner ขาดชนิด step ไหนไป ผู้ใช้ที่รันด้วย MuMupow.exe จะเสียฟีเจอร์นั้นเงียบ ๆ
(step โดน log ว่า 'ไม่รู้จักชนิด → ข้าม' แล้วเดินหน้าต่อเหมือนไม่มีอะไรเกิดขึ้น)
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import macro_runner as M


class Ctl:
    """คอนโทรลเลอร์จำลอง — บันทึกทุกคำสั่งที่โดนเรียก"""

    def __init__(self):
        self.calls = []
        self.shot_ok = True

    def capture_screenshot_bytes(self, d):
        return True, b"SCREEN"

    def take_screenshot(self, device, path):
        self.calls.append(("take_screenshot", device, path))
        return (self.shot_ok, "" if self.shot_ok else "device offline")

    def tap(self, d, x, y):
        self.calls.append(("tap", int(float(x)), int(float(y))))
        return (True, "")


def _runner(steps, **kw):
    return M.MacroRunner(Ctl(), steps, log_cb=lambda t, k="info": None,
                         running_check=lambda: True, **kw)


# ---------- 1) ค่าหน่วงเริ่มต้นตามชนิด step ----------

def test_delay_falls_back_to_type_default_when_field_absent():
    """สคริปต์เก่าที่เขียนมือไม่ใส่ delay ต้องยังได้จังหวะพักตามชนิด ไม่ใช่ 0
    (ก่อนแก้ macro_runner คืน 0 ทำให้กดรัวกว่า Tkinter จนเกมตามไม่ทัน)"""
    d = M.MacroRunner._delay({"type": "tap"})
    assert 1.0 * 0.8 <= d <= 1.0 * 1.4

    d = M.MacroRunner._delay({"type": "keyevent"})
    assert 0.3 * 0.8 <= d <= 0.3 * 1.4


def test_delay_respects_explicit_zero():
    """delay: 0 ที่ตั้งมาชัดเจน = ตั้งใจไม่หน่วง ห้ามเอาค่าเริ่มต้นมาทับ"""
    assert M.MacroRunner._delay({"type": "tap", "delay": 0}) == 0


def test_delay_zero_for_types_without_default():
    assert M.MacroRunner._delay({"type": "if_image"}) == 0


def test_delay_survives_junk_value():
    assert M.MacroRunner._delay({"type": "tap", "delay": "abc"}) == 0


def test_gui_reuses_the_same_table():
    """gui.py ต้อง re-export ตารางเดียวกัน ห้ามมีสำเนาแยกที่เลื่อนออกจากกันได้"""
    import gui
    assert gui.DEFAULT_STEP_DELAYS is M.DEFAULT_STEP_DELAYS


# ---------- 2) step 'screenshot' ----------

NOW = datetime.datetime(2026, 8, 4, 13, 5, 9)
ACC = {"email": "a@b.com", "password": "p1", "name": "ตี๋เล็ก", "group": "ชุดที่ 1"}


def test_screenshot_filename_substitutes_every_placeholder():
    out = M.screenshot_filename("shots/{DATE}/{NAME}_{GROUP}_{DEVICE}_{TIME}.png",
                                "127.0.0.1:7555", ACC, NOW)
    assert out == "shots/2026-08-04/ตี๋เล็ก_ชุดที่ 1_127_0_0_1_7555_13-05-09.png"


def test_screenshot_filename_without_account():
    out = M.screenshot_filename("{NAME}_{EMAIL}_{GROUP}.png", ":7555", None, NOW)
    assert out == "no_name_no_account_no_group.png"


def test_screenshot_filename_strips_windows_illegal_chars_and_adds_extension():
    out = M.screenshot_filename('a<>:"|?*b', ":7555", None, NOW)
    assert out == "ab.png"


def test_screenshot_filename_empty_pattern_uses_default():
    out = M.screenshot_filename("", ":7555", None, NOW)
    assert out.startswith("screenshots/") and out.endswith(".png")


def test_screenshot_step_reaches_the_controller(tmp_path, monkeypatch):
    """ก่อนแก้ ชนิดนี้ตกไปที่ 'ไม่รู้จักชนิด → ข้าม' ทั้งที่ตัวแก้ไขเสนอให้เลือกได้"""
    monkeypatch.chdir(tmp_path)
    r = _runner([{"type": "screenshot", "text": "out/{DEVICE}.png", "delay": 0}])
    r.execute_one("127.0.0.1:7555", None)

    shots = [c for c in r.controller.calls if c[0] == "take_screenshot"]
    assert len(shots) == 1
    assert shots[0][2] == "out/127_0_0_1_7555.png"
    assert (tmp_path / "out").is_dir()   # ต้องสร้างโฟลเดอร์ปลายทางให้เอง


def test_screenshot_failure_does_not_abort_the_run():
    """แคปไม่สำเร็จ = แจ้งเตือนแล้วไปต่อ (เหมือน Tkinter) ไม่ใช่ทั้งบัญชีพัง"""
    r = _runner([{"type": "screenshot", "text": "x.png", "delay": 0},
                 {"type": "tap", "x": "5", "y": "6", "delay": 0}])
    r.controller.shot_ok = False
    assert r.execute_one(":7555", None) == "completed"
    assert ("tap", 5, 6) in r.controller.calls


# ---------- 3) step 'story_auto' ----------

def test_story_auto_is_no_longer_marked_unsupported():
    assert "story_auto" not in M.MacroRunner._UNSUPPORTED


def test_story_auto_drives_story_runner_with_step_settings(monkeypatch):
    seen = {}

    class FakeStory:
        def __init__(self, controller, **kw):
            seen.update(kw)

        def run_story(self, device):
            seen["device"] = device

    monkeypatch.setattr(M, "StoryRunner", FakeStory)
    r = _runner([{"type": "story_auto", "text": "story_skip.png", "threshold": 0.9,
                  "max_stages": 4, "delay": 0}], gemini_key="KEY")
    r.execute_one("127.0.0.1:7556", None)

    assert seen["device"] == "127.0.0.1:7556"
    assert seen["buttons_field"] == "story_skip.png"
    assert seen["threshold"] == 0.9
    assert seen["max_stages"] == 4
    assert seen["gemini_key"] == "KEY"


def test_story_auto_uses_tkinter_defaults(monkeypatch):
    """ค่าเริ่มต้นต้องตรงกับ gui._step_story_auto เดิม (30 ด่าน, threshold 0.78)"""
    seen = {}

    class FakeStory:
        def __init__(self, controller, **kw):
            seen.update(kw)

        def run_story(self, device):
            pass

    monkeypatch.setattr(M, "StoryRunner", FakeStory)
    r = _runner([{"type": "story_auto", "delay": 0}])
    r.execute_one(":7555", None)

    assert seen["max_stages"] == 30
    assert seen["threshold"] == 0.78


def test_story_auto_stops_with_the_run(monkeypatch):
    """กดหยุด = StoryRunner ต้องได้ running_check ตัวเดียวกับมาโคร ไม่งั้นลูปเนื้อเรื่องไม่ยอมจบ"""
    seen = {}

    class FakeStory:
        def __init__(self, controller, **kw):
            seen.update(kw)

        def run_story(self, device):
            pass

    monkeypatch.setattr(M, "StoryRunner", FakeStory)
    flag = {"on": True}
    r = M.MacroRunner(Ctl(), [{"type": "story_auto", "delay": 0}],
                      log_cb=lambda t, k="info": None, running_check=lambda: flag["on"])
    r.execute_one(":7555", None)

    assert seen["running_check"]() is True
    flag["on"] = False
    assert seen["running_check"]() is False


# ---------- 4) ตัวแก้ไขฝั่งเว็บต้องรู้จักชนิดที่ตัวรันทำได้ ----------

def test_tkinter_has_no_second_macro_engine():
    """กันสำเนาเอนจินกลับมาอีก — Tkinter ต้องรันผ่าน MacroRunner เท่านั้น

    เดิม gui.py มีเอนจินของตัวเอง (_run_macro_steps + _step_* ~800 บรรทัด) ที่ 'พยายาม'
    เหมือน macro_runner แล้วเลื่อนออกจากกันเงียบ ๆ ทุกครั้งที่แก้ข้างเดียว
    ถ้าเทสนี้แดง แปลว่ามีคนเริ่มสร้างสำเนาที่สองขึ้นมาใหม่"""
    import gui
    leftovers = [n for n in dir(gui.MuMuGUI) if n.startswith("_step_")]
    assert leftovers == [], f"gui.py กลับมามี handler ของตัวเองอีก: {leftovers}"
    for gone in ("_run_macro_steps", "_run_block_gui", "_eval_if_image_gui",
                 "_get_step_handlers", "_expand_steps_with_sets_recursive"):
        assert not hasattr(gui.MuMuGUI, gone), f"gui.py กลับมามีเอนจินของตัวเอง: {gone}"


def test_tkinter_builds_the_shared_runner():
    """และต้องยังต่อสายเข้า MacroRunner จริง ๆ ไม่ใช่แค่ลบของเก่าทิ้ง"""
    import gui
    assert hasattr(gui.MuMuGUI, "_build_macro_runner")
    assert gui.MacroRunner is M.MacroRunner


def test_web_editor_offers_every_type_the_runner_supports():
    """ถ้าตัวรันทำได้แต่ dropdown ไม่มี ผู้ใช้สร้าง step นั้นจากเว็บไม่ได้เลย
    และ _canonical_step จะล้างฟิลด์ของมันทิ้งตอนแก้ step อื่น"""
    import web_app
    api = web_app.Api.__new__(web_app.Api)
    offered = {o["value"] for o in web_app.Api._step_type_options(api)}
    for t in ("screenshot", "story_auto", "find_yellow_stage", "read_diamond"):
        assert t in offered, f"dropdown ขาดชนิด '{t}'"
        assert t in web_app.Api.STEP_FIELDS, f"STEP_FIELDS ขาดชนิด '{t}'"
