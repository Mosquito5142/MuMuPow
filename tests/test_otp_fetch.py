"""เทสดึง OTP: คุยตรง Microsoft เป็นหลัก · read-mail.me เป็น fallback · ปุ่มเทสทีละบัญชี

ที่มา: read-mail.me (คนกลาง) ล่ม → ดึง OTP ไม่ได้ทุกบัญชีพร้อมกัน ทั้งที่ refresh_token+client_id
ยิงตรงหา Microsoft เองได้ ย้ายมาคุยตรงเป็นหลัก เก็บ read-mail ไว้สำรอง

กติกาที่ล็อกไว้:
1. Microsoft สำเร็จ → ไม่แตะ read-mail เลย
2. token ตาย (Microsoft ปฏิเสธ) → ไม่ต้องลอง read-mail (token เดียวกัน) รายงาน token_dead
3. Microsoft ต่อไม่ได้ชั่วคราว → fall back read-mail.me
4. บัญชีไม่มี token → ข้าม Microsoft ไป IMAP เหมือนเดิม (ของเก่าไม่พัง — ground rule #1)

mock urllib ทั้งหมด ไม่ยิงเน็ตจริง
"""
import io
import json
import os
import sys
import tempfile
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import macro_runner as M
import web_app


class FakeResp:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(code, err="invalid_grant"):
    body = io.BytesIO(json.dumps({"error": err}).encode("utf-8"))
    return urllib.error.HTTPError("url", code, "err", {}, body)


TOKEN_URL_HINT = "oauth2"          # endpoint แลก token ของ Microsoft
LIVE_URL_HINT = "oauth20_token"    # endpoint สำรอง login.live.com
GRAPH_HINT = "graph.microsoft.com/v1.0"


def _install(monkeypatch, handler):
    """monkeypatch urllib.request.urlopen ในโมดูล macro_runner ให้เรียก handler(url) -> FakeResp/raise"""
    def fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req.get_full_url()
        return handler(url)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)


LOG = lambda t, k="info": None


# ---------- 1. Microsoft สำเร็จ ----------

def test_microsoft_success_never_calls_readmail(monkeypatch):
    calls = {"readmail": 0}

    def handler(url):
        if "read-mail.me" in url:
            calls["readmail"] += 1
            return FakeResp({"status": True, "messages": [{"_body": "code 999999"}]})
        if TOKEN_URL_HINT in url or LIVE_URL_HINT in url:
            return FakeResp({"access_token": "ATOKEN"})
        if GRAPH_HINT in url:
            return FakeResp({"value": [{"subject": "Verify", "body": {"content": "รหัสคือ 123456 นะ"}}]})
        raise AssertionError("unexpected url " + url)

    _install(monkeypatch, handler)
    code = M.fetch_otp_from_mail(LOG, "a@x.com", "pw", None, "RTOKEN", "CID")
    assert code == "123456"
    assert calls["readmail"] == 0, "Microsoft สำเร็จแล้วต้องไม่แตะ read-mail"


def test_microsoft_reads_body_content_field(monkeypatch):
    def handler(url):
        if TOKEN_URL_HINT in url or LIVE_URL_HINT in url:
            return FakeResp({"access_token": "ATOKEN"})
        if GRAPH_HINT in url:
            return FakeResp({"value": [{"body": {"content": "Your code: 424242"}}]})
        raise AssertionError(url)
    _install(monkeypatch, handler)
    code, reason = M._fetch_otp_via_microsoft(LOG, "a@x.com", "RT", "CID", r"\b\d{6}\b")
    assert code == "424242" and reason == "ok"


# ---------- 2. token ตาย ----------

def test_token_dead_does_not_fall_back_to_readmail(monkeypatch):
    calls = {"readmail": 0}

    def handler(url):
        if "read-mail.me" in url:
            calls["readmail"] += 1
            return FakeResp({"status": True, "messages": [{"_body": "code 999999"}]})
        if TOKEN_URL_HINT in url or LIVE_URL_HINT in url:
            raise _http_error(400, "invalid_grant")   # Microsoft ปฏิเสธทุก endpoint/scope
        raise AssertionError(url)

    _install(monkeypatch, handler)
    code = M.fetch_otp_from_mail(LOG, "a@x.com", "pw", None, "RT", "CID")
    assert code is None
    assert calls["readmail"] == 0, "token ตายแล้วไม่ควรลอง read-mail (token เดียวกัน)"


def test_get_access_token_reports_token_dead(monkeypatch):
    def handler(url):
        raise _http_error(400, "unauthorized_client")
    _install(monkeypatch, handler)
    tok, reason = M._ms_get_access_token(LOG, "a@x.com", "RT", "CID")
    assert tok is None and reason == "token_dead"


# ---------- 3. Microsoft network fail → read-mail fallback ----------

def test_network_fail_falls_back_to_readmail(monkeypatch):
    def handler(url):
        if "read-mail.me" in url:
            return FakeResp({"status": True, "messages": [{"_body": "OTP 777888"}]})
        if TOKEN_URL_HINT in url or LIVE_URL_HINT in url:
            raise OSError("connection refused")     # ต่อ Microsoft ไม่ได้ชั่วคราว
        raise AssertionError(url)
    _install(monkeypatch, handler)
    code = M.fetch_otp_from_mail(LOG, "a@x.com", "pw", None, "RT", "CID")
    assert code == "777888"


def test_login_ok_but_no_otp_in_inbox(monkeypatch):
    def handler(url):
        if TOKEN_URL_HINT in url or LIVE_URL_HINT in url:
            return FakeResp({"access_token": "AT"})
        if GRAPH_HINT in url:
            return FakeResp({"value": [{"body": {"content": "welcome, no digits here"}}]})
        raise AssertionError(url)
    _install(monkeypatch, handler)
    code, reason = M._fetch_otp_via_microsoft(LOG, "a@x.com", "RT", "CID", r"\b\d{6}\b")
    assert code is None and reason == "no_otp_yet"


# ---------- 4. ไม่มี token → ข้าม Microsoft (ของเก่าไม่พัง) ----------

def test_no_token_skips_microsoft_entirely(monkeypatch):
    touched = {"ms": 0}

    def fake_ms(*a, **k):
        touched["ms"] += 1
        return None, "network"
    monkeypatch.setattr(M, "_fetch_otp_via_microsoft", fake_ms)
    # IMAP จะ fail เพราะไม่มี network จริง แต่เราแค่ยืนยันว่าไม่แตะ Microsoft
    monkeypatch.setattr(M, "_fetch_otp_via_readmail_api", lambda *a, **k: None)
    M.fetch_otp_from_mail(LOG, "a@x.com", "pw", None, "", "")
    assert touched["ms"] == 0, "บัญชีไม่มี token ต้องไม่เรียก Microsoft"


def test_default_pattern_is_six_digits(monkeypatch):
    def handler(url):
        if TOKEN_URL_HINT in url or LIVE_URL_HINT in url:
            return FakeResp({"access_token": "AT"})
        if GRAPH_HINT in url:
            return FakeResp({"value": [{"body": {"content": "ตัวเลข 000111 ในเมล"}}]})
        raise AssertionError(url)
    _install(monkeypatch, handler)
    # pattern ว่าง -> ต้อง default เป็น \b\d{6}\b
    code = M.fetch_otp_from_mail(LOG, "a@x.com", "pw", "", "RT", "CID")
    assert code == "000111"


# ---------- 6-7. ปุ่มเทสฝั่ง Api ----------

def _api(accts):
    api = web_app.Api()
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "accounts.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(accts, f, ensure_ascii=False)
    api._accounts_path = lambda: path
    return api


def test_button_reports_success_and_source(monkeypatch):
    api = _api([{"email": "a@x.com", "refresh_token": "RT", "client_id": "CID"}])

    def handler(url):
        if TOKEN_URL_HINT in url or LIVE_URL_HINT in url:
            return FakeResp({"access_token": "AT"})
        if GRAPH_HINT in url:
            return FakeResp({"value": [{"body": {"content": "code 246810"}}]})
        raise AssertionError(url)
    _install(monkeypatch, handler)
    r = api.test_otp_credentials("a@x.com")
    assert r["ok"] and r["code"] == "246810" and r["source"] == "microsoft"


def test_button_pulls_client_id_from_file_when_form_omits_it(monkeypatch):
    """ฟอร์มไม่มีช่อง client_id → ต้องดึงจาก accounts.json ตาม email"""
    api = _api([{"email": "a@x.com", "password": "pw", "refresh_token": "RT", "client_id": "CID_FROM_FILE"}])
    seen = {}

    def fake_ms(log, email, rt, cid, pat):
        seen["cid"] = cid
        return "135790", "ok"
    # test_otp_credentials import จาก macro_runner ตอนเรียก → patch ที่ M ได้ผลทันที
    monkeypatch.setattr(M, "_fetch_otp_via_microsoft", fake_ms)
    r = api.test_otp_credentials("a@x.com", "", "", "", "")   # ไม่ส่ง client_id มา
    assert seen["cid"] == "CID_FROM_FILE"
    assert r["ok"] and r["code"] == "135790"


def test_button_distinguishes_token_dead(monkeypatch):
    api = _api([{"email": "a@x.com", "refresh_token": "RT", "client_id": "CID"}])
    monkeypatch.setattr(M, "_fetch_otp_via_microsoft", lambda *a, **k: (None, "token_dead"))
    monkeypatch.setattr(M, "_fetch_otp_via_readmail_api", lambda *a, **k: None)
    r = api.test_otp_credentials("a@x.com")
    assert not r["ok"] and "Microsoft ปฏิเสธ" in r["detail"]


def test_button_distinguishes_no_otp_yet(monkeypatch):
    api = _api([{"email": "a@x.com", "refresh_token": "RT", "client_id": "CID"}])
    monkeypatch.setattr(M, "_fetch_otp_via_microsoft", lambda *a, **k: (None, "no_otp_yet"))
    monkeypatch.setattr(M, "_fetch_otp_via_readmail_api", lambda *a, **k: None)
    r = api.test_otp_credentials("a@x.com")
    assert not r["ok"] and "ยังไม่มี OTP" in r["detail"]


def test_button_needs_email():
    api = _api([])
    r = api.test_otp_credentials("")
    assert not r["ok"] and "อีเมล" in r["detail"]
