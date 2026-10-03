from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.security import hash_password

DEPARTMENTS = [(1, "it", "IT Helpdesk", 8), (2, "finance", "Financial Aid", 24),
               (3, "academic", "Academic Advising", 24), (4, "health", "Health Services", 4)]


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
        db.executemany("INSERT OR IGNORE INTO departments VALUES (?,?,?,?)", DEPARTMENTS)
        db.execute("INSERT OR IGNORE INTO settings VALUES ('confidence_threshold','0.65',NULL,?)", (utc_now(),))


def seed_demo(path):
    """Explicit opt-in. Public demonstration credentials are never production users."""
    accounts = [("Demo Student", "240103030@sdu.edu.kz", "Student123!", "student"),
                ("Second Student", "250103031@sdu.edu.kz", "Student123!", "student"),
                ("SDU Helpdesk", "helpdesk@sdu.edu.kz", "Support123!", "support"),
                ("Administrator", "admin@sdu.edu.kz", "Admin12345!", "admin")]
    legacy = {"240103030@sdu.edu.kz": ("student@demo.edu", "Demo Student"),
              "250103031@sdu.edu.kz": ("student2@demo.edu", "Second Student"),
              "helpdesk@sdu.edu.kz": ("support@demo.edu", "Support Officer"),
              "admin@sdu.edu.kz": ("admin@demo.edu", "Administrator")}
    with connection(path) as db:
        for name, email, password, role in accounts:
            if not db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
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


def review_deadline(now=None):
    """Four business hours, Mon-Fri 09:00-17:00 at UTC+5; no holiday calendar supplied."""
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
