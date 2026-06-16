# MuMupow UI Redesign Design

Date: 2026-06-16

## Goal

Redesign the MuMupow desktop UI into a dark, minimal, practical operational console. The current interface is visually noisy: buttons use too many strong colors, panels are tightly packed, list content is hard to scan, and each page feels slightly inconsistent. The redesign should make repeated macro work easier while reducing eye strain.

## Approved Direction

Use the **Operational Console** layout:

- Left column: emulator selection and connection controls.
- Center workspace: the active tab's main work area.
- Right column: contextual editor, form, or detail controls.
- Bottom run bar: run settings and primary Run/Stop controls, always visible in the macro workflow.

This direction was selected because MuMupow is primarily an operations tool for controlling multiple emulators and running repeated bot workflows. It keeps the most-used controls visible without making the screen feel crowded.

## Visual System

The app should keep a dark theme but soften it:

- Background: near-black/navy charcoal.
- Panels: slightly lighter dark surfaces with thin low-contrast borders.
- Text: white for headings, muted blue-gray for secondary text.
- Accent color: blue/cyan for selection and focus.
- Success color: green only for primary positive actions such as Run and Save.
- Danger color: red only for Stop, Delete, and destructive actions.
- Warning color: amber only for caution actions or status messages.
- General actions: neutral dark buttons instead of bright colored blocks.

Spacing should increase from the current UI. Controls should align on a consistent grid, with fewer bordered `LabelFrame` sections and fewer dense button grids.

## Macro Tab

The macro page should become the primary reference implementation for the redesign.

- Emulator selector stays in the left app column.
- Profile controls move into a cleaner toolbar above the macro steps.
- Macro steps should be displayed as structured rows instead of dense listbox text:
  - sequence number
  - command type
  - key detail, such as coordinates or text token
  - delay
  - selected state
- Reorder and delete actions should be visually secondary.
- Step editor stays on the right and uses grouped fields with consistent widths.
- Add/Update/Visual Recorder/Clear Form actions should be grouped by importance.
- Run settings and Run/Stop controls move into a persistent bottom run bar for the macro workflow.

## Accounts Tab

The accounts page should reuse the same structure:

- Main center area: searchable grouped account list.
- Right column: add/edit account form.
- Batch actions should be in a compact toolbar above the list.
- Account rows should show email/name/group/OTP status in aligned fields.
- Destructive actions should be small and red, not full-width primary visual elements.
- Long instructional text should be reduced or moved into a compact help block so the page stays operational.

## Manual Sync Tab

Manual controls should be arranged as operational command groups:

- Tap coordinates
- Text input
- System keys
- Screenshot
- Raw ADB command

Each group should use the same panel and button styles as the macro tab. Common commands should be visible without long scrolling on normal desktop heights.

## Settings Tab

Settings should be reorganized into clear utility sections:

- ADB path and connection settings.
- Screen/DPI diagnostics.
- Pointer helper.
- Any other maintenance controls.

Settings should not look like a different app. It should reuse the same dark surfaces, spacing, headings, and button hierarchy.

## Component Changes

Introduce or update reusable Tkinter helpers in `gui.py` rather than styling every widget ad hoc:

- `ModernButton`: neutral default, variants for primary, danger, warning, and subtle actions.
- `ModernEntry`: consistent padding, border, background, and focus color.
- Panel helper: standard dark surface with a small heading.
- Toolbar helper: horizontal grouped action area.
- Row helpers for device/account/macro step cards.

Keep the first implementation scoped to the existing Tkinter code. Do not introduce a new GUI framework.

## Behavior

The redesign should preserve current application behavior:

- Existing macro creation/editing behavior.
- Existing profile import/export behavior.
- Existing account management behavior.
- Existing manual sync controls.
- Existing emulator scan/connect behavior.
- Existing run, stop, stagger delay, and pause-between-sets behavior.

The change is primarily layout, styling, and scanability. Any behavior change should be intentional and separately called out before implementation.

## Testing And Verification

Verification should include:

- Run existing tests with `pytest` if available.
- Start the Tkinter app locally and verify it launches.
- Visually inspect the main tabs at a normal desktop size.
- Check that text does not overflow buttons or form fields.
- Check that Run/Stop controls remain reachable on the macro page.
- Check that selected emulator/account/step states remain visible.

## Out Of Scope

- Replacing Tkinter with a web UI or another desktop framework.
- Changing macro file formats.
- Changing account storage format.
- Rebuilding the packaged executable unless explicitly requested after UI work is verified.
- Redesigning the visual recorder dialog in the first pass, except for minor color/button consistency if it is low risk.
