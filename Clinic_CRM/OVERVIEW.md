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

## Core Features

### Patient Directory
Patients are listed in a searchable directory. Each patient record is built from an **Entity-Attribute-Value (EAV)** data model — fields (first name, last name, DOB, address, phone, email, blood group) are stored as individual rows in `patient_history`, with the most recent row per field treated as current. Every change is versioned automatically, providing a full audit trail.

Soft deletes are handled via a `marked_for_deletion_by` flag. A database trigger (`trg_archive_history`) moves deleted rows into `patient_history_archive` before deletion, acting as a safety net.

### Encounters
Clinical activity is logged as **encounters**, which have a type (`Clinical Encounter`, `Telephone Consult`, `Admin/Chart Review`) and a date. The system auto-creates an encounter for the current day when a note or test result is added, or creates a new one if none exists for that day and type.

### Clinical Notes
Free-text notes are attached to encounters via the `encounter_notes` table. Multiple notes can exist per encounter.

### Test Results
Tests follow a two-stage lifecycle:
- **Pending** — test has been ordered/taken but no result yet
- **Complete** — result has been received and logged

Each result records who took the test, when, who logged the result, and when. Results are linked to test definitions (`test_definitions`) which specify the unit, safe target range, chart type, and chart configuration (stored as JSON).

**Supported test types and their chart visualisations:**

| Chart Type | Tests | Visual |
|---|---|---|
| `gauge` | Heart Rate, Blood Glucose, O2 Saturation, Temperature | Half-donut gauge with safe zone arc |
| `bp_range` | Systolic / Diastolic | Dumbbell chart showing the BP range |
| `bmi_bullet` | BMI | Segmented bullet chart (Underweight → Obese zones) |
| `multi_bar_panel` | Total / HDL / LDL Cholesterol | Horizontal bar panel with safe zone backgrounds |
| `text_only` | Weight, Height | Large typographic display |

All gauge and range charts expand their axis dynamically if a value falls outside the configured range (elastic bounds), so outliers are always visible rather than clipped.

Trend charts are generated automatically when a patient has more than one result for a given test.

### Appointments
Appointments are scheduled per patient with a date, time, provider, and reason. Past appointments in `Scheduled` status are auto-resolved when a patient record is opened: if an encounter exists on that date, the appointment becomes `Completed`; otherwise it becomes `No Show`.

The clinic also has a schedule view across all patients for a given date range.

### PDF Health Reports
Staff can generate a branded PDF health report for any patient. The report:
- Covers a configurable date range
- Allows individual tests to be included or excluded
- Supports per-test note overrides
- Includes a Practitioner's Statement and Next Steps section
- Embeds the appropriate chart (gauge, trend, panel) for each test
- Shows a history table of previous results
- Supports theme customisation (colours, fonts, border radius) stored in `system_settings`
- Uses custom TTF fonts (Roboto, Montserrat, Open Sans) if selected; falls back to Helvetica safely

Report generation is logged to `report_log` and `report_contents` for audit purposes.

### Staff & Admin
Admin users can manage staff accounts (add/remove users, set roles). System-wide settings such as the report footer text and PDF theme are stored in the `system_settings` table.

---

## Database Tables

| Table | Purpose |
|---|---|
| `field_definitions` | Defines valid patient fields (name, display label, group, data type, order) |
| `patient_history` | EAV store of all patient field values with full change history |
| `patient_history_archive` | Safety net — deleted history rows are moved here by trigger |
| `encounters` | Clinical encounters (date, type, provider) |
| `encounter_notes` | Free-text notes linked to encounters |
| `test_results` | Test results with two-stage lifecycle (Pending/Complete) |
| `test_definitions` | Lookup table for test metadata and chart configuration |
| `appointments` | Scheduled appointments per patient |
| `report_log` | Header record of each generated PDF report |
| `report_contents` | Line items (tests and notes) for each report |
| `staff` | Staff accounts with hashed passwords and roles |
| `system_settings` | Key-value store for clinic-wide settings (footer text, PDF theme) |

---

## Dummy Data

`dummy_data.py` seeds the database with 103 fantasy-named patients (from Lord of the Rings, Harry Potter, Game of Thrones, and The Witcher). Patient 103 — Bilbo Baggins — is a curated "golden record" with a longitudinal health journey across four visits, designed to produce rich trend charts in PDF reports.
