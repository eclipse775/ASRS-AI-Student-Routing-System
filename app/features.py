"""US8-US16 domain operations: feedback, analytics, managed calendars and audit search."""
import csv
from datetime import date, datetime, time, timedelta, timezone
import io
import json
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.audit import append_audit, verify_chain
from app.business_time import add_business_hours, calendar
from app.database import utc_now
from app.delivery import gateway_status, EMAIL_RE
from app.labels import record_label
from app.service import APIError, check_version, get_request, record_event, require_role, serialize

AUDIT_ACTIONS = {"request_created", "request_edited", "request_routed", "request_deleted", "status_changed",
                 "request_reopened", "emergency_reported", "urgent_alert_created", "urgent_alert_acknowledged",
                 "feedback_submitted", "attachments_added", "sla_overdue_notified", "sla_calendar_updated",
                 "retention_policy_updated", "request_anonymized", "deletion_requested", "deletion_denied",
                 "personal_data_deleted", "on_call_contacts_changed", "routing_threshold_updated",
                 "staff_message_posted"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def submit_feedback(db, user, row, data):
    require_role(user, "student")
    if row["student_id"] != user["id"]:
        raise APIError(404, "Request not found.")
    if row["status"] != "Resolved" or row["anonymized_at"]:
        raise APIError(409, "Feedback is available after a request is resolved.")
    rating = data.get("rating")
    if type(rating) is not int or not 1 <= rating <= 5:
        raise APIError(400, "Choose a rating from 1 to 5 stars.")
    comment = data.get("comment", "")
    if not isinstance(comment, str) or len(comment.strip()) > 1000:
        raise APIError(400, "Feedback comments must be 1,000 characters or fewer.")
    if db.execute("SELECT 1 FROM request_feedback WHERE request_id=?", (row["id"],)).fetchone():
        raise APIError(409, "Feedback has already been submitted for this request.")
    now = utc_now()
    db.execute("""INSERT INTO request_feedback (request_id,department_id,rating,comment,created_at)
                  VALUES (?,?,?,?,?)""", (row["id"], row["department_id"], rating, comment.strip(), now))
    append_audit(db, user, "feedback_submitted", row["id"], new_value={"rating": rating})
    return {"rating": rating, "comment": comment.strip(), "created_at": now}


def get_feedback(db, user, row):
    require_role(user, "student")
    if row["student_id"] != user["id"]:
        raise APIError(404, "Request not found.")
    result = db.execute("SELECT rating,comment,created_at FROM request_feedback WHERE request_id=?", (row["id"],)).fetchone()
    return dict(result) if result else None


def student_reopen(db, user, row, data):
    require_role(user, "student")
    if row["student_id"] != user["id"]:
        raise APIError(404, "Request not found.")
    check_version(data, row)
    if row["status"] != "Resolved" or not row["resolved_at"]:
        raise APIError(409, "Only a resolved request can be reopened.")
    resolved = datetime.fromisoformat(row["resolved_at"])
    if resolved.tzinfo is None:
        resolved = resolved.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - resolved > timedelta(hours=48):
        raise APIError(409, "A request can be reopened within 48 hours of resolution.")
    now = utc_now()
    department = row["department_id"]
    due = None
    if department is not None:
        hours = db.execute("SELECT response_hours FROM departments WHERE id=?", (department,)).fetchone()[0]
        due = add_business_hours(db, now, hours)
        record_label(db, row["id"], row["department_code"], row["message"], "reopened")
    db.execute("""UPDATE requests SET status='Received',resolution='',resolved_at=NULL,sla_started_at=?,
                sla_due_at=?,sla_notified_at=NULL,updated_at=?,version=version+1 WHERE id=?""",
               (now, due, now, row["id"]))
    updated = get_request(db, row["id"], user)
    append_audit(db, user, "request_reopened", row["id"], old_value={"status": "Resolved"},
                 new_value={"status": "Received", "department": row["department_code"]})
    record_event(db, updated, user, "student_reopened", "You reopened this request within 48 hours. It returned to the same department's active queue.")
    staff = []
    if row["assigned_staff_id"]:
        staff = db.execute("SELECT id FROM users WHERE id=? AND role='support' AND disabled_at IS NULL",
                           (row["assigned_staff_id"],)).fetchall()
    else:
        staff = db.execute("SELECT id FROM users WHERE role='support' AND disabled_at IS NULL").fetchall()
    notice = f"REQ-{row['id']:05d} was reopened by the student and returned to {row['department_name']}."
    for recipient in staff:
        db.execute("""INSERT OR IGNORE INTO staff_notifications
                      (user_id,request_id,kind,message,created_at) VALUES (?,?,?,?,?)""",
                   (recipient["id"], row["id"], f"request_reopened:{updated['version']}", notice, now))
    return {"request": serialize(updated)}


def _parse_date(value, label):
    if not DATE_RE.fullmatch(value or ""):
        raise APIError(400, f"Enter {label} as YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise APIError(400, f"Enter a valid {label} date.") from None


def _analytics_range(db, query):
    opening, closing, zone, holidays = calendar(db)
    today = datetime.now(timezone.utc).astimezone(zone).date()
    through = today - timedelta(days=1)
    while through.weekday() >= 5 or through.isoformat() in holidays:
        through -= timedelta(days=1)
    start = _parse_date(query.get("from", [""])[0], "start date") if query.get("from") else through - timedelta(days=29)
    end = _parse_date(query.get("to", [""])[0], "end date") if query.get("to") else through
    end = min(end, through)
    if start > end:
        raise APIError(400, "The start date must be on or before the end date.")
    if end - start > timedelta(days=3650):
        raise APIError(400, "Choose a date range of 10 years or less.")
    start_utc = datetime.combine(start, time.min, tzinfo=zone).astimezone(timezone.utc).isoformat()
    end_utc = datetime.combine(end + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc).isoformat()
    return start, end, through, start_utc, end_utc


def analytics(db, user, query):
    require_role(user, "admin")
    start, end, through, start_utc, end_utc = _analytics_range(db, query)
    total = db.execute("SELECT COUNT(*) FROM requests WHERE created_at>=? AND created_at<?",
                       (start_utc, end_utc)).fetchone()[0]
    by_department = [dict(r) for r in db.execute("""SELECT COALESCE(d.name,'Staff review') department,
                         COUNT(*) total FROM requests r LEFT JOIN departments d ON d.id=r.department_id
                         WHERE r.created_at>=? AND r.created_at<? GROUP BY d.name ORDER BY total DESC,department""",
                                                  (start_utc, end_utc))]
    by_category = [dict(r) for r in db.execute("""SELECT suggested_code category,COUNT(*) total FROM requests
                       WHERE created_at>=? AND created_at<? GROUP BY suggested_code ORDER BY total DESC,category""",
                                                (start_utc, end_utc))]
    samples = db.execute("""SELECT COUNT(*) total,COALESCE(SUM(CASE WHEN predicted_code=label THEN 1 ELSE 0 END),0) correct
                            FROM training_samples WHERE created_at>=? AND created_at<?""", (start_utc, end_utc)).fetchone()
    by_source = [dict(r) for r in db.execute("""SELECT source,COUNT(*) total,
                       SUM(CASE WHEN predicted_code=label THEN 1 ELSE 0 END) correct
                       FROM training_samples WHERE created_at>=? AND created_at<? GROUP BY source ORDER BY source""",
                                             (start_utc, end_utc))]
    response_rows = db.execute("""SELECT d.name department,
                         (julianday(first.created_at)-julianday(r.created_at))*86400 response_seconds
                         FROM requests r JOIN departments d ON d.id=r.department_id
                         JOIN (SELECT request_id,MIN(created_at) created_at FROM request_events
                               WHERE kind='status_changed' AND status='In Progress' GROUP BY request_id) first
                         ON first.request_id=r.id WHERE r.created_at>=? AND r.created_at<?""",
                               (start_utc, end_utc)).fetchall()
    times = {}
    for row in response_rows:
        if row["response_seconds"] is not None and row["response_seconds"] >= 0:
            times.setdefault(row["department"], []).append(round(row["response_seconds"]))
    response_times = [{"department": name, "responses": len(values),
                       "average_seconds": round(sum(values) / len(values)), "maximum_seconds": max(values)}
                      for name, values in sorted(times.items())]
    rating_rows = [dict(r) for r in db.execute("""SELECT d.name department,COUNT(*) feedback_count,
                           ROUND(AVG(f.rating),2) average_rating FROM request_feedback f
                           LEFT JOIN departments d ON d.id=f.department_id WHERE f.created_at>=? AND f.created_at<?
                           GROUP BY d.name ORDER BY d.name""", (start_utc, end_utc))]
    return {"from": start.isoformat(), "to": end.isoformat(), "data_through": through.isoformat(),
            "refreshed_at": utc_now(), "total_requests": total, "by_department": by_department,
            "by_category": by_category, "routing_accuracy": {"correct": samples["correct"],
            "evaluated": samples["total"], "rate": samples["correct"] / samples["total"] if samples["total"] else None,
            "basis": "Staff corrections, escalation outcomes, and reopened-request labels."},
            "accuracy_by_source": by_source, "response_times": response_times, "feedback": rating_rows}


def get_sla_settings(db, user):
    require_role(user, "admin")
    opening, closing, zone, holidays = calendar(db)
    return {"business_open": opening.strftime("%H:%M"), "business_close": closing.strftime("%H:%M"),
            "business_timezone": getattr(zone, "key", "UTC+05:00"),
            "departments": [dict(r) for r in db.execute("SELECT code,name,response_hours FROM departments ORDER BY id")],
            "holidays": [dict(r) for r in db.execute("SELECT day,label FROM school_holidays ORDER BY day")],
            "retention_days": int(db.execute("SELECT value FROM settings WHERE key='retention_days'").fetchone()[0])}


def update_sla_settings(db, admin, data):
    require_role(admin, "admin")
    opening, closing = data.get("business_open"), data.get("business_close")
    zone_name = data.get("business_timezone")
    if (not isinstance(opening, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", opening)
            or not isinstance(closing, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", closing)):
        raise APIError(400, "Business hours must use HH:MM.")
    try:
        open_time, close_time = time.fromisoformat(opening), time.fromisoformat(closing)
    except (TypeError, ValueError):
        raise APIError(400, "Business hours must use HH:MM.") from None
    if open_time >= close_time or open_time.second or close_time.second:
        raise APIError(400, "Business closing time must be after opening time.")
    if not isinstance(zone_name, str) or len(zone_name) > 64:
        raise APIError(400, "Choose a valid time zone.")
    try:
        ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise APIError(400, "Choose a valid IANA time zone.") from None
    targets = data.get("departments")
    if not isinstance(targets, list):
        raise APIError(400, "Department response targets are required.")
    current = {r["code"]: r["id"] for r in db.execute("SELECT id,code FROM departments")}
    seen = set()
    for row in targets:
        if not isinstance(row, dict) or row.get("code") not in current or row.get("code") in seen:
            raise APIError(400, "Department response targets are invalid or duplicated.")
        hours = row.get("response_hours")
        if type(hours) is not int or not 1 <= hours <= 720:
            raise APIError(400, "Response targets must be between 1 and 720 business hours.")
        seen.add(row["code"])
    if seen != set(current):
        raise APIError(400, "Provide a response target for every department.")
    holidays = data.get("holidays", [])
    if not isinstance(holidays, list) or len(holidays) > 500:
        raise APIError(400, "Provide up to 500 school holidays.")
    normalized = []
    seen_days = set()
    for item in holidays:
        if not isinstance(item, dict):
            raise APIError(400, "Each holiday needs a date and optional label.")
        day = _parse_date(item.get("day"), "holiday")
        label = item.get("label", "")
        if day.year < 2000 or day.year > 2200 or day.isoformat() in seen_days or not isinstance(label, str) or len(label.strip()) > 100:
            raise APIError(400, "A holiday date or label is invalid or duplicated.")
        seen_days.add(day.isoformat())
        normalized.append((day.isoformat(), label.strip()))
    now = utc_now()
    for key, value in (("business_open", opening), ("business_close", closing),
                       ("business_timezone", zone_name)):
        db.execute("UPDATE settings SET value=?,updated_by=?,updated_at=? WHERE key=?", (value, admin["id"], now, key))
    for row in targets:
        db.execute("UPDATE departments SET response_hours=? WHERE code=?", (row["response_hours"], row["code"]))
    db.execute("DELETE FROM school_holidays")
    db.executemany("INSERT INTO school_holidays (day,label) VALUES (?,?)", normalized)
    open_requests = db.execute("""SELECT id,department_id,sla_started_at FROM requests
                                  WHERE status='Received' AND department_id IS NOT NULL AND sla_started_at IS NOT NULL""").fetchall()
    for request in open_requests:
        hours = db.execute("SELECT response_hours FROM departments WHERE id=?", (request["department_id"],)).fetchone()[0]
        due = add_business_hours(db, request["sla_started_at"], hours)
        db.execute("UPDATE requests SET sla_due_at=? WHERE id=?", (due, request["id"]))
    append_audit(db, admin, "sla_calendar_updated", new_value={"departments": len(targets), "holidays": len(normalized)})
    return get_sla_settings(db, admin)


def update_retention(db, admin, data):
    require_role(admin, "admin")
    days = data.get("retention_days")
    if type(days) is not int or not 30 <= days <= 36500:
        raise APIError(400, "Retention must be between 30 and 36,500 days.")
    previous = int(db.execute("SELECT value FROM settings WHERE key='retention_days'").fetchone()[0])
    now = utc_now()
    db.execute("UPDATE settings SET value=?,updated_by=?,updated_at=? WHERE key='retention_days'",
               (str(days), admin["id"], now))
    append_audit(db, admin, "retention_policy_updated", old_value={"days": previous}, new_value={"days": days})
    return {"retention_days": days}


def get_on_call(db, admin):
    require_role(admin, "admin")
    return {"contacts": [dict(r) for r in db.execute("""SELECT c.id,d.code department_code,d.name department_name,
                           c.escalation_level,c.contact_name,c.email,c.is_lead,c.enabled
                           FROM on_call_contacts c JOIN departments d ON d.id=c.department_id
                           WHERE c.email != ''
                           ORDER BY d.id,c.escalation_level,c.id""")], "gateways": gateway_status()}


def update_on_call(db, admin, data):
    require_role(admin, "admin")
    contacts = data.get("contacts")
    if not isinstance(contacts, list) or len(contacts) > 100:
        raise APIError(400, "Provide up to 100 on-call contacts.")
    departments = {r["code"]: r["id"] for r in db.execute("SELECT id,code FROM departments")}
    cleaned, unique = [], set()
    for item in contacts:
        if not isinstance(item, dict) or item.get("department_code") not in departments:
            raise APIError(400, "An on-call contact has an invalid department.")
        level, name = item.get("level"), item.get("name", "")
        email_value = item.get("email", "")
        if not isinstance(email_value, str):
            raise APIError(400, "Contact email must be a text value.")
        email = email_value.strip().lower()
        lead = item.get("lead", False)
        if type(level) is not int or level not in (1, 2) or not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise APIError(400, "Contact name and escalation level are invalid.")
        if email and not EMAIL_RE.fullmatch(email):
            raise APIError(400, "Enter a valid contact email.")
        if not email:
            raise APIError(400, "Each contact needs an email address.")
        if type(lead) is not bool:
            raise APIError(400, "Department lead must be on or off.")
        unique_key = (item["department_code"], level, email)
        if unique_key in unique:
            raise APIError(400, "Duplicate on-call contacts are not allowed.")
        unique.add(unique_key)
        cleaned.append((departments[item["department_code"]], level, name.strip(), email,
                        1 if lead else 0, 1, utc_now(), utc_now()))
    db.execute("DELETE FROM on_call_contacts")
    db.executemany("""INSERT INTO on_call_contacts
                    (department_id,escalation_level,contact_name,email,is_lead,enabled,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?)""", cleaned)
    append_audit(db, admin, "on_call_contacts_changed", new_value={"contact_count": len(cleaned)})
    return get_on_call(db, admin)


def pending_deletions(db, admin):
    require_role(admin, "admin")
    return [dict(r) for r in db.execute("""SELECT q.id,q.status,q.requested_at,u.name student_name,u.email,
                       (SELECT COUNT(*) FROM requests r WHERE r.student_id=q.user_id) request_count
                       FROM deletion_requests q JOIN users u ON u.id=q.user_id
                       WHERE q.status IN ('pending','approved') ORDER BY q.requested_at""")]


def _audit_rows(db, query, cap, offset=0):
    clauses, params = [], []
    ref = query.get("request_ref", [""])[0].strip().upper()
    if ref:
        if not re.fullmatch(r"REQ-\d{1,12}", ref):
            raise APIError(400, "Use a request reference such as REQ-00012.")
        clauses.append("a.request_ref=?")
        params.append(ref)
    actor = query.get("user_id", [""])[0]
    if actor:
        if not actor.isdigit() or len(actor) > 12:
            raise APIError(400, "User ID must be a number.")
        clauses.append("a.actor_id=?")
        params.append(int(actor))
    action = query.get("action", [""])[0]
    if action:
        if action not in AUDIT_ACTIONS:
            raise APIError(400, "Choose a valid audit action.")
        clauses.append("a.action=?")
        params.append(action)
    start, end = query.get("from", [""])[0], query.get("to", [""])[0]
    if start:
        clauses.append("date(a.created_at)>=?")
        params.append(_parse_date(start, "start date").isoformat())
    if end:
        clauses.append("date(a.created_at)<=?")
        params.append(_parse_date(end, "end date").isoformat())
    if start and end and start > end:
        raise APIError(400, "The start date must be on or before the end date.")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    rows = db.execute("""SELECT a.*,COALESCE(u.name,'Former or removed user') actor_name FROM audit_log a
                         LEFT JOIN users u ON u.id=a.actor_id""" + where + " ORDER BY a.id DESC LIMIT ? OFFSET ?",
                      params + [cap, offset]).fetchall()
    return rows


def search_audit(db, admin, query):
    require_role(admin, "admin")
    raw_limit, raw_offset = query.get("limit", ["100"])[0], query.get("offset", ["0"])[0]
    if not raw_limit.isdigit() or not raw_offset.isdigit():
        raise APIError(400, "Audit pagination values must be numbers.")
    limit, offset = min(200, max(1, int(raw_limit))), min(1000000, int(raw_offset))
    rows = _audit_rows(db, query, limit + 1, offset)
    more = len(rows) > limit
    results = [dict(r) for r in rows[:limit]]
    for row in results:
        for key in ("old_value", "new_value", "metadata"):
            row[key] = json.loads(row[key])
    total = db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    return {"entries": results, "has_more": more, "next_offset": offset + limit if more else None,
            "total_entries": total, "chain_valid": verify_chain(db)}


def export_audit_csv(db, admin, query):
    require_role(admin, "admin")
    rows = _audit_rows(db, query, 10000)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["request_ref", "actor_id", "actor_name", "actor_role", "action", "old_value",
                     "new_value", "metadata", "created_at", "entry_hash"])
    for row in rows:
        values = [row["request_ref"], row["actor_id"], row["actor_name"], row["actor_role"], row["action"],
                  row["old_value"], row["new_value"], row["metadata"], row["created_at"], row["entry_hash"]]
        safe_values = []
        for value in values:
            if isinstance(value, str):
                first = value.lstrip(" \t\r\n")[:1]
                if first and first in "=+-@":
                    value = "'" + value
            safe_values.append(value)
        writer.writerow(safe_values)
    return output.getvalue()
