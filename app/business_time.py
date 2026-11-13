"""Business-calendar calculations shared by review and departmental SLA deadlines."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _setting(db, key, default):
    if db is None:
        return default
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def calendar(db):
    opening = time.fromisoformat(_setting(db, "business_open", "09:00"))
    closing = time.fromisoformat(_setting(db, "business_close", "17:00"))
    if closing <= opening:
        opening, closing = time(9, 0), time(17, 0)
    zone_name = _setting(db, "business_timezone", "Asia/Almaty")
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        zone = timezone(timedelta(hours=5))
    holidays = set()
    if db is not None:
        holidays = {r[0] for r in db.execute("SELECT day FROM school_holidays")}
    return opening, closing, zone, holidays


def add_business_hours(db, start, hours):
    """Add working hours, skipping weekends and administrator-entered school holidays."""
    if isinstance(start, str):
        start = datetime.fromisoformat(start)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    remaining = max(0.0, float(hours))
    opening, closing, zone, holidays = calendar(db)
    current = start.astimezone(zone)
    while True:
        is_holiday = current.date().isoformat() in holidays
        if current.weekday() >= 5 or is_holiday:
            current = (current + timedelta(days=1)).replace(hour=opening.hour, minute=opening.minute,
                                                             second=0, microsecond=0)
            continue
        opens = current.replace(hour=opening.hour, minute=opening.minute, second=0, microsecond=0)
        closes = current.replace(hour=closing.hour, minute=closing.minute, second=0, microsecond=0)
        if current < opens:
            current = opens
        elif current >= closes:
            current = (current + timedelta(days=1)).replace(hour=opening.hour, minute=opening.minute,
                                                             second=0, microsecond=0)
            continue
        available = (closes - current).total_seconds() / 3600
        if remaining <= available:
            return (current + timedelta(hours=remaining)).astimezone(timezone.utc).isoformat(timespec="microseconds")
        remaining -= available
        current = (current + timedelta(days=1)).replace(hour=opening.hour, minute=opening.minute,
                                                         second=0, microsecond=0)


def deadline_state(due_at, now=None):
    if not due_at:
        return "untracked", None
    now = now or datetime.now(timezone.utc)
    due = datetime.fromisoformat(due_at)
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    seconds = int((due - now).total_seconds())
    return ("overdue" if seconds <= 0 else "due_soon" if seconds <= 3600 else "on_track"), seconds
