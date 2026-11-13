from datetime import datetime, time, timedelta, timezone
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.security import hash_password

DEPARTMENTS = [(1, "it", "IT Helpdesk", 8), (2, "finance", "Financial Aid", 24),
               (3, "academic", "Academic Advising", 24), (4, "health", "Health Services", 4),
               (5, "security", "Campus Security", 1)]


RETRAINING_DEFAULTS = {"retrain_enabled": "1", "retrain_interval_days": "30", "retrain_min_new_samples": "5"}
SERVICE_DEFAULTS = {"retention_days": "365", "business_open": "09:00", "business_close": "17:00",
                    "business_timezone": "Asia/Almaty"}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def connection(path):
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connection(path) as db:
        db.execute("PRAGMA journal_mode = WAL")
        db.executescript((Path(__file__).parent / "schema.sql").read_text())
        # Retire queued jobs that use a no-longer-supported delivery channel.
        # Completed deliveries stay in the database as historical records.
        db.execute("""UPDATE alert_deliveries SET status='cancelled',error_code='channel_retired'
                      WHERE channel!='email' AND status IN ('pending','sending')""")
        # CREATE TABLE IF NOT EXISTS does not add columns to existing local databases.
        migrations = {
            "users": {"disabled_at": "TEXT"},
            "requests": {"resolved_at": "TEXT", "sla_started_at": "TEXT", "sla_due_at": "TEXT", "sla_notified_at": "TEXT",
                         "assigned_staff_id": "INTEGER REFERENCES users(id)", "anonymized_at": "TEXT"},
            "training_samples": {"predicted_code": "TEXT"},
        }
        for table, columns in migrations.items():
            present = {r["name"] for r in db.execute(f"PRAGMA table_info({table})")}
            for name, declaration in columns.items():
                if name not in present:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
        db.executemany("INSERT OR IGNORE INTO departments VALUES (?,?,?,?)", DEPARTMENTS)
        db.execute("INSERT OR IGNORE INTO settings VALUES ('confidence_threshold','0.65',NULL,?)", (utc_now(),))
        # US10: retraining schedule, adjustable by an administrator without code changes.
        db.executemany("INSERT OR IGNORE INTO settings VALUES (?,?,NULL,?)",
                       [(key, value, utc_now()) for key, value in RETRAINING_DEFAULTS.items()])
        db.executemany("INSERT OR IGNORE INTO settings VALUES (?,?,NULL,?)",
                       [(key, value, utc_now()) for key, value in SERVICE_DEFAULTS.items()])
        # US10: staff decisions logged before the training table existed become labeled examples.
        # The UNIQUE correction_id makes this idempotent.
        db.execute("""INSERT OR IGNORE INTO training_samples (request_id,correction_id,source,label,text,created_at)
                      SELECT request_id,id,'staff_correction',corrected_code,message_snapshot,created_at
                      FROM routing_corrections""")
        db.execute("""UPDATE training_samples SET predicted_code=(SELECT suggested_code FROM requests
                      WHERE requests.id=training_samples.request_id) WHERE predicted_code IS NULL""")


def seed_demo(path):
    """Explicit opt-in. Public demonstration credentials are never production users."""
    accounts = [("Second Student", "250103031@sdu.edu.kz", "Student123!", "student"),
                ("Mira Khaiitboyeva", "240103173@sdu.edu.kz", "Student123!", "student"),
                ("Korkem Baigozha", "240103103@sdu.edu.kz", "Student123!", "student"),
                ("Dina Zhumatay", "240107023@sdu.edu.kz", "Student123!", "student"),
                ("Karakat Maxutova", "240103030@sdu.edu.kz", "Student123!", "student"),
                ("Asselya Imanmadinova", "240103026@sdu.edu.kz", "Student123!", "student"),
                ("SDU Helpdesk", "helpdesk@sdu.edu.kz", "Support123!", "support"),
                ("Administrator", "admin@sdu.edu.kz", "Admin12345!", "admin")]
    legacy = {"240103030@sdu.edu.kz": ("student@demo.edu", "Demo Student"),
              "250103031@sdu.edu.kz": ("student2@demo.edu", "Second Student"),
              "helpdesk@sdu.edu.kz": ("support@demo.edu", "Support Officer"),
              "admin@sdu.edu.kz": ("admin@demo.edu", "Administrator")}
    demo_student_emails = {"240103173@sdu.edu.kz", "240103103@sdu.edu.kz", "240107023@sdu.edu.kz",
                           "240103030@sdu.edu.kz", "240103026@sdu.edu.kz"}
    with connection(path) as db:
        for name, email, password, role in accounts:
            current = db.execute("SELECT id,name,role FROM users WHERE email=?", (email,)).fetchone()
            if current:
                # Refresh names only for the five explicitly supplied demo accounts.
                # Preserve each existing account ID, password, requests, and messages.
                if role == "student" and email in demo_student_emails and current["role"] == "student" and current["name"] != name:
                    db.execute("UPDATE users SET name=? WHERE id=?", (name, current["id"]))
                continue
            if email in legacy:
                old_email, old_name = legacy[email]
                previous = db.execute("SELECT id FROM users WHERE email=? AND name=? AND role=?",
                                      (old_email, old_name, role)).fetchone()
                if previous:
                    # Keep the account ID, password, requests and notices. Never merge
                    # identities if the destination address already exists.
                    db.execute("UPDATE users SET name=?,email=? WHERE id=?", (name, email, previous["id"]))
                    continue
            db.execute("INSERT INTO users (name,email,password_hash,role,created_at) VALUES (?,?,?,?,?)",
                       (name, email, hash_password(password), role, utc_now()))


DEMO_RATING_CASES = (
    ("240103173", "My laptop cannot connect to the campus Wi-Fi network. The wireless connection keeps dropping and I cannot log in to the university portal.", 5),
    ("240103103", "The campus Wi-Fi keeps disconnecting on my phone, and I cannot open the student portal unless I use mobile data.", 4),
    ("240107023", "I am having trouble connecting to the university wireless network. My laptop loses the Wi-Fi connection every few minutes.", 3),
    ("240103030", "My laptop cannot join the SDU Wi-Fi. The wireless login page fails and I have no campus internet access.", 2),
    ("240103026", "The Wi-Fi on my laptop stopped working on campus. I cannot connect to the wireless network or access the university portal.", 1),
)


def seed_demo_average_ratings(path, classifier):
    """Seed a resolved, rated IT request per added student in an opted-in demo database."""
    from app.business_time import calendar
    from app.features import submit_feedback
    from app.service import create_request, get_request, route_request, update_status

    with connection(path) as db:
        support = db.execute("SELECT * FROM users WHERE email='helpdesk@sdu.edu.kz' AND role='support'").fetchone()
        if not support:
            return
        _, _, zone, holidays = calendar(db)
        sample_day = datetime.now(timezone.utc).astimezone(zone).date() - timedelta(days=1)
        while sample_day.weekday() >= 5 or sample_day.isoformat() in holidays:
            sample_day -= timedelta(days=1)

        for index, (student_id, message, rating) in enumerate(DEMO_RATING_CASES):
            email = f"{student_id}@sdu.edu.kz"
            student = db.execute("SELECT * FROM users WHERE email=? AND role='student'", (email,)).fetchone()
            if not student:
                continue
            title = f"Demo average rating · {student_id}"
            existing = db.execute("SELECT id FROM requests WHERE student_id=? AND title=?",
                                  (student["id"], title)).fetchone()
            if existing:
                request_id = existing["id"]
            else:
                request_id = create_request(db, student, {"title": title, "message": message}, classifier)["id"]

            row = get_request(db, request_id, support)
            if row["status"] == "Escalated" or row["department_code"] != "it":
                row = route_request(db, support, row, {"department_code": "it", "version": row["version"]})
                row = get_request(db, request_id, support)
            if row["status"] == "Received":
                update_status(db, support, row, {"status": "In Progress", "version": row["version"]})
                row = get_request(db, request_id, support)
            if row["status"] == "In Progress":
                update_status(db, support, row, {
                    "status": "Resolved", "version": row["version"],
                    "resolution": "Demo resolution: reconnect to the campus Wi-Fi and check access to the student portal.",
                })
                row = get_request(db, request_id, support)
            if row["status"] == "Resolved" and not db.execute(
                    "SELECT 1 FROM request_feedback WHERE request_id=?", (request_id,)).fetchone():
                submit_feedback(db, student, row, {"rating": rating, "comment": "Synthetic demo rating."})

            # Analytics intentionally stops at the previous complete business day.
            # Keep these synthetic examples in its default date range.
            base = datetime.combine(sample_day, time(10, index * 8), tzinfo=zone).astimezone(timezone.utc)
            db.execute("UPDATE requests SET created_at=?,updated_at=?,resolved_at=? WHERE id=?",
                       (base.isoformat(timespec="microseconds"),
                        (base + timedelta(minutes=15)).isoformat(timespec="microseconds"),
                        (base + timedelta(minutes=15)).isoformat(timespec="microseconds"), request_id))
            events = db.execute("SELECT id FROM request_events WHERE request_id=? ORDER BY id", (request_id,)).fetchall()
            for event_index, event in enumerate(events):
                event_time = (base + timedelta(minutes=3 * event_index)).isoformat(timespec="microseconds")
                db.execute("UPDATE request_events SET created_at=? WHERE id=?", (event_time, event["id"]))
                db.execute("UPDATE notifications SET created_at=? WHERE event_id=?", (event_time, event["id"]))
            db.execute("UPDATE request_feedback SET created_at=? WHERE request_id=?",
                       ((base + timedelta(minutes=20)).isoformat(timespec="microseconds"), request_id))


def review_deadline(now=None, db=None):
    """Four business hours using the same administrator-managed calendar as request SLAs."""
    if db is not None:
        from app.business_time import add_business_hours
        return add_business_hours(db, now or datetime.now(timezone.utc), 4)
    try:
        local_zone = ZoneInfo("Asia/Almaty")
    except ZoneInfoNotFoundError:
        local_zone = timezone(timedelta(hours=5))
    cursor = (now or datetime.now(timezone.utc)).astimezone(local_zone)
    remaining = timedelta(hours=4)
    while True:
        if cursor.weekday() >= 5 or cursor.hour >= 17:
            cursor = (cursor + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
            continue
        if cursor.hour < 9:
            cursor = cursor.replace(hour=9, minute=0, second=0, microsecond=0)
        closing = cursor.replace(hour=17, minute=0, second=0, microsecond=0)
        available = closing - cursor
        if remaining <= available:
            return (cursor + remaining).astimezone(timezone.utc).isoformat(timespec="microseconds")
        remaining -= available
        cursor = (cursor + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
