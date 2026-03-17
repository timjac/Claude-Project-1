# Data-Driven Audit: Gaps vs. EAV Philosophy

This document catalogues places in the codebase where behaviour or configuration is hardcoded in application logic rather than driven by the database. The project's core philosophy is an EAV data model where the database is the single source of truth — this audit records where the current code falls short, to guide future improvements.

---

## 1. Encounter Types — Hardcoded in Two Places

**File:** `app.py` lines ~285 and ~320
**Severity:** Medium

**Issue:** The list `["Clinical Encounter", "Telephone Consult", "Admin/Chart Review"]` is hardcoded directly into two selectbox widgets. Adding or renaming an encounter type requires a code change and a deployment.

**Ideal:** A lookup table (e.g. `encounter_types`) or a `system_settings` entry drives this list. The UI queries the DB.

---

## 2. Appointment & Test Statuses — Magic Strings Scattered Across Files

**Files:** `app.py`, `app_functions.py`, `modules/clinic_crm.py`
**Severity:** High

**Issue:** Status values like `"Scheduled"`, `"Completed"`, `"No Show"`, `"Cancelled"`, `"Pending"`, `"Complete"` are repeated as raw strings across all three files. Any rename requires finding and replacing across the codebase, with a high risk of missing an instance.

The auto-resolve logic in `clinic_crm.py` (`auto_resolve_past_appointments`) is particularly fragile — it depends on these strings matching exactly across files.

**Ideal:** A single source of truth — either a constants module or a `status_definitions` lookup table. All status comparisons reference the table, not literal strings.

---

## 3. Staff Roles — Hardcoded List in UI

**File:** `app.py` line ~617
**Severity:** Medium

**Issue:** `["Staff", "Admin"]` is a hardcoded selectbox in the staff management UI. The role also controls access (`if role != 'Admin'`), so the role system is implicitly fixed to exactly these two values. Adding a new role (e.g. `"Clinician"`) would require changes in multiple places.

**Ideal:** Roles stored in a `roles` table or `system_settings`. The access control check queries allowed admin roles rather than comparing to a literal string.

---

## 4. Report Theme Presets — Six Full Theme Dictionaries in app.py

**File:** `app.py` lines ~669–698
**Severity:** Low–Medium

**Issue:** Six complete theme objects (each with 8 properties: `page_bg`, `banner_bg`, `inner_box`, `border`, `text_primary`, `text_muted`, `radius`, `spacing`) are hardcoded in the UI layer. The `system_settings` table already stores a *selected* theme, but the theme definitions themselves live only in Python.

**Ideal:** Theme presets stored in `system_settings` (as JSON) or a `report_themes` table. The report designer UI reads them from the DB, making it possible to add, edit, or remove presets without touching code.

---

## 5. Available Font Families — Hardcoded List Disconnected From Assets

**File:** `app.py` line ~739
**Severity:** Low

**Issue:** `["Helvetica", "Times", "Courier", "Roboto", "Montserrat", "Open Sans"]` is hardcoded. The `reports.py` font loader already checks whether a `.ttf` file exists in `assets/fonts/` before using a custom font — but the UI list doesn't reflect what's actually on disk. If a font file is added or removed, the dropdown is out of sync.

**Ideal:** The font dropdown is built by scanning `assets/fonts/` at startup (or stored in `system_settings`). Adding or removing a font file automatically updates the UI.

---

## 6. Patient Field Access by Name — Partial Bypass of the EAV Model

**Files:** `app.py` lines ~116, ~117, ~174; `modules/reports.py` lines ~310, ~319
**Severity:** High

**Issue:** Specific field names (`first_name`, `last_name`, `date_of_birth`, `blood_group`) are accessed by string key directly in display logic. The EAV model in `field_definitions` knows the display name, group, and order of every field — but this metadata isn't used to drive the UI. If a field were renamed or a new "priority" field added in the DB, the display code wouldn't automatically reflect it.

**Ideal:** The lobby/patient header UI reads `field_definitions` to know which fields to surface prominently, rather than hard-referencing specific names.

---

## 7. Schedule Date Range Limit — Magic Number in Two Places

**File:** `app.py` lines ~135 and ~139
**Severity:** Low

**Issue:** The maximum schedule view range of 7 days is expressed as both `today + 6` (the date widget upper bound) and the string `"7 days"` in a validation error message. These two instances must be kept in sync manually; if one is changed, the other silently diverges.

**Ideal:** A single constant or `system_settings` entry (e.g. `max_schedule_days = 7`) referenced in both places.

---

## 8. BMI Zone Thresholds — Duplicated Between Seed Data and UI Defaults

**Files:** `modules/clinic_crm.py` (seed data in `initialize_database`), `app.py` lines ~883–890
**Severity:** Medium

**Issue:** BMI zone boundaries (18.5, 25.0, 30.0, 40.0) appear in two places: in the `test_definitions` seed data (correct — this is the DB source of truth) and again as hardcoded defaults in the Test Dictionary admin form in `app.py`. The `app.py` copy is used to pre-fill the JSON config editor when a user selects the `bmi_bullet` chart type, so the two copies can silently diverge.

**Ideal:** When a user selects `bmi_bullet` in the admin form, the default JSON should be read from the existing `test_definitions` row for BMI (if it exists), not from a hardcoded template in `app.py`.

---

## 9. Chart Safe Range Defaults — Magic Numbers in Test Dictionary Form

**File:** `app.py` lines ~872–873, ~880–881
**Severity:** Low

**Issue:** When adding a new test via the admin Test Dictionary, default safe range values are hardcoded (`safe_min: 20.0, safe_max: 80.0` for gauge; `safe_min: 0.0, safe_max: 5.0` for multi_bar_panel). These are meaningless placeholders that a staff member must manually replace, and could mislead if accidentally saved.

**Ideal:** Defaults are either blank/null (forcing the user to fill them in deliberately) or read from an existing test of the same chart type as a reference.

---

## Summary Table

| # | Area | Files Affected | Severity |
|---|------|---------------|----------|
| 1 | Encounter types | `app.py` | Medium |
| 2 | Appointment & test statuses | `app.py`, `app_functions.py`, `clinic_crm.py` | High |
| 3 | Staff roles | `app.py` | Medium |
| 4 | Report theme presets | `app.py` | Low–Medium |
| 5 | Font families | `app.py` | Low |
| 6 | Patient field access by name | `app.py`, `reports.py` | High |
| 7 | Schedule date range limit | `app.py` | Low |
| 8 | BMI zone thresholds | `app.py`, `clinic_crm.py` | Medium |
| 9 | Chart safe range defaults | `app.py` | Low |

Items marked **High** represent the most significant divergence from the EAV philosophy and are the best candidates for early remediation.
