import json
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
