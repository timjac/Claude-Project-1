import sqlite3
import random
from datetime import datetime, timedelta

DB_NAME = "family_clinic.db"

# --- EXPANDED FANTASY DATA POOLS ---
FIRST_NAMES = ["Frodo", "Samwise", "Aragorn", "Gandalf", "Legolas", "Gimli", "Boromir", "Elrond", "Galadriel", "Arwen", "Eowyn", "Faramir", "Theoden", "Thorin", "Harry", "Ron", "Hermione", "Albus", "Severus", "Minerva", "Rubeus", "Sirius", "Remus", "Neville", "Jon", "Daenerys", "Tyrion", "Arya", "Sansa", "Bran", "Robb", "Ned", "Catelyn", "Cersei", "Jaime", "Jorah", "Sandor", "Brienne", "Geralt", "Yennefer", "Ciri", "Triss", "Dandelion", "Vesemir"]
LAST_NAMES = ["Baggins", "Gamgee", "Stark", "Potter", "Targaryen", "Lannister", "Granger", "Weasley", "Dumbledore", "of Rivia", "Snow", "Oakenshield", "Took", "Brandybuck", "Baratheon", "Tyrell", "Martell", "Greyjoy", "Strider", "Stormborn", "Snape", "McGonagall", "Hagrid", "Black", "Lupin", "Longbottom", "Clegane", "Tarth", "Merigold"]
TOWNS = ["The Shire", "Rivendell", "Minas Tirith", "Rohan", "Gondor", "Hogwarts", "Hogsmeade", "Diagon Alley", "Winterfell", "King's Landing", "Castle Black", "Kaer Morhen", "Novigrad", "Oxenfurt", "Skellige"]
BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
PROVIDERS = ["Dr. Elrond", "Nurse Pomfrey", "Maester Luwin", "Admin", "Dr. McCoy"]

ENCOUNTER_TYPES = ["Clinical Encounter", "Telephone Consult", "Admin/Chart Review"]
TEST_GROUPS = ["Blood Pressure", "Cholesterol Panel", "Vitals", "Metabolic"]

def random_date(start_days_ago, end_days_ago):
    """Generates a random datetime between X and Y days ago."""
    now = datetime.now()
    delta = timedelta(days=random.randint(end_days_ago, start_days_ago))
    # Randomize time during clinic hours
    return now.replace(hour=random.randint(8, 17), minute=random.choice([0, 15, 30, 45]), second=0) - delta

def generate_data():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    print("🐉 Seeding 103 Fantasy Patients into the database...")

    # ==========================================
    # 1. GENERATE 102 REGULAR PATIENTS
    # ==========================================
    for patient_id in range(1, 103):
        # --- A. Patient Demographics ---
        fname = random.choice(FIRST_NAMES)
        lname = random.choice(LAST_NAMES)
        dob = random_date(25000, 7000).strftime("%Y-%m-%d")
        town = random.choice(TOWNS)
        phone = f"07700 {random.randint(100000, 999999)}"
        bg = random.choice(BLOOD_GROUPS)

        fields = [
            ("first_name", fname), ("last_name", lname), ("date_of_birth", dob),
            ("address_town", town), ("phone", phone), ("blood_group", bg)
        ]
        
        for field, val in fields:
            # 5% chance to skip a field to simulate missing data (except names/DOB)
            if field not in ["first_name", "last_name", "date_of_birth"] and random.random() < 0.05:
                continue 
            cursor.execute("INSERT INTO patient_history (patient_id, field_name, field_value, changed_by, change_reason) VALUES (?, ?, ?, ?, 'System Seed')", (patient_id, field, val, "System"))

        # --- B. Encounters & Notes ---
        num_encounters = random.randint(1, 5) # Every patient gets at least 1, up to 5
        for _ in range(num_encounters):
            enc_date = random_date(700, 1)
            # Weighted random: 60% physical, 30% phone, 10% admin
            enc_type = random.choices(ENCOUNTER_TYPES, weights=[0.6, 0.3, 0.1])[0]
            provider = random.choice(PROVIDERS)

            cursor.execute("INSERT INTO encounters (patient_id, encounter_date, encounter_type, created_by) VALUES (?, ?, ?, ?)", (patient_id, enc_date.strftime("%Y-%m-%d"), enc_type, provider))
            encounter_id = cursor.lastrowid

            # EVERY encounter gets a note. Content depends on the type.
            if enc_type == "Telephone Consult":
                note = random.choice([
                    "Patient called regarding potion side effects. Advised to reduce dosage.",
                    "Telephone follow-up. Symptoms have resolved. Discharging from current care pathway.",
                    "Patient requested refill via raven. Authorized for 3 months."
                ])
            elif enc_type == "Admin/Chart Review":
                note = random.choice([
                    "Reviewed historical scrolls from previous healer. Updated allergies.",
                    "Lab results received and attached to file. No further action needed.",
                    "Referral sent to specialist in King's Landing."
                ])
            else:
                note = random.choice([
                    "Routine physical exam. Vitals stable. No acute concerns.",
                    "Patient presents with fatigue after long journey. Prescribed rest and restorative draught.",
                    "Follow-up for minor battle wound. Healing well, no signs of dragon-scale infection."
                ])
            
            cursor.execute("INSERT INTO encounter_notes (encounter_id, note_text, created_by, created_at) VALUES (?, ?, ?, ?)", (encounter_id, note, provider, enc_date.strftime("%Y-%m-%d %H:%M:%S")))

            # --- C. Test Results (Longitudinal) ---
            # 60% chance this encounter resulted in tests being ordered
            if random.random() > 0.4 and enc_type == "Clinical Encounter":
                enc_str = enc_date.strftime("%Y-%m-%d %H:%M:%S")
                # 85% chance of a note being attached to the test result
                has_test_note = random.random() < 0.85
                t_note = "Normal reading." if has_test_note else ""

                chosen_panel = random.choice(TEST_GROUPS)
                
                if chosen_panel == "Blood Pressure":
                    sys_val = str(random.randint(100, 150))
                    dia_val = str(random.randint(60, 95))
                    t_note = "Slightly elevated due to recent combat." if int(sys_val) > 130 and has_test_note else t_note
                    for t_name, t_val in [("Systolic", sys_val), ("Diastolic", dia_val)]:
                        cursor.execute("""
                            INSERT INTO test_results (encounter_id, test_name, test_taken_on, test_taken_by, test_value, result_received_on, result_logged_by, result_note, status)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Complete')
                        """, (encounter_id, t_name, enc_str, provider, t_val, enc_str, provider, t_note))
                
                elif chosen_panel == "Cholesterol Panel":
                    t_chol = str(round(random.uniform(3.5, 6.5), 1))
                    hdl = str(round(random.uniform(1.0, 2.2), 1))
                    ldl = str(round(random.uniform(1.5, 4.0), 1))
                    for t_name, t_val in [("Total Cholesterol", t_chol), ("HDL Cholesterol", hdl), ("LDL Cholesterol", ldl)]:
                        cursor.execute("""
                            INSERT INTO test_results (encounter_id, test_name, test_taken_on, test_taken_by, test_value, result_received_on, result_logged_by, result_note, status)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Complete')
                        """, (encounter_id, t_name, enc_str, provider, t_val, enc_str, provider, t_note))

                elif chosen_panel == "Vitals":
                    weight = str(random.randint(60, 110))
                    bmi = str(round(int(weight) / ((1.75)**2), 1)) # Rough math assuming everyone is 1.75m
                    for t_name, t_val in [("Weight", weight), ("BMI", bmi)]:
                        cursor.execute("""
                            INSERT INTO test_results (encounter_id, test_name, test_taken_on, test_taken_by, test_value, result_received_on, result_logged_by, result_note, status)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Complete')
                        """, (encounter_id, t_name, enc_str, provider, t_val, enc_str, provider, t_note))

    # ==========================================
    # 2. GENERATE PATIENT 103 (THE GOLDEN RECORD)
    # ==========================================
    p103_id = 103
    print("🌟 Building Patient 103 (Bilbo Baggins - The Golden Report Candidate)...")
    
    p103_fields = [
        ("first_name", "Bilbo"), ("last_name", "Baggins"), ("date_of_birth", "1937-09-22"),
        ("address_town", "The Shire"), ("phone", "07700 111222"), ("blood_group", "O-")
    ]
    for field, val in p103_fields:
        cursor.execute("INSERT INTO patient_history (patient_id, field_name, field_value, changed_by) VALUES (?, ?, ?, 'System')", (p103_id, field, val))

    # Bilbo's Timeline: 4 visits over 1 year showing a health journey.
    # This guarantees gorgeous multi-point trendlines on his PDF.
    timeline = [
        {"days_ago": 365, "weight": "95", "bmi": "31.0", "sys": "155", "dia": "95", "f_gluc": "6.8", "t_chol": "6.5", "hdl": "0.9", "ldl": "4.2", "note": "Patient presents with hypertension, elevated glucose, and poor lipids. Highly sedentary lifestyle (lots of pipe-weed and second breakfasts). Advised strict diet."},
        {"days_ago": 270, "weight": "91", "bmi": "29.7", "sys": "142", "dia": "90", "f_gluc": "6.1", "t_chol": "5.8", "hdl": "1.1", "ldl": "3.8", "note": "Making progress. Cut out elevenses. Blood pressure improving but still elevated."},
        {"days_ago": 180, "weight": "86", "bmi": "28.0", "sys": "135", "dia": "85", "f_gluc": "5.7", "t_chol": "5.2", "hdl": "1.3", "ldl": "3.1", "note": "Excellent progress. Patient is hiking daily (claims he is preparing for an adventure). Glucose is now in normal range."},
        {"days_ago": 30,  "weight": "80", "bmi": "26.1", "sys": "122", "dia": "80", "f_gluc": "5.0", "t_chol": "4.5", "hdl": "1.5", "ldl": "2.5", "note": "Target weight almost reached. All blood panels and vitals look fantastic. Cleared for travel to Rivendell."}
    ]

    for t in timeline:
        enc_date = datetime.now() - timedelta(days=t["days_ago"])
        enc_str = enc_date.strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("INSERT INTO encounters (patient_id, encounter_date, encounter_type, created_by) VALUES (?, ?, 'Clinical Encounter', 'Dr. Elrond')", (p103_id, enc_date.strftime("%Y-%m-%d")))
        enc_id = cursor.lastrowid

        cursor.execute("INSERT INTO encounter_notes (encounter_id, note_text, created_by, created_at) VALUES (?, ?, 'Dr. Elrond', ?)", (enc_id, t["note"], enc_str))

        # Insert Tests
        tests = [
            ("Weight", t["weight"]), ("BMI", t["bmi"]), 
            ("Systolic", t["sys"]), ("Diastolic", t["dia"]), 
            ("Blood Glucose (Fasting)", t["f_gluc"]), 
            ("Total Cholesterol", t["t_chol"]), ("HDL Cholesterol", t["hdl"]), ("LDL Cholesterol", t["ldl"])
        ]
        
        for t_name, t_val in tests:
            cursor.execute("""
                INSERT INTO test_results (encounter_id, test_name, test_taken_on, test_taken_by, test_value, result_received_on, result_logged_by, result_note, status)
                VALUES (?, ?, ?, 'Dr. Elrond', ?, ?, 'Dr. Elrond', ?, 'Complete')
            """, (enc_id, t_name, enc_str, t_val, enc_str, "Progressing well." if "Chol" not in t_name else ""))

    # Bilbo gets one Single-Point test (Gauge Chart)
    cursor.execute("""
        INSERT INTO test_results (encounter_id, test_name, test_taken_on, test_taken_by, test_value, result_received_on, result_logged_by, result_note, status)
        VALUES (?, 'O2 Saturation', ?, 'Dr. Elrond', '98', ?, 'Dr. Elrond', 'Lungs clear.', 'Complete')
    """, (enc_id, enc_str, enc_str))

    # Bilbo gets one Pending test
    cursor.execute("INSERT INTO encounters (patient_id, encounter_date, encounter_type, created_by) VALUES (?, ?, 'Clinical Encounter', 'Nurse Pomfrey')", (p103_id, datetime.now().strftime("%Y-%m-%d")))
    pending_enc_id = cursor.lastrowid
    cursor.execute("""
        INSERT INTO test_results (encounter_id, test_name, test_taken_on, test_taken_by, test_taken_note, status)
        VALUES (?, 'Temperature', ?, 'Nurse Pomfrey', 'Taken via ear thermometer, awaiting calibration check.', 'Pending')
    """, (pending_enc_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))


    # ==========================================
    # 3. GENERATE APPOINTMENTS (PAST & FUTURE)
    # ==========================================
    print("📅 Scheduling past and future appointments...")
    
    # --- Past Appointments (Attended and No Show) ---
    for _ in range(50):
        random_pid = random.randint(1, 103)
        appt_date = random_date(300, 1) # Past 300 days
        appt_time = f"{random.randint(9, 16):02d}:{random.choice(['00', '15', '30', '45'])}"
        provider = random.choice(PROVIDERS)
        
        # 80% chance they attended (Completed), 20% No Show
        status = "Completed" if random.random() > 0.2 else "No Show"

        cursor.execute("""
            INSERT INTO appointments (patient_id, appointment_date, appointment_time, provider, reason, status, created_by)
            VALUES (?, ?, ?, ?, 'Past Visit', ?, 'Admin')
        """, (random_pid, appt_date.strftime("%Y-%m-%d"), appt_time, provider, status))

    # --- Future Appointments (Medium Full Schedule for next 30 days) ---
    for _ in range(80):
        random_pid = random.randint(1, 103)
        appt_date = random_date(-1, -30) # Future 30 days
        appt_time = f"{random.randint(9, 16):02d}:{random.choice(['00', '15', '30', '45'])}"
        provider = random.choice(PROVIDERS)
        reason = random.choice(["Routine Checkup", "Potion refill", "Battle wound follow-up", "Vaccination", "Dietary review"])

        cursor.execute("""
            INSERT INTO appointments (patient_id, appointment_date, appointment_time, provider, reason, status, created_by)
            VALUES (?, ?, ?, ?, ?, 'Scheduled', 'Admin')
        """, (random_pid, appt_date.strftime("%Y-%m-%d"), appt_time, provider, reason))


    conn.commit()
    conn.close()
    print("✅ Done! Middle-earth database is fully populated.")

if __name__ == "__main__":
    generate_data()