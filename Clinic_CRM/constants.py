# Single source of truth for all status strings used across the application.
# Any status comparison or assignment should reference these constants,
# not a raw string literal.

# --- Appointment statuses ---
APPT_SCHEDULED = "Scheduled"
APPT_COMPLETED = "Completed"
APPT_NO_SHOW   = "No Show"
APPT_CANCELLED = "Cancelled"

# --- Test result statuses ---
TEST_PENDING  = "Pending"
TEST_COMPLETE = "Complete"
