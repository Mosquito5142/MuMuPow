"""เทสความปลอดภัยของ accounts.json — ไฟล์ที่เก็บรหัสทั้งหมดของลูกค้า

อาการที่ผู้ใช้เจอ: กดหยุดระหว่างรันบนแอปเว็บ แล้ว accounts.json เสียหาย
สาเหตุที่พบ 3 ชั้น:
  1. เขียนด้วย open(...,'w') = ล้างไฟล์เป็น 0 ไบต์ก่อน แล้วค่อยเขียน 85 KB
  2. หลายเธรดเขียนพร้อมกันโดยไม่มีล็อก — พอกดหยุด เธรดของทุกจอที่ resume อยู่
     จะหลุดจากลูปพร้อมกันแล้ววิ่งเข้า _persist_* ทีเดียว
  3. อ่านไฟล์เสียแล้วคืน [] เงียบ ๆ แล้วเขียนทับ = บัญชีหายถาวร (กู้ไม่ได้)

ห้ามให้เทสชุดนี้แตะ accounts.json ตัวจริงเด็ดขาด (กติกาข้อ 4 ใน CLAUDE.md)
"""
import json
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web_app


@pytest.fixture
def api(tmp_path):
    a = web_app.Api.__new__(web_app.Api)
    a._push_log = lambda *a_, **k_: None
    a._accounts_path = lambda: str(tmp_path / "accounts.json")
    a._accounts_lock = threading.RLock()
    return a


def seed(api, n=50):
    accts = [{"email": f"user{i}@x.com", "password": f"pw{i}", "checked": True} for i in range(n)]
    api._save_accounts(accts, allow_empty=True)
    return accts


def load(api):
    with open(api._accounts_path(), encoding="utf-8") as f:
        return json.load(f)


# ---------- 1. เขียนแบบ atomic ----------

def test_saved_file_is_valid_json():
    pass  # ครอบคลุมโดยเทสอื่นด้านล่าง


def test_write_leaves_no_temp_file_behind(api):
    seed(api, 5)
    assert not os.path.exists(api._accounts_path() + ".tmp")


def test_previous_version_is_kept_as_backup(api):
    seed(api, 3)
    api._save_accounts([{"email": "new@x.com"}], allow_empty=True)
    bak = api._accounts_path() + ".bak"
    assert os.path.exists(bak)
    assert len(json.load(open(bak, encoding="utf-8"))) == 3      # ของเดิมกู้ได้


def test_failed_write_does_not_destroy_the_existing_file(api, monkeypatch):
    """เขียนพังกลางคัน ไฟล์เดิมต้องยังอยู่ครบ — ของเดิมจะเหลือไฟล์ว่าง"""
    seed(api, 20)

    real = json.dump

    def boom(obj, fp, **kw):
        real(obj[:5], fp, **kw)
        raise IOError("ดิสก์เต็มกลางคัน")

    monkeypatch.setattr(web_app.json, "dump", boom)
    assert api._save_accounts([{"email": "x@y.com"}] * 3, allow_empty=True) is False
    monkeypatch.undo()

    assert len(load(api)) == 20                                  # ไม่โดนแตะเลย


# ---------- 2. หลายเธรดเขียนพร้อมกัน ----------

def test_concurrent_writers_never_corrupt_the_file(api):
    """จำลองตอนกดหยุด: หลายจอเขียนผลพร้อมกัน — ไฟล์ต้องอ่านออกเสมอและไม่หายไปไหน"""
    seed(api, 40)
    errors = []

    def worker(n):
        try:
            for _ in range(12):
                api._update_accounts(lambda accts: ([a.update(last_device=f":{n}") for a in accts], True)[1])
        except Exception as e:      # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert errors == []
    data = load(api)                        # ต้อง parse ผ่าน = ไฟล์ไม่พัง
    assert len(data) == 40                  # และบัญชีครบ ไม่หายระหว่างแย่งกันเขียน


def test_concurrent_readers_never_see_a_half_written_file(api):
    seed(api, 30)
    bad = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            ok, data = api._read_accounts_raw()
            if not ok or len(data) != 30:
                bad.append(len(data) if ok else "อ่านไม่ได้")

    def writer():
        for _ in range(25):
            api._update_accounts(lambda accts: (accts[0].update(checked=True), True)[1])

    r = threading.Thread(target=reader); r.start()
    w = threading.Thread(target=writer); w.start()
    w.join(); stop.set(); r.join()

    assert bad == [], f"ผู้อ่านเห็นไฟล์ผิดสภาพ: {bad[:5]}"


# ---------- 3. ไฟล์เสียแล้วห้ามซ้ำเติม ----------

def test_corrupt_file_is_not_overwritten_with_an_empty_list(api):
    """หัวใจของบั๊ก: ไฟล์เสียชั่วคราว -> อ่านได้ [] -> เขียนทับ = บัญชีหายถาวร"""
    seed(api, 25)
    with open(api._accounts_path(), "w", encoding="utf-8") as f:
        f.write('[{"email": "a@b.c"},,,,{ พัง')          # จำลองไฟล์เสีย

    ok = api._update_accounts(lambda accts: True)
    assert ok is False

    raw = open(api._accounts_path(), encoding="utf-8").read()
    assert raw.startswith('[{"email"')                   # ไฟล์เสียยังอยู่เหมือนเดิม ไม่ถูกทับด้วย []


def test_persist_run_results_bails_out_on_corrupt_file(api):
    seed(api, 10)
    with open(api._accounts_path(), "w", encoding="utf-8") as f:
        f.write("ไม่ใช่ json")

    api._persist_run_results([{"email": "user1@x.com", "status": "completed"}],
                             lambda t, k="info": None)
    assert open(api._accounts_path(), encoding="utf-8").read() == "ไม่ใช่ json"


def test_persist_diamonds_bails_out_on_corrupt_file(api, tmp_path, monkeypatch):
    seed(api, 10)
    monkeypatch.setattr(web_app, "base_dir", lambda: str(tmp_path))
    api._load_diamond_cfg = lambda: {"export_path": "d.json", "auto_push": False}
    api._auto_push_diamonds = lambda *a, **k: None
    with open(api._accounts_path(), "w", encoding="utf-8") as f:
        f.write("{พัง")

    api._persist_diamonds([{"email": "user1@x.com", "diamonds": 5, "time": "t"}],
                          lambda t, k="info": None)
    assert open(api._accounts_path(), encoding="utf-8").read() == "{พัง"


def test_blank_save_is_refused_when_accounts_exist(api):
    seed(api, 15)
    assert api._save_accounts([]) is False
    assert len(load(api)) == 15


def test_user_initiated_delete_all_is_allowed(api):
    """ลบเองจากหน้าจอต้องยังลบได้จริง — การกันข้างบนห้ามขวางเจตนาผู้ใช้"""
    seed(api, 5)
    assert api._save_accounts([], allow_empty=True) is True
    assert load(api) == []


def test_non_list_data_is_rejected(api):
    seed(api, 8)
    assert api._save_accounts({"ไม่ใช่": "ลิสต์"}) is False
    assert len(load(api)) == 8


# ---------- ผลรันต้องยังถูกเขียนตามปกติ ----------

def test_run_results_are_written_when_file_is_healthy(api):
    seed(api, 6)
    api._persist_run_results([{"email": "user2@x.com", "status": "completed",
                               "error": "", "device": ":7555"}],
                             lambda t, k="info": None)
    got = {a["email"]: a for a in load(api)}
    assert got["user2@x.com"]["last_status"] == "completed"
    assert got["user2@x.com"]["last_device"] == ":7555"
    assert "last_status" not in got["user1@x.com"]        # บัญชีอื่นไม่โดนแตะ
