import streamlit as st
from datetime import datetime
import hashlib
from constants import APPT_SCHEDULED

def go_to_lobby():
    st.session_state.page = "Lobby"
    st.session_state.selected_patient_id = None
    st.session_state.edit_mode = False
    st.rerun()

def go_to_patient(patient_id):
    st.session_state.selected_patient_id = patient_id
    st.session_state.page = "Dashboard"
    st.session_state.edit_mode = False # Always start in Read-Only
    st.rerun()

def get_patient_details(pid, crm):
    """Fetch flattened patient data."""
    directory = crm.get_patient_directory()
    return next((p for p in directory if p['patient_id'] == pid), None)

def get_patient_encounters(pid, crm):
    """Fetch encounters (formerly visits) for the tabs."""
    crm.connect()
    sql = """
        SELECT encounter_id, patient_id, encounter_date, encounter_type, created_by AS practitioner 
        FROM encounters 
        WHERE patient_id = ? 
        ORDER BY encounter_date DESC
    """
    crm.cursor.execute(sql, (pid,))
    encounters = crm.cursor.fetchall()
    crm.close()
    return encounters

def get_patient_notes(pid, crm):
    """Fetch all notes for a patient by joining with the Encounters table."""
    crm.connect()
    sql = """
        SELECT e.encounter_date, en.note_text, en.created_by AS practitioner, e.encounter_type 
        FROM encounter_notes en
        JOIN encounters e ON en.encounter_id = e.encounter_id
        WHERE e.patient_id = ?
        ORDER BY e.encounter_date DESC
    """
    crm.cursor.execute(sql, (pid,))
    data = crm.cursor.fetchall()
    crm.close()
    return data

def get_patient_tests(pid, crm):
    """Fetch test results joined with definitions (Updated for new lifecycle)."""
    crm.connect()
    # Indices map: 0:date, 1:name, 2:value, 3:unit, 4:group, 5:config, 6:note, 7:target, 8:chart, 9:result_id,
    #              10:status, 11:test_taken_on, 12:test_taken_by, 13:test_taken_note, 14:result_received_on,
    #              15:result_logged_by, 16:trend_chart_type
    sql = """
        SELECT
            e.encounter_date,
            tr.test_name,
            tr.test_value,
            td.unit,
            COALESCE(tg.group_name, td.test_group, tr.test_name) AS test_group,
            td.chart_config,
            tr.result_note,
            td.default_target AS display_target,
            COALESCE(tg.chart_type, td.chart_type, 'gauge') AS chart_type,
            tr.result_id,
            tr.status,
            tr.test_taken_on,
            tr.test_taken_by,
            tr.test_taken_note,
            tr.result_received_on,
            tr.result_logged_by,
            COALESCE(tg.trend_chart_type, 'line') AS trend_chart_type
        FROM test_results tr
        JOIN encounters e ON tr.encounter_id = e.encounter_id
        LEFT JOIN test_definitions td ON tr.test_name = td.test_name
        LEFT JOIN test_groups tg ON td.group_id = tg.group_id
        WHERE e.patient_id = ?
        ORDER BY tr.test_taken_on DESC
    """
    crm.cursor.execute(sql, (pid,))
    data = crm.cursor.fetchall()
    crm.close()
    return data

def get_field_definitions(crm):
    crm.connect()
    crm.cursor.execute("SELECT field_name, field_display_name, field_group, display_role FROM field_definitions ORDER BY ordinal_position")
    data = crm.cursor.fetchall()
    crm.close()
    return data

def calculate_age(dob_str):
    try:
        dob = datetime.strptime(dob_str, "%Y-%m-%d")
        today = datetime.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except:
        return "N/A"

def get_notes_for_encounter(encounter_id, crm):
    """Formerly get_notes_for_visit"""
    crm.connect()
    encounter_id = int(encounter_id) 
    
    sql = "SELECT note_text FROM encounter_notes WHERE encounter_id = ?"
    crm.cursor.execute(sql, (encounter_id,))
    data = crm.cursor.fetchall()
    crm.close()
    return [d[0] for d in data]

def get_patient_appointments(pid, crm):
    """Fetch all appointments for a patient, sorting future ones first."""
    crm.connect()
    sql = """
        SELECT appointment_id, appointment_date, appointment_time, provider, reason, status
        FROM appointments
        WHERE patient_id = ?
        ORDER BY 
            CASE WHEN appointment_date >= DATE('now', 'localtime') THEN 0 ELSE 1 END ASC,
            CASE WHEN appointment_date >= DATE('now', 'localtime') THEN appointment_date END ASC,
            CASE WHEN appointment_date >= DATE('now', 'localtime') THEN appointment_time END ASC,
            appointment_date DESC,
            appointment_time DESC
    """
    crm.cursor.execute(sql, (pid,))
    appts = crm.cursor.fetchall()
    crm.close()
    return appts

def log_report_generation(pid, crm, start_d, end_d, included_tests, overrides, raw_data, practitioner_statement, next_steps, current_user):
    """Saves report metadata and line items to the DB, now including statements."""
    crm.connect()
    
    # 1. Insert Header with new statement fields
    sql_header = """
        INSERT INTO report_log (patient_id, report_start_date, report_end_date, created_by, practitioner_statement, next_steps)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    crm.cursor.execute(sql_header, (pid, str(start_d), str(end_d), current_user, practitioner_statement, next_steps))
    report_id = crm.cursor.lastrowid
    
    # 2. Insert Items
    items_to_insert = []
    
    for test_name in included_tests:
        note_included = 1
        note_text = "" 
        is_override = 0
        
        specific_history = [t for t in raw_data if t[1] == test_name]
        specific_history.sort(key=lambda x: x[0], reverse=True)
        original_note = specific_history[0][6] if specific_history else ""
        
        if test_name in overrides:
            user_val = overrides[test_name]
            if user_val == "EXCLUDE":
                note_included = 0
                note_text = None
            else:
                note_included = 1
                note_text = user_val
                if user_val != original_note:
                    is_override = 1
        else:
            note_included = 1
            note_text = original_note
            is_override = 0
            
        items_to_insert.append((report_id, test_name, note_included, note_text, is_override))
        
    sql_items = """
        INSERT INTO report_contents (report_id, test_name, note_included, note_text, is_override)
        VALUES (?, ?, ?, ?, ?)
    """
    crm.cursor.executemany(sql_items, items_to_insert)
    
    crm.conn.commit()
    crm.close()
    return report_id

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_credentials(crm, username, password):
    crm.connect()
    crm.cursor.execute("SELECT password_hash, role FROM staff WHERE username = ?", (username,))
    record = crm.cursor.fetchone()
    crm.close()
    
    if record:
        stored_hash = record['password_hash']
        role = record['role']
        input_hash = hash_password(password)
        if input_hash == stored_hash:
            return True, role
    return False, None

def login_screen(crm):
    import time 
    login_placeholder = st.empty()
    
    with login_placeholder.container():
        for _ in range(4):
            st.write("")

        col_left, col_center, col_right = st.columns([1, 1.5, 1])
        
        with col_center:
            with st.container(border=True):
                st.markdown("<h1 style='text-align: center;'>🏥 Jack's Clinic</h1>", unsafe_allow_html=True)
                st.markdown("<h4 style='text-align: center; color: #666666;'>Secure Staff Login</h4>", unsafe_allow_html=True)
                st.divider()
                
                with st.form("login_form"):
                    user = st.text_input("Username", placeholder="e.g., admin")
                    pwd = st.text_input("Password", type="password", placeholder="••••••••")
                    
                    submit = st.form_submit_button("Log In", type="primary", use_container_width=True)
                    
    if submit:
        is_valid, role = check_credentials(crm, user, pwd)
        if is_valid:
            login_placeholder.empty()
            with st.spinner("Authenticating and loading command center..."):
                time.sleep(0.6) 
                st.session_state['logged_in'] = True
                st.session_state['username'] = user
                st.session_state['role'] = role
                st.session_state.page = "Lobby"
                st.rerun()
        else:
            st.error("Invalid username or password.")

def get_clinic_schedule(crm, start_date, end_date):
    crm.connect()
    sql = """
        SELECT appointment_id, patient_id, appointment_date, appointment_time, provider, reason
        FROM appointments
        WHERE appointment_date >= ? AND appointment_date <= ? AND status = ?
        ORDER BY appointment_date ASC, appointment_time ASC
    """
    crm.cursor.execute(sql, (str(start_date), str(end_date), APPT_SCHEDULED))
    appts = crm.cursor.fetchall()
    crm.close()

    if not appts:
        return []

    directory = crm.get_patient_directory()
    name_map = {p['patient_id']: f"{p.get('first_name','')} {p.get('last_name','')}" for p in directory}
    
    schedule = []
    for a in appts:
        schedule.append({
            "Date": a['appointment_date'],
            "Time": a['appointment_time'],
            "Patient": name_map.get(a['patient_id'], f"Unknown (ID: {a['patient_id']})"),
            "Provider": a['provider'],
            "Reason": a['reason'],
            "Patient ID": a['patient_id'] 
        })
        
    return schedule