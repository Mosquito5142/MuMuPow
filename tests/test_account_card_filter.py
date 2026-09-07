"""เทสตัวกรอง 'การ์ดที่บัญชีถืออยู่' + ปุ่มติ๊ก/เอาติ๊กออกทั้งชุดในหน้าบัญชี

ที่มา: ผู้ใช้ไม่อยากฟาร์มบัญชีที่ได้การ์ดตัวนั้นไปแล้ว แต่ต้องไล่หาแล้วติ๊กออกทีละอัน
(คางุระมีอยู่ 7 จาก 115 บัญชี — หายากมากในลิสต์)

กติกาสำคัญที่เทสนี้ล็อกไว้:
1. 'ไม่มีการ์ดนี้' ต้อง *ไม่* รวมบัญชีที่ยังไม่มีข้อมูลการ์ดเลย เพราะ "ไม่มีข้อมูล"
   ไม่เท่ากับ "ไม่มีการ์ด" — ถ้าเหมารวมจะเผลอฟาร์มบัญชีที่จริง ๆ มีการ์ดนั้นอยู่
   แต่ยังไม่ได้ import ข้อมูลเข้ามา (ในไฟล์จริงมี 85 บัญชีที่ยังไม่มีข้อมูลการ์ด)
2. ปุ่ม 'ติ๊กทั้งหมดที่เห็น' ต้องใช้ตัวกรองตัวเดียวกับที่วาดลิสต์เป๊ะ ๆ
   ไม่งั้นจะไปโดนบัญชีที่ไม่ได้อยู่บนจอ
3. ข้อมูล cards ที่เพี้ยน (None / ไม่ใช่ list / สมาชิกไม่ใช่ dict) ต้องไม่ทำหน้าบัญชีล่ม
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web_app


def _card(key, label, qty=1, category="gintama"):
    return {"key": key, "label": label, "qty": qty, "category": category}


KAGURA = _card("Kagura", "คางุระ", 15)
AKASHI = _card("akashi", "อาคาชิ", 12, "standard")

ACCOUNTS = [
    # มีคางุระ
    {"email": "a@x.com", "name": "A", "group": "มอส", "checked": True,
     "cards": [KAGURA, AKASHI]},
    {"email": "b@x.com", "name": "B", "group": "จา", "checked": True,
     "cards": [dict(KAGURA, qty=2)]},
    # มีข้อมูลการ์ด แต่ไม่มีคางุระ
    {"email": "c@x.com", "name": "C", "group": "มอส", "checked": True,
     "cards": [AKASHI]},
    # ยังไม่มีข้อมูลการ์ด (4 แบบที่เจอได้จริงในไฟล์)
    {"email": "d@x.com", "name": "D", "group": "มอส", "checked": True},
    {"email": "e@x.com", "name": "E", "group": "มอส", "checked": True, "cards": []},
    {"email": "f@x.com", "name": "F", "group": "จา", "checked": True, "cards": None},
    {"email": "g@x.com", "name": "G", "group": "จา", "checked": True, "cards": "พัง"},
]


def _api(accts=None):
    api = web_app.Api()
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "accounts.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(accts if accts is not None else [dict(a) for a in ACCOUNTS],
                  f, ensure_ascii=False)
    api._accounts_path = lambda: path
    return api, path


def _emails(res):
    return sorted(a["email"] for g in res["groups"] for a in g["accounts"])


def _on_disk(path):
    with open(path, encoding="utf-8") as f:
        return {a["email"]: a for a in json.load(f)}


# ---------- ตัวกรอง ----------

def test_has_card_shows_only_owners():
    api, _ = _api()
    assert _emails(api.get_accounts_grouped(card="Kagura", card_mode="has")) == \
        ["a@x.com", "b@x.com"]


def test_not_card_excludes_accounts_without_card_data():
    """หัวใจของฟีเจอร์: 'ไม่มีคางุระ' = C ตัวเดียว ไม่ใช่ C+D+E+F+G

    D–G ยังไม่มีข้อมูลการ์ด จะเหมาว่าไม่มีคางุระไม่ได้"""
    api, _ = _api()
    assert _emails(api.get_accounts_grouped(card="Kagura", card_mode="not")) == ["c@x.com"]


def test_nodata_mode_lists_every_shape_of_missing_card_data():
    api, _ = _api()
    assert _emails(api.get_accounts_grouped(card_mode="nodata")) == \
        ["d@x.com", "e@x.com", "f@x.com", "g@x.com"]


def test_no_filter_keeps_old_behaviour():
    api, _ = _api()
    assert len(_emails(api.get_accounts_grouped())) == 7
    # เลือกโหมดไว้แต่ยังไม่เลือกการ์ด -> ต้องไม่กรองอะไรทิ้ง
    assert len(_emails(api.get_accounts_grouped(card="", card_mode="has"))) == 7


def test_search_and_card_filter_combine():
    api, _ = _api()
    res = api.get_accounts_grouped(search="มอส", card="Kagura", card_mode="has")
    assert _emails(res) == ["a@x.com"]          # b อยู่กลุ่ม 'จา' เลยตกไป


# ---------- ข้อมูลที่ส่งไปให้ UI ----------

def test_card_catalog_counts_accounts_and_ignores_current_filter():
    """ดรอปดาวน์ต้องเห็นการ์ดครบทุกตัวเสมอ ไม่งั้นพอเลือกคางุระแล้วจะกลับไปเลือกตัวอื่นไม่ได้"""
    api, _ = _api()
    res = api.get_accounts_grouped(card="Kagura", card_mode="has")
    cat = {c["key"]: c for c in res["cardNames"]}
    assert cat["Kagura"]["count"] == 2          # นับ 'จำนวนบัญชี' ไม่ใช่ qty (15+2)
    assert cat["Kagura"]["label"] == "คางุระ"
    assert "akashi" in cat                      # ยังอยู่ ทั้งที่กรองคางุระอยู่
    assert res["cardNames"][0]["key"] == "Kagura"   # เรียงตามจำนวนบัญชีมากไปน้อย


def test_counts_reported_for_the_toolbar():
    api, _ = _api()
    res = api.get_accounts_grouped(card="Kagura", card_mode="has")
    assert res["shownCount"] == 2
    assert res["accountsTotal"] == 7
    assert res["noCardDataCount"] == 4


def test_card_text_shown_under_each_account():
    api, _ = _api()
    res = api.get_accounts_grouped(card="Kagura", card_mode="has")
    a = next(x for g in res["groups"] for x in g["accounts"] if x["email"] == "a@x.com")
    assert a["cardText"] == "คางุระ ×15 · อาคาชิ ×12"
    d = api.get_accounts_grouped(card_mode="nodata")["groups"][0]["accounts"][0]
    assert d["cardText"] == ""


# ---------- ปุ่มติ๊ก / เอาติ๊กออกทั้งชุด ----------

def test_uncheck_filtered_only_touches_what_is_shown():
    api, path = _api()
    api.set_checked_filtered(False, card="Kagura", card_mode="has")
    disk = _on_disk(path)
    assert disk["a@x.com"]["checked"] is False
    assert disk["b@x.com"]["checked"] is False
    for e in ("c@x.com", "d@x.com", "e@x.com", "f@x.com", "g@x.com"):
        assert disk[e]["checked"] is True, e


def test_check_filtered_turns_them_back_on():
    api, path = _api()
    api.set_checked_filtered(False, card="Kagura", card_mode="has")
    api.set_checked_filtered(True, card="Kagura", card_mode="has")
    assert _on_disk(path)["a@x.com"]["checked"] is True


def test_bulk_set_respects_the_search_box_too():
    api, path = _api()
    api.set_checked_filtered(False, search="มอส", card="Kagura", card_mode="has")
    disk = _on_disk(path)
    assert disk["a@x.com"]["checked"] is False   # กลุ่มมอส + มีคางุระ
    assert disk["b@x.com"]["checked"] is True    # มีคางุระ แต่กลุ่ม 'จา' -> ไม่โดน


def test_bulk_set_never_drops_accounts_from_the_file():
    """ground rule: อย่าให้ path เขียนไฟล์ทำบัญชีหาย"""
    api, path = _api()
    api.set_checked_filtered(False, card="Kagura", card_mode="has")
    assert len(_on_disk(path)) == 7


def test_bulk_set_with_no_match_leaves_everything_alone():
    api, path = _api()
    api.set_checked_filtered(False, card="ไม่มีตัวนี้", card_mode="has")
    assert all(a["checked"] is True for a in _on_disk(path).values())


def test_returned_state_reflects_the_change_without_a_second_call():
    api, _ = _api()
    res = api.set_checked_filtered(False, card="Kagura", card_mode="has")
    assert all(a["checked"] is False for g in res["groups"] for a in g["accounts"])


# ---------- ข้อมูลเพี้ยน ----------

def test_malformed_card_entries_do_not_crash():
    api, _ = _api([
        {"email": "z@x.com", "checked": True, "cards": ["ไม่ใช่ dict", None, 5]},
        {"email": "y@x.com", "checked": True, "cards": [{"label": "ไม่มี key"}]},
        {"email": "w@x.com", "checked": True, "cards": [{"key": "Kagura", "qty": "เยอะ"}]},
    ])
    res = api.get_accounts_grouped()
    assert len(_emails(res)) == 3
    assert [c["key"] for c in res["cardNames"]] == ["Kagura"]
    w = next(x for g in res["groups"] for x in g["accounts"] if x["email"] == "w@x.com")
    assert w["cardText"] == "Kagura"            # ไม่มี label -> ใช้ key, qty ที่ไม่ใช่ int ถูกตัดทิ้ง
    assert _emails(api.get_accounts_grouped(card="Kagura", card_mode="has")) == ["w@x.com"]
