"""เข้าเกมให้อัตโนมัติก่อนเริ่มแต่ละไอดี ถ้าจอยังไม่อยู่ในเกม

ที่มา: เปิดโปรแกรมมาแล้วกดรันเลย จอยังอยู่หน้า launcher/หน้าอื่น ไม่ต้องกดเข้าเกมทีละจอเอง
ใช้ package + boot_wait + open_login_steps จาก game_reset.json (ชุดเดียวกับตอนรีเซ็ต)

กติกาที่ล็อกไว้:
1. อยู่ในเกมแล้ว → ไม่เปิดซ้ำ
2. ไม่ได้อยู่ในเกม (รู้แน่) → เปิดให้ โดย 'ไม่' force-stop (ต่างจากรีเซ็ตที่ปิดก่อน)
3. อ่าน foreground ไม่ได้ ("") → ไม่เสี่ยงเปิดทับ (ข้าม) กันเด้งเกมที่รันอยู่กลางคิว
4. auto_enter ปิด / ไม่มี package → ไม่ทำอะไร
5. 'รันต่อ' (start_index>0) → ไม่เช็ค/ไม่เข้าเกมทับ
6. _reset_device เดิมยัง force-stop เปิดใหม่เหมือนเดิม (refactor ไม่พัง)
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import macro_runner as M
import web_app
from mumu_controller import MuMuController

PKG = "com.lmdgame.kuroko.sea"


class FakeController:
    def __init__(self, fg=""):
        self._fg = fg
        self.launched = []      # (device, force_stop_flag ที่อนุมานจาก stop ก่อนหน้า)
        self.stopped = []
        self.taps = []

    def foreground_package(self, device):
        return self._fg

    def stop_app(self, device, pkg):
        self.stopped.append((device, pkg))
        return True, ""

    def launch_app_by_package(self, device, pkg):
        self.launched.append((device, pkg))
        return True, ""

    def tap(self, device, x, y):
        self.taps.append((device, x, y))
        return True, ""


RESET_CFG = {
    "enabled": True, "package": PKG, "boot_wait": 0, "auto_enter": True,
    "open_login_steps": [{"type": "tap", "x": "920", "y": "92", "delay": 0}],
}


def _runner(ctl, reset_cfg=None):
    r = M.MacroRunner(ctl, [{"type": "tap", "x": "1", "y": "2", "delay": 0}],
                      log_cb=lambda t, k="info": None, running_check=lambda: True,
                      reset_cfg=reset_cfg if reset_cfg is not None else dict(RESET_CFG))
    return r


# ---------- foreground_package parsing ----------

def test_foreground_package_parses_mcurrentfocus():
    class C:
        def run_adb_cmd(self, args, timeout=None):
            return True, "  mCurrentFocus=Window{a1b2 u0 " + PKG + "/com.game.MainActivity}"
    pkg = MuMuController.foreground_package(C(), "d")
    assert pkg == PKG


def test_foreground_package_empty_when_unreadable():
    class C:
        def run_adb_cmd(self, args, timeout=None):
            return False, ""
    assert MuMuController.foreground_package(C(), "d") == ""


# ---------- _ensure_in_game ----------

def test_already_in_game_does_not_relaunch():
    ctl = FakeController(fg=PKG + "/com.game.Main")
    _runner(ctl)._ensure_in_game(":7555")
    assert ctl.launched == [], "อยู่ในเกมแล้วไม่ควรเปิดซ้ำ"


def test_not_in_game_launches_without_forcestop():
    ctl = FakeController(fg="com.android.launcher/.Launcher")
    _runner(ctl)._ensure_in_game(":7555")
    assert ctl.launched == [(":7555", PKG)], "ไม่อยู่ในเกมต้องเปิดเกมให้"
    assert ctl.stopped == [], "เข้าเกมให้ (ก่อนเริ่ม) ต้องไม่ force-stop"
    assert ctl.taps == [(":7555", 920, 92)], "ต้องเล่นสเต็ปเข้าหน้า login ด้วย"


def test_unknown_foreground_skips_to_avoid_disrupting():
    ctl = FakeController(fg="")
    _runner(ctl)._ensure_in_game(":7555")
    assert ctl.launched == [], "อ่าน foreground ไม่ได้ ต้องไม่เสี่ยงเปิดทับ"


def test_auto_enter_off_skips():
    ctl = FakeController(fg="com.android.launcher/.L")
    cfg = dict(RESET_CFG, auto_enter=False)
    _runner(ctl, cfg)._ensure_in_game(":7555")
    assert ctl.launched == []


def test_no_package_skips():
    ctl = FakeController(fg="com.android.launcher/.L")
    _runner(ctl, {"auto_enter": True})._ensure_in_game(":7555")
    assert ctl.launched == []


def test_auto_enter_defaults_on_when_key_missing():
    """ไฟล์ game_reset.json เก่าที่ไม่มีคีย์ auto_enter = ถือว่าเปิด"""
    ctl = FakeController(fg="com.android.launcher/.L")
    cfg = {"enabled": True, "package": PKG, "boot_wait": 0, "open_login_steps": []}
    _runner(ctl, cfg)._ensure_in_game(":7555")
    assert ctl.launched == [(":7555", PKG)]


# ---------- _reset_device ยัง force-stop (refactor ไม่พัง) ----------

def test_reset_device_still_force_stops():
    ctl = FakeController(fg=PKG)
    _runner(ctl)._reset_device(":7555")
    assert ctl.stopped == [(":7555", PKG)], "รีเซ็ตต้องปิดเกมก่อนเปิดใหม่"
    assert ctl.launched == [(":7555", PKG)]


def test_reset_device_skips_when_disabled():
    ctl = FakeController(fg=PKG)
    cfg = dict(RESET_CFG, enabled=False)
    _runner(ctl, cfg)._reset_device(":7555")
    assert ctl.launched == [] and ctl.stopped == []


# ---------- execute_one เรียกเฉพาะตอนเริ่มใหม่ (ไม่ใช่รันต่อ) ----------

def test_execute_one_ensures_on_fresh_start():
    ctl = FakeController(fg=PKG)
    r = _runner(ctl)
    calls = []
    r._ensure_in_game = lambda dev: calls.append(dev)
    r._run_steps = lambda *a, **k: "completed"
    r.execute_one(":7555", {"email": "a@x.com"}, start_index=0)
    assert calls == [":7555"], "เริ่มบัญชีใหม่ต้องเช็คเข้าเกม"


def test_execute_one_skips_ensure_on_resume():
    ctl = FakeController(fg=PKG)
    r = _runner(ctl)
    calls = []
    r._ensure_in_game = lambda dev: calls.append(dev)
    r._run_steps = lambda *a, **k: "completed"
    r.execute_one(":7555", {"email": "a@x.com"}, start_index=3)
    assert calls == [], "รันต่อ (start_index>0) ต้องไม่รีเข้าเกมทับจอที่ค้างกลางสคริปต์"


# ---------- web_app get/save auto_enter ----------

def test_reset_settings_round_trip_auto_enter(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "base_dir", lambda: str(tmp_path))
    api = web_app.Api()
    api.save_reset_settings(True, PKG, 10, auto_enter=False)
    assert api.get_reset_settings()["auto_enter"] is False
    api.save_reset_settings(True, PKG, 10, auto_enter=True)
    assert api.get_reset_settings()["auto_enter"] is True
    # ไฟล์ที่ไม่มีคีย์ auto_enter → ดีฟอลต์ True
    with open(os.path.join(str(tmp_path), "game_reset.json"), "w", encoding="utf-8") as f:
        json.dump({"enabled": True, "package": PKG, "boot_wait": 10}, f)
    assert api.get_reset_settings()["auto_enter"] is True
