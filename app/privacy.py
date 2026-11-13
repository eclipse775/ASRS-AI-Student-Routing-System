"""Retention anonymization and administrator-approved student data deletion."""
import json
import secrets

from app.audit import append_audit
from app.database import utc_now
from app.security import hash_password
from app.service import APIError, require_role


def anonymous_user_id(db):
    row = db.execute("SELECT id FROM users WHERE email='anonymized@invalid.local'").fetchone()
    if row:
        return row[0]
    cursor = db.execute("""INSERT INTO users (name,email,password_hash,role,created_at,disabled_at)
                           VALUES ('Anonymized student','anonymized@invalid.local',?,'student',?,?)""",
                        (hash_password(secrets.token_urlsafe(32)), utc_now(), utc_now()))
    return cursor.lastrowid


def anonymize_request(db, request_id, actor=None, reason="retention"):
    row = db.execute("""SELECT id,student_id,suggested_code,confidence,classification_json,anonymized_at
                        FROM requests WHERE id=?""", (request_id,)).fetchone()
    if not row or row["anonymized_at"]:
        return False
    owner_id = row["student_id"]
    target_id = anonymous_user_id(db)
    now = utc_now()
    old_class = json.loads(row["classification_json"] or "{}")
    safe_class = {key: old_class[key] for key in ("review_required", "language") if key in old_class}
    safe_class.update({"suggested_code": row["suggested_code"], "confidence": row["confidence"],
                       "provider": "redacted", "model_version": "redacted", "translated_text": ""})
    db.execute("""UPDATE requests SET student_id=?,title='Anonymized request',message='',resolution='',
                classification_json=?,anonymized_at=?,updated_at=?,version=version+1 WHERE id=?""",
               (target_id, json.dumps(safe_class), now, now, request_id))
    db.execute("UPDATE request_events SET actor_id=NULL,detail='Request details removed for privacy.' WHERE request_id=?",
               (request_id,))
    db.execute("""UPDATE request_messages SET body='Message removed for privacy.',
                sender_id=CASE WHEN sender_role='student' THEN ? ELSE sender_id END,
                read_at=COALESCE(read_at,?) WHERE request_id=?""", (target_id, now, request_id))
    db.execute("UPDATE routing_corrections SET message_snapshot='',reason='' WHERE request_id=?", (request_id,))
    db.execute("UPDATE training_samples SET text='' WHERE request_id=?", (request_id,))
    db.execute("UPDATE request_feedback SET comment='' WHERE request_id=?", (request_id,))
    db.execute("DELETE FROM request_attachments WHERE request_id=?", (request_id,))
    db.execute("DELETE FROM notifications WHERE request_id=?", (request_id,))
    db.execute("UPDATE urgent_alerts SET reason='Urgent alert retained without request content.' WHERE request_id=?",
               (request_id,))
    append_audit(db, actor, "request_anonymized", request_id,
                 old_value={"personal_data": "present"}, new_value={"personal_data": "removed"},
                 metadata={"reason": reason})
    return True


def request_deletion(db, user, data):
    require_role(user, "student")
    existing = db.execute("""SELECT id,status,requested_at FROM deletion_requests WHERE user_id=?
                           AND status IN ('pending','approved') ORDER BY id DESC LIMIT 1""", (user["id"],)).fetchone()
    if existing:
        return {"id": existing["id"], "status": existing["status"], "requested_at": existing["requested_at"]}
    now = utc_now()
    cursor = db.execute("INSERT INTO deletion_requests (user_id,status,requested_at) VALUES (?,'pending',?)",
                        (user["id"], now))
    append_audit(db, user, "deletion_requested", metadata={"scope": "student_account"})
    return {"id": cursor.lastrowid, "status": "pending", "requested_at": now}


def current_deletion_request(db, user):
    require_role(user, "student")
    row = db.execute("""SELECT id,status,requested_at,decided_at,completed_at FROM deletion_requests
                      WHERE user_id=? ORDER BY id DESC LIMIT 1""", (user["id"],)).fetchone()
    return dict(row) if row else None


def decide_deletion(db, admin, deletion_id, decision):
    require_role(admin, "admin")
    if decision not in ("approve", "deny"):
        raise APIError(400, "Choose approve or deny.")
    row = db.execute("SELECT * FROM deletion_requests WHERE id=? AND status='pending'", (deletion_id,)).fetchone()
    if not row:
        raise APIError(404, "Pending deletion request not found.")
    now = utc_now()
    if decision == "deny":
        db.execute("UPDATE deletion_requests SET status='denied',decided_at=?,decided_by=? WHERE id=?",
                   (now, admin["id"], deletion_id))
        append_audit(db, admin, "deletion_denied", metadata={"deletion_request_id": deletion_id})
        return {"status": "denied"}
    user_id = row["user_id"]
    request_ids = [r[0] for r in db.execute("SELECT id FROM requests WHERE student_id=? ORDER BY id", (user_id,))]
    db.execute("UPDATE deletion_requests SET status='approved',decided_at=?,decided_by=? WHERE id=?",
               (now, admin["id"], deletion_id))
    for request_id in request_ids:
        anonymize_request(db, request_id, actor=admin, reason="approved_deletion")
    db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM notifications WHERE user_id=?", (user_id,))
    db.execute("UPDATE users SET name='Former student',email=?,password_hash=?,disabled_at=? WHERE id=?",
               (f"former-student-{user_id}@deleted.invalid", hash_password(secrets.token_urlsafe(32)), now, user_id))
    db.execute("UPDATE deletion_requests SET status='completed',completed_at=? WHERE id=?", (now, deletion_id))
    append_audit(db, admin, "personal_data_deleted", metadata={"requests_anonymized": len(request_ids)})
    return {"status": "completed", "requests_anonymized": len(request_ids)}
