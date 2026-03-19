# Family Clinic CRM — Application Overview

A Streamlit-based patient management system for a small medical clinic. It runs entirely locally, using a SQLite database and opening in a browser window styled as a standalone desktop application.

---

## How to Run

Double-click `launch_invisible.vbs` to start the app without a visible terminal window.

This triggers the following chain:
1. `launch_invisible.vbs` — runs `launch_crm.bat` silently (no console window)
2. `launch_crm.bat` — activates the Python virtual environment, then runs `launcher.py`
3. `launcher.py` — finds a free port, opens Chrome or Edge in `--app` mode (no address bar), and starts the Streamlit server

The app is then accessible at `http://localhost:<dynamic-port>`.

---

## Authentication

Staff log in via a login screen before accessing any data. Credentials are stored in the `staff` table as SHA-256 hashed passwords. Each account has a role: `Admin` or `Staff`.

**Default account:** `admin` / `admin123`

---

## Application Structure

```
Clinic_CRM/
├── app.py                  # Main Streamlit app — routing, pages, UI
├── app_functions.py        # Helper functions: navigation, data fetching, auth, scheduling
├── constants.py            # Single source of truth for all status string constants
├── modules/
│   ├── clinic_crm.py       # ClinicCRM class — all database operations
│   ├── charts.py           # Chart generators (Matplotlib)
│   └── reports.py          # PDF report builder (FPDF2)
├── assets/
│   ├── logo.png            # Clinic logo used in PDF reports
│   └── fonts/              # Montserrat, Roboto, Open Sans TTF files for PDF theming
├── family_clinic.db        # SQLite database
├── dummy_data.py           # Standalone script to seed the database with test data
├── launcher.py             # App entry point — port selection and browser launch
├── launch_crm.bat          # Activates venv and runs launcher.py
└── launch_invisible.vbs    # Runs the .bat file silently (no console window)
```

---

## DB-Driven Configuration

Several values that might otherwise be hardcoded are stored in `system_settings` and loaded at startup, making them configurable without code changes:

| Setting Key | What It Controls |
|---|---|
| `encounter_types` | Selectbox options when adding a note or ordering a test |
| `staff_roles` | Role options in the Add Staff form |
| `admin_roles` | Which roles have access to the Admin Console |
| `max_schedule_days` | Maximum date range for the lobby schedule view |
| `report_theme_presets` | The six named colour/font presets in the Report Designer |
| `colour_palette` | JSON array of `{name, hex}` objects used in all zone/trend colour selectors |

Available PDF fonts are built dynamically at startup by scanning `assets/fonts/` for `.ttf` files and combining them with the built-in PDF fonts (Helvetica, Times, Courier). No hardcoded font list.

Status strings (`Scheduled`, `Completed`, `No Show`, `Cancelled`, `Pending`, `Complete`) are defined once in `constants.py` and imported wherever they are needed, so there is a single source of truth for all status comparisons and assignments.

---

## Core Features

### Patient Directory
Patients are listed in a searchable directory. Each patient record is built from an **Entity-Attribute-Value (EAV)** data model — fields (first name, last name, DOB, address, phone, email, blood group) are stored as individual rows in `patient_history`, with the most recent row per field treated as current. Every change is versioned automatically, providing a full audit trail.

The patient header (name, caption fields) is driven by the `display_role` column in `field_definitions` — fields with `display_role = 'name'` form the heading, fields with `display_role = 'caption'` appear in the subtitle. No field names are hardcoded in the display logic.

Soft deletes are handled via a `marked_for_deletion_by` flag. A database trigger (`trg_archive_history`) moves deleted rows into `patient_history_archive` before deletion, acting as a safety net.

### Encounters
Clinical activity is logged as **encounters**, which have a type (`Clinical Encounter`, `Telephone Consult`, `Admin/Chart Review`) and a date. The system auto-creates an encounter for the current day when a note or test result is added, or creates a new one if none exists for that day and type.

### Clinical Notes
Free-text notes are attached to encounters via the `encounter_notes` table. Multiple notes can exist per encounter.

### Test Results
Tests follow a two-stage lifecycle:
- **Pending** — test has been ordered/taken but no result yet
- **Complete** — result has been received and logged

Each result records who took the test, when, who logged the result, and when. Results are linked to test definitions (`test_definitions`) which specify the unit, safe target range, and chart configuration (stored as JSON).

#### Test Groups
Tests are organised into **groups** via the `test_groups` table. A group (e.g., "Cholesterol", "Blood Pressure") is a first-class entity with its own `chart_type`, `trend_chart_type`, `description`, and `trend_config`. Individual tests in `test_definitions` link to their group via a `group_id` FK. `chart_type` lives at the group level — all tests in a group share the same chart style, enforced by the admin UI.

`test_definitions` retains a legacy `test_group` text column and `chart_type` column for backward compatibility. All queries use `COALESCE(tg.chart_type, td.chart_type, 'gauge')` so results rows with no linked definition still render safely.

**Supported chart types (`graph_type` in `chart_config` JSON) and their visualisations:**

| `graph_type` | Example Tests | Visual |
|---|---|---|
| `gauge` | Heart Rate, Blood Glucose, BMI, O2 Saturation, Temperature | Half-donut gauge (style: `curved`) or segmented bar (style: `straight`) with colour zones |
| `dot` | Systolic / Diastolic | One or two value markers on a horizontal zone-shaded scale (e.g. Blood Pressure dumbbell) |
| `bar` | Total / HDL / LDL Cholesterol | Horizontal bars against a zone-shaded background |
| `none` | Weight, Height | Large typographic display only — no chart |

The `chart_config` JSON for each test definition stores the axis range, zone boundaries (from/to/colour/label), and type-specific options (e.g. `gauge_style`, `dots` list for the `dot` type, bar colours for the `bar` type). Colours are resolved from the clinic's named colour palette at save time — the JSON always stores hex values so no palette lookups are needed at render time.

All chart types expand their axis dynamically if a value falls outside the configured range (elastic bounds), so outliers are always visible rather than clipped.

**Trend charts** are generated automatically when a patient has more than one result for a given test. All chart types use a single unified `render_trend_chart(series, trend_config)` function in `charts.py`. The `trend_chart_type` column in `test_groups` is always set to `"trend"` for all new groups; the old values (`line`, `bp_trend`, `multi_trend`) are legacy.

`trend_config` (JSON, stored in `test_groups.trend_config`) supports the following keys:

| Key | Type | Description |
|---|---|---|
| `line_colours` | list of hex strings | One colour per series; falls back to `line_colour` (singular) for older records |
| `line_style` | `"solid"` / `"dashed"` | Line dash style |
| `show_markers` | bool | Whether to mark individual data points |
| `fill_area` | bool | Fill under the line (1 series) or between two lines (2 series) |
| `show_legend` | bool | Show a legend when there is more than one series |
| `zones` | list of zone objects | Optional zone bands (`{from, to, colour, label}`) drawn on the trend axis |

For `gauge` and `dot` groups the admin can opt in to showing snapshot zones on the trend chart. For `bar` groups (where each test has its own scale) the admin instead chooses a zone reference: None, any named test's zones, or a custom zone set.

### Appointments
Appointments are scheduled per patient with a date, time, provider, and reason. Past appointments in `Scheduled` status are auto-resolved when a patient record is opened: if an encounter exists on that date, the appointment becomes `Completed`; otherwise it becomes `No Show`.

The booking UI shows a **day-view availability table** for the selected provider and date — existing bookings are listed above the form so staff can see conflicts before booking.

The clinic also has a schedule view across all patients for a given date range (Today / Tomorrow / Next 7 Days / Custom Range), with a **provider filter** to narrow to a single practitioner's diary.

### PDF Health Reports
Staff can generate a branded PDF health report for any patient. The report:
- Covers a configurable date range
- Allows test groups to be included or excluded, and their order changed via drag-and-drop (`streamlit_sortables`)
- Supports per-test note overrides via an inline data editor (shows Latest date and result count per test)
- Includes a Practitioner's Opening Statement and a Next Steps section
- Embeds the appropriate chart (gauge, dot, bar, trend) for each test
- Shows a history table of previous results
- Supports theme customisation (colours, fonts, border radius, spacing) stored in `system_settings`
- Uses custom TTF fonts (Roboto, Montserrat, Open Sans) if selected; falls back to Helvetica safely

Report generation is logged to `report_log` and `report_contents` for audit purposes.

### Staff & Admin
Admin users can manage staff accounts (add/remove users, change passwords, set roles). System-wide settings such as the report footer text and PDF theme are stored in the `system_settings` table.

The Admin Console has four tabs:

**Staff Management** — two collapsible sections:

- **Add New Staff Member** — form to create a new account (username, password, role).
- **Manage Existing Staff** — select a staff member from a dropdown, then choose from four contextual action panels (all hidden until selected):
  - **View/Edit Shift Pattern** — see the current pattern and manage scheduled changes (see Shift Patterns below).
  - **Manage Time Off** — record and delete availability exceptions for the selected staff member.
  - **Change Password** — inline password update form.
  - **Delete Staff Member** — explicit confirm/cancel step; disabled for own account and last remaining account.

**Report Designer** — configure the PDF theme (colours, font, border radius, spacing) with six named presets loaded from `system_settings`. A live PDF preview renders in real time alongside the controls. Saving writes the theme back to `system_settings` and applies to all future reports.

**Staff Rota** — manage staff working patterns and availability exceptions:

- **Shift Patterns** — each staff member holds up to three pattern slots: `current` (active today), `future` (scheduled to take over on a future Monday), and `previous` (the most recently superseded pattern, kept for reference). Older records are archived. Patterns are weekly (7-day cycle) or fortnightly (14-day cycle), anchored to a Monday start date so cycle alignment is always correct.

  All changes create a new pattern record — there is no in-place editing. The **Schedule Pattern Change** form determines the slot automatically based on the chosen start date:
  - **Future Monday** → stored as `future`; current stays active until that date, then auto-promotes overnight.
  - **Today** → stored as `current` immediately; existing current moves to `previous`.
  - **Past Monday** → intent is ambiguous; the admin is asked to choose "Replace current" (`current` slot) or "Store as previous" (`previous` slot). If the resulting date ordering would be inconsistent (Previous dated after Current), a conflict warning is shown before saving.

  Auto-promotion runs whenever a staff member's patterns are read: if a `future` pattern's anchor date has arrived, it cascades `previous→archived`, `current→previous`, `future→current`.

  Fortnightly pattern tables display as **Day | Week 1 | Week 2** columns for readability.

  Within the Shift Pattern panel, **Upcoming Change** and **Previous Pattern** sections are hidden behind toggle buttons and only shown on demand.

- **Manage Time Off** — record exceptions to the regular pattern (Annual Leave, Training, Sick Leave, Appointment, Other). Overrides can be full-day or cover a partial time range, and an "Available" flag supports extra shifts. Overrides always take precedence over the base pattern when computing availability for a given date.

The appointment booking form queries the rota automatically: it shows scheduled hours in green, a warning when the provider is not rostered on that day, and a leave/sickness alert when an override is active.

**Test Dictionary** — define clinical tests and how they render. Contains three sections:

- **Colour Palette** — manage the clinic's named colour palette (`system_settings` key `colour_palette`). Add colours by name + hex picker; includes a "Transparent" shortcut checkbox. All zone colour and trend colour selectors use this palette — no free-form colour pickers.

- **Test Groups** — view existing group-level entities (`test_groups`): group name, chart style, trend style, description. Includes an **Edit** flow to update zone config, trend tuning, and metadata for any existing group.

- **Add New Test Group** — a multi-step zone-based editor:
  1. Select chart type (`gauge`, `dot`, `bar`, `none`) with a caption explaining how many test definitions each type creates. Live preview value inputs also live here.
  2. Configure type-specific options (gauge style, axis range/zones, dot names/labels/colours, bar names/colours/zones).
  3. Configure trend chart appearance: per-series line colours (palette), line style (solid/dashed), mark data points, fill area, show legend, and optional zone bands on the trend axis.
  4. Set test metadata (group name, unit, target, description) and save.
  5. **Live preview** (right column) renders a full PDF banner — identical to the printed report — using dummy data: snapshot chart, current value, history table, and trend chart. Reflects the current designer theme.

- **Edit Existing Test Group** — mirrors the Add New flow for groups that already have patient data. Loads all saved config (snapshot chart config, trend config) from the database and pre-populates the editor. Constraints:
  - Test names can be renamed (cascades atomically across `test_definitions`, `test_results`, `report_contents`, and JSON dot configs); an explicit acknowledgement checkbox is required before saving.
  - Units and targets can be changed with acknowledgement.
  - Zone colours and boundaries (aesthetic only) can be changed freely.
  - Trend chart config (all aesthetic) can be changed freely — same unified Trend Chart section as Add New.
  - Adding extra tests to an existing group is not permitted — create a new group instead.

---

## Lobby

The lobby has two panels:

**Left column — tabbed:**
- **Patient Directory** — searchable patient list; click a row to open the patient dashboard
- **Pending Tests** — lists all `Pending` test results across all patients (Patient, Test, Ordered Date, Ordered By); click a row to open that patient

**Right column:**
- **Clinic Schedule** — upcoming appointments across all patients for a selected date range, with a **provider filter** input to narrow to one practitioner's diary

---

## Database Tables

| Table | Purpose |
|---|---|
| `field_definitions` | Defines valid patient fields (name, display label, group, data type, order, `display_role`) |
| `patient_history` | EAV store of all patient field values with full change history |
| `patient_history_archive` | Safety net — deleted history rows are moved here by trigger |
| `encounters` | Clinical encounters (date, type, provider) |
| `encounter_notes` | Free-text notes linked to encounters |
| `test_results` | Test results with two-stage lifecycle (Pending/Complete) |
| `test_groups` | First-class group entity — holds `chart_type`, `trend_chart_type`, `trend_config`, and `description` at the group level |
| `test_definitions` | Individual test metadata (unit, target, chart config JSON); linked to `test_groups` via `group_id` |
| `appointments` | Scheduled appointments per patient |
| `staff_shift_patterns` | Shift pattern records per staff member. Each row has a `status` of `current`, `future`, `previous`, or `archived`. At most one of each of the first three exist per staff member at any time. |
| `staff_shift_days` | Per-day working hours within a pattern (week number, day of week, start/end time) |
| `staff_availability_overrides` | Exception records overriding the pattern for a specific date (leave, training, sickness, etc.) |
| `report_log` | Header record of each generated PDF report (includes `practitioner_statement` and `next_steps`) |
| `report_contents` | Line items (tests and notes) for each report |
| `staff` | Staff accounts with hashed passwords and roles |
| `system_settings` | Key-value store for clinic-wide settings (footer text, PDF theme, encounter types, staff roles, schedule limit, theme presets, colour palette) |

---

## Dummy Data

`dummy_data.py` seeds the database with 103 fantasy-named patients (from Lord of the Rings, Harry Potter, Game of Thrones, and The Witcher). Patient 103 — Bilbo Baggins — is a curated "golden record" with a longitudinal health journey across four visits, designed to produce rich trend charts in PDF reports.

The script seeds shift patterns for all five fantasy staff members. Two of them (**Dr. Elrond** and **Maester Luwin**) have a `previous` pattern on record — they each moved from standard Mon–Fri 09:00–17:00 hours to a new pattern at different points in the past. **Nurse Pomfrey** has a `future` pattern scheduled two Mondays from the seed date, switching from a fortnightly early/late rotation to fixed 08:00–16:00 hours. This gives working examples of all three pattern slots in the UI immediately after seeding.

The script calls `initialize_database()` before inserting any data, so it is safe to run against a fresh (or missing) database. Run it from inside the `Clinic_CRM/` directory so the relative `family_clinic.db` path resolves correctly:

```
cd Clinic_CRM
python dummy_data.py
```
