# Save_Web_Game Export Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a file-based bridge so `Save_Web_Game` can export selected account credentials and character/card metadata, and `MuMupow` can import them into its local account queue.

**Architecture:** Add a typed exporter in `Save_Web_Game` that produces a versioned JSON envelope with plaintext credentials only at download time. Add a pure importer in `MuMupow` that validates the envelope and merges accounts by email, then wire it into the Accounts tab with a file picker.

**Tech Stack:** Next.js 16, React 19, TypeScript, Vitest, Supabase client patterns already in `Save_Web_Game`; Python 3, Tkinter, unittest/pytest in `MuMupow`.

---

## File Structure

### Save_Web_Game

- Create `lib/mumupow-export.ts`: pure mapping, decrypting, and export-shape builder.
- Create `lib/mumupow-export.test.ts`: unit coverage for schema, default PIN decrypt, invalid PIN failure, and card metadata mapping.
- Modify `app/admin/manage/page.tsx`: add selected-account state, export controls, and JSON download.

### MuMupow

- Create `save_web_game_import.py`: pure JSON validation and merge helpers.
- Create `tests/test_save_web_game_import.py`: unit coverage for validation, create, update, duplicate-row, and metadata behavior.
- Modify `gui.py`: import helper, add Accounts-tab button, file picker, and summary display for imported metadata.
- Modify `tests/test_gui_helpers.py`: adjust account-summary expectations for owner/card metadata.

---

## Task 1: Save_Web_Game Export Helper

**Files:**
- Create: `C:\Users\PC\Desktop\CODE\Save_Web_Game\lib\mumupow-export.ts`
- Create: `C:\Users\PC\Desktop\CODE\Save_Web_Game\lib\mumupow-export.test.ts`

- [ ] **Step 1: Write failing exporter tests**

Create `lib/mumupow-export.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { encryptData } from "./crypto-utils";
import {
  buildMuMupowExport,
  type MuMupowExportAccountInput,
} from "./mumupow-export";

const account = {
  id: "acc-1",
  title: "Kuroko Main",
  username: encryptData("player@example.com", "1234"),
  password: encryptData("Secret123", "1234"),
  ownerName: "Owner A",
  ingamename: "PlayerOne",
};

const cards = [
  {
    account_id: "acc-1",
    card_type: "kuroko",
    quantity: 2,
    sellable: true,
  },
  {
    account_id: "acc-1",
    card_type: "kagami",
    quantity: 0,
    sellable: false,
  },
];

const definitions = [
  { key: "kuroko", label: "Kuroko", category: "normal" },
  { key: "kagami", label: "Kagami", category: "normal" },
];

describe("buildMuMupowExport", () => {
  it("builds a versioned MuMupow export with decrypted credentials and card metadata", () => {
    const result = buildMuMupowExport({
      accounts: [account],
      cardsByAccountId: { "acc-1": cards },
      definitions,
      pin: "1234",
      exportedAt: "2026-06-18T00:00:00.000Z",
    });

    expect(result.export.accounts).toEqual([
      {
        gameAccountId: "acc-1",
        title: "Kuroko Main",
        email: "player@example.com",
        password: "Secret123",
        ownerName: "Owner A",
        ingamename: "PlayerOne",
        group: "Owner A",
        cards: [
          { key: "kuroko", label: "Kuroko", qty: 2, category: "normal" },
        ],
      },
    ]);
    expect(result.skipped).toEqual([]);
    expect(result.export.schema).toBe("mumupow-save-web-game-export");
    expect(result.export.version).toBe(1);
  });

  it("skips accounts that cannot be decrypted with the provided pin", () => {
    const result = buildMuMupowExport({
      accounts: [account],
      cardsByAccountId: { "acc-1": cards },
      definitions,
      pin: "9999",
      exportedAt: "2026-06-18T00:00:00.000Z",
    });

    expect(result.export.accounts).toEqual([]);
    expect(result.skipped).toEqual([
      { id: "acc-1", title: "Kuroko Main", reason: "decrypt_failed" },
    ]);
  });

  it("uses Save_Web_Game as group when owner is blank", () => {
    const input: MuMupowExportAccountInput = {
      ...account,
      ownerName: "",
    };

    const result = buildMuMupowExport({
      accounts: [input],
      cardsByAccountId: { "acc-1": [] },
      definitions,
      pin: "1234",
      exportedAt: "2026-06-18T00:00:00.000Z",
    });

    expect(result.export.accounts[0].group).toBe("Save_Web_Game");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run from `C:\Users\PC\Desktop\CODE\Save_Web_Game`:

```powershell
npm test -- lib/mumupow-export.test.ts
```

Expected: FAIL because `./mumupow-export` does not exist.

- [ ] **Step 3: Implement exporter**

Create `lib/mumupow-export.ts`:

```ts
import { decryptData } from "./crypto-utils";

export const MUMUPOW_EXPORT_SCHEMA = "mumupow-save-web-game-export";
export const MUMUPOW_EXPORT_VERSION = 1;

export type MuMupowExportAccountInput = {
  id: string;
  title?: string;
  username?: string;
  password?: string;
  ownerName?: string;
  ingamename?: string;
};

export type MuMupowExportCardInput = {
  account_id: string;
  card_type: string;
  quantity?: number;
  sellable?: boolean;
};

export type MuMupowExportDefinitionInput = {
  key: string;
  label?: string;
  category?: string;
};

export type MuMupowExportCard = {
  key: string;
  label: string;
  qty: number;
  category: string;
};

export type MuMupowExportAccount = {
  gameAccountId: string;
  title: string;
  email: string;
  password: string;
  ownerName: string;
  ingamename: string;
  group: string;
  cards: MuMupowExportCard[];
};

export type MuMupowExportPayload = {
  schema: typeof MUMUPOW_EXPORT_SCHEMA;
  version: typeof MUMUPOW_EXPORT_VERSION;
  exportedAt: string;
  source: {
    app: "Save_Web_Game";
  };
  accounts: MuMupowExportAccount[];
};

export type MuMupowExportSkipped = {
  id: string;
  title: string;
  reason: "decrypt_failed" | "missing_credentials";
};

export function buildMuMupowExport(options: {
  accounts: MuMupowExportAccountInput[];
  cardsByAccountId: Record<string, MuMupowExportCardInput[]>;
  definitions: MuMupowExportDefinitionInput[];
  pin: string;
  exportedAt?: string;
}): { export: MuMupowExportPayload; skipped: MuMupowExportSkipped[] } {
  const definitionMap = new Map(
    options.definitions.map((definition) => [definition.key, definition]),
  );
  const skipped: MuMupowExportSkipped[] = [];
  const exportedAccounts: MuMupowExportAccount[] = [];

  for (const account of options.accounts) {
    const title = account.title || "";
    const email = decryptData(account.username || "", options.pin).trim();
    const password = decryptData(account.password || "", options.pin).trim();

    if (!email || !password) {
      skipped.push({
        id: account.id,
        title,
        reason: account.username || account.password ? "decrypt_failed" : "missing_credentials",
      });
      continue;
    }

    const cards = (options.cardsByAccountId[account.id] || [])
      .filter((card) => Number(card.quantity || 0) > 0)
      .map((card) => {
        const definition = definitionMap.get(card.card_type);
        return {
          key: card.card_type,
          label: definition?.label || card.card_type,
          qty: Number(card.quantity || 0),
          category: definition?.category || "unknown",
        };
      });

    const ownerName = (account.ownerName || "").trim();
    const ingamename = (account.ingamename || "").trim();

    exportedAccounts.push({
      gameAccountId: account.id,
      title,
      email,
      password,
      ownerName,
      ingamename,
      group: ownerName || "Save_Web_Game",
      cards,
    });
  }

  return {
    export: {
      schema: MUMUPOW_EXPORT_SCHEMA,
      version: MUMUPOW_EXPORT_VERSION,
      exportedAt: options.exportedAt || new Date().toISOString(),
      source: { app: "Save_Web_Game" },
      accounts: exportedAccounts,
    },
    skipped,
  };
}
```

- [ ] **Step 4: Run exporter tests**

Run:

```powershell
npm test -- lib/mumupow-export.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit Save_Web_Game exporter**

Run:

```powershell
git add -- lib/mumupow-export.ts lib/mumupow-export.test.ts
git commit -m "feat: add MuMupow export builder"
```

---

## Task 2: Save_Web_Game Export UI

**Files:**
- Modify: `C:\Users\PC\Desktop\CODE\Save_Web_Game\app\admin\manage\page.tsx`

- [ ] **Step 1: Add imports**

Add `buildMuMupowExport` to the imports:

```ts
import { buildMuMupowExport } from "@/lib/mumupow-export";
```

- [ ] **Step 2: Add export state near existing component state**

Inside `ManageAccountsPage`, near existing `useState` calls, add:

```ts
  const [selectedExportIds, setSelectedExportIds] = useState<Set<string>>(new Set());
  const [exportPin, setExportPin] = useState("1234");
  const [exportingMuMupow, setExportingMuMupow] = useState(false);
```

- [ ] **Step 3: Add helper functions inside the component**

Add these functions after `fetchAccounts`:

```ts
  const toggleExportSelection = (id: string) => {
    setSelectedExportIds((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const selectFilteredForExport = () => {
    setSelectedExportIds(new Set(filteredAccounts.map((account) => account.id)));
  };

  const clearExportSelection = () => {
    setSelectedExportIds(new Set());
  };

  const downloadJson = (filename: string, payload: unknown) => {
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  const exportSelectedToMuMupow = async () => {
    const selectedAccounts = accounts.filter((account) => selectedExportIds.has(account.id));
    if (selectedAccounts.length === 0) {
      alert("เลือกอย่างน้อย 1 รหัสก่อน export");
      return;
    }

    setExportingMuMupow(true);
    try {
      const [cardsResponses, definitionsResponse] = await Promise.all([
        Promise.all(
          selectedAccounts.map(async (account) => {
            const response = await fetch(`/api/cards?account_id=${encodeURIComponent(account.id)}`);
            const cards = response.ok ? await response.json() : [];
            return [account.id, Array.isArray(cards) ? cards : []] as const;
          }),
        ),
        fetch("/api/cards/definitions"),
      ]);

      const definitions = definitionsResponse.ok ? await definitionsResponse.json() : [];
      const cardsByAccountId = Object.fromEntries(cardsResponses);
      const result = buildMuMupowExport({
        accounts: selectedAccounts,
        cardsByAccountId,
        definitions: Array.isArray(definitions) ? definitions : [],
        pin: exportPin || "1234",
      });

      if (result.export.accounts.length === 0) {
        alert("ไม่มีรหัสที่ export ได้ ตรวจสอบ PIN หรือข้อมูล username/password");
        return;
      }

      if (result.skipped.length > 0) {
        const proceed = confirm(
          `Export ได้ ${result.export.accounts.length} รหัส และข้าม ${result.skipped.length} รหัส ต้องการดาวน์โหลดต่อไหม?`,
        );
        if (!proceed) return;
      }

      downloadJson(
        `mumupow-save-web-game-${new Date().toISOString().slice(0, 10)}.json`,
        result.export,
      );
    } finally {
      setExportingMuMupow(false);
    }
  };
```

- [ ] **Step 4: Add export controls to the account management UI**

Place this block near the account count/search controls above the account list:

```tsx
              <div className="mb-4 rounded-lg border border-primary/20 bg-base-200/60 p-3">
                <div className="flex flex-wrap items-end gap-3">
                  <div>
                    <p className="text-[10px] font-black uppercase tracking-[0.25em] text-primary">
                      Export to MuMupow
                    </p>
                    <p className="mt-1 text-[11px] text-muted">
                      เลือก ID แล้วดาวน์โหลดไฟล์ JSON สำหรับนำเข้า MuMupow
                    </p>
                  </div>
                  <input
                    className="input input-bordered input-sm w-24"
                    type="password"
                    value={exportPin}
                    onChange={(event) => setExportPin(event.target.value)}
                    placeholder="PIN"
                  />
                  <button className="btn btn-sm" type="button" onClick={selectFilteredForExport}>
                    เลือกที่กรองอยู่
                  </button>
                  <button className="btn btn-sm btn-ghost" type="button" onClick={clearExportSelection}>
                    ล้างเลือก
                  </button>
                  <button
                    className="btn btn-sm btn-primary"
                    type="button"
                    onClick={exportSelectedToMuMupow}
                    disabled={exportingMuMupow || selectedExportIds.size === 0}
                  >
                    {exportingMuMupow
                      ? "กำลัง export..."
                      : `Export ${selectedExportIds.size} ID`}
                  </button>
                </div>
              </div>
```

- [ ] **Step 5: Add per-account selection checkbox**

Inside the account card/table row where each `acc` is rendered, add a checkbox close to the account title:

```tsx
                      <input
                        type="checkbox"
                        className="checkbox checkbox-xs checkbox-primary mr-2"
                        checked={selectedExportIds.has(acc.id)}
                        onChange={() => toggleExportSelection(acc.id)}
                        onClick={(event) => event.stopPropagation()}
                        aria-label={`Export ${acc.title || acc.id} to MuMupow`}
                      />
```

If there are desktop and mobile render paths, add the same checkbox to both locations where `filteredAccounts.map((acc) => ...)` renders account rows.

- [ ] **Step 6: Run Save_Web_Game tests**

Run:

```powershell
npm test -- lib/mumupow-export.test.ts
npm test
```

Expected: PASS.

- [ ] **Step 7: Commit Save_Web_Game UI**

Run:

```powershell
git add -- app/admin/manage/page.tsx
git commit -m "feat: export accounts for MuMupow"
```

---

## Task 3: MuMupow Import Helper

**Files:**
- Create: `C:\Users\PC\Desktop\CODE\MuMupow\save_web_game_import.py`
- Create: `C:\Users\PC\Desktop\CODE\MuMupow\tests\test_save_web_game_import.py`

- [ ] **Step 1: Write failing importer tests**

Create `tests/test_save_web_game_import.py`:

```python
import pytest

from save_web_game_import import import_save_web_game_accounts


def export_payload(accounts):
    return {
        "schema": "mumupow-save-web-game-export",
        "version": 1,
        "exportedAt": "2026-06-18T00:00:00.000Z",
        "source": {"app": "Save_Web_Game"},
        "accounts": accounts,
    }


def test_rejects_wrong_schema():
    with pytest.raises(ValueError, match="Invalid Save_Web_Game export"):
        import_save_web_game_accounts([], {"schema": "wrong", "version": 1, "accounts": []})


def test_import_creates_new_accounts_with_metadata():
    payload = export_payload([
        {
            "gameAccountId": "acc-1",
            "title": "Main",
            "email": "player@example.com",
            "password": "Secret123",
            "ownerName": "Owner A",
            "ingamename": "PlayerOne",
            "group": "Owner A",
            "cards": [{"key": "kuroko", "label": "Kuroko", "qty": 2, "category": "normal"}],
        }
    ])

    accounts, summary = import_save_web_game_accounts([], payload)

    assert summary == {"created": 1, "updated": 0, "skipped": 0}
    assert accounts == [
        {
            "email": "player@example.com",
            "password": "Secret123",
            "checked": True,
            "group": "Owner A",
            "name": "PlayerOne",
            "source": "Save_Web_Game",
            "gameAccountId": "acc-1",
            "ownerName": "Owner A",
            "ingamename": "PlayerOne",
            "title": "Main",
            "cards": [{"key": "kuroko", "label": "Kuroko", "qty": 2, "category": "normal"}],
        }
    ]


def test_import_updates_existing_by_email_and_preserves_checked():
    existing = [
        {
            "email": "player@example.com",
            "password": "Old",
            "checked": False,
            "group": "Old",
        }
    ]
    payload = export_payload([
        {
            "gameAccountId": "acc-1",
            "title": "Main",
            "email": "player@example.com",
            "password": "Secret123",
            "ownerName": "Owner A",
            "ingamename": "PlayerOne",
            "group": "Owner A",
            "cards": [],
        }
    ])

    accounts, summary = import_save_web_game_accounts(existing, payload)

    assert summary == {"created": 0, "updated": 1, "skipped": 0}
    assert accounts[0]["checked"] is False
    assert accounts[0]["password"] == "Secret123"
    assert accounts[0]["group"] == "Owner A"
    assert accounts[0]["gameAccountId"] == "acc-1"


def test_import_skips_rows_without_email_or_password():
    payload = export_payload([
        {"email": "", "password": "Secret123"},
        {"email": "player@example.com", "password": ""},
    ])

    accounts, summary = import_save_web_game_accounts([], payload)

    assert accounts == []
    assert summary == {"created": 0, "updated": 0, "skipped": 2}


def test_duplicate_rows_last_wins():
    payload = export_payload([
        {"email": "player@example.com", "password": "First", "title": "First"},
        {"email": "player@example.com", "password": "Second", "title": "Second"},
    ])

    accounts, summary = import_save_web_game_accounts([], payload)

    assert summary == {"created": 1, "updated": 1, "skipped": 0}
    assert accounts[0]["password"] == "Second"
    assert accounts[0]["title"] == "Second"
```

- [ ] **Step 2: Run test to verify it fails**

Run from `C:\Users\PC\Desktop\CODE\MuMupow`:

```powershell
python -m pytest tests/test_save_web_game_import.py -q
```

Expected: FAIL because `save_web_game_import` does not exist.

- [ ] **Step 3: Implement importer**

Create `save_web_game_import.py`:

```python
MUMUPOW_EXPORT_SCHEMA = "mumupow-save-web-game-export"
MUMUPOW_EXPORT_VERSION = 1


def _clean(value):
    return str(value or "").strip()


def _normalize_export_account(row, existing_checked=True):
    email = _clean(row.get("email"))
    password = _clean(row.get("password"))
    if not email or not password:
        return None

    ingamename = _clean(row.get("ingamename"))
    title = _clean(row.get("title"))
    owner_name = _clean(row.get("ownerName"))
    group = _clean(row.get("group")) or owner_name or "Save_Web_Game"

    return {
        "email": email,
        "password": password,
        "checked": existing_checked,
        "group": group,
        "name": ingamename or title or email,
        "source": "Save_Web_Game",
        "gameAccountId": _clean(row.get("gameAccountId")),
        "ownerName": owner_name,
        "ingamename": ingamename,
        "title": title,
        "cards": row.get("cards") if isinstance(row.get("cards"), list) else [],
    }


def import_save_web_game_accounts(existing_accounts, payload):
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != MUMUPOW_EXPORT_SCHEMA
        or payload.get("version") != MUMUPOW_EXPORT_VERSION
    ):
        raise ValueError("Invalid Save_Web_Game export")

    exported_rows = payload.get("accounts")
    if not isinstance(exported_rows, list):
        raise ValueError("Invalid Save_Web_Game export accounts")

    merged = [dict(account) for account in existing_accounts]
    by_email = {
        _clean(account.get("email")).lower(): idx
        for idx, account in enumerate(merged)
        if _clean(account.get("email"))
    }
    summary = {"created": 0, "updated": 0, "skipped": 0}

    for row in exported_rows:
        if not isinstance(row, dict):
            summary["skipped"] += 1
            continue

        email_key = _clean(row.get("email")).lower()
        existing_idx = by_email.get(email_key)
        existing_checked = (
            bool(merged[existing_idx].get("checked", True))
            if existing_idx is not None
            else True
        )
        normalized = _normalize_export_account(row, existing_checked)
        if normalized is None:
            summary["skipped"] += 1
            continue

        if existing_idx is None:
            by_email[email_key] = len(merged)
            merged.append(normalized)
            summary["created"] += 1
        else:
            updated = dict(merged[existing_idx])
            updated.update(normalized)
            merged[existing_idx] = updated
            summary["updated"] += 1

    return merged, summary
```

- [ ] **Step 4: Run importer tests**

Run:

```powershell
python -m pytest tests/test_save_web_game_import.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit MuMupow importer**

Run:

```powershell
git add -- save_web_game_import.py tests/test_save_web_game_import.py
git commit -m "feat: import Save Web Game accounts"
```

---

## Task 4: MuMupow Import UI

**Files:**
- Modify: `C:\Users\PC\Desktop\CODE\MuMupow\gui.py`
- Modify: `C:\Users\PC\Desktop\CODE\MuMupow\tests\test_gui_helpers.py`

- [ ] **Step 1: Add imports**

In `gui.py`, update imports:

```python
from tkinter import ttk, messagebox, filedialog
from save_web_game_import import import_save_web_game_accounts
```

- [ ] **Step 2: Update account summary metadata display**

Replace `build_account_summary` with:

```python
def build_account_summary(account):
    name = account.get("ingamename") or account.get("name") or account.get("title") or "-"
    email = account.get("email") or "-"
    group = account.get("group") or "ทั่วไป"
    owner = account.get("ownerName") or ""
    cards = account.get("cards") if isinstance(account.get("cards"), list) else []
    card_text = f"{len(cards)} cards" if cards else ""
    otp = "OTP" if account.get("refresh_token") else ""
    extra = " ".join(part for part in (owner, card_text, otp) if part)
    return f"{name:<16}  {email:<32}  {group:<12}  {extra}"
```

- [ ] **Step 3: Update summary tests**

Add this test to `tests/test_gui_helpers.py`:

```python
    def test_account_summary_prefers_save_web_game_metadata(self):
        summary = build_account_summary(
            {
                "email": "player@example.com",
                "name": "Old Name",
                "ingamename": "PlayerOne",
                "group": "Owner A",
                "ownerName": "Owner A",
                "cards": [{"key": "kuroko"}, {"key": "kagami"}],
            }
        )

        self.assertIn("PlayerOne", summary)
        self.assertIn("Owner A", summary)
        self.assertIn("2 cards", summary)
```

- [ ] **Step 4: Add import button in Accounts tab**

In `build_accounts_tab`, after the existing batch import button:

```python
        self.save_web_game_import_btn = ModernButton(
            add_box,
            text="นำเข้าจาก Save_Web_Game",
            command=self.import_save_web_game_file,
            variant="warning",
        )
        self.save_web_game_import_btn.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(8, 0))
```

If edit mode changes the existing `batch_import_btn` grid row, keep this new button hidden or always in row 9 while editing so it does not overlap existing cancel controls.

- [ ] **Step 5: Add import method**

Add this method near `open_batch_import_dialog`:

```python
    def import_save_web_game_file(self):
        path = filedialog.askopenfilename(
            title="เลือกไฟล์ Export จาก Save_Web_Game",
            filetypes=[("Save_Web_Game Export", "*.json"), ("JSON", "*.json"), ("All Files", "*.*")],
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as file:
                payload = json.load(file)

            merged_accounts, summary = import_save_web_game_accounts(self.accounts, payload)
        except Exception as exc:
            messagebox.showerror("นำเข้าไม่สำเร็จ", f"ไฟล์ Save_Web_Game ไม่ถูกต้อง:\n{exc}")
            return

        if summary["created"] == 0 and summary["updated"] == 0:
            messagebox.showwarning("ไม่มีข้อมูลนำเข้า", "ไม่พบ account ที่นำเข้าได้ในไฟล์นี้")
            return

        self.accounts = merged_accounts
        self.save_accounts()
        self.refresh_accounts_ui()
        self.write_log(
            f"นำเข้าจาก Save_Web_Game สำเร็จ: เพิ่ม {summary['created']} / อัปเดต {summary['updated']} / ข้าม {summary['skipped']}",
            "success",
        )
        messagebox.showinfo(
            "นำเข้าสำเร็จ",
            f"เพิ่ม {summary['created']} บัญชี\nอัปเดต {summary['updated']} บัญชี\nข้าม {summary['skipped']} รายการ",
        )
```

- [ ] **Step 6: Run MuMupow tests**

Run:

```powershell
python -m py_compile gui.py save_web_game_import.py
python -m pytest tests/test_save_web_game_import.py tests/test_gui_helpers.py -q
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 7: Commit MuMupow UI**

Run:

```powershell
git add -- gui.py tests/test_gui_helpers.py
git commit -m "feat: import Save Web Game export in UI"
```

---

## Task 5: Cross-Repo Manual Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run Save_Web_Game verification**

Run from `C:\Users\PC\Desktop\CODE\Save_Web_Game`:

```powershell
npm test
npm run build
```

Expected: PASS.

- [ ] **Step 2: Run MuMupow verification**

Run from `C:\Users\PC\Desktop\CODE\MuMupow`:

```powershell
python -m py_compile gui.py quick_builder.py save_web_game_import.py
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 3: Manual bridge smoke test**

Use the web UI:

1. Open `Save_Web_Game`.
2. Go to account management.
3. Select one or two test accounts.
4. Export with PIN `1234`.
5. Confirm the downloaded JSON has schema `mumupow-save-web-game-export`.

Use MuMupow:

1. Open Accounts tab.
2. Click `นำเข้าจาก Save_Web_Game`.
3. Select the exported JSON.
4. Confirm the account appears or updates.
5. Confirm owner/in-game name/card count appears in the account row.

- [ ] **Step 4: Inspect git status in both repos**

Run:

```powershell
git -C C:\Users\PC\Desktop\CODE\Save_Web_Game status --short
git -C C:\Users\PC\Desktop\CODE\MuMupow status --short
```

Expected: no unstaged source changes from this feature. Generated build/cache files may be dirty and should not be staged unless explicitly requested.
