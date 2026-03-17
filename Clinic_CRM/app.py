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
                            'ResultID', 'Status', 'TakenOn', 'TakenBy', 'TakenNote', 'RecOn', 'LogBy'
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
            
            # Padded out to match the new 16-column data structure for test results
            dummy_tests = [
                ("2026-02-26", "Vitamin D", 68, "nmol/L", "Vitamin D", '{"safe_min": 50, "safe_max": 125}', "Levels are sufficient. Continue current supplement routine.", "50 - 125", "gauge", 1, "Complete", "2026-02-26", "Admin", "", "2026-02-26", "Admin"),
                ("2026-02-26", "Fasting Glucose", 5.1, "mmol/L", "Blood Glucose", '{"safe_min": 4.0, "safe_max": 5.4}', "Excellent progress. Fasting levels have stabilized.", "4.0 - 5.4", "gauge", 2, "Complete", "2026-02-26", "Admin", "", "2026-02-26", "Admin"),
                ("2025-11-10", "Fasting Glucose", 5.3, "mmol/L", "Blood Glucose", '{"safe_min": 4.0, "safe_max": 5.4}', "", "4.0 - 5.4", "gauge", 3, "Complete", "2025-11-10", "Admin", "", "2025-11-10", "Admin"),
                ("2025-08-15", "Fasting Glucose", 5.6, "mmol/L", "Blood Glucose", '{"safe_min": 4.0, "safe_max": 5.4}', "", "4.0 - 5.4", "gauge", 4, "Complete", "2025-08-15", "Admin", "", "2025-08-15", "Admin")
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
        crm.cursor.execute("SELECT group_id, group_name, chart_type, description FROM test_groups ORDER BY group_name")
        all_test_groups = crm.cursor.fetchall()
        crm.close()
        
        # ---- SECTION A: Test Panels ----
        st.markdown("#### 🗂️ Test Panels")

        with st.expander(f"📋 View Panels ({len(all_test_groups)})", expanded=False):
            if all_test_groups:
                df_tg = pd.DataFrame(all_test_groups, columns=['group_id', 'Panel Name', 'Chart Style', 'Description'])
                st.dataframe(
                    df_tg, hide_index=True, use_container_width=True,
                    column_config={"group_id": None}
                )
            else:
                st.caption("No test panels defined yet.")

        with st.expander("➕ Add New Test Panel", expanded=False):
            new_panel_chart = st.selectbox(
                "Chart Style",
                [
                    "gauge (Standard dial chart)",
                    "multi_bar_panel (For grouping multiple tests together)",
                    "text_only (No chart, just numbers/text)",
                    "bp_range (Blood Pressure style)",
                    "bmi_bullet (BMI specific)"
                ],
                key="new_panel_chart_select"
            )
            panel_chart_val = new_panel_chart.split(" ")[0]

            with st.form("new_panel_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                new_panel_name = col1.text_input("Panel Name (e.g., Cholesterol, Vitamin D Panel)")
                new_panel_desc = col2.text_input("Description (optional)", placeholder="e.g., Lipid panel metrics")

                if st.form_submit_button("💾 Save Panel", type="primary"):
                    if new_panel_name.strip():
                        crm.connect()
                        try:
                            crm.cursor.execute("""
                                INSERT INTO test_groups (group_name, chart_type, description)
                                VALUES (?, ?, ?)
                            """, (new_panel_name.strip(), panel_chart_val, new_panel_desc.strip() or None))
                            crm.conn.commit()
                            st.success(f"Panel '{new_panel_name}' added successfully!")
                            time.sleep(1)
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error(f"Panel '{new_panel_name}' already exists.")
                        finally:
                            crm.close()
                    else:
                        st.warning("Panel Name is required.")

        st.divider()

        # ---- SECTION B: Individual Tests ----
        st.markdown("#### 📋 Active Test Library")

        if all_test_defs:
            df_td = pd.DataFrame(all_test_defs, columns=['ID', 'Test Name', 'Group', 'Unit', 'Target', 'Chart', 'Desc', 'JSON', 'Active'])
        else:
            df_td = pd.DataFrame(columns=['ID', 'Test Name', 'Group', 'Unit', 'Target', 'Chart', 'Desc', 'JSON', 'Active'])

        with st.expander(f"📋 View Tests ({len(df_td)})", expanded=False):
            if not df_td.empty:
                st.dataframe(
                    df_td, hide_index=True, use_container_width=True,
                    column_config={
                        "ID": None, "Desc": None, "JSON": None,
                        "Active": st.column_config.CheckboxColumn("Active?")
                    }
                )
            else:
                st.caption("No test definitions found.")

        with st.expander("➕ Add New Test to a Panel", expanded=False):
            panel_options = [row['group_name'] for row in all_test_groups] if all_test_groups else []
            if not panel_options:
                st.warning("Create a Test Panel first before adding individual tests.")
            else:
                selected_panel = st.selectbox("Select Panel", options=panel_options, key="new_test_panel_select")

                # Look up the chart type inherited from the selected panel
                inherited_chart = next(
                    (row['chart_type'] for row in all_test_groups if row['group_name'] == selected_panel),
                    'gauge'
                )
                inherited_group_id = next(
                    (row['group_id'] for row in all_test_groups if row['group_name'] == selected_panel),
                    None
                )
                st.info(f"Chart style: **{inherited_chart}** (inherited from panel — not editable here)")

                with st.form("new_test_form", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    new_t_name = col1.text_input("Specific Test Name (e.g., Vitamin D, Calcium)")
                    new_t_unit = col2.text_input("Unit (e.g., nmol/L, mg/dL)")

                    new_t_target = st.text_input("Target Display Text (e.g., '50-125' or '<5.0')")

                    config_dict = {}

                    if inherited_chart in ["gauge", "bp_range"]:
                        st.markdown("#### Chart Boundaries")
                        st.caption("Define the absolute edges of the chart, and the healthy 'Green' zone within it.")
                        c1, c2, c3, c4 = st.columns(4)
                        config_dict["axis_min"] = c1.number_input("Absolute Minimum (Left Edge)", value=0.0)
                        config_dict["safe_min"] = c2.number_input("Healthy Min (Green Start)", value=0.0, help="Enter the lower bound of the healthy range for this test")
                        config_dict["safe_max"] = c3.number_input("Healthy Max (Green End)", value=0.0, help="Enter the upper bound of the healthy range for this test")
                        config_dict["axis_max"] = c4.number_input("Absolute Maximum (Right Edge)", value=100.0)

                    elif inherited_chart == "multi_bar_panel":
                        st.markdown("#### Healthy Range")
                        st.caption("Bar panels auto-scale their outer edges, so they only need the healthy targets.")
                        c1, c2 = st.columns(2)
                        config_dict["safe_min"] = c1.number_input("Healthy Minimum", value=0.0, help="Enter the lower bound of the healthy range for this test")
                        config_dict["safe_max"] = c2.number_input("Healthy Maximum", value=0.0, help="Enter the upper bound of the healthy range for this test")

                    elif inherited_chart == "bmi_bullet":
                        crm.connect()
                        crm.cursor.execute("SELECT chart_config FROM test_definitions WHERE chart_type = 'bmi_bullet' LIMIT 1")
                        _bmi_row = crm.cursor.fetchone()
                        crm.close()
                        if _bmi_row and _bmi_row['chart_config']:
                            config_dict = json.loads(_bmi_row['chart_config'])
                            st.success("Standard BMI zones loaded from test definitions.")
                        else:
                            config_dict = {
                                "axis_min": 10.0, "axis_max": 40.0,
                                "zones": [
                                    {"limit": 18.5, "color": "blue"}, {"limit": 25.0, "color": "green"},
                                    {"limit": 30.0, "color": "warning"}, {"limit": 40.0, "color": "alert"}
                                ]
                            }
                            st.info("Using default BMI zones (no existing BMI test definition found).")

                    st.divider()
                    if st.form_submit_button("💾 Save Test Definition", type="primary"):
                        if new_t_name.strip():
                            crm.connect()
                            try:
                                crm.cursor.execute("""
                                    INSERT INTO test_definitions
                                        (test_name, test_group, unit, default_target, chart_type, chart_config, group_id)
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    new_t_name.strip(), selected_panel, new_t_unit.strip(),
                                    new_t_target.strip(), inherited_chart, json.dumps(config_dict),
                                    inherited_group_id
                                ))
                                crm.conn.commit()
                                st.success(f"Test '{new_t_name}' added to panel '{selected_panel}'!")
                                time.sleep(1)
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error(f"Test '{new_t_name}' already exists.")
                            finally:
                                crm.close()
                        else:
                            st.warning("Test Name is required.")

        # Edit an existing test definition
        if not df_td.empty:
            with st.expander("✏️ Edit Existing Test", expanded=False):
                edit_test_name = st.selectbox("Select Test to Edit", options=df_td['Test Name'].tolist(), key="edit_test_select")
                edit_row = df_td[df_td['Test Name'] == edit_test_name].iloc[0]

                with st.form("edit_test_form", clear_on_submit=False):
                    col1, col2 = st.columns(2)
                    edit_unit = col1.text_input("Unit", value=edit_row['Unit'] or "")
                    edit_target = col2.text_input("Target Display Text", value=edit_row['Target'] or "")
                    edit_config = st.text_area("Chart Config (JSON)", value=edit_row['JSON'] or "{}", height=120)

                    if st.form_submit_button("💾 Save Changes", type="primary"):
                        try:
                            json.loads(edit_config)  # validate before saving
                            crm.connect()
                            crm.cursor.execute("""
                                UPDATE test_definitions SET unit = ?, default_target = ?, chart_config = ?
                                WHERE test_name = ?
                            """, (edit_unit.strip(), edit_target.strip(), edit_config.strip(), edit_test_name))
                            crm.conn.commit()
                            crm.close()
                            st.success(f"'{edit_test_name}' updated successfully!")
                            time.sleep(1)
                            st.rerun()
                        except json.JSONDecodeError:
                            st.error("Invalid JSON in Chart Config — check the format and try again.")
                        finally:
                            crm.close()

        # Form to toggle active status (Soft Delete)
        if not df_td.empty:
            with st.form("toggle_test_form"):
                toggle_test_name = st.selectbox("Select Test to Archive/Restore", options=df_td['Test Name'].tolist())
                current_state = df_td[df_td['Test Name'] == toggle_test_name]['Active'].iloc[0]
                action_text = "Archive (Hide)" if current_state == 1 else "Restore (Activate)"

                if st.form_submit_button(f"🔄 {action_text} Selected Test"):
                    new_state = 0 if current_state == 1 else 1
                    crm.connect()
                    crm.cursor.execute("UPDATE test_definitions SET is_active = ? WHERE test_name = ?", (new_state, toggle_test_name))
                    crm.conn.commit(); crm.close()
                    st.success(f"Test '{toggle_test_name}' has been updated."); st.rerun()
