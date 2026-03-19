import sqlite3
import hashlib
import datetime
import random
import json
import os
import sys

# Import status constants; fall back gracefully if path not yet on sys.path
try:
    from constants import APPT_SCHEDULED, APPT_COMPLETED, APPT_NO_SHOW
except ImportError:
    _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _base not in sys.path:
        sys.path.insert(0, _base)
    from constants import APPT_SCHEDULED, APPT_COMPLETED, APPT_NO_SHOW

class ClinicCRM:
    def __init__(self, db_name="family_clinic.db"):
        self.db_name = db_name
        self.conn = None
        self.cursor = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_name)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

    def close(self):
        if self.conn:
            self.conn.commit()
            self.conn.close()

    # ==========================================
    # 1. SETUP & INITIALIZATION
    # ==========================================
    def initialize_database(self):
        self.connect()
        print("--- Initializing Database Structure ---")
        
        # --- Table: Field Definitions ---
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS field_definitions (
                field_id INTEGER PRIMARY KEY AUTOINCREMENT,
                field_name TEXT UNIQUE NOT NULL,
                field_display_name TEXT NOT NULL,
                field_group TEXT,
                data_type TEXT DEFAULT 'text',
                ordinal_position INTEGER,
                display_role TEXT DEFAULT NULL
            );
        """)

        # --- Table: Patient History (The EAV Table) ---
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS patient_history (
                history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL,
                field_name TEXT NOT NULL,
                field_value TEXT,
                change_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                change_reason TEXT,
                changed_by TEXT,
                marked_for_deletion_by TEXT, 
                FOREIGN KEY (field_name) REFERENCES field_definitions(field_name)
            );
        """)

        # --- Table: Archive (The Safety Net) ---
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS patient_history_archive (
                archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_history_id INTEGER,
                patient_id INTEGER,
                field_name TEXT,
                field_value TEXT,
                original_change_date DATETIME,
                archived_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                deleted_by TEXT,
                deletion_reason TEXT
            );
        """)

        # --- TRIGGER: The Safety Valve ---
        self.cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_archive_history
            BEFORE DELETE ON patient_history
            BEGIN
                INSERT INTO patient_history_archive (
                    original_history_id, patient_id, field_name, field_value, 
                    original_change_date, deleted_by
                )
                VALUES (
                    OLD.history_id, OLD.patient_id, OLD.field_name, OLD.field_value, 
                    OLD.change_date, OLD.marked_for_deletion_by
                );
            END;
        """)

        # --- Table: Encounters (Replaced Visits) ---
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS encounters (
                encounter_id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER,
                encounter_date DATETIME,
                encounter_type TEXT, -- e.g., 'In-Person', 'Telephone', 'Admin'
                created_by TEXT 
            );
        """)

        # --- Table: Encounter Notes (Replaced Visit Notes) ---
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS encounter_notes (
                note_id INTEGER PRIMARY KEY AUTOINCREMENT,
                encounter_id INTEGER,
                note_text TEXT,
                created_by TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (encounter_id) REFERENCES encounters(encounter_id)
            );
        """)

        # --- Table: Test Results (NEW MULTI-STAGE SCHEMA) ---
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_results (
                result_id INTEGER PRIMARY KEY AUTOINCREMENT,
                encounter_id INTEGER,
                test_name TEXT,
                
                -- "Taken" Lifecycle
                test_taken_on DATETIME,
                test_taken_by TEXT,
                is_taken_by_override INTEGER DEFAULT 0,
                test_taken_note TEXT,
                
                -- Result Data
                test_value TEXT,
                
                -- "Resulted" Lifecycle
                result_received_on DATETIME,
                result_logged_by TEXT,
                is_result_logged_by_override INTEGER DEFAULT 0,
                result_note TEXT,
                
                -- State Tracking
                status TEXT DEFAULT 'Pending', 
                
                FOREIGN KEY (encounter_id) REFERENCES encounters(encounter_id)
            );
        """)

        # --- Table: Test Groups (first-class group entity) ---
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_groups (
                group_id         INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name       TEXT UNIQUE NOT NULL,
                chart_type       TEXT NOT NULL DEFAULT 'gauge',
                trend_chart_type TEXT NOT NULL DEFAULT 'line',
                description      TEXT
            );
        """)

        # Add trend_config column idempotently (may already exist in upgraded DBs)
        try:
            self.cursor.execute("ALTER TABLE test_groups ADD COLUMN trend_config TEXT")
        except:
            pass  # column already exists

        # --- Table: Test Definitions ---
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_definitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_name TEXT UNIQUE NOT NULL,
                unit TEXT,
                default_target TEXT,
                description TEXT,
                chart_config TEXT,
                is_active INTEGER DEFAULT 1,
                group_id INTEGER NOT NULL REFERENCES test_groups(group_id)
            );
        """)

        # --- Table: Report Log ---
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS report_log (
                report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT DEFAULT 'Admin',
                report_start_date TEXT,
                report_end_date TEXT,
                practitioner_statement TEXT,
                next_steps TEXT
            );
        """)

        # --- Table: Report Contents ---
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS report_contents (
                content_id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER,
                test_name TEXT,
                note_included INTEGER, 
                note_text TEXT,        
                is_override INTEGER,   
                FOREIGN KEY(report_id) REFERENCES report_log(report_id)
            );
        """)

        # --- Table: Staff ---
        self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS staff (
                staff_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'Staff'
            );
        """)

        # --- Table: Appointments ---
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS appointments (
                appointment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER,
                appointment_date DATE,
                appointment_time TEXT,
                provider TEXT,
                reason TEXT,
                status TEXT DEFAULT 'Scheduled',
                created_by TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # --- Table: Staff Shift Patterns ---
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS staff_shift_patterns (
                pattern_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                username     TEXT NOT NULL,
                pattern_type TEXT NOT NULL CHECK(pattern_type IN ('weekly', 'fortnightly')),
                anchor_date  TEXT NOT NULL,
                is_active    INTEGER DEFAULT 1,
                created_by   TEXT,
                created_at   TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # --- Migrate: add status column if not present ---
        self.cursor.execute("PRAGMA table_info(staff_shift_patterns)")
        _cols = [r['name'] for r in self.cursor.fetchall()]
        if 'status' not in _cols:
            self.cursor.execute("ALTER TABLE staff_shift_patterns ADD COLUMN status TEXT DEFAULT 'archived'")
            self.cursor.execute("UPDATE staff_shift_patterns SET status = 'current' WHERE is_active = 1")

        # --- Table: Staff Shift Days ---
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS staff_shift_days (
                shift_day_id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_id   INTEGER NOT NULL REFERENCES staff_shift_patterns(pattern_id),
                week_number  INTEGER NOT NULL,
                day_of_week  INTEGER NOT NULL,
                start_time   TEXT,
                end_time     TEXT
            );
        """)

        # --- Table: Staff Availability Overrides ---
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS staff_availability_overrides (
                override_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT NOT NULL,
                override_date TEXT NOT NULL,
                override_type TEXT NOT NULL,
                is_available  INTEGER DEFAULT 0,
                start_time    TEXT,
                end_time      TEXT,
                notes         TEXT,
                created_by    TEXT,
                created_at    TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # --- Populate Field Definitions ---
        # display_role: 'name' = part of patient heading, 'caption' = shown in subtitle, NULL = not in header
        fields = [
            ("first_name", "First Name", "personal", "text", 1, "name"),
            ("middle_names", "Middle Names", "personal", "text", 2, None),
            ("last_name", "Last Name", "personal", "text", 3, "name"),
            ("preferred_name", "Preferred Name", "personal", "text", 4, None),
            ("date_of_birth", "Date of Birth", "personal", "date", 5, "caption"),
            ("address_line_1", "Address Line 1", "address", "text", 6, None),
            ("address_line_2", "Address Line 2", "address", "text", 7, None),
            ("address_town", "Town/City", "address", "text", 8, None),
            ("address_postcode", "Postcode", "address", "text", 9, None),
            ("phone", "Phone Number", "contact", "text", 10, None),
            ("email", "Email Address", "contact", "email", 11, None),
            ("blood_group", "Blood Group", "clinical", "text", 12, "caption")
        ]

        self.cursor.executemany("""
            INSERT OR IGNORE INTO field_definitions
            (field_name, field_display_name, field_group, data_type, ordinal_position, display_role)
            VALUES (?, ?, ?, ?, ?, ?)
        """, fields)

        # Stamp display_role on rows that pre-date this column (UPDATE is idempotent)
        header_roles = [
            ("name",    "first_name"),
            ("name",    "last_name"),
            ("caption", "date_of_birth"),
            ("caption", "blood_group"),
        ]
        self.cursor.executemany(
            "UPDATE field_definitions SET display_role = ? WHERE field_name = ? AND display_role IS NULL",
            header_roles
        )

        # --- Seed Test Groups (must be seeded before test_definitions) ---
        # Tuples: (group_name, chart_type, trend_chart_type, description)
        test_group_seeds = [
            ("Weight",                  "none",  "trend", "Body mass"),
            ("Height",                  "none",  "trend", "Stature"),
            ("BMI",                     "gauge", "trend", "Body Mass Index"),
            ("Blood Pressure",          "dot",   "trend", "Systolic and diastolic readings"),
            ("Resting Heart Rate",      "gauge", "trend", "Pulse rate"),
            ("Cholesterol",             "bar",   "trend", "Lipid panel"),
            ("Blood Glucose (Fasting)", "gauge", "trend", "Fasting blood sugar"),
            ("O2 Saturation",           "gauge", "trend", "Oxygen saturation"),
            ("Temperature",             "gauge", "trend", "Body temperature"),
        ]
        self.cursor.executemany("""
            INSERT OR IGNORE INTO test_groups (group_name, chart_type, trend_chart_type, description)
            VALUES (?, ?, ?, ?)
        """, test_group_seeds)

        # --- Seed Test Definitions ---
        # Tuples: (test_name, group_name, unit, default_target, description, chart_config)
        # group_name is used only to look up group_id via subquery — not stored on test_definitions.
        definitions = [
            ("Weight", "Weight", "kg", "N/A", "Body mass", json.dumps({
                "graph_type": "none"
            })),
            ("Height", "Height", "cm", "N/A", "Stature", json.dumps({
                "graph_type": "none"
            })),
            ("BMI", "BMI", "kg/m2", "18.5-24.9", "Body Mass Index", json.dumps({
                "graph_type": "gauge", "gauge_style": "straight",
                "axis_min": 10, "axis_max": 40,
                "zones": [
                    {"from": 10,   "to": 18.5, "color": "#ADD8E6", "label": "Underweight"},
                    {"from": 18.5, "to": 25.0, "color": "#D4EDDA", "label": "Healthy"},
                    {"from": 25.0, "to": 30.0, "color": "#FFE4B5", "label": "Overweight"},
                    {"from": 30.0, "to": 40.0, "color": "#FFCCCB", "label": "Obese"}
                ]
            })),
            ("Systolic", "Blood Pressure", "mmHg", "90-120", "Systolic Pressure", json.dumps({
                "graph_type": "dot",
                "axis_min": 40, "axis_max": 200,
                "zones": [
                    {"from": 40,  "to": 90,  "color": "#FFCCCB", "label": "Low"},
                    {"from": 90,  "to": 120, "color": "#D4EDDA", "label": "Normal"},
                    {"from": 120, "to": 200, "color": "#FFCCCB", "label": "High"}
                ],
                "dots": [
                    {"test_name": "Systolic",  "fill_color": "#003366", "stroke_color": "#003366", "label": "SYS"},
                    {"test_name": "Diastolic", "fill_color": "#FFFFFF",  "stroke_color": "#003366", "label": "DIA"}
                ]
            })),
            ("Diastolic", "Blood Pressure", "mmHg", "60-80", "Diastolic Pressure", json.dumps({
                "graph_type": "dot",
                "dot_role": "secondary",
                "axis_min": 40, "axis_max": 200,
                "zones": [
                    {"from": 40,  "to": 90,  "color": "#FFCCCB", "label": "Low"},
                    {"from": 90,  "to": 120, "color": "#D4EDDA", "label": "Normal"},
                    {"from": 120, "to": 200, "color": "#FFCCCB", "label": "High"}
                ]
            })),
            ("Resting Heart Rate", "Resting Heart Rate", "bpm", "60-100", "Pulse rate", json.dumps({
                "graph_type": "gauge", "gauge_style": "curved",
                "axis_min": 30, "axis_max": 150,
                "zones": [
                    {"from": 30,  "to": 60,  "color": "#FFCCCB", "label": "Low"},
                    {"from": 60,  "to": 100, "color": "#D4EDDA", "label": "Normal"},
                    {"from": 100, "to": 150, "color": "#FFCCCB", "label": "High"}
                ]
            })),
            ("Total Cholesterol", "Cholesterol", "mmol/L", "<5.0", "Total lipid level", json.dumps({
                "graph_type": "bar",
                "bar_color": "#003366", "bar_alert_color": "#DC3545",
                "zones": [
                    {"from": 0.0, "to": 5.0,  "color": "#D4EDDA", "label": "Normal"},
                    {"from": 5.0, "to": 15.0, "color": "#FFCCCB", "label": "High"}
                ]
            })),
            ("HDL Cholesterol", "Cholesterol", "mmol/L", ">1.0", "Good cholesterol", json.dumps({
                "graph_type": "bar",
                "bar_color": "#003366", "bar_alert_color": "#DC3545",
                "zones": [
                    {"from": 0.0, "to": 1.0,  "color": "#FFCCCB", "label": "Low"},
                    {"from": 1.0, "to": 15.0, "color": "#D4EDDA", "label": "Good"}
                ]
            })),
            ("LDL Cholesterol", "Cholesterol", "mmol/L", "<3.0", "Bad cholesterol", json.dumps({
                "graph_type": "bar",
                "bar_color": "#003366", "bar_alert_color": "#DC3545",
                "zones": [
                    {"from": 0.0, "to": 3.0,  "color": "#D4EDDA", "label": "Normal"},
                    {"from": 3.0, "to": 15.0, "color": "#FFCCCB", "label": "High"}
                ]
            })),
            ("Blood Glucose (Fasting)", "Blood Glucose (Fasting)", "mmol/L", "4.0-5.9", "Fasting blood sugar", json.dumps({
                "graph_type": "gauge", "gauge_style": "curved",
                "axis_min": 0.0, "axis_max": 15.0,
                "zones": [
                    {"from": 0.0, "to": 4.0,  "color": "#FFCCCB", "label": "Low"},
                    {"from": 4.0, "to": 5.9,  "color": "#D4EDDA", "label": "Normal"},
                    {"from": 5.9, "to": 15.0, "color": "#FFCCCB", "label": "High"}
                ]
            })),
            ("O2 Saturation", "O2 Saturation", "%", ">95", "Oxygen saturation", json.dumps({
                "graph_type": "gauge", "gauge_style": "curved",
                "axis_min": 80.0, "axis_max": 100.0,
                "zones": [
                    {"from": 80.0, "to": 95.0,  "color": "#FFCCCB", "label": "Low"},
                    {"from": 95.0, "to": 100.0, "color": "#D4EDDA", "label": "Normal"}
                ]
            })),
            ("Temperature", "Temperature", "C", "36.5-37.5", "Body temperature", json.dumps({
                "graph_type": "gauge", "gauge_style": "curved",
                "axis_min": 34.0, "axis_max": 40.0,
                "zones": [
                    {"from": 34.0, "to": 36.5, "color": "#FFCCCB", "label": "Low"},
                    {"from": 36.5, "to": 37.5, "color": "#D4EDDA", "label": "Normal"},
                    {"from": 37.5, "to": 40.0, "color": "#FFCCCB", "label": "High"}
                ]
            }))
        ]

        self.cursor.executemany("""
            INSERT OR IGNORE INTO test_definitions
            (test_name, unit, default_target, description, chart_config, group_id)
            VALUES (?, ?, ?, ?, ?, (SELECT group_id FROM test_groups WHERE group_name = ?))
        """, [(t_name, unit, target, desc, cfg, grp) for t_name, grp, unit, target, desc, cfg in definitions])

        # --- Populate Staff with Admin ---
        default_user = "admin"
        default_pass = "admin123"
        hashed_pass = hashlib.sha256(default_pass.encode()).hexdigest()

        self.cursor.execute("INSERT OR IGNORE INTO staff (username, password_hash, role) VALUES (?, ?, ?)", 
                  (default_user, hashed_pass, "Admin"))
        
        # --- Table: System Settings ---
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT
            );
        """)
        
        self.cursor.execute("""
            INSERT OR IGNORE INTO system_settings (setting_key, setting_value)
            VALUES ('report_footer', 'Jack''s Family Clinic | 123 Health Way, Medical District | Phone: (555) 019-2837')
        """)

        # --- Seed configurable lookup values (DB-driven, no magic strings in code) ---
        config_seeds = [
            ("encounter_types",   json.dumps(["Clinical Encounter", "Telephone Consult", "Admin/Chart Review"])),
            ("staff_roles",       json.dumps(["Staff", "Admin"])),
            ("admin_roles",       json.dumps(["Admin"])),
            ("max_schedule_days", "7"),
            ("report_theme_presets", json.dumps({
                "Classic Blue": {
                    "page_bg": "#E6F5FF", "banner_bg": "#FFFFFF", "inner_box": "#F8FBFF",
                    "border": "#B4D2E6", "text_primary": "#003366", "text_muted": "#505050",
                    "radius": 5, "spacing": 8, "font": "Helvetica"
                },
                "Modern Minimal": {
                    "page_bg": "#F5F5F5", "banner_bg": "#FFFFFF", "inner_box": "#FAFAFA",
                    "border": "#E0E0E0", "text_primary": "#212121", "text_muted": "#757575",
                    "radius": 0, "spacing": 12, "font": "Roboto"
                },
                "Warm Emerald": {
                    "page_bg": "#E8F5E9", "banner_bg": "#FFFFFF", "inner_box": "#F1F8E9",
                    "border": "#C8E6C9", "text_primary": "#1B5E20", "text_muted": "#558B2F",
                    "radius": 8, "spacing": 6, "font": "Times"
                },
                "Sunset Coral": {
                    "page_bg": "#FFF3E0", "banner_bg": "#FFFFFF", "inner_box": "#FFF8E1",
                    "border": "#FFCC80", "text_primary": "#E65100", "text_muted": "#8D6E63",
                    "radius": 12, "spacing": 10, "font": "Helvetica"
                },
                "Royal Violet": {
                    "page_bg": "#F3E5F5", "banner_bg": "#FFFFFF", "inner_box": "#FAFAFA",
                    "border": "#CE93D8", "text_primary": "#4A148C", "text_muted": "#6A1B9A",
                    "radius": 4, "spacing": 8, "font": "Montserrat"
                },
                "Crisp Slate": {
                    "page_bg": "#ECEFF1", "banner_bg": "#FFFFFF", "inner_box": "#F5F7F8",
                    "border": "#B0BEC5", "text_primary": "#263238", "text_muted": "#546E7A",
                    "radius": 2, "spacing": 9, "font": "Open Sans"
                }
            })),
            ("colour_palette", json.dumps([
                {"name": "Pale Green",   "hex": "#D4EDDA"},
                {"name": "Pale Amber",   "hex": "#FFE4B5"},
                {"name": "Pale Red",     "hex": "#FFCCCB"},
                {"name": "Pale Blue",    "hex": "#ADD8E6"},
                {"name": "Green",        "hex": "#28A745"},
                {"name": "Amber",        "hex": "#FFA500"},
                {"name": "Red",          "hex": "#DC3545"},
                {"name": "Blue",         "hex": "#003366"},
                {"name": "Neutral Grey", "hex": "#E0E0E0"},
                {"name": "Transparent",  "hex": "transparent"}
            ])),
        ]
        self.cursor.executemany(
            "INSERT OR IGNORE INTO system_settings (setting_key, setting_value) VALUES (?, ?)",
            config_seeds
        )

        print("--- Database Initialized Successfully ---")
        self.close()

    # ==========================================
    # 2. CORE FUNCTIONS
    # ==========================================

    def _get_next_patient_id(self):
        self.cursor.execute("SELECT MAX(patient_id) FROM patient_history")
        val = self.cursor.fetchone()[0]
        return 1 if val is None else val + 1

    def log_patient_change(self, patient_id, field_name, field_value, changed_by, reason="Update"):
        self.connect()
        self.cursor.execute("SELECT 1 FROM field_definitions WHERE field_name = ?", (field_name,))
        if not self.cursor.fetchone():
            print(f"Error: Field '{field_name}' is not defined in Field_Definitions.")
            return None

        if patient_id is None:
            patient_id = self._get_next_patient_id()

        self.cursor.execute("""
            INSERT INTO patient_history (patient_id, field_name, field_value, changed_by, change_reason)
            VALUES (?, ?, ?, ?, ?)
        """, (patient_id, field_name, str(field_value), changed_by, reason))
        
        self.close()
        return patient_id
    
    def _get_or_create_todays_encounter(self, patient_id, current_user, encounter_type="Clinical Encounter"):
        """Finds an encounter for today, or creates one if it doesn't exist."""
        self.connect()
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")

        self.cursor.execute("""
            SELECT encounter_id FROM encounters 
            WHERE patient_id = ? AND DATE(encounter_date) = ? AND encounter_type = ?
        """, (patient_id, today_str, encounter_type))

        record = self.cursor.fetchone()

        if record:
            encounter_id = record['encounter_id']
        else:
            self.cursor.execute("""
                INSERT INTO encounters (patient_id, encounter_date, encounter_type, created_by)
                VALUES (?, ?, ?, ?)
            """, (patient_id, today_str, encounter_type, current_user))
            encounter_id = self.cursor.lastrowid

        self.conn.commit()  
        self.close()
        return encounter_id

    def clear_patient_field(self, patient_id, field_name, changed_by):
        return self.log_patient_change(patient_id, field_name, "", changed_by, "Field Cleared")

    def delete_specific_field_history(self, history_id, user):
        self.connect()
        self.cursor.execute("""
            UPDATE patient_history SET marked_for_deletion_by = ? WHERE history_id = ?
        """, (user, history_id))
        self.cursor.execute("DELETE FROM patient_history WHERE history_id = ?", (history_id,))
        self.close()

    def delete_patient_history_completely(self, patient_id, user):
        self.connect()
        self.cursor.execute("""
            UPDATE patient_history SET marked_for_deletion_by = ? WHERE patient_id = ?
        """, (user, patient_id))
        self.cursor.execute("DELETE FROM patient_history WHERE patient_id = ?", (patient_id,))
        self.close()
    
    def add_clinical_note(self, patient_id, note_text, current_user, encounter_type="Clinical Encounter"):
        encounter_id = self._get_or_create_todays_encounter(patient_id, current_user, encounter_type)
        self.connect()
        self.cursor.execute("""
            INSERT INTO encounter_notes (encounter_id, note_text, created_by)
            VALUES (?, ?, ?)
        """, (encounter_id, note_text, current_user))
        self.conn.commit()
        self.close()
        return True

    def add_test_result(self, patient_id, test_name, test_taken_on, test_taken_by, 
                        is_taken_by_override, test_taken_note, test_value, 
                        result_received_on, result_logged_by, is_result_logged_by_override, 
                        result_note, current_user, encounter_type="Clinical Encounter"):
        """Creates a new test record. Determines Pending vs Complete based on test_value."""
        
        encounter_id = self._get_or_create_todays_encounter(patient_id, current_user, encounter_type)
        
        # Determine Status dynamically
        status = "Complete" if test_value and str(test_value).strip() != "" else "Pending"

        self.connect()
        self.cursor.execute("""
            INSERT INTO test_results (
                encounter_id, test_name, test_taken_on, test_taken_by, is_taken_by_override,
                test_taken_note, test_value, result_received_on, result_logged_by,
                is_result_logged_by_override, result_note, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            encounter_id, test_name, str(test_taken_on), test_taken_by, int(is_taken_by_override),
            test_taken_note, str(test_value) if test_value else None, 
            str(result_received_on) if result_received_on else None, 
            result_logged_by, int(is_result_logged_by_override), result_note, status
        ))
        
        self.conn.commit()
        self.close()
        return True

    def update_test_result(self, result_id, test_value, result_received_on, 
                           result_logged_by, is_result_logged_by_override, result_note):
        """Updates an existing test. Used to move Pending tests to Complete."""
        
        status = "Complete" if test_value and str(test_value).strip() != "" else "Pending"
        
        self.connect()
        self.cursor.execute("""
            UPDATE test_results 
            SET test_value = ?, 
                result_received_on = ?, 
                result_logged_by = ?, 
                is_result_logged_by_override = ?, 
                result_note = ?, 
                status = ?
            WHERE result_id = ?
        """, (
            str(test_value), str(result_received_on), result_logged_by, 
            int(is_result_logged_by_override), result_note, status, result_id
        ))
        
        self.conn.commit()
        self.close()
        return True

    def add_staff_member(self, username, password, role="Staff"):
        self.connect()
        hashed_pass = hashlib.sha256(password.encode()).hexdigest()
        try:
            self.cursor.execute("INSERT INTO staff (username, password_hash, role) VALUES (?, ?, ?)", 
                                (username, hashed_pass, role))
            self.conn.commit()
            success = True
        except sqlite3.IntegrityError:
            success = False
        self.close()
        return success
    
    def add_appointment(self, patient_id, appt_date, appt_time, provider, reason, created_by, status="Scheduled"):
        self.connect()
        self.cursor.execute("""
            INSERT INTO appointments (patient_id, appointment_date, appointment_time, provider, reason, status, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (patient_id, str(appt_date), str(appt_time), provider, reason, status, created_by))
        self.conn.commit()
        self.close()
        return True

    def update_appointment_status(self, appointment_id, status):
        self.connect()
        self.cursor.execute("UPDATE appointments SET status = ? WHERE appointment_id = ?", (status, appointment_id))
        self.conn.commit()
        self.close()
        return True
    
    def auto_resolve_past_appointments(self, patient_id):
        self.connect()
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")

        self.cursor.execute("""
            SELECT appointment_id, appointment_date
            FROM appointments
            WHERE patient_id = ? AND appointment_date < ? AND status = ?
        """, (patient_id, today_str, APPT_SCHEDULED))

        past_appts = self.cursor.fetchall()

        for appt in past_appts:
            appt_id = appt['appointment_id']
            appt_date = appt['appointment_date']

            # Point to 'encounters' now
            self.cursor.execute("""
                SELECT 1 FROM encounters
                WHERE patient_id = ? AND DATE(encounter_date) = ?
            """, (patient_id, appt_date))

            has_encounter = self.cursor.fetchone()
            new_status = APPT_COMPLETED if has_encounter else APPT_NO_SHOW
            
            self.cursor.execute("UPDATE appointments SET status = ? WHERE appointment_id = ?", (new_status, appt_id))
            
        self.conn.commit()
        self.close()
    
    # ==========================================
    # STAFF ROTA
    # ==========================================

    def _promote_future_patterns(self, username):
        """If a future pattern's anchor_date has arrived, promote it: future→current, current→previous, old previous→archived."""
        today = str(datetime.date.today())
        self.connect()
        self.cursor.execute(
            "SELECT pattern_id FROM staff_shift_patterns WHERE username=? AND status='future' AND anchor_date<=?",
            (username, today)
        )
        future = self.cursor.fetchone()
        if future:
            self.cursor.execute(
                "UPDATE staff_shift_patterns SET status='archived' WHERE username=? AND status='previous'", (username,))
            self.cursor.execute(
                "UPDATE staff_shift_patterns SET status='previous' WHERE username=? AND status='current'", (username,))
            self.cursor.execute(
                "UPDATE staff_shift_patterns SET status='current' WHERE pattern_id=?", (future['pattern_id'],))
            self.conn.commit()
        self.close()

    def save_shift_pattern(self, username, pattern_type, anchor_date, days_data, created_by, slot='current'):
        """
        Save a shift pattern for a staff member.
        slot='current': replaces current immediately (current→previous, old previous→archived).
        slot='future':  schedules for a future date (replaces any existing future pattern).
        slot='previous': stores as a historical reference only (archives any existing previous; current unchanged).
        days_data: list of (week_number, day_of_week, start_time, end_time) tuples.
        """
        self.connect()
        if slot == 'current':
            self.cursor.execute(
                "UPDATE staff_shift_patterns SET status='archived' WHERE username=? AND status='previous'", (username,))
            self.cursor.execute(
                "UPDATE staff_shift_patterns SET status='previous' WHERE username=? AND status='current'", (username,))
        elif slot == 'future':
            self.cursor.execute(
                "UPDATE staff_shift_patterns SET status='archived' WHERE username=? AND status='future'", (username,))
        elif slot == 'previous':
            self.cursor.execute(
                "UPDATE staff_shift_patterns SET status='archived' WHERE username=? AND status='previous'", (username,))
        self.cursor.execute("""
            INSERT INTO staff_shift_patterns (username, pattern_type, anchor_date, status, created_by)
            VALUES (?, ?, ?, ?, ?)
        """, (username, pattern_type, str(anchor_date), slot, created_by))
        pattern_id = self.cursor.lastrowid
        for week_num, day_of_week, start_time, end_time in days_data:
            self.cursor.execute("""
                INSERT INTO staff_shift_days (pattern_id, week_number, day_of_week, start_time, end_time)
                VALUES (?, ?, ?, ?, ?)
            """, (pattern_id, week_num, day_of_week, start_time, end_time))
        self.conn.commit()
        self.close()
        return pattern_id

    def cancel_future_pattern(self, username):
        """Archive the pending future pattern, leaving current unchanged."""
        self.connect()
        self.cursor.execute(
            "UPDATE staff_shift_patterns SET status='archived' WHERE username=? AND status='future'", (username,))
        self.conn.commit()
        self.close()

    def get_shift_pattern(self, username):
        """
        Returns {'current': (pattern_dict, [days]), 'future': (pattern_dict, [days]), 'previous': (pattern_dict, [days])}.
        Each value is (None, []) if that slot is empty.
        Auto-promotes any due future patterns before reading.
        """
        self._promote_future_patterns(username)
        self.connect()
        result = {}
        for slot in ('current', 'future', 'previous'):
            self.cursor.execute(
                "SELECT * FROM staff_shift_patterns WHERE username=? AND status=? ORDER BY created_at DESC LIMIT 1",
                (username, slot)
            )
            pattern = self.cursor.fetchone()
            if pattern:
                self.cursor.execute(
                    "SELECT week_number, day_of_week, start_time, end_time FROM staff_shift_days WHERE pattern_id=? ORDER BY week_number, day_of_week",
                    (pattern['pattern_id'],)
                )
                result[slot] = (dict(pattern), [dict(d) for d in self.cursor.fetchall()])
            else:
                result[slot] = (None, [])
        self.close()
        return result

    def get_staff_availability(self, username, check_date):
        """
        Returns availability for a staff member on a specific date.
        Overrides take precedence over the shift pattern.
        Returns dict: {is_working, start_time, end_time, override_type, notes, source}
        source values: 'override', 'pattern', 'before_start', 'none'
        """
        if isinstance(check_date, str):
            check_date = datetime.date.fromisoformat(check_date)
        self._promote_future_patterns(username)
        self.connect()
        # Override takes precedence
        self.cursor.execute("""
            SELECT * FROM staff_availability_overrides
            WHERE username = ? AND override_date = ?
            ORDER BY created_at DESC LIMIT 1
        """, (username, str(check_date)))
        override = self.cursor.fetchone()
        if override:
            override = dict(override)
            self.close()
            return {
                'is_working': bool(override['is_available']),
                'start_time': override['start_time'],
                'end_time': override['end_time'],
                'override_type': override['override_type'],
                'notes': override['notes'],
                'source': 'override'
            }
        # Fall back to shift pattern
        self.cursor.execute(
            "SELECT * FROM staff_shift_patterns WHERE username=? AND status='current' ORDER BY created_at DESC LIMIT 1",
            (username,)
        )
        pattern = self.cursor.fetchone()
        if not pattern:
            self.close()
            return {'is_working': None, 'start_time': None, 'end_time': None,
                    'override_type': None, 'notes': 'No shift pattern set', 'source': 'none'}
        pattern = dict(pattern)
        anchor = datetime.date.fromisoformat(pattern['anchor_date'])
        days_since_anchor = (check_date - anchor).days
        if days_since_anchor < 0:
            self.close()
            return {'is_working': None, 'start_time': None, 'end_time': None,
                    'override_type': None, 'notes': 'Before pattern start', 'source': 'before_start'}
        period_length = 7 if pattern['pattern_type'] == 'weekly' else 14
        day_in_period = days_since_anchor % period_length
        week_number = (day_in_period // 7) + 1
        day_of_week = day_in_period % 7
        self.cursor.execute("""
            SELECT start_time, end_time FROM staff_shift_days
            WHERE pattern_id = ? AND week_number = ? AND day_of_week = ?
        """, (pattern['pattern_id'], week_number, day_of_week))
        shift = self.cursor.fetchone()
        self.close()
        if shift:
            return {'is_working': True, 'start_time': shift['start_time'], 'end_time': shift['end_time'],
                    'override_type': None, 'notes': None, 'source': 'pattern'}
        return {'is_working': False, 'start_time': None, 'end_time': None,
                'override_type': None, 'notes': None, 'source': 'pattern'}

    def add_availability_override(self, username, override_date, override_type, is_available,
                                   start_time, end_time, notes, created_by):
        self.connect()
        self.cursor.execute("""
            INSERT INTO staff_availability_overrides
            (username, override_date, override_type, is_available, start_time, end_time, notes, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (username, str(override_date), override_type, int(is_available),
              start_time, end_time, notes, created_by))
        self.conn.commit()
        self.close()
        return True

    def get_availability_overrides(self, username, from_date=None, to_date=None):
        self.connect()
        sql = "SELECT * FROM staff_availability_overrides WHERE username = ?"
        params = [username]
        if from_date:
            sql += " AND override_date >= ?"
            params.append(str(from_date))
        if to_date:
            sql += " AND override_date <= ?"
            params.append(str(to_date))
        sql += " ORDER BY override_date DESC"
        self.cursor.execute(sql, params)
        rows = [dict(r) for r in self.cursor.fetchall()]
        self.close()
        return rows

    def delete_availability_override(self, override_id):
        self.connect()
        self.cursor.execute("DELETE FROM staff_availability_overrides WHERE override_id = ?", (override_id,))
        self.conn.commit()
        self.close()
        return True

    def get_all_staff_availability_range(self, usernames, from_date, to_date):
        """
        Bulk availability computation for multiple staff over a date range.
        Returns {username: {date_str: {is_working, start_time, end_time, override_type, source}}}.
        Handles future patterns (a pattern whose anchor_date falls within the range).
        """
        if not usernames:
            return {}
        if isinstance(from_date, str):
            from_date = datetime.date.fromisoformat(from_date)
        if isinstance(to_date, str):
            to_date = datetime.date.fromisoformat(to_date)

        self.connect()
        ph = ','.join('?' for _ in usernames)
        today_str = str(datetime.date.today())

        # Promote any due future patterns first
        self.cursor.execute(
            f"SELECT DISTINCT username FROM staff_shift_patterns WHERE username IN ({ph}) AND status='future' AND anchor_date<=?",
            list(usernames) + [today_str]
        )
        to_promote = [r['username'] for r in self.cursor.fetchall()]
        self.close()
        for u in to_promote:
            self._promote_future_patterns(u)
        self.connect()

        # Load current AND future patterns (future ones may apply to future dates in the range)
        self.cursor.execute(
            f"SELECT * FROM staff_shift_patterns WHERE username IN ({ph}) AND status IN ('current','future')",
            list(usernames)
        )
        patterns_by_user = {}
        for row in self.cursor.fetchall():
            patterns_by_user.setdefault(row['username'], {})[row['status']] = dict(row)

        # Load shift days for all loaded patterns
        all_pattern_ids = [p['pattern_id'] for pu in patterns_by_user.values() for p in pu.values()]
        shift_days_by_pattern = {}
        if all_pattern_ids:
            ph2 = ','.join('?' for _ in all_pattern_ids)
            self.cursor.execute(
                f"SELECT * FROM staff_shift_days WHERE pattern_id IN ({ph2})", all_pattern_ids)
            for row in self.cursor.fetchall():
                shift_days_by_pattern.setdefault(row['pattern_id'], {})[(row['week_number'], row['day_of_week'])] = dict(row)

        # Load overrides in range
        self.cursor.execute(
            f"""SELECT * FROM staff_availability_overrides
                WHERE username IN ({ph}) AND override_date >= ? AND override_date <= ?
                ORDER BY created_at DESC""",
            list(usernames) + [str(from_date), str(to_date)]
        )
        overrides = {}
        for row in self.cursor.fetchall():
            overrides.setdefault((row['username'], row['override_date']), dict(row))
        self.close()

        def _apply_pattern(pattern, check_date):
            anchor = datetime.date.fromisoformat(pattern['anchor_date'])
            days_since = (check_date - anchor).days
            if days_since < 0:
                return {'is_working': None, 'source': 'before_start'}
            period = 7 if pattern['pattern_type'] == 'weekly' else 14
            day_in_period = days_since % period
            wk = (day_in_period // 7) + 1
            dow = day_in_period % 7
            shift = shift_days_by_pattern.get(pattern['pattern_id'], {}).get((wk, dow))
            if shift:
                return {'is_working': True, 'start_time': shift['start_time'],
                        'end_time': shift['end_time'], 'source': 'pattern'}
            return {'is_working': False, 'source': 'pattern'}

        result = {u: {} for u in usernames}
        current = from_date
        while current <= to_date:
            ds = str(current)
            for username in usernames:
                ov = overrides.get((username, ds))
                if ov:
                    result[username][ds] = {
                        'is_working': bool(ov['is_available']), 'start_time': ov['start_time'],
                        'end_time': ov['end_time'], 'override_type': ov['override_type'],
                        'notes': ov['notes'], 'source': 'override'
                    }
                    continue
                user_patterns = patterns_by_user.get(username, {})
                # Use future pattern if its anchor_date has arrived for this date
                future_pat = user_patterns.get('future')
                current_pat = user_patterns.get('current')
                if future_pat and current >= datetime.date.fromisoformat(future_pat['anchor_date']):
                    result[username][ds] = _apply_pattern(future_pat, current)
                elif current_pat:
                    result[username][ds] = _apply_pattern(current_pat, current)
                else:
                    result[username][ds] = {'is_working': None, 'source': 'none'}
            current += datetime.timedelta(days=1)
        return result

    def get_setting(self, key, default_value=""):
        self.connect()
        self.cursor.execute("SELECT setting_value FROM system_settings WHERE setting_key = ?", (key,))
        row = self.cursor.fetchone()
        self.close()
        return row['setting_value'] if row else default_value

    def update_setting(self, key, value):
        self.connect()
        self.cursor.execute("REPLACE INTO system_settings (setting_key, setting_value) VALUES (?, ?)", (key, value))
        self.conn.commit()
        self.close()
        return True

    # ==========================================
    # 3. DYNAMIC REPORTING (The View)
    # ==========================================
    
    def get_patient_directory(self):
        self.connect()
        self.cursor.execute("SELECT field_name FROM field_definitions ORDER BY ordinal_position")
        defined_fields = [row['field_name'] for row in self.cursor.fetchall()]

        sql = """
            SELECT ph.patient_id, ph.field_name, ph.field_value
            FROM patient_history ph
            INNER JOIN (
                SELECT patient_id, field_name, MAX(change_date) as latest_date
                FROM patient_history
                GROUP BY patient_id, field_name
            ) latest ON ph.patient_id = latest.patient_id 
                    AND ph.field_name = latest.field_name 
                    AND ph.change_date = latest.latest_date
        """
        self.cursor.execute(sql)
        rows = self.cursor.fetchall()

        patients = {}
        for row in rows:
            pid = row['patient_id']
            if pid not in patients:
                patients[pid] = {field: "" for field in defined_fields}
                patients[pid]['patient_id'] = pid
            patients[pid][row['field_name']] = row['field_value']

        self.close()
        return list(patients.values())

    # ==========================================
    # 4. DUMMY DATA GENERATOR
    # ==========================================
    
    def populate_dummy_data(self):
        print("--- Generating Dummy Data ---")
        dummy_patients = [
            {"first_name": "John", "last_name": "Doe", "date_of_birth": "1980-05-12", "phone": "07700900123", "blood_group": "O+"},
            {"first_name": "Sarah", "last_name": "Smith", "middle_names": "Jane", "address_town": "London", "email": "sarah.s@example.com"},
            {"first_name": "Robert", "last_name": "Jones", "address_line_1": "123 High St", "blood_group": "A-"}
        ]

        for i, p_data in enumerate(dummy_patients):
            new_pid = i + 1 
            for field, value in p_data.items():
                self.log_patient_change(new_pid, field, value, "System_Init", "Initial Import")
        
        print("Dummy data generation complete.")

if __name__ == "__main__":
    crm = ClinicCRM()
    crm.initialize_database()