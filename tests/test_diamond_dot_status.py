"""จุดสถานะหน้าบัญชี: 'ได้เพชรแล้ว' ต้องแยกออกจาก 'รันเสร็จ' และชนะทุกสถานะอื่น

ที่มา: ปล่อยบอทฟาร์มตอนเช้า (จอทั้งหมดจบงาน -> จุด 'เสร็จ' สีเดียวกันหมด) แล้วรันสคริปต์
รับเพชรทีหลัง ถ้าถูกหยุดกลางคันแล้วมารันต่อ บัญชีที่ได้เพชรแล้วกับยังไม่ได้ จะขึ้นจุดสีเดียวกัน
ต้องไล่ดูทีละแถวเอง — แก้โดยให้ diamond_time (เขียนไว้แล้วทุกครั้งที่อ่านเพชรสำเร็จ) กำหนดจุดสีม่วง

กติกาที่ผู้ใช้ยืนยันไว้ (ต้องล็อกด้วยเทส):
1. นับว่า 'ได้เพชรแล้ว' ทันทีที่อ่านเพชรสำเร็จ ไม่ต้องรอผลส่งเว็บ
2. ม่วงชนะทุกสถานะอื่น รวมถึง 'พลาด' — ได้เพชรแล้ว = ผ่านแล้ว ต่อให้ขั้นตอนหลังจากนั้นพัง
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web_app

PURPLE = "#A78BFA"
BLUE = "#38BDF8"
RED = "#F87171"
GRAY = "#58677E"


def _api(accts):
    api = web_app.Api()
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "accounts.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(accts, f, ensure_ascii=False)
    api._accounts_path = lambda: path
    return api, path


def _at(offset_from_now_hours=0):
    """timestamp สตริงในฟอร์แมตเดียวกับ diamond_time/last_run"""
    import datetime
    dt = datetime.datetime.now() + datetime.timedelta(hours=offset_from_now_hours)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _farming_boundary_now():
    """เวลาปัจจุบันเทียบกับเขต 05:00 -> คืน (เวลาที่ 'อยู่ในรอบวันนี้', เวลาที่ 'เมื่อวาน')"""
    import datetime
    now = datetime.datetime.now()
    today = web_app._farming_day_start(now)
    yesterday = today - datetime.timedelta(seconds=1)
    return today.strftime("%Y-%m-%d %H:%M:%S"), yesterday.strftime("%Y-%m-%d %H:%M:%S")


TODAY_TS, YESTERDAY_TS = _farming_boundary_now()


def test_diamond_today_shows_purple():
    api, _ = _api([{"email": "a@x.com", "checked": True, "diamond_time": TODAY_TS}])
    row = api.get_accounts_grouped()["groups"][0]["accounts"][0]
    assert row["dot"] == PURPLE


def test_diamond_from_before_todays_farming_window_is_not_purple():
    """diamond_time ของ 'เมื่อวาน' (ก่อนเขต 05:00) ต้องไม่ทำให้ขึ้นม่วง"""
    api, _ = _api([{"email": "a@x.com", "checked": True, "diamond_time": YESTERDAY_TS,
                    "last_status": "completed", "last_run": YESTERDAY_TS}])
    row = api.get_accounts_grouped()["groups"][0]["accounts"][0]
    assert row["dot"] != PURPLE


def test_purple_wins_over_failed():
    """หัวใจของฟีเจอร์: ได้เพชรวันนี้แล้ว แต่ last_status เป็น device_error -> ต้องได้ม่วง ไม่ใช่แดง"""
    api, _ = _api([{"email": "a@x.com", "checked": True,
                    "diamond_time": TODAY_TS,
                    "last_status": "device_error", "last_run": TODAY_TS}])
    row = api.get_accounts_grouped()["groups"][0]["accounts"][0]
    assert row["dot"] == PURPLE


def test_purple_wins_over_completed_too():
    api, _ = _api([{"email": "a@x.com", "checked": True,
                    "diamond_time": TODAY_TS,
                    "last_status": "completed", "last_run": TODAY_TS}])
    row = api.get_accounts_grouped()["groups"][0]["accounts"][0]
    assert row["dot"] == PURPLE


def test_no_diamond_time_falls_back_to_old_behaviour():
    """ไม่มี diamond_time เลย -> พฤติกรรมเดิมเป๊ะ (ไม่กระทบสคริปต์/บัญชีเก่าที่ไม่เคยอ่านเพชร)"""
    api, _ = _api([
        {"email": "done@x.com", "checked": True, "last_status": "completed", "last_run": TODAY_TS},
        {"email": "fail@x.com", "checked": True, "last_status": "device_error", "last_run": TODAY_TS},
        {"email": "new@x.com", "checked": True},
    ])
    rows = {a["email"]: a for g in api.get_accounts_grouped()["groups"] for a in g["accounts"]}
    assert rows["done@x.com"]["dot"] == BLUE
    assert rows["fail@x.com"]["dot"] == RED
    assert rows["new@x.com"]["dot"] == GRAY


def test_malformed_diamond_time_does_not_crash():
    api, _ = _api([
        {"email": "a@x.com", "checked": True, "diamond_time": "ไม่ใช่วันที่"},
        {"email": "b@x.com", "checked": True, "diamond_time": ""},
        {"email": "c@x.com", "checked": True, "diamond_time": None},
    ])
    rows = api.get_accounts_grouped()["groups"][0]["accounts"]
    assert all(r["dot"] != PURPLE for r in rows)


def test_select_no_diamond_ticks_only_accounts_without_diamond_today():
    api, path = _api([
        {"email": "got@x.com", "checked": False, "diamond_time": TODAY_TS},
        {"email": "not_yet@x.com", "checked": False},
        {"email": "old_diamond@x.com", "checked": False, "diamond_time": YESTERDAY_TS},
    ])
    api.select_accounts_by_status("no_diamond")
    with open(path, encoding="utf-8") as f:
        disk = {a["email"]: a for a in json.load(f)}
    assert disk["got@x.com"]["checked"] is False
    assert disk["not_yet@x.com"]["checked"] is True
    assert disk["old_diamond@x.com"]["checked"] is True


def test_select_failed_and_pending_still_work_unchanged():
    """ปุ่มเดิม 2 ปุ่ม ต้องไม่โดนกระทบจากการเพิ่มเงื่อนไขที่ 3"""
    api, path = _api([
        {"email": "done@x.com", "checked": False, "last_status": "completed", "last_run": TODAY_TS},
        {"email": "fail@x.com", "checked": False, "last_status": "device_error", "last_run": TODAY_TS},
    ])
    api.select_accounts_by_status("failed")
    with open(path, encoding="utf-8") as f:
        disk = {a["email"]: a for a in json.load(f)}
    assert disk["done@x.com"]["checked"] is False
    assert disk["fail@x.com"]["checked"] is True

    api.select_accounts_by_status("pending")
    with open(path, encoding="utf-8") as f:
        disk = {a["email"]: a for a in json.load(f)}
    assert disk["done@x.com"]["checked"] is False
    assert disk["fail@x.com"]["checked"] is True


def test_shares_the_exact_same_day_boundary_as_effective_status():
    """diamond_today กับ _get_effective_status ต้องใช้เขตเวลาเดียวกันจริง ไม่ใช่ค่าคงที่ 5 ซ้ำกันโดยบังเอิญ"""
    import datetime
    for hour_offset in (-6, -1, 0, 1, 6):
        probe = datetime.datetime.now() + datetime.timedelta(hours=hour_offset)
        ts = probe.strftime("%Y-%m-%d %H:%M:%S")
        in_today_via_status = bool(web_app._get_effective_status(
            {"last_status": "completed", "last_run": ts}))
        in_today_via_diamond = web_app.Api._diamond_today({"diamond_time": ts})
        assert in_today_via_status == in_today_via_diamond, (hour_offset, ts)
