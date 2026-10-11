"""Transactional request creation, routing, status, history, and notifications."""
import json
from datetime import datetime, timezone
from app.database import review_deadline, utc_now
from app.urgency import URGENT_FALLBACK_CODE, detect_urgency, merge_ai_flag

ALERT_OVERDUE_SECONDS = 120  # story: an alert nobody acknowledges within 2 minutes is "deferred"


class APIError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def require_role(user, *roles):
    if not user:
        raise APIError(401, "Please sign in.")
    if user["role"] not in roles:
        raise APIError(403, "You do not have access to this action.")


def clean_text(data, key, minimum, maximum, default=None):
    value = data.get(key, default)
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise APIError(400, f"{key.replace('_', ' ').capitalize()} must contain {minimum}-{maximum} characters.")
    # Preserve the submitted message exactly; validation only checks its trimmed length.
    return value


def check_version(data, row):
    version = data.get("version")
    if type(version) is not int:
        raise APIError(400, "A request version is required.")
    if version != row["version"]:
        raise APIError(409, "This request changed. Refresh before saving.")


def get_request(db, request_id, user):
    row = db.execute("""SELECT r.*,d.name department_name,d.code department_code,u.name student_name
                        FROM requests r LEFT JOIN departments d ON d.id=r.department_id
                        JOIN users u ON u.id=r.student_id WHERE r.id=?""", (request_id,)).fetchone()
    if row is None or (user["role"] == "student" and row["student_id"] != user["id"]):
        raise APIError(404, "Request not found.")
    return row


def serialize(row):
    result = dict(row)
    result["reference"] = f"REQ-{row['id']:05d}"
    result["classification"] = json.loads(result.pop("classification_json"))
    result["review_overdue"] = bool(row["status"] == "Escalated" and row["review_due_at"] and row["review_due_at"] < utc_now())
    return result


def record_event(db, row, actor, kind, detail, notify=True):
    now = utc_now()
    cursor = db.execute("""INSERT INTO request_events
               (request_id,actor_id,kind,status,detail,version,created_at) VALUES (?,?,?,?,?,?,?)""",
               (row["id"], actor["id"], kind, row["status"], detail, row["version"], now))
    if notify:
        db.execute("""INSERT INTO notifications (user_id,request_id,event_id,message,created_at)
                      VALUES (?,?,?,?,?)""", (row["student_id"], row["id"], cursor.lastrowid,
                                              f"REQ-{row['id']:05d}: {detail}", now))


def routing_detail(db, department_id):
    if department_id is None:
        return "Your request is in the staff review queue. Review target: within 4 business hours."
    department = db.execute("SELECT * FROM departments WHERE id=?", (department_id,)).fetchone()
    return f"Sent to {department['name']}. Estimated initial response: {department['response_hours']} business hours."


def urgent_department_id(db, classification, urgency, preferred=None):
    """Department for an emergency: rule/staff choice first, then a confident AI route, else the fallback."""
    code = preferred or urgency.get("department")
    if not code:
        threshold = float(db.execute("SELECT value FROM settings WHERE key='confidence_threshold'").fetchone()[0])
        suggested = classification.get("suggested_code")
        confident = (suggested not in (None, "review") and not classification.get("review_required")
                     and classification.get("confidence", 0) >= threshold)
        code = suggested if confident else URGENT_FALLBACK_CODE  # never route an emergency on a weak guess
    row = db.execute("SELECT id FROM departments WHERE code=?", (code,)).fetchone()
    if not row:
        raise APIError(503, "The routing department is unavailable. Please try again.")
    return row[0]


def assess_urgency(title, message, classification):
    return merge_ai_flag(detect_urgency(title, message), classification)


def urgent_detail(db, department_id):
    name = db.execute("SELECT name FROM departments WHERE id=?", (department_id,)).fetchone()[0]
    return (f"Flagged as urgent and sent immediately to {name}, which has been alerted. "
            "If you are in immediate danger, contact emergency services directly.")


def raise_alert(db, request_id, department_id, kind, reason):
    db.execute("INSERT INTO urgent_alerts (request_id,department_id,kind,reason,created_at) VALUES (?,?,?,?,?)",
               (request_id, department_id, kind, reason, utc_now()))


def has_open_alert(db, request_id):
    return db.execute("SELECT 1 FROM urgent_alerts WHERE request_id=? AND acknowledged_at IS NULL",
                      (request_id,)).fetchone() is not None


def routing_decision(db, classification, urgency=None):
    if urgency and urgency["detected"]:
        # Emergency bypass: never wait in the staff review queue, whatever the confidence.
        return urgent_department_id(db, classification, urgency), "Received", None
    threshold = float(db.execute("SELECT value FROM settings WHERE key='confidence_threshold'").fetchone()[0])
    if classification.get("review_required") or classification["confidence"] < threshold:
        return None, "Escalated", review_deadline()
    department = db.execute("SELECT id FROM departments WHERE code=?", (classification["suggested_code"],)).fetchone()
    if not department:
        raise APIError(503, "The routing department is unavailable. Please try again.")
    return department[0], "Received", None


def create_request(db, user, data, classifier, classification=None):
    require_role(user, "student")
    title = clean_text(data, "title", 3, 120)
    message = clean_text(data, "message", 10, 4000)
    priority = data.get("priority", "normal")
    if priority not in ("normal", "urgent"):
        raise APIError(400, "Choose a valid priority.")
    result = classification if classification is not None else classifier.classify(message)
    urgency = assess_urgency(title, message, result)
    result = {**result, "urgency": urgency}
    department, status, due = routing_decision(db, result, urgency)
    if urgency["detected"]:
        priority = "urgent"
    now = utc_now()
    cursor = db.execute("""INSERT INTO requests
         (student_id,title,message,department_id,suggested_code,confidence,classification_json,
          status,priority,created_at,updated_at,review_due_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
         (user["id"], title, message, department, result["suggested_code"], result["confidence"],
          json.dumps(result), status, priority, now, now, due))
    row = get_request(db, cursor.lastrowid, user)
    if urgency["detected"]:
        record_event(db, row, user, "submitted", urgent_detail(db, department))
        raise_alert(db, row["id"], department, "urgent", urgency["reason"])
    else:
        record_event(db, row, user, "submitted", routing_detail(db, department))
    return serialize(row)


def edit_request(db, user, row, data, classifier, classification=None):
    require_role(user, "student")
    if row["status"] not in ("Received", "Escalated"):
        raise APIError(409, "A request can be edited only before staff starts working on it.")
    check_version(data, row)
    title = clean_text(data, "title", 3, 120)
    message = clean_text(data, "message", 10, 4000)
    result = classification if classification is not None else classifier.classify(message)
    urgency = assess_urgency(title, message, result)
    result = {**result, "urgency": urgency}
    department, status, due = routing_decision(db, result, urgency)
    priority = "urgent" if urgency["detected"] or row["priority"] == "urgent" else "normal"  # never downgrade
    db.execute("""UPDATE requests SET title=?,message=?,department_id=?,suggested_code=?,confidence=?,
                classification_json=?,status=?,priority=?,review_due_at=?,updated_at=?,version=version+1 WHERE id=?""",
               (title, message, department, result["suggested_code"], result["confidence"],
                json.dumps(result), status, priority, due, utc_now(), row["id"]))
    updated = get_request(db, row["id"], user)
    if urgency["detected"]:
        record_event(db, updated, user, "edited", "Request edited. " + urgent_detail(db, department))
        if not has_open_alert(db, row["id"]):
            raise_alert(db, row["id"], department, "urgent", urgency["reason"])
    else:
        record_event(db, updated, user, "edited", "Request edited. " + routing_detail(db, department))
    return serialize(updated)


def route_request(db, user, row, data):
    require_role(user, "support")
    check_version(data, row)
    if row["status"] == "Resolved":
        raise APIError(409, "A resolved request cannot be rerouted.")
    code = data.get("department_code")
    if not isinstance(code, str):
        raise APIError(400, "Choose a department.")
    department = db.execute("SELECT id FROM departments WHERE code=?", (code,)).fetchone()
    if not department:
        raise APIError(400, "Choose a valid department.")
    reason = clean_text(data, "reason", 0, 500, "")
    if row["department_id"] == department[0]:
        return serialize(row)  # Refresh/repeated routing does not create another notification.
    db.execute("""INSERT INTO routing_corrections
        (request_id,staff_id,original_code,corrected_code,original_confidence,message_snapshot,reason,created_at)
        VALUES (?,?,?,?,?,?,?,?)""", (row["id"], user["id"], row["suggested_code"], code,
         row["confidence"], row["message"], reason, utc_now()))
    db.execute("""UPDATE requests SET department_id=?,status='Received',resolution='',review_due_at=NULL,
                updated_at=?,version=version+1 WHERE id=?""", (department[0], utc_now(), row["id"]))
    updated = get_request(db, row["id"], user)
    record_event(db, updated, user, "routed", "Staff reviewed the route. " + routing_detail(db, department[0]))
    return serialize(updated)


def update_status(db, user, row, data):
    require_role(user, "support")
    check_version(data, row)
    status = data.get("status")
    transitions = {"Received": {"In Progress"}, "In Progress": {"Resolved", "Received"}, "Resolved": {"In Progress"}, "Escalated": set()}
    if status == row["status"]:
        return serialize(row)
    if not isinstance(status, str) or status not in transitions[row["status"]]:
        raise APIError(409, "This status transition is unavailable. Route an escalated request first.")
    resolution = clean_text(data, "resolution", 5 if status == "Resolved" else 0, 2000, "")
    db.execute("UPDATE requests SET status=?,resolution=?,updated_at=?,version=version+1 WHERE id=?",
               (status, resolution, utc_now(), row["id"]))
    updated = get_request(db, row["id"], user)
    detail = f"Status changed to {status}." + (f" Resolution: {resolution}" if status == "Resolved" else "")
    record_event(db, updated, user, "status_changed", detail)
    return serialize(updated)


def report_missed_emergency(db, user, row, data):
    """Story constraint: a missed emergency (false negative) is escalated to a human immediately.
    The owner or support can report it. Idempotent while an alert is still open."""
    require_role(user, "student", "support")
    check_version(data, row)
    if has_open_alert(db, row["id"]):
        return serialize(row)
    note = clean_text(data, "note", 0, 500, "").strip()
    preferred = data.get("department_code") if user["role"] == "support" else None
    if preferred is not None and (not isinstance(preferred, str) or not db.execute(
            "SELECT 1 FROM departments WHERE code=?", (preferred,)).fetchone()):
        raise APIError(400, "Choose a valid department.")
    classification = json.loads(row["classification_json"])
    if preferred:
        department = urgent_department_id(db, classification, {}, preferred)
    elif row["department_id"] is not None:
        department = row["department_id"]
    else:
        department = urgent_department_id(db, classification, {})
    reason = f"Missed emergency reported by {user['role']}" + (f": {note}" if note else ".")
    db.execute("""UPDATE requests SET priority='urgent',department_id=?,
                status=CASE WHEN status='Escalated' THEN 'Received' ELSE status END,
                review_due_at=NULL,updated_at=?,version=version+1 WHERE id=?""",
               (department, utc_now(), row["id"]))
    updated = get_request(db, row["id"], user)
    record_event(db, updated, user, "emergency_reported", urgent_detail(db, department))
    raise_alert(db, row["id"], department, "escalation", reason)
    return serialize(updated)


def _open_alerts(db):
    rows = db.execute("""SELECT a.id,a.request_id,a.kind,a.reason,a.created_at,d.code department_code,
                         d.name department_name,r.title,r.status FROM urgent_alerts a
                         JOIN departments d ON d.id=a.department_id JOIN requests r ON r.id=a.request_id
                         WHERE a.acknowledged_at IS NULL ORDER BY a.created_at ASC,a.id ASC""").fetchall()
    now = datetime.now(timezone.utc)
    alerts = []
    for r in rows:
        item = dict(r)
        age = (now - datetime.fromisoformat(r["created_at"])).total_seconds()
        item.update(reference=f"REQ-{r['request_id']:05d}", age_seconds=int(age),
                    overdue=age > ALERT_OVERDUE_SECONDS)
        alerts.append(item)
    return alerts


def list_alerts(db, user):
    """Unacknowledged alerts for the staff dashboard (poll every few seconds), oldest first."""
    require_role(user, "support")
    return _open_alerts(db)


def overdue_alert_summary(db, user):
    """Supervisor view: alerts nobody acknowledged within the SLA. Administrators may not read request
    content, so this returns references, department and age only (no title, message or student name)."""
    require_role(user, "admin")
    return [{k: a[k] for k in ("id", "reference", "kind", "department_name", "age_seconds")}
            for a in _open_alerts(db) if a["overdue"]]


def acknowledge_alert(db, user, alert_id):
    require_role(user, "support")
    cursor = db.execute("UPDATE urgent_alerts SET acknowledged_at=?,acknowledged_by=? WHERE id=? AND acknowledged_at IS NULL",
                        (utc_now(), user["id"], alert_id))
    if cursor.rowcount == 0 and not db.execute("SELECT 1 FROM urgent_alerts WHERE id=?", (alert_id,)).fetchone():
        raise APIError(404, "Alert not found.")
    return {"acknowledged": True}  # repeating an acknowledgement is harmless
