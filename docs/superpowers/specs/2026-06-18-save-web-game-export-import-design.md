# Save_Web_Game to MuMupow Export Import Design

## Context

The user has account and character/card data in `C:\Users\PC\Desktop\CODE\Save_Web_Game` and wants to use that data in `C:\Users\PC\Desktop\CODE\MuMupow`.

`Save_Web_Game` is the source of truth for game accounts, owners, in-game names, and character/card inventory. `MuMupow` is the automation runner that needs login credentials and useful account metadata while running emulator workflows.

The preferred direction is file-based export/import:

- `Save_Web_Game` exports selected accounts to a MuMupow-compatible JSON file.
- `MuMupow` imports that JSON into its local `accounts.json`.
- The export can decrypt passwords using default PIN `1234`.

## Goal

Build a bridge that lets the user move selected account data from `Save_Web_Game` into `MuMupow` without manually copying each email/password.

The imported MuMupow accounts should include enough metadata to answer:

- Which owner owns this account?
- What is the in-game name?
- Which character/card data is associated with the account?
- Which Save_Web_Game account row did this come from?

## Non-Goals

- Live sync from MuMupow to the web app.
- Writing MuMupow changes back into Save_Web_Game.
- CAPTCHA solving or account creation bypasses.
- Changing the current Save_Web_Game encryption model.
- Logging decrypted passwords to console or saving them outside the explicit export/import files.

## Export File Shape

The export file should be JSON with a versioned envelope:

```json
{
  "schema": "mumupow-save-web-game-export",
  "version": 1,
  "exportedAt": "2026-06-18T00:00:00.000Z",
  "source": {
    "app": "Save_Web_Game"
  },
  "accounts": [
    {
      "gameAccountId": "uuid-or-db-id",
      "title": "Account display title",
      "email": "login@example.com",
      "password": "plain password after PIN decrypt",
      "ownerName": "owner",
      "ingamename": "in-game name",
      "group": "owner or chosen export group",
      "cards": [
        {
          "key": "kuroko",
          "label": "Kuroko",
          "qty": 1,
          "category": "normal"
        }
      ]
    }
  ]
}
```

Fields:

- `email`: maps to MuMupow `email`.
- `password`: maps to MuMupow `password`.
- `group`: defaults to `ownerName` if present, otherwise a user-selected export group or `Save_Web_Game`.
- `gameAccountId`: stored in MuMupow metadata so future imports can update the same account.
- `cards`: stored as metadata for display/filtering. The first implementation only needs import/display; card-based run filtering can be added later.

## Save_Web_Game Export Behavior

Add an export entry point in the web app:

- Recommended page/action: an `Export to MuMupow` action from the account management area.
- The user selects accounts to export.
- PIN defaults to `1234` but remains editable in the export UI.
- The export decrypts each selected password in memory and writes the JSON download.
- If a password cannot be decrypted, that account is skipped or marked as failed in the export preview.
- The UI shows a preview count before download:
  - selected accounts
  - exportable accounts
  - accounts with missing/decrypt-failed password

Security handling:

- Do not print decrypted passwords to logs.
- Do not store decrypted passwords in localStorage.
- The downloaded JSON contains plaintext passwords by design because MuMupow needs to type them into the emulator.

## MuMupow Import Behavior

Add an import action in the Accounts tab:

- Button label: `นำเข้าจาก Save_Web_Game`
- File picker accepts `.json`.
- Validate `schema === "mumupow-save-web-game-export"` and `version === 1`.
- For each exported account:
  - Require `email` and `password`.
  - If an existing MuMupow account has the same `email`, update it.
  - Otherwise, create a new account.
  - Preserve existing MuMupow fields not present in the export, such as local checkbox state, unless the export explicitly replaces them.

Imported MuMupow account shape:

```json
{
  "email": "login@example.com",
  "password": "plain password",
  "checked": true,
  "group": "owner",
  "name": "in-game name or title",
  "source": "Save_Web_Game",
  "gameAccountId": "uuid-or-db-id",
  "ownerName": "owner",
  "ingamename": "in-game name",
  "cards": []
}
```

Merge strategy:

- Match by `email` first.
- If `email` is missing or blank, skip the row.
- Updating existing accounts should replace `password`, `group`, `name`, `source`, `gameAccountId`, `ownerName`, `ingamename`, and `cards`.
- Existing `checked` should remain as-is if the account already exists.
- New accounts default to `checked: true`.

## Display Behavior in MuMupow

The account list should include enough summary text to identify imported data:

- Display name: prefer `ingamename`, then `name`, then `title`, then email.
- Metadata summary can include `ownerName` and a compact card count.
- A future enhancement can add a character/card filter, but the first implementation only needs the metadata available on each account.

## Error Handling

Save_Web_Game export:

- Invalid PIN: show a clear error and export no plaintext passwords.
- Partial decrypt failures: show a preview of failed rows and allow exporting only successful rows.

MuMupow import:

- Invalid file/schema: show an error and do not modify `accounts.json`.
- Empty account list: show an error and do not modify `accounts.json`.
- Duplicate accounts in the file: last row wins by email.
- File parse failure: show an error and leave existing accounts unchanged.

## Testing

Save_Web_Game:

- Unit test export mapping from account/card data to the MuMupow JSON shape.
- Unit test default PIN `1234` can decrypt fixture encrypted passwords.
- Test invalid PIN does not export plaintext passwords.

MuMupow:

- Unit test import validation rejects wrong schema.
- Unit test import creates new accounts from export rows.
- Unit test import updates existing account by email and preserves existing `checked`.
- Unit test import stores owner, ingamename, gameAccountId, and cards metadata.

## Implementation Order

1. Add shared export shape tests and exporter in `Save_Web_Game`.
2. Add export UI/download action in `Save_Web_Game`.
3. Add pure import helper tests and implementation in `MuMupow`.
4. Add Accounts tab button and file picker in `MuMupow`.
5. Run both projects' test suites.

## Open Decisions

- Exact Save_Web_Game page placement can follow the existing account management UI.
- Character/card labels should use the existing card definition labels when available; otherwise store raw keys.
- If the web app has multiple game types, the first export can include all selected accounts and their card metadata without filtering by game type unless the current account management UI already has a game filter.
