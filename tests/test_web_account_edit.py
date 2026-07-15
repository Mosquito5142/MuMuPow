"""เทสฟอร์มแก้ไขบัญชีฝั่ง webui ไม่ทำข้อมูลบัญชีพัง (พอร์ตให้ตรงกับ Tkinter start_edit_account/add_account)

บั๊กเดิม 3 ตัวที่เจอพร้อมกัน:
1. get_accounts_grouped ไม่ส่ง password มาเลย -> ช่องรหัสผ่านบนเว็บว่างตลอด
   แล้ว save_account เขียนทับด้วย "" -> แก้แค่ชื่อ/กลุ่ม = รหัสผ่านหาย
2. ส่งมาแต่ 'tok' ที่ถูกหั่นเหลือ 14 ตัว + '…' -> ฝั่ง JS เอาไปเขียนกลับ = refresh_token พัง
3. 'name' ที่ส่งมาคือชื่อที่คำนวณไว้โชว์ (save_web_game_title มาก่อน) ไม่ใช่ค่าดิบในไฟล์
   -> กดบันทึก = name จริงโดนทับด้วย save_web_game_title
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web_app

FULL_TOKEN = "M.C123_BAY.0.U.-ClDGBSp9xxxxxxxxxxxxxxxxxxxxxxLONGTOKEN"

ACCT = {
    "email": "r7db8uhdo7w@outlook.com",
    "password": "KuRokoth55212",
    "name": "EgoEat",                      # ชื่อดิบ
    "save_web_game_title": "1.หลักมอส",    # ชื่อที่เอาไปโชว์ (ต้องไม่ถูกเขียนทับลง name)
    "ingamename": "EgoEat",
    "group": "มอส",
    "refresh_token": FULL_TOKEN,
    "client_id": "cid-123",
    "checked": True,
}


def _api(accts):
    api = web_app.Api()
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "accounts.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(accts, f, ensure_ascii=False)
    api._accounts_path = lambda: path
    return api, path


def _first_account(api):
    return api.get_accounts_grouped()["groups"][0]["accounts"][0]


def test_grouped_sends_real_password_and_full_token_for_the_edit_form():
    api, _ = _api([dict(ACCT)])
    a = _first_account(api)

    assert a["password"] == "KuRokoth55212"   # เดิมไม่มีคีย์นี้เลย -> ช่องบนเว็บเลยว่าง
    assert a["token"] == FULL_TOKEN           # ตัวเต็ม ไม่ใช่ตัวย่อ
    assert a["rawname"] == "EgoEat"           # ค่าดิบ ไม่ใช่ "1.หลักมอส"

    # ค่าที่ใช้โชว์ในลิสต์ต้องยังเหมือนเดิม (ชื่อที่ตั้งบนเว็บมาก่อน + โทเคนย่อ)
    assert a["name"] == "1.หลักมอส"
    assert a["tok"] == FULL_TOKEN[:14] + "…"


def test_editing_name_only_keeps_password_token_and_client_id():
    """จำลองการกดดินสอ -> แก้ชื่อเรียก -> กดบันทึก (ช่องอื่นเติมมาจาก editAccount ตามเดิม)"""
    api, path = _api([dict(ACCT)])
    a = _first_account(api)

    api.save_account({
        "email": a["email"],
        "name": "ชื่อใหม่",
        "group": a["grp"],
        "password": a["password"],   # ฟอร์มเติมค่าจริงกลับมาแล้ว
        "token": a["token"],
    })

    saved = json.load(open(path, encoding="utf-8"))
    assert len(saved) == 1
    s = saved[0]
    assert s["name"] == "ชื่อใหม่"
    assert s["password"] == "KuRokoth55212"
    assert s["refresh_token"] == FULL_TOKEN          # ไม่โดนหั่นเหลือ 14 ตัว
    assert s["client_id"] == "cid-123"               # ฟิลด์ที่ฟอร์มไม่มี ต้องอยู่ครบ
    assert s["save_web_game_title"] == "1.หลักมอส"   # ไม่โดนกลืนหายไป
    assert s["checked"] is True


def test_blank_password_and_token_do_not_wipe_existing_values():
    """ยามชั้นสุดท้าย: ต่อให้ฟอร์มส่งค่าว่างมา (เช่นฟอร์มเก่า/เติมไม่ทัน) ห้ามล้างของเดิมทิ้ง"""
    api, path = _api([dict(ACCT)])

    api.save_account({"email": ACCT["email"], "name": "EgoEat", "group": "มอส",
                      "password": "", "token": ""})

    s = json.load(open(path, encoding="utf-8"))[0]
    assert s["password"] == "KuRokoth55212"
    assert s["refresh_token"] == FULL_TOKEN


def test_password_and_token_still_updatable_and_new_account_still_works():
    api, path = _api([dict(ACCT)])

    # แก้รหัสผ่านจริง ๆ ต้องยังเปลี่ยนได้
    api.save_account({"email": ACCT["email"], "name": "EgoEat", "group": "มอส",
                      "password": "NewPass999", "token": "NEWTOKEN"})
    s = json.load(open(path, encoding="utf-8"))[0]
    assert s["password"] == "NewPass999"
    assert s["refresh_token"] == "NEWTOKEN"

    # เพิ่มบัญชีใหม่ต้องไม่พัง
    api.save_account({"email": "new@x.com", "name": "n1", "group": "ทั่วไป",
                      "password": "p1", "token": "t1"})
    saved = json.load(open(path, encoding="utf-8"))
    assert len(saved) == 2
    new = [x for x in saved if x["email"] == "new@x.com"][0]
    assert new["password"] == "p1"
    assert new["refresh_token"] == "t1"
    assert new["checked"] is True
