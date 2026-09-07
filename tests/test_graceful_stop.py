"""เทสการหยุดแบบ 'จบรหัสที่ทำอยู่ก่อน' (stop_after_current)

เดิมมีการหยุดแบบเดียว: stop() สั่ง running=False -> ทุก self.running() ตัดกลางขั้นทันที
บัญชีที่กำลังทำจึงค้างครึ่ง ๆ กลาง ๆ กลับมารันต่อทีต้องมานั่งไล่ว่าทำถึงไหนแล้ว

แบบใหม่: บัญชีที่ค้างอยู่เดินจนจบสคริปต์ (สถานะถูกบันทึกครบ) แล้วค่อยเลิกหยิบตัวใหม่

กติกาที่เทสนี้ล็อกไว้:
1. สั่งหยุดแบบสุภาพแล้ว บัญชีที่กำลังทำต้อง 'ไม่' ถูกตัดกลางคัน
2. ต้องไม่หยิบบัญชีใหม่จากคิวมาทำต่อ
3. ปุ่มหยุดเดิม (ตัดทันที) ต้องทำงานเหมือนเดิมเป๊ะ ไม่โดนกระทบ
4. สั่งหยุดแบบสุภาพแล้วต้องไม่ขึ้น 'รอบซ่อม' ใหม่
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import macro_runner as M
import web_app


# ----------------------------------------------------------------- ฝั่ง engine

class Ctl:
    def __init__(self):
        self.taps = []

    def tap(self, d, x, y):
        self.taps.append((d, int(float(x)), int(float(y))))
        return True, ""


def _runner(steps, accounts, running=lambda: True):
    r = M.MacroRunner(Ctl(), steps, log_cb=lambda t, k="info": None,
                      running_check=running)
    r._interruptible_sleep = lambda s: r.running()
    r.done_accounts = []
    return r


STEPS = [{"type": "tap", "x": "10", "y": "20", "delay": 0}]


def _accounts(n):
    return [{"email": f"a{i}@x.com", "password": "p"} for i in range(n)]


def test_default_is_off_so_nothing_changes():
    r = _runner(STEPS, None)
    assert r.stop_after_current is False


def test_queue_stops_taking_new_accounts_after_flag_is_set():
    """สั่งหยุดตอนทำบัญชีที่ 2 -> ต้องได้ครบ 2 ตัว ไม่ใช่ 5"""
    accounts = _accounts(5)
    r = _runner(STEPS, accounts)
    done = []

    def fake_execute(dev, acc, start_index=0):
        done.append(acc["email"])
        if len(done) == 2:
            r.stop_after_current = True      # กดปุ่มระหว่างที่บัญชีที่ 2 กำลังทำ
        return "completed"

    r.execute_one = fake_execute
    r.run_queue([":7555"], accounts)
    assert done == ["a0@x.com", "a1@x.com"], done


def test_the_account_in_flight_is_never_cut_off():
    """หัวใจของฟีเจอร์: บัญชีที่ค้างอยู่ต้องเดินจนจบสคริปต์ ไม่ใช่ถูกตัดกลางขั้น"""
    accounts = _accounts(3)
    r = _runner(STEPS, accounts)
    finished_cleanly = []

    def fake_execute(dev, acc, start_index=0):
        r.stop_after_current = True          # สั่งหยุด 'ระหว่าง' บัญชีนี้กำลังทำ
        # ถ้าโดนตัดกลางคัน running() จะเป็น False ตรงนี้
        assert r.running() is True, "บัญชีที่ค้างอยู่โดนตัดกลางคัน"
        finished_cleanly.append(acc["email"])
        return "completed"

    r.execute_one = fake_execute
    r.run_queue([":7555"], accounts)
    assert finished_cleanly == ["a0@x.com"]


def test_sequential_mode_also_stops_after_finishing_one():
    accounts = _accounts(4)
    r = _runner(STEPS, accounts)
    done = []

    def fake_execute(dev, acc, start_index=0):
        done.append(acc["email"])
        if len(done) == 2:
            r.stop_after_current = True
        return "completed"

    r.execute_one = fake_execute
    r.run_sequential([":7555", ":7556"], accounts, gap=(0, 0))
    assert done == ["a0@x.com", "a1@x.com"], done


def test_hard_stop_still_cuts_immediately():
    """ปุ่มหยุดเดิมต้องไม่เปลี่ยนพฤติกรรม"""
    accounts = _accounts(5)
    alive = {"on": True}
    r = _runner(STEPS, accounts, running=lambda: alive["on"])
    done = []

    def fake_execute(dev, acc, start_index=0):
        done.append(acc["email"])
        alive["on"] = False                  # กดปุ่ม 'หยุดเลย'
        return "stopped"

    r.execute_one = fake_execute
    r.run_queue([":7555"], accounts)
    assert done == ["a0@x.com"]


# -------------------------------------------------------------------- ฝั่ง Api

def _api():
    api = web_app.Api()
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "accounts.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump([{"email": "a@x.com", "checked": True}], f)
    api._accounts_path = lambda: path
    api._running = True
    api._paused = {}
    return api


class FakeRunner:
    def __init__(self):
        self.account_results = []
        self.diamond_rows = []
        self.attempt_no = 1
        self.stop_after_current = False
        self.rounds = []


def test_api_sets_the_flag_on_the_live_runner():
    api = _api()
    r = FakeRunner()
    api._runner = r
    assert api.stop_after_current()["ok"] is True
    assert r.stop_after_current is True
    assert api._graceful_stop is True


def test_api_refuses_when_nothing_is_running():
    api = _api()
    api._running = False
    assert api.stop_after_current()["ok"] is False


def test_pressing_it_twice_is_harmless():
    api = _api()
    api._runner = FakeRunner()
    api.stop_after_current()
    again = api.stop_after_current()
    assert again["ok"] is True and again.get("already") is True


def test_hard_stop_clears_the_graceful_flag():
    api = _api()
    api._runner = FakeRunner()
    api.stop_after_current()
    api.stop()
    assert api._graceful_stop is False
    assert api._running is False


def test_starting_a_new_run_clears_the_flag():
    api = _api()
    api._runner = FakeRunner()
    api.stop_after_current()
    assert api._graceful_stop is True
    # run() จะรีเซ็ตให้ แต่เรียกจริงไม่ได้ในเทส (ต้องมีจอ) เลยเช็คว่ามีบรรทัดรีเซ็ตอยู่
    import inspect
    src = inspect.getsource(web_app.Api.run)
    assert "_graceful_stop = False" in src, "run() ต้องรีเซ็ตธงหยุดทุกครั้งที่เริ่มรอบใหม่"


def test_no_retry_round_after_graceful_stop():
    """รอบซ่อม = การหยิบบัญชีมาทำเพิ่ม จึงต้องไม่ขึ้นหลังสั่งหยุด"""
    api = _api()
    r = FakeRunner()
    api._runner = r

    def run_once(accts):
        r.rounds.append([a["email"] for a in accts])
        for a in accts:
            r.account_results.append({"email": a["email"], "status": "device_error",
                                      "error": "", "device": ":7555"})
        api.stop_after_current()             # กดปุ่มระหว่างรอบแรก

    api._run_with_retries(r, [{"email": "a@x.com"}], run_once, 3, lambda t, k="info": None)
    assert len(r.rounds) == 1, f"ไม่ควรขึ้นรอบซ่อมหลังสั่งหยุด แต่รันไป {len(r.rounds)} รอบ"


def test_graceful_state_is_reported_to_the_ui():
    api = _api()
    api._runner = FakeRunner()
    api.stop_after_current()
    assert api.get_run_state()["gracefulStop"] is True
