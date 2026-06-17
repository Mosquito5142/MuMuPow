# Sequential Macro Run Design

## Context

MuMupow currently runs selected accounts across selected Emulator devices in parallel. The normal account queue starts one worker per selected device, so a 10-device signup run can trigger many account registration flows close together. A start stagger can delay each device's first run, but the run still behaves like a parallel burst over time.

For account signup workflows, the desired behavior is stricter: finish one screen/account run completely, then start the next one.

## Goal

Add a sequential run mode for account macro runs:

- Run only one account/device pair at a time.
- Wait until the current macro finishes before starting the next account/device pair.
- Keep the existing parallel mode available for workflows that benefit from speed.
- Keep stop behavior responsive between macro steps and before starting the next account.

## User Flow

1. The user selects devices and checked accounts as usual.
2. The user enables a new option in the Macro tab, labeled `รันทีละจอจนจบ`.
3. The user starts the macro.
4. The app runs the first checked account on the first selected device.
5. When that macro finishes, the app runs the next checked account on the next selected device.
6. If accounts outnumber devices, the app cycles through devices in order.
7. The run ends when all checked accounts have completed or the user presses stop.

Example with 10 accounts and 3 devices:

```text
Account 1 -> Device 1
Account 2 -> Device 2
Account 3 -> Device 3
Account 4 -> Device 1
...
Account 10 -> Device 1
```

## Behavior Details

### Account Runs

Sequential mode applies when checked accounts exist. Each account is paired to a device by index using round-robin device selection:

```text
device = devices[account_index % len(devices)]
```

The app calls the existing `execute_device_macro(device, account, highlight)` for each pair. This preserves existing macro step behavior, account variable replacement, OTP handling, screenshots, and logs.

### No-Account Runs

If no accounts are selected, sequential mode should run the script once per selected device, one device at a time. This keeps the option intuitive: "one screen at a time" means one selected device at a time even without accounts.

### Stop Handling

The existing `self.macro_running` flag remains the cancellation signal. The sequential loop checks it before each new account/device run. `execute_device_macro` already checks the flag between steps, so stop can interrupt a long sequence without starting the next account.

### Pause Between Sets

`pause_between_sets` remains a separate mode for manual batch checkpoints. If both `รันทีละจอจนจบ` and `พักระหว่างชุดบัญชี` are enabled, sequential mode takes precedence because it is the stricter anti-burst mode. The UI should make this clear through logs when the run starts.

### Stagger Delay

Start stagger is not needed in sequential mode because only one account/device pair runs at a time. Existing stagger settings should be ignored in sequential mode and the log should say sequential mode is active.

## UI

Add a checkbox near the existing macro run controls:

```text
รันทีละจอจนจบ
```

Recommended helper text or tooltip-level wording:

```text
เหมาะกับสมัครรหัส ลดการเริ่มหลายจอพร้อมกัน
```

The status/log output should identify the mode:

```text
Sequential: เริ่มรันบัญชี 1/10 บน emulator-5554
Sequential: บัญชี 1/10 เสร็จแล้ว
```

## Error Handling

- If a single account/device run raises an exception, log the device/account and stop the overall run, matching current macro error behavior.
- If the user presses stop, do not start the next account/device run.
- Preserve the existing final cleanup that re-enables the run button and disables the stop button.

## Testing

Add focused tests around the new scheduling helper instead of testing Tk threads directly:

- Account/device round-robin pairs are generated in the expected order.
- More accounts than devices cycles devices.
- No accounts produces one device-only run per selected device.
- Empty devices produces no pairs.

Run existing GUI helper and quick builder tests, plus full `pytest`.

## Out of Scope

- CAPTCHA solving or bypassing.
- Randomized human-like behavior.
- Proxy/IP rotation.
- Per-account retry policy.
- Reworking the macro runner architecture beyond the minimal sequential scheduling path.
