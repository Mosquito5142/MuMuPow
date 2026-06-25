import json
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


SAVE_WEB_GAME_EXPORT_SCHEMA = "mumupow-save-web-game-export"


def _clean_text(value):
    return str(value or "").strip()


def _normalize_email(value):
    return _clean_text(value).lower()


def _normalize_cards(cards):
    normalized = []
    total = 0
    for card in cards or []:
        key = _clean_text(card.get("key"))
        if not key:
            continue
        qty = int(card.get("qty") or 0)
        if qty <= 0:
            continue
        normalized.append(
            {
                "key": key,
                "label": _clean_text(card.get("label")) or key,
                "qty": qty,
                "category": _clean_text(card.get("category")) or "unknown",
            }
        )
        total += qty
    return normalized, total


def _validate_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("Save_Web_Game export must be a JSON object.")
    if payload.get("schema") != SAVE_WEB_GAME_EXPORT_SCHEMA:
        raise ValueError("Unsupported Save_Web_Game export schema.")
    if not isinstance(payload.get("accounts"), list):
        raise ValueError("Save_Web_Game export is missing accounts[].")


def _build_import_account(export_account, existing=None):
    email = _clean_text(export_account.get("email"))
    password = _clean_text(export_account.get("password"))
    if not email or not password or "@" not in email:
        return None

    cards, card_count = _normalize_cards(export_account.get("cards"))
    ingamename = _clean_text(export_account.get("ingamename"))
    title = _clean_text(export_account.get("title"))
    owner_name = _clean_text(export_account.get("ownerName"))
    group = _clean_text(export_account.get("group")) or owner_name or "Save_Web_Game"

    merged = dict(existing or {})
    merged.update(
        {
            "password": password,
            "name": ingamename or title or merged.get("name", ""),
            "group": group,
            "save_web_game_id": _clean_text(export_account.get("gameAccountId")),
            "save_web_game_title": title,
            "ownerName": owner_name,
            "ingamename": ingamename,
            "cards": cards,
            "card_count": card_count,
            "source": "Save_Web_Game",
        }
    )

    if existing:
        merged["email"] = existing.get("email") or email
        merged["checked"] = existing.get("checked", True)
    else:
        merged["email"] = email
        merged["checked"] = True

    return merged


def merge_save_web_game_accounts(existing_accounts, payload):
    _validate_payload(payload)

    merged_accounts = [dict(account) for account in existing_accounts]
    index_by_email = {
        _normalize_email(account.get("email")): idx
        for idx, account in enumerate(merged_accounts)
        if _normalize_email(account.get("email"))
    }
    stats = {"imported": 0, "updated": 0, "skipped": 0}

    for export_account in payload["accounts"]:
        if not isinstance(export_account, dict):
            stats["skipped"] += 1
            continue

        normalized_email = _normalize_email(export_account.get("email"))
        existing_idx = index_by_email.get(normalized_email)
        existing = merged_accounts[existing_idx] if existing_idx is not None else None
        account = _build_import_account(export_account, existing=existing)
        if account is None:
            stats["skipped"] += 1
            continue

        if existing_idx is None:
            index_by_email[normalized_email] = len(merged_accounts)
            merged_accounts.append(account)
            stats["imported"] += 1
        else:
            merged_accounts[existing_idx] = account
            stats["updated"] += 1

    return merged_accounts, stats


def import_save_web_game_accounts(export_path, accounts_path):
    export_path = Path(export_path)
    accounts_path = Path(accounts_path)

    payload = json.loads(export_path.read_text(encoding="utf-8"))
    if accounts_path.exists():
        existing_accounts = json.loads(accounts_path.read_text(encoding="utf-8") or "[]")
    else:
        existing_accounts = []

    merged_accounts, stats = merge_save_web_game_accounts(existing_accounts, payload)
    accounts_path.write_text(
        json.dumps(merged_accounts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return stats


def push_diamonds_to_web(base_url, updates, timeout=20):
    """ยิงอัปเดตจำนวนเพชรเข้าเว็บ Save_Web_Game ผ่าน PUT {base_url}/api/accounts (จับคู่ด้วย id)

    base_url: ที่อยู่เว็บ เช่น https://your-app.vercel.app (ตัด / ท้ายออกให้)
    updates: list ของ {"id": <web id>, "diamonds": int, "lastFarmDate": "YYYY-MM-DD" (ออปชัน)}
    คืน (results, stats) โดย results = {id: (ok: bool, msg: str)}, stats = {"sent","failed"}

    ใช้ PUT /api/accounts ซึ่งอัปเดต .eq("id") -> อัปเดตเฉพาะ id ที่มีจริง ไม่สร้างแถวขยะ
    (ต่างจาก /api/accounts/farming/batch ที่ upsert) ส่งแบบขนานเพื่อความเร็ว
    """
    base = (base_url or "").strip().rstrip("/")
    results = {}
    if not base:
        return results, {"sent": 0, "failed": 0}
    url = base + "/api/accounts"

    def _put_one(update):
        acc_id = str(update.get("id") or "").strip()
        if not acc_id:
            return None, (False, "no id")
        body = {"id": acc_id, "diamonds": int(update.get("diamonds") or 0)}
        if update.get("lastFarmDate"):
            body["lastFarmDate"] = update["lastFarmDate"]
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            try:
                parsed = json.loads(raw)
            except ValueError:
                parsed = {}
            if isinstance(parsed, dict) and parsed.get("success") is False:
                return acc_id, (False, str(parsed.get("error") or "update failed"))
            return acc_id, (True, "ok")
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", errors="ignore")[:200]
            except Exception:
                detail = ""
            return acc_id, (False, f"HTTP {e.code}: {detail}".strip())
        except urllib.error.URLError as e:
            return acc_id, (False, f"network: {e.reason}")
        except Exception as e:
            return acc_id, (False, str(e))

    valid = [u for u in updates if str(u.get("id") or "").strip()]
    if not valid:
        return results, {"sent": 0, "failed": 0}

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(valid)))) as ex:
        for acc_id, outcome in ex.map(_put_one, valid):
            if acc_id is not None:
                results[acc_id] = outcome

    sent = sum(1 for ok, _ in results.values() if ok)
    return results, {"sent": sent, "failed": len(results) - sent}


def fetch_web_accounts(base_url, timeout=20):
    """ดึงรายการบัญชีจากเว็บ Save_Web_Game ผ่าน GET {base_url}/api/accounts

    คืน list ของ dict บัญชีเว็บ (มี id, title, ingamename, owner_name ฯลฯ). raise ถ้าพลาด/URL ว่าง
    """
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("ยังไม่ได้ตั้ง URL เว็บ")
    req = urllib.request.Request(
        base + "/api/accounts", headers={"Accept": "application/json"}, method="GET"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="ignore"))
    if isinstance(data, dict):  # เผื่อ API ห่อเป็น {accounts:[...]} หรือ {data:[...]}
        data = data.get("accounts") or data.get("data") or []
    return data if isinstance(data, list) else []


def _norm_name(value):
    """ปรับชื่อให้เทียบกันง่าย: รวบช่องว่างซ้ำ ตัดหัวท้าย ตัวพิมพ์เล็ก"""
    return " ".join(str(value or "").split()).strip().lower()


def match_accounts_to_web(mumupow_accounts, web_accounts):
    """จับคู่บัญชี MuMuPow (เฉพาะที่ยังไม่มี save_web_game_id) กับบัญชีเว็บ ด้วยชื่อที่ตรงเป๊ะ
    (MuMuPow name/ingamename เทียบกับ web title ก่อน แล้วค่อย web ingamename) แบบ 1 ต่อ 1

    คืน list ของ proposal: {email, mumupow_name, web_id, web_title, web_owner, by}
    โดย by = 'title' หรือ 'ingamename'
    """
    by_title, by_ingame = {}, {}
    for w in web_accounts or []:
        wid = str(w.get("id") or "").strip()
        if not wid:
            continue
        t = _norm_name(w.get("title"))
        ig = _norm_name(w.get("ingamename"))
        if t:
            by_title.setdefault(t, []).append(w)
        if ig:
            by_ingame.setdefault(ig, []).append(w)

    used_ids = {
        str(a.get("save_web_game_id") or "").strip()
        for a in mumupow_accounts
        if str(a.get("save_web_game_id") or "").strip()
    }

    proposals = []
    for a in mumupow_accounts:
        if str(a.get("save_web_game_id") or "").strip():
            continue  # มี id แล้ว ข้าม
        keys = [k for k in (_norm_name(a.get("name")), _norm_name(a.get("ingamename"))) if k]
        matched, by = None, None
        for k in keys:
            for src, label in ((by_title, "title"), (by_ingame, "ingamename")):
                for w in src.get(k, []):
                    wid = str(w.get("id") or "").strip()
                    if wid and wid not in used_ids:
                        matched, by = w, label
                        break
                if matched:
                    break
            if matched:
                break
        if matched:
            wid = str(matched.get("id")).strip()
            used_ids.add(wid)
            proposals.append({
                "email": a.get("email", ""),
                "mumupow_name": a.get("name") or a.get("ingamename") or a.get("email", ""),
                "web_id": wid,
                "web_title": matched.get("title", ""),
                "web_owner": matched.get("owner_name") or matched.get("ownerName") or "",
                "by": by,
            })
    return proposals
