"""เทส 'รอบซ่อม' — จบเซ็ตแล้ววนกลับมาทำเฉพาะรหัสที่พลาดเอง

เดิมจบรันแล้วต้องไล่ติ๊กตัวแดงเองทุกครั้งแล้วกดรันใหม่ ตอนนี้ Api วนให้เอง
โดย MacroRunner ไม่รู้เรื่องรอบซ่อมเลย — แค่ถูกเรียกซ้ำด้วยลิสต์ที่สั้นลง

กติกาที่เทสนี้ล็อกไว้:
1. รอบซ่อมต้องทำ 'เฉพาะตัวที่พลาด' ไม่ใช่ทั้งเซ็ตใหม่
2. ต้องมีเพดานกันวนไม่รู้จบ และต้องหยุดเร็วกว่าเพดานถ้าอาการเดิมซ้ำ
   (รหัสที่พังจริง เช่นเมลตาย จะพลาดทุกรอบตลอดไป — วนต่อก็เสียเวลาเปล่า)
3. ผู้ใช้กดหยุด หรือมีจอจอดรอแก้ไข = ห้ามขึ้นรอบใหม่
4. 'stopped' (คนกดหยุด) ไม่ใช่ 'พลาด' ห้ามเอาไปซ่อม
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web_app

EMAILS = ["a@x.com", "b@x.com", "c@x.com", "d@x.com"]


class FakeRunner:
    """MacroRunner ปลอม — กำหนดผลรายรอบได้ (script[i] = {email: status} ของรอบที่ i)"""

    def __init__(self, script):
        self.script = script
        self.account_results = []
        self.diamond_rows = []
        self.attempt_no = 1
        self.rounds = []          # อีเมลที่ถูกส่งเข้ามาแต่ละรอบ
        self.attempt_seen = []    # ค่า attempt_no ที่ Api ตั้งให้แต่ละรอบ

    def run(self, accts):
        table = self.script[min(len(self.rounds), len(self.script) - 1)]
        self.rounds.append([a["email"] for a in accts])
        self.attempt_seen.append(self.attempt_no)
        for a in accts:
            self.account_results.append({
                "email": a["email"], "device": ":7555", "error": "",
                "status": table.get(a["email"], "completed")})


def _api(emails=EMAILS):
    api = web_app.Api()
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "accounts.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump([{"email": e, "password": "p", "checked": True} for e in emails],
                  f, ensure_ascii=False)
    api._accounts_path = lambda: path
    api._running = True
    api._paused = {}
    return api, path


def go(api, runner, rounds, emails=EMAILS):
    accounts = [{"email": e, "password": "p"} for e in emails]
    return api._run_with_retries(runner, accounts, runner.run, rounds,
                                 lambda t, k="info": None)


def _disk(path):
    with open(path, encoding="utf-8") as f:
        return {a["email"]: a for a in json.load(f)}


FAIL_AB = {"a@x.com": "device_error", "b@x.com": "device_error"}


# ---------- ทำเฉพาะตัวที่พลาด ----------

def test_retry_round_only_takes_the_failed_ones():
    api, _ = _api()
    r = FakeRunner([FAIL_AB, {}])
    go(api, r, rounds=2)
    assert r.rounds[0] == EMAILS                       # รอบแรก = ทั้งเซ็ต
    assert r.rounds[1] == ["a@x.com", "b@x.com"]       # รอบซ่อม = เฉพาะตัวแดง


def test_stops_as_soon_as_the_retry_fixes_everything():
    api, _ = _api()
    r = FakeRunner([FAIL_AB, {}])
    go(api, r, rounds=3)
    assert len(r.rounds) == 2, "ซ่อมผ่านแล้วยังวนต่ออีก"


def test_no_failures_means_no_retry_round_at_all():
    api, _ = _api()
    r = FakeRunner([{}])
    go(api, r, rounds=3)
    assert len(r.rounds) == 1


def test_rounds_zero_keeps_the_old_single_pass_behaviour():
    api, _ = _api()
    r = FakeRunner([FAIL_AB])
    go(api, r, rounds=0)
    assert len(r.rounds) == 1


# ---------- กันวนไม่รู้จบ ----------

def test_stops_early_when_the_same_accounts_keep_failing():
    """ตัวตัดจริงในทางปฏิบัติ: รอบซ่อมไม่มีใครผ่านเลย + ชุดที่พลาดเหมือนเดิมเป๊ะ"""
    api, _ = _api()
    r = FakeRunner([FAIL_AB, FAIL_AB, FAIL_AB, FAIL_AB, FAIL_AB])
    go(api, r, rounds=5)
    assert len(r.rounds) == 2, f"ควรหยุดตั้งแต่รอบซ่อมแรก แต่วนไป {len(r.rounds)} รอบ"


def test_keeps_going_while_each_round_still_fixes_someone():
    """ค่อย ๆ ดีขึ้นทุกรอบ = ยังมีหวัง วนต่อจนครบเพดานพอดี ไม่เกิน"""
    api, _ = _api()
    r = FakeRunner([
        {"a@x.com": "device_error", "b@x.com": "device_error", "c@x.com": "device_error"},
        {"a@x.com": "device_error", "b@x.com": "device_error"},
        {"a@x.com": "device_error"},
        {"a@x.com": "device_error"},
    ])
    go(api, r, rounds=3)
    assert len(r.rounds) == 4, f"เพดาน 3 รอบซ่อม = รันได้ 4 รอบ แต่ได้ {len(r.rounds)}"
    assert r.rounds[-1] == ["a@x.com"]


def test_stop_button_prevents_another_round():
    api, _ = _api()
    r = FakeRunner([FAIL_AB, {}])

    def run_then_stop(accts):
        r.run(accts)
        api._running = False

    accounts = [{"email": e} for e in EMAILS]
    api._run_with_retries(r, accounts, run_then_stop, 3, lambda t, k="info": None)
    assert len(r.rounds) == 1


def test_paused_device_prevents_another_round():
    api, _ = _api()
    r = FakeRunner([FAIL_AB, {}])

    def run_then_pause(accts):
        r.run(accts)
        api._paused[":7555"] = {"account": None}

    accounts = [{"email": e} for e in EMAILS]
    api._run_with_retries(r, accounts, run_then_pause, 3, lambda t, k="info": None)
    assert len(r.rounds) == 1, "มีจอรอคนแก้อยู่ ห้ามรันทับ"


def test_stopped_accounts_are_not_treated_as_failures():
    api, _ = _api()
    r = FakeRunner([{"a@x.com": "stopped", "b@x.com": "stopped"}, {}])
    go(api, r, rounds=3)
    assert len(r.rounds) == 1, "คนกดหยุด ไม่ใช่ 'พลาด' — ห้ามเอาไปซ่อม"


# ---------- นับรอบให้ผู้ใช้เห็น ----------

def test_attempts_counted_per_account():
    api, _ = _api()
    r = FakeRunner([
        {"a@x.com": "device_error", "b@x.com": "device_error", "c@x.com": "device_error"},
        {"a@x.com": "device_error", "b@x.com": "device_error"},
        {},
    ])
    at = go(api, r, rounds=3)
    assert at["d@x.com"] == 1      # ผ่านตั้งแต่รอบแรก
    assert at["c@x.com"] == 2      # โดนซ่อมรอบเดียว
    assert at["a@x.com"] == 3      # โดนซ่อมสองรอบ


def test_attempts_written_onto_the_accounts_file():
    api, path = _api()
    r = FakeRunner([FAIL_AB, {}])
    go(api, r, rounds=2)
    disk = _disk(path)
    assert disk["a@x.com"]["last_attempts"] == 2
    assert disk["d@x.com"]["last_attempts"] == 1


def test_runner_is_told_which_round_it_is_on():
    api, _ = _api()
    r = FakeRunner([FAIL_AB, {}])
    go(api, r, rounds=2)
    assert r.attempt_seen == [1, 2]


def test_shown_in_the_account_list():
    api, _ = _api()
    r = FakeRunner([FAIL_AB, {}])
    go(api, r, rounds=2)
    rows = {a["email"]: a for g in api.get_accounts_grouped()["groups"]
            for a in g["accounts"]}
    assert rows["a@x.com"]["attempts"] == 2
    assert rows["d@x.com"]["attempts"] == 1


# ---------- ผลลัพธ์ที่เขียนลงไฟล์ ----------

def test_final_status_is_from_the_last_round_not_the_first():
    api, path = _api()
    r = FakeRunner([FAIL_AB, {}])
    go(api, r, rounds=2)
    disk = _disk(path)
    assert disk["a@x.com"]["last_status"] == "completed", "ซ่อมผ่านแล้วต้องหายแดง"
    assert disk["b@x.com"]["last_status"] == "completed"


def test_account_that_never_recovers_stays_red():
    api, path = _api()
    r = FakeRunner([FAIL_AB, FAIL_AB, FAIL_AB])
    go(api, r, rounds=3)
    assert _disk(path)["a@x.com"]["last_status"] == "device_error"


def test_no_account_is_lost_after_several_rounds():
    """ground rule #4: path ที่เขียนไฟล์ห้ามทำบัญชีหาย"""
    api, path = _api()
    r = FakeRunner([FAIL_AB, FAIL_AB, {}])
    go(api, r, rounds=3)
    assert len(_disk(path)) == len(EMAILS)


def test_results_persisted_every_round_not_only_at_the_end():
    """จุดสีในลิสต์ต้องอัปเดตระหว่างทาง ไม่ใช่รอจบทุกรอบ"""
    api, _ = _api()
    calls = []
    real = api._persist_run_results

    def spy(res, log, at=None):
        calls.append(len(res))
        return real(res, log, at)

    api._persist_run_results = spy
    # ต้องเป็นสคริปต์ที่ 'ดีขึ้นทุกรอบ' ไม่งั้นตัวหยุดเร็ว (ชุดเดิมซ้ำ) จะตัดจบตั้งแต่รอบ 2
    r = FakeRunner([
        {"a@x.com": "device_error", "b@x.com": "device_error"},
        {"a@x.com": "device_error"},
        {},
    ])
    go(api, r, rounds=3)
    assert len(calls) == len(r.rounds) == 3


# ---------- ค่าตั้งจำนวนรอบ ----------

def test_retry_rounds_setting_round_trips_and_is_clamped(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "base_dir", lambda: str(tmp_path))
    api = web_app.Api()
    assert api.save_retry_rounds(3) == {"retry_rounds": 3}
    assert api.get_retry_rounds() == {"retry_rounds": 3}
    assert api.save_retry_rounds(99)["retry_rounds"] == 5          # เพดาน
    assert api.save_retry_rounds(-4)["retry_rounds"] == 0          # พื้น
    assert api.save_retry_rounds("ไม่ใช่เลข")["retry_rounds"] == 2  # ค่าเริ่มต้น
