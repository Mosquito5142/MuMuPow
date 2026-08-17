"""เทสระดับ Api (web_app.py) สำหรับฟีเจอร์ 'เรียนรู้ทีละจอ': anchor_on_fail='pause' ทำให้จอค้าง
โผล่ในแผง 'จอที่รอแก้ไข' (list_paused) แล้วกด 'รันต่อจากขั้นนี้' (resume_paused) ต่อได้จริง
โดยไม่รบกวนจอ/บัญชีอื่นที่กำลังรันคู่ขนานอยู่ — ต่างจาก tests/test_pause_resume.py ที่เทสแค่
MacroRunner ตรงๆ ไฟล์นี้เทสการต่อสาย Api<->MacroRunner<->progress_cb ทั้งชุด

หมายเหตุ: ค่าตั้งต้นของระบบคือ on_stuck='next' (ติดแล้วข้ามไปไอดีถัดไป ตามที่ผู้ใช้ต้องการ)
ไฟล์นี้จึงต้องส่ง on_stuck='pause' เองทุกครั้ง เพราะกำลังเทสโหมดจอดรอโดยเฉพาะ"""
import base64
import json
import os
import shutil
import sys
import tempfile
import time

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
        r = api.run(anchor_poll="0.01", pause_between_batches=False, on_stuck="pause")
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
        api.run(anchor_poll="0.01", pause_between_batches=False, on_stuck="pause")
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
        api.run(anchor_poll="0.01", pause_between_batches=False, on_stuck="pause")
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
        api.run(anchor_poll="0.01", pause_between_batches=False, on_stuck="pause")
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
        api.run(anchor_poll="0.01", pause_between_batches=False, on_stuck="pause")
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
        r = api.run(anchor_poll="0.01", pause_between_batches=False, on_stuck="pause")
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


def _tap(n):
    return {"type": "tap", "x": str(n), "y": str(n), "delay": 0}


def test_resume_keeps_reporting_the_original_step_number():
    """บั๊กที่ผู้ใช้เจอ: กด 'รันต่อ' แล้วเหมือนไม่ทำอะไร

    ของเดิม resume ตัดสคริปต์ (macro_steps[root_idx:]) ตัวรันเลยนับขั้นใหม่ตั้งแต่ 0
    จุดที่ค้างรอบสองจึงถูกบันทึกเป็นขั้น 1 ทั้งที่จริงคือขั้น 4 ผลคือ:
      - แผงโชว์เลขขั้นผิด และปุ่ม 'แก้ไขที่นี่' กระโดดผิดขั้น
      - กด 'รันต่อ' อีกครั้ง = เริ่มสคริปต์ใหม่ทั้งหมดตั้งแต่ขั้น 1 (ล็อกอินใหม่)
    """
    steps = [_tap(1), _tap(2), _tap(3), _pause_step(), _tap(5)]
    api, tmp = _api_with_temp_accounts(1, steps)
    try:
        api.run(anchor_poll="0.01", on_stuck="pause")
        api._run_thread.join(timeout=10)
        assert api.list_paused()["items"][0]["step_path"] == "3"

        api.resume_paused(":7555")
        for _ in range(100):
            if not api._active_resumes:
                break
            time.sleep(0.05)

        items = api.list_paused()["items"]
        assert items, "ค้างซ้ำแล้วต้องยังอยู่ในแผง"
        assert items[0]["step_path"] == "3", "เลขขั้นต้องยังเป็นขั้นเดิมของสคริปต์เต็ม"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_resume_starts_at_the_paused_step_not_from_the_beginning():
    """รันต่อต้องเริ่มที่ขั้นที่ค้าง ไม่ใช่ไล่ขั้น 1-3 ใหม่"""
    steps = [_tap(1), _tap(2), _tap(3), _pause_step(), _tap(5)]
    api, tmp = _api_with_temp_accounts(1, steps)
    try:
        api.run(anchor_poll="0.01", on_stuck="pause")
        api._run_thread.join(timeout=10)

        api.controller.taps.clear()
        api.controller.found = True          # จำลองว่าผู้ใช้แก้แล้ว รอบนี้เจอภาพ
        api.resume_paused(":7555")
        for _ in range(100):
            if not api._active_resumes:
                break
            time.sleep(0.05)

        pts = [(t[1], t[2]) for t in api.controller.taps if t[0] == ":7555"]
        assert (1, 1) not in pts, "ต้องไม่ย้อนไปทำขั้น 1 ใหม่"
        assert (5, 5) in pts, "ต้องเดินต่อไปถึงขั้นหลังจุดที่ค้าง"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_retry_target_still_points_at_the_right_step_after_resume():
    """anchor_retry_target เก็บเป็นดัชนีของสคริปต์เต็ม ถ้า resume ตัดลิสต์ เลขนี้จะชี้ผิดขั้น"""
    stuck = dict(_pause_step(), anchor_on_fail="retry", anchor_retry_target=1, anchor_retry_limit=1)
    steps = [_tap(1), _tap(2), _tap(3), stuck, _tap(5)]
    api, tmp = _api_with_temp_accounts(1, steps)
    try:
        api.macro_steps = steps
        runner = web_app.MacroRunner(api.controller, steps, log_cb=lambda t, k="info": None,
                                     running_check=lambda: True, anchor_poll=0.01)
        runner.execute_one(":7555", {"email": "a@x.com"}, start_index=3)

        pts = [(t[1], t[2]) for t in api.controller.taps if t[0] == ":7555"]
        assert (2, 2) in pts, "ต้องวนกลับไปทำขั้นที่ 2 (ดัชนี 1) ตามที่ตั้งไว้"
        assert (1, 1) not in pts, "ต้องไม่ไปโดนขั้นที่ 1"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_resume_failures_report_a_reason_instead_of_silence():
    """บั๊กที่ผู้ใช้เจอ: กด 'รันต่อ' แล้วเงียบสนิท ไม่ขยับ ไม่มีข้อความ

    ของเดิมทุกทางที่รันต่อไม่ได้จะ return {"ok": False} เฉย ๆ และเขียน log ลง self._log
    ซึ่งคอนโซลตอนรันไม่ได้อ่าน (อ่านจาก self._run_log) ผู้ใช้เลยไม่เห็นอะไรสักอย่าง
    """
    api, tmp = _api_with_temp_accounts(1)
    try:
        r = api.resume_paused(":7555")           # ไม่มีจุดค้างเลย
        assert r["ok"] is False
        assert r.get("error"), "ต้องบอกสาเหตุกลับไปให้ UI แสดง"
        assert any("รันต่อไม่ได้" in e["text"] for e in api._run_log), \
            "ต้องเขียนลงช่อง log ที่คอนโซลอ่านจริง (_run_log)"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_resume_explains_when_the_loaded_script_is_too_short():
    """สลับสคริปต์แล้วกดรันต่อ — ต้องบอกว่าสคริปต์ไม่ตรง ไม่ใช่เงียบ"""
    steps = [_tap(1), _tap(2), _tap(3), _pause_step(), _tap(5)]
    api, tmp = _api_with_temp_accounts(1, steps)
    try:
        api.run(anchor_poll="0.01", on_stuck="pause")
        api._run_thread.join(timeout=10)
        assert api.list_paused()["items"][0]["step_path"] == "3"

        api.macro_steps = [_tap(1)]              # ผู้ใช้สลับไปสคริปต์สั้นกว่า
        r = api.resume_paused(":7555")
        assert r["ok"] is False
        assert "สลับสคริปต์" in r["error"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_stale_resume_flag_does_not_block_future_resumes():
    """ถ้ารอบก่อนตายไปโดยไม่เคลียร์สถานะ จอนั้นจะกดรันต่อไม่ได้อีกเลยทั้งรอบ
    ต้องตรวจว่าเธรดยังมีชีวิตอยู่จริงไหม ไม่ใช่เชื่อแค่ว่ามีคีย์ค้างอยู่"""
    steps = [_tap(1), _pause_step(), _tap(5)]
    api, tmp = _api_with_temp_accounts(1, steps)
    try:
        api.run(anchor_poll="0.01", on_stuck="pause")
        api._run_thread.join(timeout=10)

        api._active_resumes[":7555"] = {"running": False, "thread": None}   # ซากจากรอบก่อน
        api.controller.found = True
        r = api.resume_paused(":7555")
        assert r["ok"] is True, f"ควรรันต่อได้ แต่ได้: {r.get('error')}"
        for _ in range(100):
            if not api._active_resumes:
                break
            time.sleep(0.05)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_a_genuinely_running_resume_is_still_rejected():
    """แต่ถ้ากำลังรันต่ออยู่จริง ๆ ต้องไม่ยิงซ้ำ (กันสองเธรดคุมจอเดียวกัน)"""
    import threading as _t
    steps = [_tap(1), _pause_step(), _tap(5)]
    api, tmp = _api_with_temp_accounts(1, steps)
    try:
        api.run(anchor_poll="0.01", on_stuck="pause")
        api._run_thread.join(timeout=10)

        alive = _t.Event()
        th = _t.Thread(target=alive.wait, daemon=True)
        th.start()
        api._active_resumes[":7555"] = {"running": True, "thread": th}

        r = api.resume_paused(":7555")
        assert r["ok"] is False
        assert "กำลังรันต่ออยู่แล้ว" in r["error"]
        alive.set(); th.join(timeout=2)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
