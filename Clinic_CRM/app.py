import streamlit as st
import pandas as pd
import os
import time
import sqlite3
from datetime import datetime, timedelta, date
from modules.clinic_crm import ClinicCRM
from streamlit_sortables import sort_items
from modules.reports import create_custom_report_pdf
from app_functions import (
    go_to_lobby, go_to_patient, get_patient_details, get_patient_encounters, get_patient_notes,
    get_patient_tests, get_field_definitions, calculate_age, get_notes_for_encounter, log_report_generation,
    hash_password, check_credentials, login_screen, get_patient_appointments, get_clinic_schedule
)
from constants import (
    APPT_SCHEDULED, APPT_COMPLETED, APPT_NO_SHOW, APPT_CANCELLED,
    TEST_PENDING, TEST_COMPLETE
)
import json
import base64

# --- PAGE CONFIG ---
st.set_page_config(page_title="Family Clinic CRM", layout="wide", page_icon="🏥", initial_sidebar_state="collapsed")

# --- INITIALIZATION ---
@st.cache_resource
def get_crm():
    crm = ClinicCRM()
    crm.initialize_database()
    return crm

crm = get_crm()

# --- DB-DRIVEN CONFIGURATION (single source of truth via system_settings) ---
ENCOUNTER_TYPES   = json.loads(crm.get_setting("encounter_types",  '["Clinical Encounter", "Telephone Consult", "Admin/Chart Review"]'))
STAFF_ROLES       = json.loads(crm.get_setting("staff_roles",      '["Staff", "Admin"]'))
ADMIN_ROLES       = json.loads(crm.get_setting("admin_roles",      '["Admin"]'))
MAX_SCHEDULE_DAYS = int(crm.get_setting("max_schedule_days", "7"))

# Available fonts: built-in PDF fonts + any .ttf files present in assets/fonts/
_BUILTIN_FONTS = ["Helvetica", "Times", "Courier"]
_font_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")
_custom_fonts = sorted(
    set(os.path.splitext(f)[0].replace("-Regular", "").replace("-Bold", "").replace("-Italic", "")
        for f in os.listdir(_font_dir) if f.endswith(".ttf"))
) if os.path.isdir(_font_dir) else []
AVAILABLE_FONTS = _BUILTIN_FONTS + [f for f in _custom_fonts if f not in _BUILTIN_FONTS]

# Patient header field roles (drives lobby + dashboard header — no hardcoded field names)
_field_defs = get_field_definitions(crm)
_NAME_FIELDS    = [f['field_name'] for f in _field_defs if f['display_role'] == 'name']
_CAPTION_FIELDS = [(f['field_name'], f['field_display_name']) for f in _field_defs if f['display_role'] == 'caption']

# --- SESSION STATE MANAGEMENT ---
if "page" not in st.session_state:
    st.session_state.page = "Lobby" 
if "selected_patient_id" not in st.session_state:
    st.session_state.selected_patient_id = None
if "edit_mode" not in st.session_state:
    st.session_state.edit_mode = False 
if "shutdown_mode" not in st.session_state:
    st.session_state.shutdown_mode = False

# --- SHUTDOWN SCREEN ---
if st.session_state.shutdown_mode:
    st.markdown("""
        <div style='text-align: center; padding-top: 50px;'>
            <h1 style='color: #2E8B57;'>✅ System Shutdown Complete</h1>
            <h3>It is safe to close this window.</h3>
        </div>
    """, unsafe_allow_html=True)
    time.sleep(3)
    os._exit(0)

# --- THE GATEKEEPER & GLOBAL SIDEBAR ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

with st.sidebar:
    st.title("🏥 System Menu")
    if st.session_state['logged_in']:
        st.write(f"👤 **{st.session_state.get('username', '')}**")
        st.caption(f"Role: {st.session_state.get('role', 'Unknown')}")
        
        if st.button("Log Out", use_container_width=True):
            for key in ['logged_in', 'role', 'username', 'page', 'selected_patient_id']:
                if key in st.session_state: del st.session_state[key]
            st.rerun()
            
        if st.session_state.get('role') in ADMIN_ROLES:
            st.divider()
            st.subheader("⚙️ Admin Tools")
            if st.button("⚙️ Admin Console", use_container_width=True):
                st.session_state.page = "Admin Console"
                st.rerun()
                
    st.divider()
    if st.button("🔴 Shutdown System", use_container_width=True):
        st.session_state.shutdown_mode = True
        st.rerun()

if not st.session_state['logged_in']:
    login_screen(crm)
    st.stop()

# =========================================================
#  PART 1: THE LOBBY (Command Center)
# =========================================================

if st.session_state.page == "Lobby":
    header_col1, header_col2 = st.columns([3, 1])
    with header_col1:
        st.title("🏥 Jack's Clinic Dashboard")
        st.caption(f"Welcome back. Today is {datetime.today().strftime('%A, %B %d, %Y')}.")
    with header_col2:
        st.write("") 
        if st.button("➕ Register New Patient", type="primary", use_container_width=True):
            st.session_state.selected_patient_id = "NEW"
            st.session_state.page = "Dashboard"
            st.session_state.edit_mode = True
            st.rerun()

    st.divider()
    col_main, col_side = st.columns([1, 1], gap="large")
    
    with col_main:
        st.subheader("📋 Patient Directory")
        search_query = st.text_input("🔍 Find a Patient", placeholder="Search by Name, Phone, Postcode...")
        
        if search_query:
            full_data = crm.get_patient_directory()
            results = [p for p in full_data if search_query.lower() in str(p.values()).lower()]
            
            if results:
                st.success(f"Found {len(results)} patients matching '{search_query}'.")
                for p in results:
                    with st.container(border=True):
                        c1, c2, c3, c4 = st.columns([1, 2, 2, 1])
                        c1.write(f"**ID:** {p['patient_id']}")
                        patient_name = ' '.join(filter(None, (p.get(f, '') for f in _NAME_FIELDS)))
                        c2.write(f"**{patient_name}**")
                        caption_parts = [f"{label}: {p.get(fn, 'N/A')}" for fn, label in _CAPTION_FIELDS]
                        c3.write(' | '.join(caption_parts))
                        if c4.button("Open", key=f"btn_{p['patient_id']}", use_container_width=True):
                            go_to_patient(p['patient_id'])
            else:
                st.warning("No patients found.")
        else:
            st.info("Start typing in the search bar above to find a patient record.")

    with col_side:
        c_title, c_filter = st.columns([1.5, 1])
        c_title.subheader("📅 Schedule")
        schedule_filter = c_filter.selectbox("Timeframe", ["Today", "Tomorrow", "Next 7 Days", "Custom Range"], label_visibility="collapsed")
        
        today_date = date.today()
        start_d, end_d = None, None
        
        if schedule_filter == "Today": start_d, end_d = today_date, today_date
        elif schedule_filter == "Tomorrow": start_d, end_d = today_date + timedelta(days=1), today_date + timedelta(days=1)
        elif schedule_filter == "Next 7 Days": start_d, end_d = today_date, today_date + timedelta(days=MAX_SCHEDULE_DAYS - 1)
        elif schedule_filter == "Custom Range":
            custom_dates = st.date_input("Select Date Range", value=(today_date, today_date + timedelta(days=3)), format="DD/MM/YYYY")
            if len(custom_dates) == 2:
                if (custom_dates[1] - custom_dates[0]).days > MAX_SCHEDULE_DAYS: st.warning(f"⚠️ Please select a range of {MAX_SCHEDULE_DAYS} days or fewer.")
                else: start_d, end_d = custom_dates
            else: st.info("Please select an end date.")
            
        if start_d and end_d:
            appts = get_clinic_schedule(crm, start_d, end_d)
            if appts:
                df_schedule = pd.DataFrame(appts)
                df_schedule['Date'] = pd.to_datetime(df_schedule['Date']).dt.strftime('%d/%m/%Y')
                hide_cols = {"Patient ID": None, "Date": None if start_d == end_d else st.column_config.TextColumn("Date", width="small")}
                st.dataframe(df_schedule, hide_index=True, use_container_width=True, column_config=hide_cols, height=400)
            else:
                st.success("No appointments scheduled for this timeframe.")


# =========================================================
#  PART 2: THE PATIENT DASHBOARD (The EHR View)
# =========================================================

elif st.session_state.page == "Dashboard":
    pid = st.session_state.selected_patient_id
    is_new_patient = (pid == "NEW")
    
    if is_new_patient:
        patient_data = {}
        st.warning("🆕 CREATING NEW PATIENT RECORD")
    else:
        patient_data = get_patient_details(pid, crm)
        if not patient_data:
            st.error("Patient not found."); st.stop()

    top_c1, top_c2 = st.columns([6, 1])
    with top_c1:
        if not is_new_patient:
            patient_name = ' '.join(filter(None, (patient_data.get(f, '') for f in _NAME_FIELDS)))
            st.markdown(f"## 👤 {patient_name}")
            caption_parts = [f"ID: {pid}"] + [f"{label}: {patient_data.get(fn, 'Unknown')}" for fn, label in _CAPTION_FIELDS]
            st.caption(' | '.join(caption_parts))
        else:
            st.title("👤 New Patient Registration")
    with top_c2:
        if st.button("⬅ Lobby"): go_to_lobby()

    st.divider()
    row1_c1, row1_c2 = st.columns([1, 2])

    # -----------------------------------------------------
    # LEFT COLUMN: DEMOGRAPHICS
    # -----------------------------------------------------
    with row1_c1:
        st.subheader("📋 Patient Details")
        if not is_new_patient:
            if not st.session_state.edit_mode:
                if st.button("✏️ Edit Details", use_container_width=True):
                    st.session_state.edit_mode = True; st.rerun()
            else:
                st.info("📝 Editing Mode Active")
        
        field_defs = get_field_definitions(crm)
        groups = sorted(list(set(f['field_group'] for f in field_defs)))
        
        if st.session_state.edit_mode:
            with st.form("patient_edit_form"):
                form_values = {}
                for group in groups:
                    st.markdown(f"**{group.capitalize()}**")
                    for field in [f for f in field_defs if f['field_group'] == group]:
                        f_key, f_label = field['field_name'], field['field_display_name']
                        form_values[f_key] = st.text_input(f_label, value=str(patient_data.get(f_key, "")))
                    st.write("") 

                c_save, c_cancel = st.columns(2)
                if c_save.form_submit_button("💾 Save Changes", type="primary"):
                    target_id, saved_id = (None, None) if is_new_patient else (pid, pid)
                    for k, v in form_values.items():
                        if v != patient_data.get(k, "") or is_new_patient:
                            if v.strip(): 
                                new_id = crm.log_patient_change(target_id, k, v, st.session_state['username'], "Dashboard Update")
                                if not saved_id: saved_id = new_id
                                target_id = saved_id 
                    st.session_state.selected_patient_id = saved_id
                    st.session_state.edit_mode = False; st.rerun()
                if c_cancel.form_submit_button("Cancel"):
                    st.session_state.edit_mode = False
                    if is_new_patient: go_to_lobby()
                    st.rerun()
        else:
            for group in groups:
                with st.expander(group.capitalize(), expanded=True):
                    for field in [f for f in field_defs if f['field_group'] == group]:
                        st.markdown(f"**{field['field_display_name']}:** {patient_data.get(field['field_name'], '-')}")

        if not is_new_patient and not st.session_state.edit_mode:
            st.divider()
            if "confirm_delete" not in st.session_state: st.session_state.confirm_delete = False
            if st.button("🗑️ Delete Patient Record", type="secondary"): st.session_state.confirm_delete = True
            if st.session_state.confirm_delete:
                st.error("⚠️ Are you sure? This will archive all history.")
                dc1, dc2 = st.columns(2)
                if dc1.button("Yes, Delete"):
                    crm.delete_patient_history_completely(pid, st.session_state['username'])
                    go_to_lobby()
                if dc2.button("Cancel Delete"):
                    st.session_state.confirm_delete = False; st.rerun()

    # -----------------------------------------------------
    # RIGHT COLUMN: CLINICAL HISTORY
    # -----------------------------------------------------
    with row1_c2:
        if is_new_patient:
            st.info("Save the patient details to unlock Clinical Notes.")
        else:
            st.subheader("🩺 Clinical History")
            tab_encounters, tab_notes, tab_tests, tab_report, tab_appointments = st.tabs(
                ["Encounters", "Notes", "Test Results", "Report Builder", "Appointments"]
            )
            
            # --- TAB 1: ENCOUNTERS ---
            with tab_encounters:
                encounters = get_patient_encounters(pid, crm)
                if encounters:
                    df_e = pd.DataFrame(encounters, columns=['ID', 'PatID', 'Date', 'Type', 'Practitioner'])
                    selection = st.dataframe(
                        df_e, hide_index=True, use_container_width=True, selection_mode="single-row", on_select="rerun",
                        column_config={
                            "ID": None, "PatID": None, 
                            "Date": st.column_config.DateColumn("Date"),
                            "Type": st.column_config.TextColumn("Type"),
                            "Practitioner": st.column_config.TextColumn("Practitioner")
                        }
                    )
                    
                    if selection.selection.rows:
                        selected_index = selection.selection.rows[0]
                        enc_id = int(df_e.iloc[selected_index]['ID'])
                        st.divider()
                        st.markdown(f"#### 🔎 Encounter Details: {df_e.iloc[selected_index]['Date']} ({df_e.iloc[selected_index]['Type']})")
                        specific_notes = get_notes_for_encounter(enc_id, crm)
                        if specific_notes:
                            for note in specific_notes: st.info(f"📝 {note}")
                        else: st.warning("No notes found for this encounter.")
                else:
                    st.info("No previous encounters recorded.")

            # --- TAB 2: NOTES ---
            with tab_notes:
                with st.expander("➕ Add Clinical Note", expanded=False):
                    with st.form("add_note_form", clear_on_submit=True):
                        enc_type = st.selectbox("Encounter Type", ENCOUNTER_TYPES)
                        new_note = st.text_area("Write note here...", height=150)
                        if st.form_submit_button("💾 Save Note", type="primary"):
                            if new_note.strip():
                                crm.add_clinical_note(pid, new_note.strip(), st.session_state['username'], enc_type)
                                st.success("Note saved!"); st.rerun()
                            else: st.warning("Note cannot be empty.")
                
                st.divider()
                notes = get_patient_notes(pid, crm)
                if notes:
                    for n in notes:
                        st.markdown(f"**{n['encounter_date']}** — *{n['practitioner']}* ({n['encounter_type']})")
                        st.info(n['note_text'])
                else: st.caption("No clinical notes found.")

            # --- TAB 3: TEST RESULTS ---
            with tab_tests:
                # 1. Fetch Tests
                crm.connect()
                crm.cursor.execute("""
                    SELECT
                        td.test_name,
                        COALESCE(tg.group_name, td.test_group) AS test_group,
                        td.unit,
                        COALESCE(tg.chart_type, td.chart_type) AS chart_type,
                        COALESCE(tg.description, '') AS description
                    FROM test_definitions td
                    LEFT JOIN test_groups tg ON td.group_id = tg.group_id
                    WHERE td.is_active = 1
                    ORDER BY test_group, test_name
                """)
                test_defs = crm.cursor.fetchall()
                crm.close()
                
                from collections import defaultdict
                test_groups = defaultdict(list)
                for t in test_defs:
                    grp = t['test_group'] if t['test_group'] else t['test_name']
                    test_groups[grp].append(t)
                group_list = sorted(list(test_groups.keys()))
                
                # --- ADD TEST FORM ---
                with st.expander("➕ Add / Order New Test", expanded=False):
                    st.info("💡 **Tip:** Leave the 'Result Value' blank to save the test as Pending.")
                    selected_group = st.selectbox("Select Test Panel / Group", options=group_list)
                    _group_desc = test_groups[selected_group][0]['description'] if test_groups.get(selected_group) and test_groups[selected_group][0]['description'] else None
                    if _group_desc:
                        st.caption(_group_desc)
                    enc_type_test = st.selectbox("Encounter Type (for the order)", ENCOUNTER_TYPES)
                    
                    with st.form(f"add_test_form"):
                        st.markdown(f"**Enter data for: {selected_group}**")
                        input_vals, input_notes = {}, {}
                        
                        for child in test_groups[selected_group]:
                            t_name, t_unit, t_chart = child['test_name'], child['unit'], child['chart_type']
                            p_holder = "e.g., 120/80" if t_chart == 'bp_range' else "e.g., 5.2"
                            c1, c2 = st.columns(2)
                            input_vals[t_name] = c1.text_input(f"Result Value: {t_name} ({t_unit})", placeholder=p_holder)
                            input_notes[t_name] = c2.text_input(f"Note for {t_name}", key=f"note_{t_name}", placeholder="Optional note...")
                        
                        with st.expander("⚙️ Advanced Metadata Overrides"):
                            c_date, c_user = st.columns(2)
                            ov_date = c_date.date_input("Test Taken Date", value=datetime.today())
                            ov_time = c_date.time_input("Test Taken Time", value=datetime.now().time())
                            ov_taken_by = c_user.text_input("Test Taken By", value=st.session_state['username'])
                        
                        if st.form_submit_button("💾 Save Test(s)", type="primary"):
                            taken_datetime = f"{ov_date} {ov_time.strftime('%H:%M:%S')}"
                            is_user_overridden = (ov_taken_by != st.session_state['username'])
                            saved_count = 0
                            
                            for child in test_groups[selected_group]:
                                t_name = child['test_name']
                                val = input_vals[t_name].strip()
                                note = input_notes[t_name].strip()
                                
                                # Only process if they entered *something* (either a value or a note)
                                if val or note:
                                    # Implicit smart mirroring for results if value is provided
                                    result_date = taken_datetime if val else None
                                    result_user = ov_taken_by if val else None
                                    
                                    crm.add_test_result(
                                        patient_id=pid, test_name=t_name, test_taken_on=taken_datetime,
                                        test_taken_by=ov_taken_by, is_taken_by_override=is_user_overridden,
                                        test_taken_note=note if not val else "", # If resulting immediately, note goes to result
                                        test_value=val, result_received_on=result_date, result_logged_by=result_user,
                                        is_result_logged_by_override=is_user_overridden, result_note=note if val else "",
                                        current_user=st.session_state['username'], encounter_type=enc_type_test
                                    )
                                    saved_count += 1
                                    
                            if saved_count > 0: st.success(f"Saved {saved_count} test(s)!"); st.rerun()
                            else: st.warning("Enter at least a value or a note to save.")

                st.divider()

                # --- DISPLAY TESTS (With Pending/Complete Filter) ---
                tests = get_patient_tests(pid, crm)
                if tests:
                    filter_status = st.radio("Filter Tests:", ["All", TEST_PENDING, TEST_COMPLETE], horizontal=True)
                    
                    # Indices mapped from get_patient_tests
                    filtered_tests = []
                    for t in tests:
                        if filter_status == "All" or t[10] == filter_status:
                            filtered_tests.append(t)
                            
                    if filtered_tests:
                        # Build clean dataframe for display
                        # Build clean dataframe for display
                        df_t = pd.DataFrame(filtered_tests, columns=[
                            'Date', 'Test', 'Value', 'Unit', 'Group', 'Config', 'ResultNote', 'Target', 'Chart',
                            'ResultID', 'Status', 'TakenOn', 'TakenBy', 'TakenNote', 'RecOn', 'LogBy', 'TrendChart'
                        ])
                        
                        st.dataframe(
                            df_t, hide_index=True, use_container_width=True, height=300,
                            # Use column_order to visually place "Group" right next to "Test Name"
                            column_order=("Date", "Group", "Test", "Value", "Unit", "Status", "ResultNote"),
                            column_config={
                                "Date": st.column_config.TextColumn("Ordered/Taken", width="small"),
                                "Group": st.column_config.TextColumn("Test Panel", width="medium"), # <--- NOW VISIBLE
                                "Test": st.column_config.TextColumn("Specific Test", width="medium"),
                                "Value": st.column_config.TextColumn("Result", width="small"),
                                "Unit": st.column_config.TextColumn("Unit", width="small"),
                                "Status": st.column_config.TextColumn("Status", width="small"),
                                "ResultNote": st.column_config.TextColumn("Note", width="large"),
                                # Hide internal tracking fields from the main grid view
                                "Config": None, "Target": None, "Chart": None, "ResultID": None,
                                "TakenOn": None, "TakenBy": None, "TakenNote": None, "RecOn": None, "LogBy": None
                            }
                        )
                        
                        # --- PENDING RESOLUTION UI ---
                        pending_df = df_t[df_t['Status'] == TEST_PENDING]
                        if not pending_df.empty:
                            st.divider()
                            st.subheader("⏳ Resolve Pending Tests")
                            
                            pending_dict = {row['ResultID']: f"{row['Test']} (Ordered: {row['Date']} by {row['TakenBy']})" for _, row in pending_df.iterrows()}
                            sel_pending_id = st.selectbox("Select Test to Result", options=list(pending_dict.keys()), format_func=lambda x: pending_dict[x])
                            
                            with st.form("resolve_pending_form", clear_on_submit=True):
                                c1, c2 = st.columns(2)
                                new_val = c1.text_input("Result Value")
                                new_note = c2.text_input("Result Note (Optional)")
                                
                                if st.form_submit_button("✅ Mark Complete", type="primary"):
                                    if new_val.strip():
                                        crm.update_test_result(
                                            result_id=sel_pending_id, test_value=new_val.strip(), 
                                            result_received_on=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                            result_logged_by=st.session_state['username'],
                                            is_result_logged_by_override=False, result_note=new_note.strip()
                                        )
                                        st.success("Test Resolved!"); st.rerun()
                                    else:
                                        st.warning("Please enter a result value.")
                    else:
                        st.info(f"No {filter_status.lower()} tests found.")
                else:
                    st.caption("No test records found.")

            # --- TAB 4: REPORT BUILDER ---
            with tab_report:
                tests = get_patient_tests(pid, crm)
                # Only include Complete tests in the report
                complete_tests = [t for t in tests if t[10] == TEST_COMPLETE]
                
                if complete_tests:
                    st.header("📄 Custom Report Builder")
                    
                    # --- INSTRUCTION 1: DATES ---
                    st.info("⬇️ **Instructions:** Select the timeframe of the Test Results to be included.")
                    
                    all_dates = [datetime.strptime(t[0].split()[0], "%Y-%m-%d").date() for t in complete_tests]
                    c1, c2 = st.columns(2)
                    start_d = c1.date_input("Report Start Date", min(all_dates))
                    end_d = c2.date_input("Report End Date", max(all_dates))
                    
                    filtered_data = [t for t in complete_tests if start_d <= datetime.strptime(t[0].split()[0], "%Y-%m-%d").date() <= end_d]
                    
                    if filtered_data:
                        st.divider()
                        
                        # --- INSTRUCTION 2: OPENING STATEMENT ---
                        st.info("⬇️ **Instructions:** Add an introductory statement. This will appear at the top of the report.")
                        practitioner_statement = st.text_area("Practitioner's Opening Statement", height=100)
                        
                        st.divider()
                        
                        # --- INSTRUCTION 3: DRAG AND DROP ---
                        st.info("⬇️ **Instructions:** Drag the Test Groups into the order they should appear.")
                        unique_groups = sorted(list(set([t[4] for t in filtered_data])))
                        sortable_data = [{'header': '✅ Included Test Groups', 'items': unique_groups}, {'header': '🗑️ Excluded', 'items': []}]
                        sorted_results = sort_items(sortable_data, multi_containers=True)
                        final_order = sorted_results[0]['items']
                        
                        if final_order:
                            st.divider()
                            
                            # --- INSTRUCTION 4: NOTES EDITOR ---
                            st.info("⬇️ **Instructions:** Review & edit notes for each included specific test. Uncheck 'Note' to exclude.")
                            notes_data = []
                            for group_name in final_order:
                                group_history = [t for t in filtered_data if t[4] == group_name]
                                unique_tests = sorted(list(set([t[1] for t in group_history])))
                                for t_name in unique_tests:
                                    th = [t for t in group_history if t[1] == t_name]
                                    th.sort(key=lambda x: x[0], reverse=True)
                                    curr_note = th[0][6] if th[0][6] else ""
                                    notes_data.append({"Group": group_name, "Test": t_name, "Include Note": True, "Note Text": curr_note})
                            
                            edited_notes_df = st.data_editor(
                                pd.DataFrame(notes_data), 
                                hide_index=True, 
                                use_container_width=True, 
                                key="notes_editor",
                                column_config={
                                    "Group": st.column_config.TextColumn("Test Panel", disabled=True, width="small"),
                                    "Test": st.column_config.TextColumn("Specific Test", disabled=True, width="medium"),
                                    "Include Note": st.column_config.CheckboxColumn("Note", width="small"), 
                                    "Note Text": st.column_config.TextColumn("Edit Note Content", width="large")
                                }
                            )
                            
                            st.divider()
                            
                            # --- INSTRUCTION 5: CLOSING STATEMENT ---
                            st.info("⬇️ **Instructions:** Add closing remarks and next steps.")
                            next_steps = st.text_area("Next Steps & Recommendations (Closing)", height=100)
                            st.divider()

                            # -- GENERATE AND CALLBACK LOGGING --
                            final_config = [{'test': t} for t in final_order]
                            overrides = {}
                            for index, row in edited_notes_df.iterrows():
                                if not row['Include Note']: overrides[row['Test']] = "EXCLUDE"
                                elif row['Note Text'] != notes_data[index]['Note Text']: overrides[row['Test']] = row['Note Text']
                                else: overrides[row['Test']] = row['Note Text']

                            saved_theme = crm.get_setting("report_theme")
                            try: live_theme = json.loads(saved_theme) if saved_theme else None
                            except: live_theme = None
                            
                            pdf_bytes = create_custom_report_pdf(
                                get_patient_details(pid, crm), filtered_data, final_config, overrides,
                                start_d, end_d, practitioner_statement.strip(), next_steps.strip(),
                                crm.get_setting("report_footer", "Confidential Report"),
                                creator_name=st.session_state.get('username', 'System'), theme_config=live_theme
                            )

                            # --- CALLBACK FUNCTION FOR DOWNLOAD ---
                            def handle_download():
                                new_id = log_report_generation(
                                    pid, crm, start_d, end_d, final_order, overrides, filtered_data,
                                    practitioner_statement.strip(), next_steps.strip(), st.session_state['username']
                                )
                                # Streamlit callbacks can't easily print st.success directly here without weird state issues,
                                # but the database logging is guaranteed.
                            
                            st.download_button(
                                label="🚀 Download PDF & Log to Patient Record", 
                                data=pdf_bytes, 
                                file_name=f"Report_{pid}_{datetime.now().strftime('%Y%m%d')}.pdf", 
                                mime="application/pdf",
                                on_click=handle_download,
                                type="primary"
                            )
                        else: st.warning("Please include at least one test.")
                    else: st.warning("No tests found in this date range.")
                else: st.info("No completed tests available for reporting.")

            # --- TAB 5: APPOINTMENTS ---
            with tab_appointments:
                st.header("📅 Appointments")
                with st.expander("➕ Schedule New Appointment", expanded=False):
                    with st.form("new_appt_form", clear_on_submit=True):
                        c1, c2 = st.columns(2)
                        appt_date = c1.date_input("Date", min_value=datetime.today())
                        appt_time = c2.time_input("Time")
                        provider = st.text_input("Provider / Resource (e.g., Dr. Smith, Blood Clinic)")
                        reason = st.text_input("Reason for Visit")
                        if st.form_submit_button("Book Appointment", type="primary"):
                            if provider.strip() and reason.strip():
                                crm.add_appointment(pid, appt_date, appt_time, provider.strip(), reason.strip(), st.session_state['username'])
                                st.success("Appointment booked!"); st.rerun()
                            else: st.warning("Provider and Reason are required.")
                
                st.divider()
                crm.auto_resolve_past_appointments(pid)
                appts = get_patient_appointments(pid, crm)
                
                if appts:
                    upcoming = [a for a in appts if a[5] == APPT_SCHEDULED]
                    noshow = [a for a in appts if a[5] == APPT_NO_SHOW]

                    def color_status(val):
                        if val == APPT_NO_SHOW: return 'color: #dc3545'
                        if val == APPT_SCHEDULED: return 'color: #28a745'
                        return ''

                    st.subheader("🟢 Upcoming")
                    if upcoming:
                        df_up = pd.DataFrame(upcoming, columns=['ID', 'Date', 'Time', 'Provider', 'Reason', 'Status'])
                        st.dataframe(df_up.style.map(color_status, subset=['Status']), hide_index=True, use_container_width=True, column_config={"ID": None})
                        appt_mapping = {a[0]: f"{a[1]} at {a[2]} with {a[3]}" for a in upcoming}
                        cancel_id = st.selectbox("Cancel an upcoming appointment?", options=list(appt_mapping.keys()), format_func=lambda x: appt_mapping[x])
                        if cancel_id and st.button("🚫 Cancel Selected Appointment"):
                            crm.update_appointment_status(cancel_id, APPT_CANCELLED); st.rerun()
                    else: st.info("No upcoming appointments.")

                    if noshow:
                        st.divider(); st.subheader("❌ No Shows")
                        df_no = pd.DataFrame(noshow, columns=['ID', 'Date', 'Time', 'Provider', 'Reason', 'Status'])
                        st.dataframe(df_no.style.map(color_status, subset=['Status']), hide_index=True, use_container_width=True, column_config={"ID": None})
                else: st.info("No appointments found.")

# =========================================================
#  PART 3: THE ADMIN CONSOLE (Restricted)
# =========================================================

elif st.session_state.page == "Admin Console":
    if st.session_state.get('role') not in ADMIN_ROLES:
        st.error("Unauthorized access."); st.stop()

    st.title("⚙️ Admin Console")
    if st.button("⬅ Back to Lobby"): go_to_lobby()
    st.divider()
    
    # --- ADDED TAB 3 FOR TEST DICTIONARY ---
    tab_staff, tab_report_design, tab_tests = st.tabs(["👥 Staff Management", "🎨 Report Designer", "🧪 Test Dictionary"])
    
    # -----------------------------------------------------
    # TAB 1: STAFF MANAGEMENT
    # -----------------------------------------------------
    with tab_staff:
        st.subheader("Staff Management")
        with st.expander("➕ Add New Staff Member", expanded=False):
            with st.form("new_staff_form", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                n_user = c1.text_input("New Username")
                n_pwd = c2.text_input("New Password", type="password")
                n_role = c3.selectbox("Role", STAFF_ROLES)
                if st.form_submit_button("Create User", type="primary"):
                    if n_user.strip() and n_pwd.strip():
                        if crm.add_staff_member(n_user.strip(), n_pwd.strip(), n_role): st.success(f"✅ User '{n_user}' created!")
                        else: st.error("❌ Username already exists.")
                    else: st.warning("Please provide both username and password.")
                        
        with st.expander("📋 View Current Staff Directory", expanded=False):
            crm.connect()
            crm.cursor.execute("SELECT staff_id, username, role FROM staff ORDER BY role, username")
            staff_list = crm.cursor.fetchall()
            crm.close()
            if staff_list:
                df_staff = pd.DataFrame(staff_list, columns=['Staff ID', 'Username', 'Role'])
                st.dataframe(df_staff, hide_index=True, use_container_width=True)

        with st.expander("⚙️ Manage Existing Staff (Passwords & Removal)", expanded=False):
            if staff_list:
                staff_dict = {s['Staff ID']: f"{s['Username']} ({s['Role']})" for _, s in df_staff.iterrows()}
                selected_staff_id = st.selectbox("Select Staff Member", options=list(staff_dict.keys()), format_func=lambda x: staff_dict[x])
                action = st.radio("Action to perform:", ["Change Password", "Delete User"], horizontal=True)
                st.divider()
                
                if action == "Change Password":
                    with st.form("change_pwd_form", clear_on_submit=True):
                        new_pwd = st.text_input("New Password", type="password")
                        if st.form_submit_button("💾 Update Password", type="primary"):
                            if new_pwd.strip():
                                crm.connect()
                                crm.cursor.execute("UPDATE staff SET password_hash = ? WHERE staff_id = ?", (hash_password(new_pwd.strip()), selected_staff_id))
                                crm.conn.commit(); crm.close()
                                st.success("Password successfully updated!"); st.rerun()
                elif action == "Delete User":
                    selected_username = staff_dict[selected_staff_id].split(" (")[0]
                    if st.session_state.get('username') == selected_username: st.error("⚠️ You cannot delete your own account.")
                    elif len(staff_dict) <= 1: st.error("⛔ **Action Denied:** Cannot delete the last remaining staff member.")
                    else:
                        st.warning(f"Permenantly delete **{selected_username}**?")
                        if st.button("🗑️ Confirm Delete User", type="primary"):
                            crm.connect()
                            crm.cursor.execute("DELETE FROM staff WHERE staff_id = ?", (selected_staff_id,))
                            crm.conn.commit(); crm.close()
                            st.success("User deleted."); time.sleep(1); st.rerun()

    # -----------------------------------------------------
    # TAB 2: REPORT DESIGNER
    # -----------------------------------------------------
    with tab_report_design:
        st.subheader("📄 Health Report Designer")
        
        # Theme presets are seeded into system_settings by initialize_database.
        # Reading from DB means presets can be edited without touching code.
        PRESETS = json.loads(crm.get_setting("report_theme_presets", "{}")) or {
            "Classic Blue": {
                "page_bg": "#E6F5FF", "banner_bg": "#FFFFFF", "inner_box": "#F8FBFF",
                "border": "#B4D2E6", "text_primary": "#003366", "text_muted": "#505050",
                "radius": 5, "spacing": 8, "font": "Helvetica"
            }
        }
        
        if 'designer_theme' not in st.session_state:
            saved_theme_str = crm.get_setting("report_theme")
            try: db_theme = json.loads(saved_theme_str) if saved_theme_str else {}
            except: db_theme = {}
            st.session_state.designer_theme = {**PRESETS["Classic Blue"], **db_theme}

        theme = st.session_state.designer_theme
        design_col, preview_col = st.columns([1, 1.2], gap="large")
        
        with design_col:
            st.markdown("#### 🎨 Preset Themes")
            
            # Force buttons to respect newlines
            st.markdown("""
                <style>
                div.stButton > button p {
                    white-space: pre-wrap;
                    text-align: center;
                }
                </style>
            """, unsafe_allow_html=True)
            
            # --- ALL 6 BUTTONS RESTORED ---
            pc1, pc2, pc3 = st.columns(3)
            if pc1.button("🌊 Classic\nBlue", use_container_width=True): st.session_state.designer_theme = PRESETS["Classic Blue"]; st.rerun()
            if pc2.button("🏢 Modern\nMinimal", use_container_width=True): st.session_state.designer_theme = PRESETS["Modern Minimal"]; st.rerun()
            if pc3.button("🌿 Warm\nEmerald", use_container_width=True): st.session_state.designer_theme = PRESETS["Warm Emerald"]; st.rerun()
            
            pc4, pc5, pc6 = st.columns(3)
            if pc4.button("🌅 Sunset\nCoral", use_container_width=True): st.session_state.designer_theme = PRESETS["Sunset Coral"]; st.rerun()
            if pc5.button("☂️ Royal\nViolet", use_container_width=True): st.session_state.designer_theme = PRESETS["Royal Violet"]; st.rerun()
            if pc6.button("🪨 Crisp\nSlate", use_container_width=True): st.session_state.designer_theme = PRESETS["Crisp Slate"]; st.rerun()
            
            st.divider(); st.markdown("#### ⚙️ Global Report Settings")
            with st.form("theme_designer_form", border=False):
                
                # Font list is built at startup by scanning assets/fonts/ + built-in PDF fonts
                c_font, c_rad, c_spc = st.columns(3)
                try: font_index = AVAILABLE_FONTS.index(theme.get('font', 'Helvetica'))
                except ValueError: font_index = 0
                
                new_font = c_font.selectbox("Font Family", AVAILABLE_FONTS, index=font_index)
                
                new_rad = c_rad.slider("Box Radius", 0, 15, int(theme['radius']))
                new_spc = c_spc.slider("Spacing", 2, 20, theme.get('spacing', 8))
                
                col1, col2 = st.columns(2)
                new_page_bg = col1.color_picker("Page Background", theme['page_bg'])
                new_border = col2.color_picker("Borders", theme['border'])
                new_banner_bg = col1.color_picker("Banner Box", theme['banner_bg'])
                new_inner_box = col2.color_picker("Inner Box", theme['inner_box'])
                new_text_pri = col1.color_picker("Primary Text", theme['text_primary'])
                new_text_mut = col2.color_picker("Muted Text", theme['text_muted'])
                
                new_footer = st.text_input("PDF Report Footer", crm.get_setting("report_footer", "Confidential Report"))
                
                btn_col1, btn_col2 = st.columns(2)
                update_preview = btn_col1.form_submit_button("👁️ Update Preview")
                save_theme = btn_col2.form_submit_button("💾 Save Live Theme", type="primary")
                
                new_theme_config = {
                    "page_bg": new_page_bg, "banner_bg": new_banner_bg, "inner_box": new_inner_box,
                    "border": new_border, "text_primary": new_text_pri, "text_muted": new_text_mut,
                    "radius": 0.1 if new_rad == 0 else new_rad, "spacing": new_spc, "font": new_font
                }

                if update_preview or save_theme: st.session_state.designer_theme = new_theme_config
                if save_theme:
                    crm.update_setting("report_footer", new_footer.strip())
                    crm.update_setting("report_theme", json.dumps(new_theme_config))
                    st.success("Theme saved!"); st.rerun()
                elif update_preview: st.rerun()

        with preview_col:
            st.markdown("#### 👁️ Live PDF Preview")
            
            # --- Streamlined Dummy Data (Updated for new schema) ---
            dummy_patient = {"first_name": "Jane", "last_name": "Doe", "dob": "1982-08-24", "patient_id": "DEMO-001"}
            
            # 17-column format: date, name, value, unit, group, config(v2), note, target,
            #                   chart_type, result_id, status, taken_on, taken_by, taken_note,
            #                   received_on, logged_by, trend_chart_type
            _vd_cfg = json.dumps({
                "graph_type": "gauge", "gauge_style": "curved",
                "axis_min": 0, "axis_max": 150,
                "zones": [
                    {"from": 0,   "to": 50,  "color": "#FFCCCB", "label": "Low"},
                    {"from": 50,  "to": 125, "color": "#D4EDDA", "label": "Normal"},
                    {"from": 125, "to": 150, "color": "#FFE4B5", "label": "High"}
                ]
            })
            _gl_cfg = json.dumps({
                "graph_type": "gauge", "gauge_style": "curved",
                "axis_min": 0.0, "axis_max": 15.0,
                "zones": [
                    {"from": 0.0, "to": 4.0, "color": "#FFCCCB", "label": "Low"},
                    {"from": 4.0, "to": 5.4, "color": "#D4EDDA", "label": "Normal"},
                    {"from": 5.4, "to": 15.0, "color": "#FFCCCB", "label": "High"}
                ]
            })
            dummy_tests = [
                ("2026-02-26", "Vitamin D",     68,  "nmol/L", "Vitamin D",    _vd_cfg, "Levels are sufficient. Continue current supplement routine.", "50 - 125", "gauge", 1, "Complete", "2026-02-26", "Admin", "", "2026-02-26", "Admin", "line"),
                ("2026-02-26", "Fasting Glucose", 5.1, "mmol/L", "Blood Glucose", _gl_cfg, "Excellent progress. Fasting levels have stabilized.", "4.0 - 5.4", "gauge", 2, "Complete", "2026-02-26", "Admin", "", "2026-02-26", "Admin", "line"),
                ("2025-11-10", "Fasting Glucose", 5.3, "mmol/L", "Blood Glucose", _gl_cfg, "", "4.0 - 5.4", "gauge", 3, "Complete", "2025-11-10", "Admin", "", "2025-11-10", "Admin", "line"),
                ("2025-08-15", "Fasting Glucose", 5.6, "mmol/L", "Blood Glucose", _gl_cfg, "", "4.0 - 5.4", "gauge", 4, "Complete", "2025-08-15", "Admin", "", "2025-08-15", "Admin", "line"),
            ]
            
            dummy_config = [{"test": "Vitamin D"}, {"test": "Blood Glucose"}]
            dummy_overrides = {
                "Vitamin D": "Levels are sufficient. Continue current supplement routine.", 
                "Fasting Glucose": "Excellent progress. Fasting levels have stabilized."
            }
            
            prac_statement = (
                "Welcome to the upgraded Health Report Designer! We've completely overhauled the reporting engine to give you unprecedented control over your clinic's branding. "
                "You can now adjust primary and muted text colors, seamlessly tweak the spacing between elements, and select from multiple professional font families.\n\n"
                "Use the controls on the left to experiment with these new capabilities, and watch the preview below update in real-time."
            )

            try:
                pdf_bytes = create_custom_report_pdf(
                    patient=dummy_patient, 
                    tests=dummy_tests, 
                    report_config=dummy_config,
                    note_overrides=dummy_overrides, 
                    start_d=None, 
                    end_d=None,
                    practitioner_statement=prac_statement,
                    next_steps="Review the changes. Once satisfied, click 'Save Live Theme' to apply these settings globally to all future patient reports.",
                    footer_text=new_footer, 
                    creator_name=st.session_state.get('username', 'Admin'), 
                    theme_config=new_theme_config
                )
                
                b64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
                pdf_display = f'<iframe src="data:application/pdf;base64,{b64_pdf}" width="100%" height="800" type="application/pdf"></iframe>'
                st.markdown(pdf_display, unsafe_allow_html=True)
                
            except Exception as e:
                st.error(f"Error generating preview: {e}")

    # -----------------------------------------------------
    # TAB 3: TEST DICTIONARY
    # -----------------------------------------------------
    with tab_tests:
        st.subheader("🧪 Metadata & Test Dictionary")
        st.write("Define new clinical tests and specify how they render in the report builder.")
        
        # 1. Fetch All Tests (with group JOIN for denormalised display)
        crm.connect()
        crm.cursor.execute("""
            SELECT
                td.id,
                td.test_name,
                COALESCE(tg.group_name, td.test_group) AS test_group,
                td.unit,
                td.default_target,
                COALESCE(tg.chart_type, td.chart_type) AS chart_type,
                COALESCE(tg.description, td.description) AS description,
                td.chart_config,
                td.is_active
            FROM test_definitions td
            LEFT JOIN test_groups tg ON td.group_id = tg.group_id
            ORDER BY test_group, test_name
        """)
        all_test_defs = crm.cursor.fetchall()

        # 2. Fetch Test Groups for the panels section
        crm.cursor.execute("SELECT group_id, group_name, chart_type, trend_chart_type, description FROM test_groups ORDER BY group_name")
        all_test_groups = crm.cursor.fetchall()
        crm.close()

        # ---- SECTION A: Test Panels ----
        st.markdown("#### 🗂️ Test Panels")

        with st.expander(f"📋 View Panels ({len(all_test_groups)})", expanded=False):
            if all_test_groups:
                df_tg = pd.DataFrame(all_test_groups, columns=['group_id', 'Panel Name', 'Chart Style', 'Trend Chart', 'Description'])
                st.dataframe(
                    df_tg, hide_index=True, use_container_width=True,
                    column_config={"group_id": None}
                )
            else:
                st.caption("No test panels defined yet.")

        # ==========================================
        # ZONE EDITOR — shared helper functions
        # ==========================================

        def _zfrom(pfx, i):
            """Zone i's 'from' — live-derived: prev zone's 'to', or axis_start for i=0."""
            if i == 0:
                return float(st.session_state.get(f'{pfx}_axis_start', 0.0))
            return float(st.session_state.get(f'{pfx}_zone_to_{i-1}', 0.0))

        def _zbuild(pfx, n):
            """Assemble zones list from current session-state widget values."""
            result = []
            for i in range(n):
                from_v = _zfrom(pfx, i)
                to_v   = float(st.session_state.get(f'{pfx}_zone_to_{i}', from_v + 10.0))
                is_t   = bool(st.session_state.get(f'{pfx}_zone_transp_{i}', False))
                color  = 'transparent' if is_t else str(st.session_state.get(f'{pfx}_zone_color_{i}', '#D4EDDA'))
                label  = str(st.session_state.get(f'{pfx}_zone_label_{i}', ''))
                result.append({"from": from_v, "to": to_v, "color": color, "label": label})
            return result

        def _zinit(pfx, config):
            """Populate zone-editor session state from a chart_config dict."""
            zones = config.get("zones", [])
            n = max(len(zones), 2)
            st.session_state[f'{pfx}_n_zones'] = n
            # Axis start = first zone's 'from' (or axis_min fallback)
            axis_start = float(zones[0]['from']) if zones else float(config.get('axis_min', 0.0))
            st.session_state[f'{pfx}_axis_start'] = axis_start
            # Clear stale zone keys
            for _k in list(st.session_state.keys()):
                if _k.startswith(f'{pfx}_zone_'):
                    del st.session_state[_k]
            for i, z in enumerate(zones):
                st.session_state[f'{pfx}_zone_to_{i}']     = float(z.get('to', axis_start + (i+1)*10.0))
                color = z.get('color', '#D4EDDA')
                is_t  = (color == 'transparent')
                st.session_state[f'{pfx}_zone_transp_{i}'] = is_t
                st.session_state[f'{pfx}_zone_color_{i}']  = '#D4EDDA' if is_t else color
                st.session_state[f'{pfx}_zone_label_{i}']  = z.get('label', '')
            # Fill any extra slots
            for i in range(len(zones), n):
                prev = float(st.session_state.get(f'{pfx}_zone_to_{i-1}', axis_start + i*10.0))
                st.session_state[f'{pfx}_zone_to_{i}']     = prev + 10.0
                st.session_state[f'{pfx}_zone_transp_{i}'] = False
                st.session_state[f'{pfx}_zone_color_{i}']  = '#D4EDDA'
                st.session_state[f'{pfx}_zone_label_{i}']  = ''
            if config.get('graph_type') == 'gauge':
                st.session_state[f'{pfx}_gauge_style'] = config.get('gauge_style', 'curved')
            if config.get('graph_type') == 'dot':
                dots = config.get('dots', [])
                nd = max(len(dots), 2)
                st.session_state[f'{pfx}_n_dots'] = nd
                for _k in list(st.session_state.keys()):
                    if _k.startswith(f'{pfx}_dot_'):
                        del st.session_state[_k]
                for i, d in enumerate(dots):
                    st.session_state[f'{pfx}_dot_name_{i}']   = d.get('test_name', '')
                    st.session_state[f'{pfx}_dot_label_{i}']  = d.get('label', '')
                    st.session_state[f'{pfx}_dot_fill_{i}']   = d.get('fill_color', '#003366')
                    st.session_state[f'{pfx}_dot_stroke_{i}'] = d.get('stroke_color', '#003366')
                for i in range(len(dots), nd):
                    st.session_state[f'{pfx}_dot_name_{i}']   = ''
                    st.session_state[f'{pfx}_dot_label_{i}']  = ''
                    st.session_state[f'{pfx}_dot_fill_{i}']   = '#003366'
                    st.session_state[f'{pfx}_dot_stroke_{i}'] = '#003366'
            if config.get('graph_type') == 'bar':
                st.session_state[f'{pfx}_bar_color']       = config.get('bar_color', '#003366')
                st.session_state[f'{pfx}_bar_alert_color'] = config.get('bar_alert_color', '#DC3545')

        def _zrender(pfx, n, rm_key_sfx=""):
            """
            Render zone editor rows (axis_start is displayed above this call).
            - 'From' is read-only, derived live from previous 'To'.
            - Red ⚠ if 'to' <= 'from' (zone has zero or negative width).
            - Transparent checkbox skips zone colour background in charts.
            Returns True if any zones have validation issues.
            """
            has_issues = False
            _zh = st.columns([1.3, 1.5, 1, 2.5, 0.7, 0.5])
            for _lbl, _c in zip(["From ↓", "To", "Colour", "Label", "Transp.", ""], _zh):
                _c.caption(_lbl)
            for i in range(n):
                from_v = _zfrom(pfx, i)
                to_v   = float(st.session_state.get(f'{pfx}_zone_to_{i}', from_v + 10.0))
                bad    = to_v <= from_v
                if bad:
                    has_issues = True
                _zc = st.columns([1.3, 1.5, 1, 2.5, 0.7, 0.5])
                # From: read-only, warning colour if bad
                _zc[0].markdown(f"**:red[{from_v:g} ⚠]**" if bad else f"**{from_v:g}**")
                # To: number input
                if f'{pfx}_zone_to_{i}' not in st.session_state:
                    st.session_state[f'{pfx}_zone_to_{i}'] = from_v + 10.0
                _zc[1].number_input("To", key=f'{pfx}_zone_to_{i}',
                                    label_visibility="collapsed", step=0.1)
                # Colour (hidden when transparent)
                is_t = bool(st.session_state.get(f'{pfx}_zone_transp_{i}', False))
                if not is_t:
                    if f'{pfx}_zone_color_{i}' not in st.session_state:
                        st.session_state[f'{pfx}_zone_color_{i}'] = '#D4EDDA'
                    _zc[2].color_picker("Colour", key=f'{pfx}_zone_color_{i}',
                                        label_visibility="collapsed")
                else:
                    _zc[2].caption("*(none)*")
                # Label
                if f'{pfx}_zone_label_{i}' not in st.session_state:
                    st.session_state[f'{pfx}_zone_label_{i}'] = ''
                _zc[3].text_input("Label", key=f'{pfx}_zone_label_{i}',
                                  label_visibility="collapsed")
                # Transparent toggle
                if f'{pfx}_zone_transp_{i}' not in st.session_state:
                    st.session_state[f'{pfx}_zone_transp_{i}'] = False
                _zc[4].checkbox("", key=f'{pfx}_zone_transp_{i}',
                                label_visibility="collapsed")
                # Remove
                if _zc[5].button("✕", key=f'{pfx}_zone_rm_{i}{rm_key_sfx}') and n > 1:
                    for j in range(i, n - 1):
                        for s in ['to', 'color', 'transp', 'label']:
                            src = f'{pfx}_zone_{s}_{j+1}'
                            dst = f'{pfx}_zone_{s}_{j}'
                            if src in st.session_state:
                                st.session_state[dst] = st.session_state.pop(src)
                    for s in ['to', 'color', 'transp', 'label']:
                        _k = f'{pfx}_zone_{s}_{n-1}'
                        if _k in st.session_state:
                            del st.session_state[_k]
                    st.session_state[f'{pfx}_n_zones'] = n - 1
                    st.rerun()
                if bad:
                    st.warning(f"Zone {i+1}: 'to' ({to_v:g}) must be > 'from' ({from_v:g})", icon="⚠️")
            return has_issues

        # ==========================================
        # NEW TEST CREATION — Composable Zone-Based Flow
        # ==========================================

        def _nt_reset():
            st.session_state['nt_graph_type'] = 'gauge'
            for _k in list(st.session_state.keys()):
                if any(_k.startswith(_p) for _p in
                       ['nt_gauge', 'nt_n_', 'nt_axis', 'nt_zone_', 'nt_dot_', 'nt_bt', 'nt_bar_']):
                    del st.session_state[_k]
            _zinit('nt', {
                "graph_type": "gauge", "gauge_style": "curved",
                "zones": [
                    {"from": 0.0,  "to": 50.0,  "color": "#FFCCCB", "label": "Low"},
                    {"from": 50.0, "to": 100.0, "color": "#D4EDDA", "label": "Normal"},
                ]
            })

        if 'nt_graph_type' not in st.session_state:
            _nt_reset()

        with st.expander("➕ Add New Test or Panel", expanded=False):
            from modules.charts import render_gauge, render_dot, render_bars, render_text

            nt_left, nt_right = st.columns([1.1, 1], gap="large")

            with nt_left:
                # ---- STEP 1: Graph type ----
                st.markdown("#### Step 1 — Chart Type")
                nt_graph = st.radio(
                    "Graph type",
                    options=["gauge", "dot", "bar", "none"],
                    format_func=lambda x: {
                        "gauge": "Dial / Gauge — single value on a curved or straight scale",
                        "dot":   "Dot on a line — one or two values as markers (e.g. Blood Pressure)",
                        "bar":   "Horizontal bars — multiple related values side by side",
                        "none":  "Numbers only — display value as large text, no chart",
                    }[x],
                    index=["gauge", "dot", "bar", "none"].index(st.session_state['nt_graph_type']),
                    key="nt_graph_type_radio",
                )
                if nt_graph != st.session_state['nt_graph_type']:
                    st.session_state['nt_graph_type'] = nt_graph
                    _nt_reset()
                    st.session_state['nt_graph_type'] = nt_graph
                    st.rerun()

                st.divider()

                # ---- STEP 2: Conditional configuration ----
                st.markdown("#### Step 2 — Configuration")

                if nt_graph == "gauge":
                    _gc1, _gc2 = st.columns(2)
                    nt_gauge_style = _gc1.radio("Style", ["curved", "straight"],
                                                index=["curved","straight"].index(
                                                    st.session_state.get('nt_gauge_style','curved')),
                                                key="nt_gauge_style_radio")
                    st.session_state['nt_gauge_style'] = nt_gauge_style

                    _az_col, _ = st.columns(2)
                    if 'nt_axis_start' not in st.session_state:
                        st.session_state['nt_axis_start'] = 0.0
                    _az_col.number_input("Axis Start (first zone 'from')",
                                         key='nt_axis_start', step=0.1)

                    nt_n_zones = st.session_state.get('nt_n_zones', 2)
                    st.markdown("**Zones** (left to right)")
                    _zrender('nt', nt_n_zones)
                    if st.button("+ Add Zone", key="nt_add_zone_gauge"):
                        _n = st.session_state.get('nt_n_zones', 2)
                        _prev = float(st.session_state.get(f'nt_zone_to_{_n-1}', 0.0))
                        st.session_state[f'nt_zone_to_{_n}']     = _prev + 10.0
                        st.session_state[f'nt_zone_color_{_n}']  = '#D4EDDA'
                        st.session_state[f'nt_zone_transp_{_n}'] = False
                        st.session_state[f'nt_zone_label_{_n}']  = ''
                        st.session_state['nt_n_zones'] = _n + 1
                        st.rerun()

                elif nt_graph == "dot":
                    # Initialize dot state if missing
                    if 'nt_n_dots' not in st.session_state:
                        st.session_state['nt_n_dots'] = 2
                        for _di in range(2):
                            st.session_state[f'nt_dot_name_{_di}']   = ''
                            st.session_state[f'nt_dot_label_{_di}']  = f'T{_di+1}'
                            st.session_state[f'nt_dot_fill_{_di}']   = '#003366'
                            st.session_state[f'nt_dot_stroke_{_di}'] = '#003366'
                    nd = st.session_state['nt_n_dots']

                    st.markdown("**Dots** (1–4)")
                    _dh = st.columns([2, 2, 1.5, 1.5, 1])
                    for _lbl, _c in zip(["Test Name", "Display Label", "Fill Colour", "Stroke Colour", ""], _dh):
                        _c.caption(_lbl)
                    for _di in range(nd):
                        if f'nt_dot_name_{_di}' not in st.session_state:
                            st.session_state[f'nt_dot_name_{_di}'] = ''
                        if f'nt_dot_label_{_di}' not in st.session_state:
                            st.session_state[f'nt_dot_label_{_di}'] = ''
                        if f'nt_dot_fill_{_di}' not in st.session_state:
                            st.session_state[f'nt_dot_fill_{_di}'] = '#003366'
                        if f'nt_dot_stroke_{_di}' not in st.session_state:
                            st.session_state[f'nt_dot_stroke_{_di}'] = '#003366'
                        _dc = st.columns([2, 2, 1.5, 1.5, 1])
                        _dc[0].text_input("Test Name", key=f'nt_dot_name_{_di}', label_visibility="collapsed")
                        _dc[1].text_input("Label",     key=f'nt_dot_label_{_di}', label_visibility="collapsed")
                        _dc[2].color_picker("Fill",    key=f'nt_dot_fill_{_di}', label_visibility="collapsed")
                        _dc[3].color_picker("Stroke",  key=f'nt_dot_stroke_{_di}', label_visibility="collapsed")
                        if _dc[4].button("✕", key=f'nt_dot_rm_{_di}') and nd > 1:
                            for _j in range(_di, nd - 1):
                                for _s in ['name', 'label', 'fill', 'stroke']:
                                    src = f'nt_dot_{_s}_{_j+1}'
                                    dst = f'nt_dot_{_s}_{_j}'
                                    if src in st.session_state:
                                        st.session_state[dst] = st.session_state.pop(src)
                            for _s in ['name', 'label', 'fill', 'stroke']:
                                _k = f'nt_dot_{_s}_{nd-1}'
                                if _k in st.session_state:
                                    del st.session_state[_k]
                            st.session_state['nt_n_dots'] = nd - 1
                            st.rerun()
                    if nd < 4 and st.button("+ Add Dot", key="nt_add_dot"):
                        st.session_state['nt_n_dots'] = nd + 1
                        st.rerun()

                    st.markdown("**Zones**")
                    _az_col, _ = st.columns(2)
                    if 'nt_axis_start' not in st.session_state:
                        st.session_state['nt_axis_start'] = 0.0
                    _az_col.number_input("Axis Start (first zone 'from')",
                                         key='nt_axis_start', step=0.1)
                    nt_n_zones = st.session_state.get('nt_n_zones', 2)
                    _zrender('nt', nt_n_zones)
                    if st.button("+ Add Zone", key="nt_add_zone_dot"):
                        _n = st.session_state.get('nt_n_zones', 2)
                        _prev = float(st.session_state.get(f'nt_zone_to_{_n-1}', 0.0))
                        st.session_state[f'nt_zone_to_{_n}']     = _prev + 10.0
                        st.session_state[f'nt_zone_color_{_n}']  = '#D4EDDA'
                        st.session_state[f'nt_zone_transp_{_n}'] = False
                        st.session_state[f'nt_zone_label_{_n}']  = ''
                        st.session_state['nt_n_zones'] = _n + 1
                        st.rerun()

                elif nt_graph == "bar":
                    nt_bar_n = int(st.number_input("Number of component tests", min_value=1, max_value=8,
                                                    value=st.session_state.get('nt_bar_n', 2),
                                                    key="nt_bar_n_input"))
                    st.session_state['nt_bar_n'] = nt_bar_n

                    for _bi in range(nt_bar_n):
                        _bpfx = f'nt_bt_{_bi}'
                        st.markdown(f"**Test {_bi+1}**")
                        _bc1, _bc2, _bc3 = st.columns([2, 1, 1.5])
                        if f'{_bpfx}_name' not in st.session_state:
                            st.session_state[f'{_bpfx}_name'] = ''
                        if f'{_bpfx}_unit' not in st.session_state:
                            st.session_state[f'{_bpfx}_unit'] = ''
                        if f'{_bpfx}_target' not in st.session_state:
                            st.session_state[f'{_bpfx}_target'] = ''
                        _bc1.text_input("Test Name", key=f'{_bpfx}_name',
                                         label_visibility="collapsed" if _bi > 0 else "visible")
                        _bc2.text_input("Unit", key=f'{_bpfx}_unit',
                                         label_visibility="collapsed" if _bi > 0 else "visible")
                        _bc3.text_input("Target", key=f'{_bpfx}_target',
                                         label_visibility="collapsed" if _bi > 0 else "visible")
                        _bcolor1, _bcolor2 = st.columns(2)
                        if f'{_bpfx}_barcol' not in st.session_state:
                            st.session_state[f'{_bpfx}_barcol'] = '#003366'
                        if f'{_bpfx}_alertcol' not in st.session_state:
                            st.session_state[f'{_bpfx}_alertcol'] = '#DC3545'
                        _bcolor1.color_picker("Bar colour",       key=f'{_bpfx}_barcol')
                        _bcolor2.color_picker("Alert bar colour", key=f'{_bpfx}_alertcol')

                        if f'{_bpfx}_axis_start' not in st.session_state:
                            st.session_state[f'{_bpfx}_axis_start'] = 0.0
                        if f'{_bpfx}_n_zones' not in st.session_state:
                            st.session_state[f'{_bpfx}_n_zones']        = 2
                            st.session_state[f'{_bpfx}_zone_to_0']      = 5.0
                            st.session_state[f'{_bpfx}_zone_color_0']   = '#D4EDDA'
                            st.session_state[f'{_bpfx}_zone_transp_0']  = False
                            st.session_state[f'{_bpfx}_zone_label_0']   = ''
                            st.session_state[f'{_bpfx}_zone_to_1']      = 15.0
                            st.session_state[f'{_bpfx}_zone_color_1']   = '#FFCCCB'
                            st.session_state[f'{_bpfx}_zone_transp_1']  = False
                            st.session_state[f'{_bpfx}_zone_label_1']   = ''
                        _baz_col, _ = st.columns(2)
                        _baz_col.number_input("Axis Start", key=f'{_bpfx}_axis_start', step=0.1)
                        _bnz = st.session_state.get(f'{_bpfx}_n_zones', 2)
                        st.markdown("**Zones**")
                        _zrender(_bpfx, _bnz, rm_key_sfx=f"_bt{_bi}")
                        if st.button(f"+ Add Zone (Test {_bi+1})", key=f'{_bpfx}_add_zone'):
                            _n = st.session_state.get(f'{_bpfx}_n_zones', 2)
                            _prev = float(st.session_state.get(f'{_bpfx}_zone_to_{_n-1}', 0.0))
                            st.session_state[f'{_bpfx}_zone_to_{_n}']     = _prev + 10.0
                            st.session_state[f'{_bpfx}_zone_color_{_n}']  = '#D4EDDA'
                            st.session_state[f'{_bpfx}_zone_transp_{_n}'] = False
                            st.session_state[f'{_bpfx}_zone_label_{_n}']  = ''
                            st.session_state[f'{_bpfx}_n_zones'] = _n + 1
                            st.rerun()
                        st.markdown("---")

                # else: none — nothing more needed

                # ---- STEP 3: Metadata & Save (inside a form) ----
                st.markdown("#### Step 3 — Metadata")
                with st.form("new_test_save_form", clear_on_submit=True):
                    _m1, _m2 = st.columns(2)
                    nt_panel_name = _m1.text_input("Test / Panel Name")
                    nt_unit       = _m2.text_input("Unit (e.g., bpm, mmol/L)")
                    nt_target     = st.text_input("Target Display Text (e.g., '60-100' or '>95')")
                    nt_desc       = st.text_input("Description (optional)")

                    _save = st.form_submit_button("💾 Save", type="primary")

                    if _save:
                        if not nt_panel_name.strip():
                            st.warning("Test / Panel Name is required.")
                        else:
                            _gt = st.session_state['nt_graph_type']

                            if _gt == "none":
                                _cfg = {"graph_type": "none"}
                                _trend = "line"
                                _defs = [(nt_panel_name.strip(), nt_panel_name.strip(),
                                          nt_unit.strip(), nt_target.strip(), "none",
                                          json.dumps(_cfg), None)]

                            elif _gt == "gauge":
                                _n = st.session_state.get('nt_n_zones', 2)
                                _zones = _zbuild('nt', _n)
                                _ax_min = _zones[0]['from'] if _zones else 0.0
                                _ax_max = _zones[-1]['to']  if _zones else 100.0
                                _cfg = {
                                    "graph_type": "gauge",
                                    "gauge_style": st.session_state.get('nt_gauge_style', 'curved'),
                                    "axis_min": _ax_min,
                                    "axis_max": _ax_max,
                                    "zones": _zones
                                }
                                _trend = "line"
                                _defs = [(nt_panel_name.strip(), nt_panel_name.strip(),
                                          nt_unit.strip(), nt_target.strip(), "gauge",
                                          json.dumps(_cfg), None)]

                            elif _gt == "dot":
                                _n = st.session_state.get('nt_n_zones', 2)
                                _zones = _zbuild('nt', _n)
                                _ax_min = _zones[0]['from'] if _zones else 0.0
                                _ax_max = _zones[-1]['to']  if _zones else 100.0
                                _nd = st.session_state.get('nt_n_dots', 2)
                                _dots = [
                                    {
                                        "test_name":    st.session_state.get(f'nt_dot_name_{_di}', ''),
                                        "label":        st.session_state.get(f'nt_dot_label_{_di}', ''),
                                        "fill_color":   st.session_state.get(f'nt_dot_fill_{_di}', '#003366'),
                                        "stroke_color": st.session_state.get(f'nt_dot_stroke_{_di}', '#003366'),
                                    }
                                    for _di in range(_nd)
                                    if st.session_state.get(f'nt_dot_name_{_di}', '').strip()
                                ]
                                _primary_cfg = {
                                    "graph_type": "dot",
                                    "axis_min": _ax_min,
                                    "axis_max": _ax_max,
                                    "zones": _zones,
                                    "dots": _dots
                                }
                                _secondary_cfg = {
                                    "graph_type": "dot",
                                    "dot_role": "secondary",
                                    "axis_min": _ax_min,
                                    "axis_max": _ax_max,
                                    "zones": _zones
                                }
                                _trend = "bp_trend"
                                _defs = []
                                for _di, dot in enumerate(_dots):
                                    _t_name = dot["test_name"].strip()
                                    _t_cfg  = json.dumps(_primary_cfg if _di == 0 else _secondary_cfg)
                                    _defs.append((_t_name, nt_panel_name.strip(),
                                                  nt_unit.strip(), nt_target.strip(), "dot", _t_cfg, None))

                            elif _gt == "bar":
                                _trend = "multi_trend"
                                _defs = []
                                for _bi in range(st.session_state.get('nt_bar_n', 2)):
                                    _bpfx = f'nt_bt_{_bi}'
                                    _bt_name = st.session_state.get(f'{_bpfx}_name', '').strip()
                                    if not _bt_name:
                                        continue
                                    _bnz = st.session_state.get(f'{_bpfx}_n_zones', 2)
                                    _bt_zones = _zbuild(_bpfx, _bnz)
                                    _bt_cfg = {
                                        "graph_type": "bar",
                                        "bar_color":       st.session_state.get(f'{_bpfx}_barcol',   '#003366'),
                                        "bar_alert_color": st.session_state.get(f'{_bpfx}_alertcol', '#DC3545'),
                                        "zones": _bt_zones
                                    }
                                    _defs.append((_bt_name, nt_panel_name.strip(),
                                                  st.session_state.get(f'{_bpfx}_unit', '').strip(),
                                                  st.session_state.get(f'{_bpfx}_target', '').strip(),
                                                  "bar", json.dumps(_bt_cfg), None))

                            # Write to DB
                            if not _defs:
                                st.warning("No valid test definitions to save.")
                            else:
                                crm.connect()
                                try:
                                    crm.cursor.execute("""
                                        INSERT INTO test_groups (group_name, chart_type, trend_chart_type, description)
                                        VALUES (?, ?, ?, ?)
                                    """, (nt_panel_name.strip(), _gt, _trend, nt_desc.strip() or None))
                                    new_gid = crm.cursor.lastrowid
                                    for (t_n, t_grp, t_u, t_t, t_ct, t_cfg, _) in _defs:
                                        crm.cursor.execute("""
                                            INSERT INTO test_definitions
                                            (test_name, test_group, unit, default_target, chart_type, chart_config, group_id)
                                            VALUES (?, ?, ?, ?, ?, ?, ?)
                                        """, (t_n, t_grp, t_u, t_t, t_ct, t_cfg, new_gid))
                                    crm.conn.commit()
                                    st.success(f"'{nt_panel_name.strip()}' saved!")
                                    _nt_reset()
                                    time.sleep(0.8)
                                    st.rerun()
                                except sqlite3.IntegrityError as e:
                                    st.error(f"Error: {e}")
                                finally:
                                    crm.close()

            # ---- RIGHT COLUMN: Live Preview ----
            with nt_right:
                st.markdown("#### Live Preview")
                try:
                    _gt_prev    = st.session_state['nt_graph_type']
                    _n_prev     = st.session_state.get('nt_n_zones', 2)
                    _zones_prev = _zbuild('nt', _n_prev)
                    _ax_min = _zones_prev[0]['from'] if _zones_prev else 0.0
                    _ax_max = _zones_prev[-1]['to']  if _zones_prev else 100.0

                    if _gt_prev == "none":
                        _prev_img = render_text(72.5, "unit")
                        if _prev_img:
                            st.image(_prev_img, use_container_width=True)

                    elif _gt_prev == "gauge":
                        _mock_val = _ax_min + (_ax_max - _ax_min) * 0.55
                        _prev_cfg = {
                            "graph_type": "gauge",
                            "gauge_style": st.session_state.get('nt_gauge_style', 'curved'),
                            "axis_min": _ax_min, "axis_max": _ax_max,
                            "zones": _zones_prev
                        }
                        _prev_img = render_gauge(_mock_val, _prev_cfg)
                        if _prev_img:
                            st.image(_prev_img, use_container_width=True)

                    elif _gt_prev == "dot":
                        _nd_prev = st.session_state.get('nt_n_dots', 2)
                        _mock_dots = {
                            (st.session_state.get(f'nt_dot_name_{i}') or f"Test{i+1}"): _ax_min + (_ax_max - _ax_min) * (0.4 + i * 0.2)
                            for i in range(min(_nd_prev, 2))
                        }
                        _dot_cfg = [
                            {
                                "test_name":    st.session_state.get(f'nt_dot_name_{i}') or f"Test{i+1}",
                                "fill_color":   st.session_state.get(f'nt_dot_fill_{i}', '#003366'),
                                "stroke_color": st.session_state.get(f'nt_dot_stroke_{i}', '#003366'),
                                "label":        st.session_state.get(f'nt_dot_label_{i}', f"T{i+1}"),
                            }
                            for i in range(min(_nd_prev, 2))
                        ]
                        _prev_cfg = {
                            "graph_type": "dot",
                            "axis_min": _ax_min, "axis_max": _ax_max,
                            "zones": _zones_prev,
                            "dots": _dot_cfg
                        }
                        _prev_img = render_dot(_mock_dots, _prev_cfg)
                        if _prev_img:
                            st.image(_prev_img, use_container_width=True)

                    elif _gt_prev == "bar":
                        _bar_n_prev  = st.session_state.get('nt_bar_n', 2)
                        _bar_items_prev = []
                        for _bi in range(_bar_n_prev):
                            _bpfx = f'nt_bt_{_bi}'
                            _bnz = st.session_state.get(f'{_bpfx}_n_zones', 2)
                            _bt_zones = _zbuild(_bpfx, _bnz)
                            _mock_v = (_bt_zones[0]['to'] + _bt_zones[-1]['from']) / 2 if _bt_zones else 5.0
                            _bar_items_prev.append({
                                "name":   st.session_state.get(f'{_bpfx}_name', f"Test {_bi+1}") or f"Test {_bi+1}",
                                "value":  _mock_v,
                                "unit":   st.session_state.get(f'{_bpfx}_unit', ''),
                                "target": st.session_state.get(f'{_bpfx}_target', ''),
                                "config": {
                                    "graph_type": "bar",
                                    "bar_color":       st.session_state.get(f'{_bpfx}_barcol',   '#003366'),
                                    "bar_alert_color": st.session_state.get(f'{_bpfx}_alertcol', '#DC3545'),
                                    "zones": _bt_zones
                                }
                            })
                        _prev_img = render_bars(_bar_items_prev)
                        if _prev_img:
                            st.image(_prev_img, use_container_width=True)

                except Exception as _prev_err:
                    st.caption(f"Preview unavailable: {_prev_err}")

        st.divider()

        # ---- SECTION B: Individual Tests ----
        st.markdown("#### 📋 Active Test Library")

        if all_test_defs:
            df_td = pd.DataFrame(all_test_defs, columns=['ID', 'Test Name', 'Group', 'Unit', 'Target', 'Chart', 'Desc', 'JSON', 'Active'])
        else:
            df_td = pd.DataFrame(columns=['ID', 'Test Name', 'Group', 'Unit', 'Target', 'Chart', 'Desc', 'JSON', 'Active'])

        df_active   = df_td[df_td['Active'] == 1] if not df_td.empty else df_td
        df_archived = df_td[df_td['Active'] == 0] if not df_td.empty else df_td

        _COL_W = [3, 2, 1, 1.5, 1.2]

        with st.expander(f"📋 View Active Tests ({len(df_active)})", expanded=False):
            # Confirmation prompt for a pending archive action
            _pending_archive = st.session_state.get('pending_archive')
            if _pending_archive and _pending_archive in df_active['Test Name'].values:
                st.warning(f"Archive **{_pending_archive}**? It will be hidden from patient test ordering.")
                _ca, _cb = st.columns(2)
                if _ca.button("Yes, Archive", type="primary", key="confirm_archive_btn", use_container_width=True):
                    crm.connect()
                    crm.cursor.execute("UPDATE test_definitions SET is_active = 0 WHERE test_name = ?", (_pending_archive,))
                    crm.conn.commit(); crm.close()
                    del st.session_state['pending_archive']
                    st.rerun()
                if _cb.button("Cancel", key="cancel_archive_btn", use_container_width=True):
                    del st.session_state['pending_archive']
                    st.rerun()
                st.divider()

            if not df_active.empty:
                _h = st.columns(_COL_W)
                for _col, _label in zip(_h, ["**Test**", "**Group**", "**Unit**", "**Target**", ""]):
                    _col.markdown(_label)
                for _, _row in df_active.iterrows():
                    _c = st.columns(_COL_W)
                    _c[0].write(_row['Test Name'])
                    _c[1].write(_row['Group'] or "—")
                    _c[2].write(_row['Unit'] or "—")
                    _c[3].write((_row['Target'] or "—").replace("<", "\\<").replace(">", "\\>"))
                    if _c[4].button("Archive", key=f"arch_{_row['Test Name']}", use_container_width=True):
                        st.session_state['pending_archive'] = _row['Test Name']
                        st.rerun()
            else:
                st.caption("No active test definitions found.")

        _bar_groups = [row for row in all_test_groups if row['chart_type'] == 'bar']
        with st.expander(f"➕ Add Test to Existing Bar Panel ({len(_bar_groups)} available)", expanded=False):
            st.caption("Adds an extra test to an existing horizontal bar panel.")
            if not _bar_groups:
                st.info("No bar panels exist yet. Use 'Add New Test or Panel' above to create one first.")
            else:
                atp_panel = st.selectbox("Select Panel", options=[row['group_name'] for row in _bar_groups], key="add_to_panel_select")
                atp_inherited = next((row for row in _bar_groups if row['group_name'] == atp_panel), None)
                atp_group_id  = atp_inherited['group_id']         if atp_inherited else None
                atp_trend     = atp_inherited['trend_chart_type'] if atp_inherited else 'multi_trend'
                st.info(f"Chart style: **bar** | Trend chart: **{atp_trend}** (inherited from panel)")

                with st.form("add_to_panel_form", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    atp_name   = col1.text_input("Test Name (e.g., HDL Cholesterol)")
                    atp_unit   = col2.text_input("Unit (e.g., mmol/L)")
                    atp_target = st.text_input("Target Display Text (e.g., '>1.0')")
                    atp_barcol   = st.color_picker("Bar colour",       value="#003366", key="atp_barcol")
                    atp_alertcol = st.color_picker("Alert bar colour", value="#DC3545", key="atp_alertcol")
                    st.markdown("#### Zones")
                    st.caption("Define colour zones for this test's bar background (left to right).")
                    _atp_zones_raw = [
                        {"from": 0.0, "to": 5.0, "color": "#D4EDDA", "label": "Normal"},
                        {"from": 5.0, "to": 15.0, "color": "#FFCCCB", "label": "High"}
                    ]
                    atp_zones_text = st.text_area("Zones JSON", value=json.dumps(_atp_zones_raw, indent=2), height=140)
                    st.divider()
                    if st.form_submit_button("💾 Save Test", type="primary"):
                        if atp_name.strip():
                            try:
                                _parsed_zones = json.loads(atp_zones_text)
                            except json.JSONDecodeError:
                                st.error("Invalid zones JSON — check format.")
                                st.stop()
                            crm.connect()
                            try:
                                _atp_cfg = json.dumps({
                                    "graph_type": "bar",
                                    "bar_color": atp_barcol,
                                    "bar_alert_color": atp_alertcol,
                                    "zones": _parsed_zones
                                })
                                crm.cursor.execute("""
                                    INSERT INTO test_definitions (test_name, test_group, unit, default_target, chart_type, chart_config, group_id)
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                """, (atp_name.strip(), atp_panel, atp_unit.strip(), atp_target.strip(), "bar",
                                      _atp_cfg, atp_group_id))
                                crm.conn.commit()
                                st.success(f"Test '{atp_name}' added to panel '{atp_panel}'!")
                                time.sleep(1)
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error(f"Test '{atp_name}' already exists.")
                            finally:
                                crm.close()
                        else:
                            st.warning("Test Name is required.")

        # Edit an existing test definition
        if not df_td.empty:
            with st.expander("✏️ Edit Existing Test", expanded=False):
                edit_test_name = st.selectbox("Select Test to Edit", options=df_td['Test Name'].tolist(), key="edit_test_select")
                edit_row = df_td[df_td['Test Name'] == edit_test_name].iloc[0]

                # Re-init zone editor when selection changes
                if st.session_state.get('et_selected') != edit_test_name:
                    # Wipe ALL et_ widget keys so no values bleed from the previous test
                    for _k in list(st.session_state.keys()):
                        if _k.startswith('et_') and _k != 'et_selected':
                            del st.session_state[_k]
                    st.session_state['et_selected'] = edit_test_name
                    try:
                        _et_cfg_init = json.loads(edit_row['JSON'] or '{}')
                    except (json.JSONDecodeError, TypeError):
                        _et_cfg_init = {}
                    st.session_state['et_graph_type'] = _et_cfg_init.get('graph_type', 'none')
                    st.session_state['et_unit']   = edit_row['Unit']   or ''
                    st.session_state['et_target'] = edit_row['Target'] or ''
                    _zinit('et', _et_cfg_init)

                _et_gt = st.session_state.get('et_graph_type', 'none')
                et_left, et_right = st.columns([1.1, 1], gap="large")

                with et_left:
                    st.markdown(f"**Chart type:** `{_et_gt}`")
                    _etm1, _etm2 = st.columns(2)
                    if 'et_unit' not in st.session_state:
                        st.session_state['et_unit'] = ''
                    if 'et_target' not in st.session_state:
                        st.session_state['et_target'] = ''
                    _etm1.text_input("Unit", key='et_unit')
                    _etm2.text_input("Target Display Text", key='et_target')

                    if _et_gt == "gauge":
                        _etc1, _ = st.columns(2)
                        _et_gs = _etc1.radio("Style", ["curved", "straight"],
                                              index=["curved", "straight"].index(
                                                  st.session_state.get('et_gauge_style', 'curved')),
                                              key="et_gauge_style_radio")
                        st.session_state['et_gauge_style'] = _et_gs
                        _etaz_col, _ = st.columns(2)
                        if 'et_axis_start' not in st.session_state:
                            st.session_state['et_axis_start'] = 0.0
                        _etaz_col.number_input("Axis Start", key='et_axis_start', step=0.1)
                        _et_nz = st.session_state.get('et_n_zones', 2)
                        st.markdown("**Zones**")
                        _zrender('et', _et_nz)
                        if st.button("+ Add Zone", key="et_add_zone"):
                            _n = st.session_state.get('et_n_zones', 2)
                            _prev = float(st.session_state.get(f'et_zone_to_{_n-1}', 0.0))
                            st.session_state[f'et_zone_to_{_n}']     = _prev + 10.0
                            st.session_state[f'et_zone_color_{_n}']  = '#D4EDDA'
                            st.session_state[f'et_zone_transp_{_n}'] = False
                            st.session_state[f'et_zone_label_{_n}']  = ''
                            st.session_state['et_n_zones'] = _n + 1
                            st.rerun()

                    elif _et_gt == "dot":
                        _et_nd = st.session_state.get('et_n_dots', 2)
                        st.markdown("**Dots**")
                        _dh2 = st.columns([2, 2, 1.5, 1.5, 1])
                        for _lbl, _c in zip(["Test Name", "Display Label", "Fill Colour", "Stroke Colour", ""], _dh2):
                            _c.caption(_lbl)
                        for _di in range(_et_nd):
                            if f'et_dot_name_{_di}' not in st.session_state:
                                st.session_state[f'et_dot_name_{_di}'] = ''
                            if f'et_dot_label_{_di}' not in st.session_state:
                                st.session_state[f'et_dot_label_{_di}'] = ''
                            if f'et_dot_fill_{_di}' not in st.session_state:
                                st.session_state[f'et_dot_fill_{_di}'] = '#003366'
                            if f'et_dot_stroke_{_di}' not in st.session_state:
                                st.session_state[f'et_dot_stroke_{_di}'] = '#003366'
                            _etc = st.columns([2, 2, 1.5, 1.5, 1])
                            _etc[0].text_input("Test Name", key=f'et_dot_name_{_di}', label_visibility="collapsed")
                            _etc[1].text_input("Label",     key=f'et_dot_label_{_di}', label_visibility="collapsed")
                            _etc[2].color_picker("Fill",    key=f'et_dot_fill_{_di}', label_visibility="collapsed")
                            _etc[3].color_picker("Stroke",  key=f'et_dot_stroke_{_di}', label_visibility="collapsed")
                            if _etc[4].button("✕", key=f'et_dot_rm_{_di}') and _et_nd > 1:
                                for _j in range(_di, _et_nd - 1):
                                    for _s in ['name', 'label', 'fill', 'stroke']:
                                        src = f'et_dot_{_s}_{_j+1}'
                                        dst = f'et_dot_{_s}_{_j}'
                                        if src in st.session_state:
                                            st.session_state[dst] = st.session_state.pop(src)
                                for _s in ['name', 'label', 'fill', 'stroke']:
                                    _k = f'et_dot_{_s}_{_et_nd-1}'
                                    if _k in st.session_state:
                                        del st.session_state[_k]
                                st.session_state['et_n_dots'] = _et_nd - 1
                                st.rerun()
                        if _et_nd < 4 and st.button("+ Add Dot", key="et_add_dot"):
                            st.session_state['et_n_dots'] = _et_nd + 1
                            st.rerun()
                        if 'et_axis_start' not in st.session_state:
                            st.session_state['et_axis_start'] = 0.0
                        st.number_input("Axis Start", key='et_axis_start', step=0.1)
                        st.markdown("**Zones**")
                        _et_nz = st.session_state.get('et_n_zones', 2)
                        _zrender('et', _et_nz)
                        if st.button("+ Add Zone", key="et_add_zone_dot"):
                            _n = st.session_state.get('et_n_zones', 2)
                            _prev = float(st.session_state.get(f'et_zone_to_{_n-1}', 0.0))
                            st.session_state[f'et_zone_to_{_n}']     = _prev + 10.0
                            st.session_state[f'et_zone_color_{_n}']  = '#D4EDDA'
                            st.session_state[f'et_zone_transp_{_n}'] = False
                            st.session_state[f'et_zone_label_{_n}']  = ''
                            st.session_state['et_n_zones'] = _n + 1
                            st.rerun()

                    elif _et_gt == "bar":
                        if 'et_axis_start' not in st.session_state:
                            st.session_state['et_axis_start'] = 0.0
                        st.number_input("Axis Start", key='et_axis_start', step=0.1)
                        if 'et_bar_color' not in st.session_state:
                            st.session_state['et_bar_color'] = '#003366'
                        if 'et_bar_alert_color' not in st.session_state:
                            st.session_state['et_bar_alert_color'] = '#DC3545'
                        _etbc1, _etbc2 = st.columns(2)
                        _etbc1.color_picker("Bar colour",       key='et_bar_color')
                        _etbc2.color_picker("Alert bar colour", key='et_bar_alert_color')
                        st.markdown("**Zones**")
                        _et_nz = st.session_state.get('et_n_zones', 2)
                        _zrender('et', _et_nz)
                        if st.button("+ Add Zone", key="et_add_zone_bar"):
                            _n = st.session_state.get('et_n_zones', 2)
                            _prev = float(st.session_state.get(f'et_zone_to_{_n-1}', 0.0))
                            st.session_state[f'et_zone_to_{_n}']     = _prev + 10.0
                            st.session_state[f'et_zone_color_{_n}']  = '#D4EDDA'
                            st.session_state[f'et_zone_transp_{_n}'] = False
                            st.session_state[f'et_zone_label_{_n}']  = ''
                            st.session_state['et_n_zones'] = _n + 1
                            st.rerun()

                    # else: none — unit/target only

                    st.divider()
                    if st.button("💾 Save Changes", type="primary", key="et_save_btn"):
                        _et_nz   = st.session_state.get('et_n_zones', 2)
                        _et_zones = _zbuild('et', _et_nz)
                        _et_ax_min = _et_zones[0]['from'] if _et_zones else 0.0
                        _et_ax_max = _et_zones[-1]['to']  if _et_zones else 100.0

                        if _et_gt == "none":
                            _et_new_cfg = {"graph_type": "none"}
                        elif _et_gt == "gauge":
                            _et_new_cfg = {
                                "graph_type": "gauge",
                                "gauge_style": st.session_state.get('et_gauge_style', 'curved'),
                                "axis_min": _et_ax_min,
                                "axis_max": _et_ax_max,
                                "zones": _et_zones
                            }
                        elif _et_gt == "dot":
                            _et_nd = st.session_state.get('et_n_dots', 2)
                            _et_dots = [
                                {
                                    "test_name":    st.session_state.get(f'et_dot_name_{_di}', ''),
                                    "label":        st.session_state.get(f'et_dot_label_{_di}', ''),
                                    "fill_color":   st.session_state.get(f'et_dot_fill_{_di}', '#003366'),
                                    "stroke_color": st.session_state.get(f'et_dot_stroke_{_di}', '#003366'),
                                }
                                for _di in range(_et_nd)
                            ]
                            _et_new_cfg = {
                                "graph_type": "dot",
                                "axis_min": _et_ax_min,
                                "axis_max": _et_ax_max,
                                "zones": _et_zones,
                                "dots": _et_dots
                            }
                        elif _et_gt == "bar":
                            _et_new_cfg = {
                                "graph_type": "bar",
                                "bar_color":       st.session_state.get('et_bar_color', '#003366'),
                                "bar_alert_color": st.session_state.get('et_bar_alert_color', '#DC3545'),
                                "zones": _et_zones
                            }
                        else:
                            _et_new_cfg = {}

                        crm.connect()
                        try:
                            crm.cursor.execute("""
                                UPDATE test_definitions SET unit = ?, default_target = ?, chart_config = ?
                                WHERE test_name = ?
                            """, (st.session_state.get('et_unit', '').strip(),
                                  st.session_state.get('et_target', '').strip(),
                                  json.dumps(_et_new_cfg),
                                  edit_test_name))
                            crm.conn.commit()
                            st.success(f"'{edit_test_name}' updated successfully!")
                            time.sleep(1)
                            st.rerun()
                        except Exception as _e:
                            st.error(f"Save failed: {_e}")
                        finally:
                            crm.close()

                with et_right:
                    st.markdown("#### Preview")
                    try:
                        _et_nz_p     = st.session_state.get('et_n_zones', 2)
                        _et_zones_p  = _zbuild('et', _et_nz_p)
                        _et_ax_min_p = _et_zones_p[0]['from'] if _et_zones_p else 0.0
                        _et_ax_max_p = _et_zones_p[-1]['to']  if _et_zones_p else 100.0

                        if _et_gt == "none":
                            _et_img = render_text(72.5, st.session_state.get('et_unit', ''))
                        elif _et_gt == "gauge":
                            _mock_v = _et_ax_min_p + (_et_ax_max_p - _et_ax_min_p) * 0.55
                            _et_img = render_gauge(_mock_v, {
                                "graph_type": "gauge",
                                "gauge_style": st.session_state.get('et_gauge_style', 'curved'),
                                "axis_min": _et_ax_min_p, "axis_max": _et_ax_max_p,
                                "zones": _et_zones_p
                            })
                        elif _et_gt == "dot":
                            _et_nd_p = st.session_state.get('et_n_dots', 2)
                            _et_mock_dots = {
                                (st.session_state.get(f'et_dot_name_{i}') or f"Test{i+1}"): _et_ax_min_p + (_et_ax_max_p - _et_ax_min_p) * (0.4 + i * 0.2)
                                for i in range(min(_et_nd_p, 2))
                            }
                            _et_dot_cfg = [
                                {
                                    "test_name":    st.session_state.get(f'et_dot_name_{i}') or f"Test{i+1}",
                                    "fill_color":   st.session_state.get(f'et_dot_fill_{i}', '#003366'),
                                    "stroke_color": st.session_state.get(f'et_dot_stroke_{i}', '#003366'),
                                    "label":        st.session_state.get(f'et_dot_label_{i}', f"T{i+1}"),
                                }
                                for i in range(min(_et_nd_p, 2))
                            ]
                            _et_img = render_dot(_et_mock_dots, {
                                "graph_type": "dot",
                                "axis_min": _et_ax_min_p, "axis_max": _et_ax_max_p,
                                "zones": _et_zones_p,
                                "dots": _et_dot_cfg
                            })
                        elif _et_gt == "bar":
                            _et_img = render_bars([{
                                "name":   edit_test_name,
                                "value":  _et_ax_min_p + (_et_ax_max_p - _et_ax_min_p) * 0.55,
                                "unit":   st.session_state.get('et_unit', ''),
                                "target": st.session_state.get('et_target', ''),
                                "config": {
                                    "graph_type": "bar",
                                    "bar_color":       st.session_state.get('et_bar_color', '#003366'),
                                    "bar_alert_color": st.session_state.get('et_bar_alert_color', '#DC3545'),
                                    "zones": _et_zones_p
                                }
                            }])
                        else:
                            _et_img = None

                        if _et_img:
                            st.image(_et_img, use_container_width=True)
                    except Exception as _e:
                        st.caption(f"Preview unavailable: {_e}")

        with st.expander(f"🗄️ Archived Tests ({len(df_archived)})", expanded=False):
            # Confirmation prompt for a pending restore action
            _pending_restore = st.session_state.get('pending_restore')
            if _pending_restore and _pending_restore in df_archived['Test Name'].values:
                st.success(f"Restore **{_pending_restore}**? It will become available for patient test ordering.")
                _ra, _rb = st.columns(2)
                if _ra.button("Yes, Restore", type="primary", key="confirm_restore_btn", use_container_width=True):
                    crm.connect()
                    crm.cursor.execute("UPDATE test_definitions SET is_active = 1 WHERE test_name = ?", (_pending_restore,))
                    crm.conn.commit(); crm.close()
                    del st.session_state['pending_restore']
                    st.rerun()
                if _rb.button("Cancel", key="cancel_restore_btn", use_container_width=True):
                    del st.session_state['pending_restore']
                    st.rerun()
                st.divider()

            if not df_archived.empty:
                _h = st.columns(_COL_W)
                for _col, _label in zip(_h, ["**Test**", "**Group**", "**Unit**", "**Target**", ""]):
                    _col.markdown(_label)
                for _, _row in df_archived.iterrows():
                    _c = st.columns(_COL_W)
                    _c[0].write(_row['Test Name'])
                    _c[1].write(_row['Group'] or "—")
                    _c[2].write(_row['Unit'] or "—")
                    _c[3].write((_row['Target'] or "—").replace("<", "\\<").replace(">", "\\>"))
                    if _c[4].button("Restore", key=f"rest_{_row['Test Name']}", use_container_width=True):
                        st.session_state['pending_restore'] = _row['Test Name']
                        st.rerun()
            else:
                st.caption("No archived tests.")
