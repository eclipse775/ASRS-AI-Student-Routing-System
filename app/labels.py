"""US10: collect labeled training examples from staff decisions (no dependencies on other app modules)."""
from app.database import utc_now

# staff_correction:   staff moved a request the AI had already routed (the AI was wrong).
# escalation_outcome: staff chose the department for a request the AI could not route confidently.
# reopened:           a resolved request was reopened and stayed with its department, which keeps the
#                     department as a weaker label (it is never used as validation ground truth).
SOURCES = ("staff_correction", "escalation_outcome", "reopened")
STRONG_SOURCES = ("staff_correction", "escalation_outcome")


def record_label(db, request_id, label, text, source, correction_id=None):
    if source not in SOURCES:
        raise ValueError("Unknown label source.")
    db.execute("""INSERT OR IGNORE INTO training_samples (request_id,correction_id,source,label,text,created_at)
                  VALUES (?,?,?,?,?,?)""", (request_id, correction_id, source, label, text, utc_now()))
