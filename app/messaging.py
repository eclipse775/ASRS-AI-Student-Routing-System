"""US11: a message thread between the request owner and support staff.

Access control is decided by the caller (``server.py``): ``get_request`` returns 404 for another
student's request, administrators are refused before this module is reached, and only the
``student`` and ``support`` roles are accepted here. Message text is never sent to the AI provider.
"""
import re

from app.audit import append_audit
from app.database import utc_now
from app.service import APIError, clean_text, record_event, require_role

MAX_BODY = 1000          # "short messages"
MAX_THREAD_MESSAGES = 300
PAGE_SIZE = 200
CLIENT_ID = re.compile(r"[A-Za-z0-9_-]{8,64}")

# Message SQL used by the request lists, so staff and students can see unread counts without extra calls.
UNREAD_FOR_STUDENT = """(SELECT COUNT(*) FROM request_messages m WHERE m.request_id=r.id
                         AND m.sender_role='support' AND m.read_at IS NULL) unread_messages"""
UNREAD_FOR_SUPPORT = """(SELECT COUNT(*) FROM request_messages m WHERE m.request_id=r.id
                         AND m.sender_role='student' AND m.read_at IS NULL) unread_messages"""
MESSAGE_COUNT = "(SELECT COUNT(*) FROM request_messages m WHERE m.request_id=r.id) message_count"


def thread_is_open(row):
    """The thread is read-only while the request is Resolved and writable again if it is reopened."""
    return row["status"] != "Resolved"


def serialize_message(row, user):
    return {"id": row["id"], "request_id": row["request_id"], "sender_role": row["sender_role"],
            "sender_name": row["sender_name"], "body": row["body"], "created_at": row["created_at"],
            # "mine" means "on my side of the conversation": the student, or any support staff member.
            "mine": row["sender_role"] == user["role"], "read": row["read_at"] is not None}


def _fetch(db, request_id, after=0):
    return db.execute("""SELECT m.*,u.name sender_name FROM request_messages m JOIN users u ON u.id=m.sender_id
                         WHERE m.request_id=? AND m.id>? ORDER BY m.id ASC LIMIT ?""",
                      (request_id, after, PAGE_SIZE)).fetchall()


def list_messages(db, user, row, after=0):
    require_role(user, "student", "support")
    messages = [serialize_message(m, user) for m in _fetch(db, row["id"], after)]
    return {"messages": messages, "open": thread_is_open(row), "status": row["status"],
            "request_id": row["id"], "reference": f"REQ-{row['id']:05d}"}


def post_message(db, user, row, data):
    require_role(user, "student", "support")
    if not thread_is_open(row):
        raise APIError(409, "This conversation is read-only because the request is resolved. "
                            "It opens again if the request is reopened.")
    body = clean_text(data, "body", 1, MAX_BODY).strip()
    client_id = data.get("client_id")
    if client_id is not None and (not isinstance(client_id, str) or not CLIENT_ID.fullmatch(client_id)):
        raise APIError(400, "The message identifier is invalid.")
    if client_id:
        # A retry of the same send (double click, lost response) returns the original message.
        duplicate = db.execute("""SELECT m.*,u.name sender_name FROM request_messages m JOIN users u ON u.id=m.sender_id
                                  WHERE m.request_id=? AND m.sender_id=? AND m.client_id=?""",
                               (row["id"], user["id"], client_id)).fetchone()
        if duplicate:
            return serialize_message(duplicate, user), False
    if db.execute("SELECT COUNT(*) FROM request_messages WHERE request_id=?", (row["id"],)).fetchone()[0] >= MAX_THREAD_MESSAGES:
        raise APIError(409, "This conversation reached its message limit. Please wait for the department to follow up.")
    cursor = db.execute("""INSERT INTO request_messages (request_id,sender_id,sender_role,body,client_id,created_at)
                           VALUES (?,?,?,?,?,?)""", (row["id"], user["id"], user["role"], body, client_id, utc_now()))
    if user["role"] == "support":
        append_audit(db, user, "staff_message_posted", row["id"], metadata={"message_id": cursor.lastrowid})
        # The student is notified in the existing notification history. The text is not copied into the
        # notice, and the unique event kind keeps one notification per message.
        record_event(db, row, user, f"message:{cursor.lastrowid}",
                     "New message from support staff. Open your request to read and reply.")
    saved = db.execute("""SELECT m.*,u.name sender_name FROM request_messages m JOIN users u ON u.id=m.sender_id
                          WHERE m.id=?""", (cursor.lastrowid,)).fetchone()
    return serialize_message(saved, user), True


def mark_read(db, user, row):
    """Mark the other party's messages as read. Returns the number of newly read messages."""
    require_role(user, "student", "support")
    other = "support" if user["role"] == "student" else "student"
    cursor = db.execute("""UPDATE request_messages SET read_at=? WHERE request_id=? AND sender_role=? AND read_at IS NULL""",
                        (utc_now(), row["id"], other))
    return cursor.rowcount


def unread_total_for_support(db):
    return db.execute("""SELECT COUNT(*) FROM request_messages m JOIN requests r ON r.id=m.request_id
                         WHERE m.sender_role='student' AND m.read_at IS NULL""").fetchone()[0]
