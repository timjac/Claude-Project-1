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
Tests are organised into **panels** via the `test_groups` table. A panel (e.g., "Cholesterol", "Blood Pressure") is a first-class entity with its own `chart_type`, `trend_chart_type`, and optional `description`. Individual tests in `test_definitions` link to their panel via a `group_id` FK. `chart_type` lives at the group level — all tests in a panel share the same chart style, enforced by the admin UI.

`test_definitions` retains a legacy `test_group` text column and `chart_type` column for backward compatibility. All queries use `COALESCE(tg.chart_type, td.chart_type, 'gauge')` so results rows with no linked definition still render safely.

**Supported chart types (`graph_type` in `chart_config` JSON) and their visualisations:**

| `graph_type` | Example Tests | Visual |
|---|---|---|
| `gauge` | Heart Rate, Blood Glucose, BMI, O2 Saturation, Temperature | Half-donut gauge (style: `curved`) or segmented bar (style: `straight`) with colour zones |
| `dot` | Systolic / Diastolic | One or two value markers on a horizontal zone-shaded scale (e.g. Blood Pressure dumbbell) |
| `bar` | Total / HDL / LDL Cholesterol | Horizontal bars against a zone-shaded background |
| `none` | Weight, Height | Large typographic display only — no chart |

The `chart_config` JSON for each test definition stores the axis range, zone boundaries (from/to/colour/label), and type-specific options (e.g. `gauge_style`, `dots` list for the `dot` type, bar colours for the `bar` type).

All chart types expand their axis dynamically if a value falls outside the configured range (elastic bounds), so outliers are always visible rather than clipped.

Trend charts are generated automatically when a patient has more than one result for a given test. The trend style is set at the panel level via `test_groups.trend_chart_type` (`line`, `bp_trend`, `multi_trend`).

### Appointments
Appointments are scheduled per patient with a date, time, provider, and reason. Past appointments in `Scheduled` status are auto-resolved when a patient record is opened: if an encounter exists on that date, the appointment becomes `Completed`; otherwise it becomes `No Show`.

The clinic also has a schedule view across all patients for a given date range (Today / Tomorrow / Next 7 Days / Custom Range).

### PDF Health Reports
Staff can generate a branded PDF health report for any patient. The report:
- Covers a configurable date range
- Allows test groups to be included or excluded, and their order changed via drag-and-drop (`streamlit_sortables`)
- Supports per-test note overrides via an inline data editor
- Includes a Practitioner's Opening Statement and a Next Steps section
- Embeds the appropriate chart (gauge, dot, bar, trend) for each test
- Shows a history table of previous results
- Supports theme customisation (colours, fonts, border radius, spacing) stored in `system_settings`
- Uses custom TTF fonts (Roboto, Montserrat, Open Sans) if selected; falls back to Helvetica safely

Report generation is logged to `report_log` and `report_contents` for audit purposes.

### Staff & Admin
Admin users can manage staff accounts (add/remove users, change passwords, set roles). System-wide settings such as the report footer text and PDF theme are stored in the `system_settings` table.

The Admin Console has three tabs:

**Staff Management** — add users, view the staff directory, change passwords, and delete accounts (with a guard preventing self-deletion and deletion of the last account).

**Report Designer** — configure the PDF theme (colours, font, border radius, spacing) with six named presets loaded from `system_settings`. A live PDF preview renders in real time alongside the controls. Saving writes the theme back to `system_settings` and applies to all future reports.

**Test Dictionary** — define clinical tests and how they render. Split into two sections:
- **Test Panels** — view existing group-level entities (`test_groups`): panel name, chart style, trend style, description.
- **Add New Test or Panel** — a multi-step zone-based editor:
  1. Select chart type (`gauge`, `dot`, `bar`, `none`)
  2. Configure type-specific options (gauge style, axis range, dot definitions, bar colours)
  3. Define colour zones interactively (add/remove/reorder zones with `from`/`to` bounds, colour pickers, labels, and a transparent option)
  4. A live chart preview updates as zones are configured
  5. Set test metadata (name, panel, unit, target) and save

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
| `test_groups` | First-class panel entity — holds `chart_type`, `trend_chart_type`, and `description` at the group level |
| `test_definitions` | Individual test metadata (unit, target, chart config JSON); linked to `test_groups` via `group_id` |
| `appointments` | Scheduled appointments per patient |
| `report_log` | Header record of each generated PDF report (includes `practitioner_statement` and `next_steps`) |
| `report_contents` | Line items (tests and notes) for each report |
| `staff` | Staff accounts with hashed passwords and roles |
| `system_settings` | Key-value store for clinic-wide settings (footer text, PDF theme, encounter types, staff roles, schedule limit, theme presets) |

---

## Dummy Data

`dummy_data.py` seeds the database with 103 fantasy-named patients (from Lord of the Rings, Harry Potter, Game of Thrones, and The Witcher). Patient 103 — Bilbo Baggins — is a curated "golden record" with a longitudinal health journey across four visits, designed to produce rich trend charts in PDF reports.

The script calls `initialize_database()` before inserting any data, so it is safe to run against a fresh (or missing) database. Run it from inside the `Clinic_CRM/` directory so the relative `family_clinic.db` path resolves correctly:

```
cd Clinic_CRM
python dummy_data.py
```
