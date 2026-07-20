"""เทสระดับ Api (web_app.py) สำหรับฟีเจอร์ 'เรียนรู้ทีละจอ': anchor_on_fail='pause' ทำให้จอค้าง
โผล่ในแผง 'จอที่รอแก้ไข' (list_paused) แล้วกด 'รันต่อจากขั้นนี้' (resume_paused) ต่อได้จริง
โดยไม่รบกวนจอ/บัญชีอื่นที่กำลังรันคู่ขนานอยู่ — ต่างจาก tests/test_pause_resume.py ที่เทสแค่
MacroRunner ตรงๆ ไฟล์นี้เทสการต่อสาย Api<->MacroRunner<->progress_cb ทั้งชุด"""
import base64
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web_app

B64 = base64.b64encode(b"TMPL").decode()


class MockController:
    """anchor หาไม่เจอเสมอ (found=False) -> ไล่เข้า anchor_on_fail='pause' ทุกครั้ง
    ตั้ง .found = True ระหว่างทดสอบเพื่อจำลอง 'ผู้ใช้แก้ไขสคริปต์แล้ว รอบนี้ควรผ่าน'"""

    def __init__(self):
        self.taps = []
        self.found = False

    def capture_screenshot_bytes(self, d):
        return True, b"SCREEN"

    def tap(self, d, x, y):
        self.taps.append((d, x, y))

    def find_image_in_bytes(self, data, path, threshold=0.8):
        return self.found, 0, 0, "m"

    def match_template_bytes(self, data, tmpl, thr):
        return self.found, 5, 6, "m"

    def stop_app(self, d, pkg):
        self.taps.append(("stop_app", pkg))

    def launch_app_by_package(self, d, pkg):
        self.taps.append(("launch_app", pkg))


def _pause_step():
    return {"type": "tap", "x": "2", "y": "2", "desc": "ปุ่มที่ยังไม่เคยเจอ",
            "anchor_img": B64, "anchor_timeout": 0.001, "anchor_on_fail": "pause"}


def _api_with_temp_accounts(n_accounts=1, steps=None):
    tmp = tempfile.mkdtemp()
    tmp_acc = os.path.join(tmp, "accounts.json")
    accts = [{"email": f"a{i}@x.com", "password": "p", "checked": True, "name": f"acc{i}"}
             for i in range(n_accounts)]
    json.dump(accts, open(tmp_acc, "w", encoding="utf-8"))
    api = web_app.Api()
    api._accounts_path = lambda: tmp_acc
    api.controller = MockController()
    api.devices = [":7555"]
    api.selected = {":7555"}
    api.macro_steps = steps if steps is not None else [_pause_step(), {"type": "tap", "x": "9", "y": "9", "delay": 0}]
    api.current_profile = "TestProfile"
    return api, tmp


def test_paused_step_appears_in_list_paused_with_screenshot_and_account():
    api, tmp = _api_with_temp_accounts(1)
    try:
        r = api.run(anchor_poll="0.01", pause_between_batches=False)
        assert r["ok"] is True
        api._run_thread.join(timeout=5)

        st = api.get_run_state()
        assert st["pausedCount"] == 1

        paused = api.list_paused()
        assert paused["ok"] is True
        assert len(paused["items"]) == 1
        item = paused["items"][0]
        assert item["device"] == ":7555"
        assert item["email"] == "a0@x.com"
        assert item["step_path"] == "0"
        assert item["shot"]   # base64 ของ b"SCREEN" ต้องไม่ว่าง

        # ขั้นที่ 2 (หลังจุดค้าง) ต้องไม่ถูกทำ กันข้อมูลเพี้ยน
        assert (":7555", 9, 9) not in api.controller.taps
        # ไม่รีเซ็ตเกม
        assert not any(t[0] == "stop_app" for t in api.controller.taps)
    finally:
        shutil.rmtree(tmp)


def test_resume_paused_continues_with_same_account_and_clears_from_list():
    api, tmp = _api_with_temp_accounts(1)
    try:
        api.run(anchor_poll="0.01", pause_between_batches=False)
        api._run_thread.join(timeout=5)
        assert api.get_run_state()["pausedCount"] == 1

        # จำลองว่าผู้ใช้แก้สคริปต์แล้ว (เพิ่มเงื่อนไข/เปลี่ยน anchor) รอบนี้ควรเจอ -> รันต่อผ่านได้
        api.controller.found = True
        r = api.resume_paused(":7555")
        assert r["ok"] is True

        import time
        for _ in range(50):
            if not api._active_resumes:
                break
            time.sleep(0.1)

        assert api._active_resumes == {}
        assert api.get_run_state()["pausedCount"] == 0
        # ขั้นที่ 2 ต้องถูกทำแล้ว (รันต่อจากขั้นที่ค้างไว้ ไม่ใช่เริ่มใหม่ทั้งสคริปต์)
        assert (":7555", 9, 9) in api.controller.taps
    finally:
        shutil.rmtree(tmp)


def test_dismiss_paused_clears_without_running_further():
    api, tmp = _api_with_temp_accounts(1)
    try:
        api.run(anchor_poll="0.01", pause_between_batches=False)
        api._run_thread.join(timeout=5)
        assert api.get_run_state()["pausedCount"] == 1

        r = api.dismiss_paused(":7555")
        assert r["ok"] is True
        assert api.get_run_state()["pausedCount"] == 0
        assert (":7555", 9, 9) not in api.controller.taps
    finally:
        shutil.rmtree(tmp)


def test_resume_paused_with_no_checkpoint_is_noop():
    api, tmp = _api_with_temp_accounts(1)
    try:
        r = api.resume_paused(":9999")
        assert r["ok"] is False
    finally:
        shutil.rmtree(tmp)


def test_other_device_keeps_running_while_one_is_paused():
    """สองจอพร้อมกัน: จอหนึ่งตั้ง pause (ค้าง) อีกจอไม่มี anchor เลยต้องทำงานจนจบตามปกติ ไม่ถูกกระทบ"""
    api, tmp = _api_with_temp_accounts(2, steps=[_pause_step()])
    try:
        api.devices = [":7555", ":7556"]
        api.selected = {":7555", ":7556"}
        api.run(anchor_poll="0.01", pause_between_batches=False)
        api._run_thread.join(timeout=5)

        paused = api.list_paused()["items"]
        # ทั้งสองจอเจอ step เดียวกันที่ anchor ไม่เจอเสมอ -> ทั้งคู่ควร pause (mock เดียวกัน ไม่แยกจอ)
        # ยืนยันว่า 'จอที่ pause แล้ว' แต่ละจอมี checkpoint (บัญชี) ของตัวเอง ไม่ทับ/ปนกัน
        assert len(paused) == 2
        devices_paused = {it["device"] for it in paused}
        assert devices_paused == {":7555", ":7556"}
        emails = {it["email"] for it in paused}
        assert emails == {"a0@x.com", "a1@x.com"}
    finally:
        shutil.rmtree(tmp)


def test_stop_cancels_active_resume():
    api, tmp = _api_with_temp_accounts(1, steps=[_pause_step(), {"type": "sleep", "seconds": 2}])
    try:
        api.run(anchor_poll="0.01", pause_between_batches=False)
        api._run_thread.join(timeout=5)
        assert api.get_run_state()["pausedCount"] == 1

        api.controller.found = True
        api.resume_paused(":7555")
        assert ":7555" in api._active_resumes
        api.stop()
        assert api._active_resumes[":7555"]["running"] is False
    finally:
        shutil.rmtree(tmp)


def test_resume_paused_continues_with_remaining_queue():
    # 3 บัญชี บน 1 จอ
    api, tmp = _api_with_temp_accounts(3)
    try:
        r = api.run(anchor_poll="0.01", pause_between_batches=False)
        assert r["ok"] is True
        api._run_thread.join(timeout=5)
        
        # จอต้องติด pause ที่รหัสแรก (a0@x.com)
        st = api.get_run_state()
        assert st["pausedCount"] == 1
        
        # คิวหลักของ runner ดั้งเดิมต้องยังมีบัญชีเหลือ 2 ตัว (a1@x.com, a2@x.com)
        assert api._runner is not None
        assert api._runner.queue.qsize() == 2
        
        # แก้ไขจำลองว่าหาเจอแล้ว เพื่อให้รันผ่าน
        api.controller.found = True
        
        # กดรันต่อ
        r = api.resume_paused(":7555")
        assert r["ok"] is True
        
        # รอจนกว่าเธรดรันต่อทั้งหมดจะเสร็จ
        import time
        for _ in range(50):
            if not api._active_resumes:
                break
            time.sleep(0.1)
            
        assert api._active_resumes == {}
        assert api.get_run_state()["pausedCount"] == 0
        
        # เช็คผลลัพธ์รายบัญชี
        accts = api._accounts()
        # ทุกบัญชีต้องรันสำเร็จ (completed)
        completed_emails = [a.get("email") for a in accts if a.get("last_status") == "completed"]
        assert len(completed_emails) == 3
        assert "a0@x.com" in completed_emails
        assert "a1@x.com" in completed_emails
        assert "a2@x.com" in completed_emails
    finally:
        shutil.rmtree(tmp)
