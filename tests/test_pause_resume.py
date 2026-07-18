"""เทส anchor_on_fail='pause': ไม่เจอภาพ -> จอหยุดค้าง (ไม่รีเซ็ตเกม ไม่หยิบบัญชีถัดไปมาทับ)
ฟีเจอร์ 'เรียนรู้ทีละจอ': หยุดให้ผู้ใช้มาเพิ่มเงื่อนไขแล้วรันต่อ — ตอนนี้เป็นค่าเริ่มต้นแทน 'abort' เดิมแล้ว
และไม่มีนโยบายไหนรีเซ็ตเกมอัตโนมัติอีกต่อไป (ผู้ใช้ตัดสินใจถอดพฤติกรรมนี้ออก เพราะใช้การเรียนรู้แทน)"""
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import macro_runner as M

B64 = base64.b64encode(b"TMPL").decode()


class Ctl:
    """คอนโทรลเลอร์จำลอง — anchor หาไม่เจอเสมอ (found=False) เพื่อไล่เข้า anchor_on_fail
    บันทึกว่า stop_app/launch_app_by_package (ใช้ตอนรีเซ็ตเกม) ถูกเรียกไหม"""

    def __init__(self, found=False):
        self.found = found
        self.calls = []

    def capture_screenshot_bytes(self, d):
        return True, b"SCREEN"

    def match_template_bytes(self, data, tmpl, thr):
        return (self.found, 5, 6, "m")

    def tap(self, d, x, y):
        self.calls.append(("tap", int(float(x)), int(float(y))))

    def stop_app(self, d, pkg):
        self.calls.append(("stop_app", pkg))

    def launch_app_by_package(self, d, pkg):
        self.calls.append(("launch_app", pkg))


def _tap(x, y, **extra):
    step = {"type": "tap", "x": str(x), "y": str(y)}
    step.update(extra)
    return step


RESET_CFG = {"enabled": True, "package": "com.test.app", "boot_wait": 0}


def test_pause_stops_device_without_resetting_game():
    c = Ctl(found=False)
    steps = [
        _tap(1, 1),
        _tap(2, 2, anchor_img=B64, anchor_timeout=0.001, anchor_on_fail="pause"),
        _tap(3, 3),
    ]
    progress_events = []
    r = M.MacroRunner(c, steps, log_cb=lambda t, k="info": None, anchor_poll=0.01,
                      reset_cfg=RESET_CFG, progress_cb=lambda dev, **kw: progress_events.append(kw))
    status = r.execute_one(":7555", {"email": "a@b.c"})

    assert status == "paused"
    # ขั้น 1 ถูกทำ 2 ครั้ง: ครั้งแรก + self-heal ลองย้อนไปทำซ้ำ 1 ครั้งก่อนยอมหยุดรอจริง
    # (เผื่อกดตอนนั้นแล้วจอ/เครื่องค้าง เลยไม่ขยับมาจอนี้จริง ๆ) แต่ขั้น 3 (หลังจุดค้าง) ต้องไม่ถูกทำ
    assert c.calls.count(("tap", 1, 1)) == 2
    assert ("tap", 3, 3) not in c.calls
    # ต้องไม่รีเซ็ตเกม (ต่างจาก abort เดิม)
    assert ("stop_app", "com.test.app") not in c.calls
    assert ("launch_app", "com.test.app") not in c.calls

    # progress ต้องมี event สถานะ paused พร้อมภาพหน้าจอ + บัญชีที่ค้าง (สำหรับ resume ทีหลัง)
    paused_events = [e for e in progress_events if e.get("status") == "paused"]
    assert len(paused_events) == 1
    ev = paused_events[0]
    assert ev.get("step_path") == "1"
    assert ev.get("_pause_shot")  # base64 ของ b"SCREEN"
    assert ev.get("_pause_account") == {"email": "a@b.c"}

    # ไม่บันทึกผลบัญชีตอนนี้ (ยังไม่จบจริง รอ resume)
    assert r.account_results == []


def test_abort_no_longer_resets_game(monkeypatch, tmp_path):
    """abort ยังหยุดจอ+บันทึกจุดที่ติดเหมือนเดิม แต่ต้อง 'ไม่รีเซ็ตเกม' อีกต่อไป (พฤติกรรมเดิมถูกถอดออก
    ตามคำขอผู้ใช้ — ใช้ระบบเรียนรู้ทีละจอแทน) แม้จะตั้ง reset_cfg ให้พร้อมทำงานไว้ก็ตาม
    เส้นทางนี้ตกไป _save_failure_report (เขียนไฟล์จริง) -> ชี้ base_dir() ไปโฟลเดอร์ชั่วคราว
    กัน error_reports/ ของจริงในเรโปโดนขยะเทสสร้างทุกครั้งที่รัน pytest"""
    monkeypatch.setattr(M, "base_dir", lambda: str(tmp_path))
    c = Ctl(found=False)
    steps = [_tap(2, 2, anchor_img=B64, anchor_timeout=0.001, anchor_on_fail="abort")]
    r = M.MacroRunner(c, steps, log_cb=lambda t, k="info": None, anchor_poll=0.01, reset_cfg=RESET_CFG)
    status = r.execute_one(":7555", {"email": "a@b.c"})
    assert status == "device_error"
    assert ("stop_app", "com.test.app") not in c.calls
    assert ("launch_app", "com.test.app") not in c.calls
    assert r.account_results[0]["status"] == "device_error"


def test_missing_anchor_on_fail_defaults_to_pause_not_abort(monkeypatch, tmp_path):
    """ขั้นที่ไม่ได้ตั้ง anchor_on_fail เลย (เช่น สคริปต์เก่า หรือยังไม่เคยกดตั้งค่า) ต้องเข้า 'pause'
    เป็นค่าเริ่มต้นใหม่ ไม่ใช่ 'abort' เดิม — ตรงตามที่ผู้ใช้ต้องการให้การเรียนรู้เป็นเส้นทางหลัก"""
    monkeypatch.setattr(M, "base_dir", lambda: str(tmp_path))
    c = Ctl(found=False)
    steps = [_tap(2, 2, anchor_img=B64, anchor_timeout=0.001)]  # ไม่มี anchor_on_fail เลย
    r = M.MacroRunner(c, steps, log_cb=lambda t, k="info": None, anchor_poll=0.01, reset_cfg=RESET_CFG)
    status = r.execute_one(":7555", {"email": "a@b.c"})
    assert status == "paused"
    assert ("stop_app", "com.test.app") not in c.calls


def test_run_queue_pauses_one_device_without_blocking_others():
    """หลายจอพร้อมกัน: จอที่เจอ pause ต้องหยุดหยิบคิวต่อ (ไม่เอาบัญชีถัดไปมาทับจอที่ค้าง)
    ส่วนจออื่นที่ไม่ pause ต้องทำงานจนครบคิวตามปกติ ไม่ถูกกระทบ"""
    class MultiCtl(Ctl):
        def match_template_bytes(self, data, tmpl, thr):
            # จอ :7555 ไม่เจอเสมอ (จะ pause ตั้งแต่บัญชีแรก) จออื่นเจอเสมอ (ผ่านปกติ)
            return (False, 5, 6, "m") if "7555" in str(getattr(self, "_cur_dev", "")) else (True, 5, 6, "m")

    c = MultiCtl()

    steps = [_tap(2, 2, anchor_img=B64, anchor_timeout=0.001, anchor_on_fail="pause")]
    r = M.MacroRunner(c, steps, log_cb=lambda t, k="info": None, anchor_poll=0.01, reset_cfg=RESET_CFG)

    # ผูก device ปัจจุบันเข้ากับ controller ก่อนเรียก match (จำลองพฤติกรรมจริงที่ผลลัพธ์ขึ้นกับจอ)
    real_wait = r._wait_anchor

    def wait_per_device(device, step):
        c._cur_dev = device
        return real_wait(device, step)

    r._wait_anchor = wait_per_device

    # คิวรวม 3 บัญชี ใช้ร่วมกันทั้ง 2 จอ (worker ไหนว่างหยิบไปทำ) — ตั้งไว้มากกว่าจำนวนจอ
    # เพื่อให้แน่ใจว่า :7556 ยังมีบัญชีเหลือให้ทำต่อได้จริง แม้ :7555 จะหยิบไปแล้ว 1 บัญชี (ก่อน pause)
    accounts = [{"email": "a@b.c"}, {"email": "d@e.f"}, {"email": "g@h.i"}]
    r.run_queue([":7555", ":7556"], accounts)

    # :7555 pause ตั้งแต่บัญชีแรกที่หยิบมา -> เลิกหยิบคิวต่อ (เสร็จแค่ 0 ไม่ทำบัญชีถัดไปทับจอที่ค้าง)
    assert r._done[":7555"] == 0
    # :7556 ไม่ pause -> หยิบบัญชีที่เหลือในคิวมาทำจนหมด (2 บัญชี เพราะ :7555 หยิบไปแล้ว 1)
    assert r._done[":7556"] == 2
