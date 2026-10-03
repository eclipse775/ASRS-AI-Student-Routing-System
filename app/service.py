"""Transactional request creation, routing, status, history, and notifications."""
import json
from app.database import review_deadline, utc_now


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


def routing_decision(db, classification):
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
    department, status, due = routing_decision(db, result)
    now = utc_now()
    cursor = db.execute("""INSERT INTO requests
         (student_id,title,message,department_id,suggested_code,confidence,classification_json,
          status,priority,created_at,updated_at,review_due_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
         (user["id"], title, message, department, result["suggested_code"], result["confidence"],
          json.dumps(result), status, priority, now, now, due))
    row = get_request(db, cursor.lastrowid, user)
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
    department, status, due = routing_decision(db, result)
    db.execute("""UPDATE requests SET title=?,message=?,department_id=?,suggested_code=?,confidence=?,
                classification_json=?,status=?,review_due_at=?,updated_at=?,version=version+1 WHERE id=?""",
               (title, message, department, result["suggested_code"], result["confidence"],
                json.dumps(result), status, due, utc_now(), row["id"]))
    updated = get_request(db, row["id"], user)
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
