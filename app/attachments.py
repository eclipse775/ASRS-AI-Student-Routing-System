"""Private request attachments with strict size/type checks and role-gated downloads."""
import base64
import binascii
import hashlib
import re
from pathlib import PurePath
from urllib.parse import quote

from app.audit import append_audit
from app.database import utc_now
from app.service import APIError, require_role

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_FILES = 3
TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".pdf": "application/pdf"}


def _decode_file(item):
    if not isinstance(item, dict):
        raise APIError(400, "Each attachment must include a file name and encoded file data.")
    name = item.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 255:
        raise APIError(400, "Attachment file name is invalid.")
    name = PurePath(name.replace("\\", "/")).name
    if not name or any(ord(c) < 32 for c in name):
        raise APIError(400, "Attachment file name is invalid.")
    ext = PurePath(name).suffix.lower()
    content_type = TYPES.get(ext)
    if not content_type:
        raise APIError(400, "Only PNG, JPG, and PDF files are accepted.")
    claimed = item.get("type", "")
    if claimed and claimed not in (content_type, "image/jpg" if ext in (".jpg", ".jpeg") else content_type):
        raise APIError(400, "The attachment type does not match its file extension.")
    encoded = item.get("data")
    if not isinstance(encoded, str):
        raise APIError(400, "Attachment file data is missing.")
    if encoded.startswith("data:"):
        header, separator, encoded = encoded.partition(",")
        if not separator or not header.endswith(";base64"):
            raise APIError(400, "Attachment encoding is invalid.")
    if len(encoded) > (MAX_FILE_BYTES * 4 // 3 + 8):
        raise APIError(413, "Each attachment must be 5 MB or smaller.")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise APIError(400, "Attachment encoding is invalid.") from None
    if not 1 <= len(content) <= MAX_FILE_BYTES:
        raise APIError(413, "Each attachment must be 5 MB or smaller.")
    valid = ((content_type == "image/png" and content.startswith(b"\x89PNG\r\n\x1a\n")) or
             (content_type == "image/jpeg" and content.startswith(b"\xff\xd8\xff")) or
             (content_type == "application/pdf" and content.startswith(b"%PDF-") and b"%%EOF" in content[-1024:]))
    if not valid:
        raise APIError(400, "The file contents do not match an allowed PNG, JPG, or PDF file.")
    return name[:120], content_type, content


def add_attachments(db, user, request_row, data):
    require_role(user, "student")
    if request_row["student_id"] != user["id"]:
        raise APIError(404, "Request not found.")
    if request_row["status"] == "Resolved" or request_row["anonymized_at"]:
        raise APIError(409, "Attachments can be added only to an open request.")
    files = data.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise APIError(400, "Choose one to three attachments.")
    existing = db.execute("SELECT COUNT(*) FROM request_attachments WHERE request_id=?", (request_row["id"],)).fetchone()[0]
    if existing + len(files) > MAX_FILES:
        raise APIError(400, "A request can have at most three attachments.")
    parsed = [_decode_file(item) for item in files]
    now = utc_now()
    for name, content_type, content in parsed:
        db.execute("""INSERT INTO request_attachments
                      (request_id,original_name,content_type,byte_length,sha256,content,created_at)
                      VALUES (?,?,?,?,?,?,?)""",
                   (request_row["id"], name, content_type, len(content), hashlib.sha256(content).hexdigest(), content, now))
    append_audit(db, user, "attachments_added", request_row["id"],
                 new_value={"count": len(parsed)}, metadata={"total_bytes": sum(len(f[2]) for f in parsed)})
    return list_attachments(db, request_row)


def list_attachments(db, request_row):
    return [dict(row) for row in db.execute("""SELECT id,original_name,content_type,byte_length,sha256,created_at
                                                 FROM request_attachments WHERE request_id=? ORDER BY id""",
                                            (request_row["id"],))]


def download_attachment(db, user, attachment_id):
    if not user:
        raise APIError(401, "Please sign in.")
    if user["role"] not in ("student", "support"):
        raise APIError(403, "You do not have access to this attachment.")
    row = db.execute("""SELECT a.*,r.student_id,r.anonymized_at FROM request_attachments a
                        JOIN requests r ON r.id=a.request_id WHERE a.id=?""", (attachment_id,)).fetchone()
    if not row or (user["role"] == "student" and row["student_id"] != user["id"]):
        raise APIError(404, "Attachment not found.")
    if row["anonymized_at"]:
        raise APIError(404, "Attachment not found.")
    filename = re.sub(r"[\r\n\x00-\x1f\x7f\"]", "_", row["original_name"])
    return {"_file_response": True, "body": row["content"], "content_type": "application/octet-stream",
            "disposition": "attachment; filename=attachment; filename*=UTF-8''" +
                           quote(filename)}
