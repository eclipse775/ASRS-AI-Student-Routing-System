"""Append-only, hash-chained audit events. Never pass request text or message bodies here."""
import hashlib
import hmac
import json
from app.database import utc_now

GENESIS = "0" * 64


def _json(value):
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _payload(request_ref, actor_id, actor_role, action, old_value, new_value, metadata, created_at, prev_hash):
    return {"request_ref": request_ref or "", "actor_id": actor_id, "actor_role": actor_role or "system",
            "action": action, "old_value": old_value or {}, "new_value": new_value or {},
            "metadata": metadata or {}, "created_at": created_at, "prev_hash": prev_hash}


def append_audit(db, actor, action, request_id=None, request_ref=None, old_value=None, new_value=None, metadata=None):
    if request_ref is None and request_id is not None:
        request_ref = f"REQ-{int(request_id):05d}"
    previous = db.execute("SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    prev_hash = previous[0] if previous else GENESIS
    created_at = utc_now()
    actor_id = actor["id"] if actor else None
    actor_role = actor["role"] if actor else "system"
    payload = _payload(request_ref, actor_id, actor_role, action, old_value, new_value, metadata,
                       created_at, prev_hash)
    digest = hashlib.sha256((prev_hash + "\n" + _json(payload)).encode("utf-8")).hexdigest()
    db.execute("""INSERT INTO audit_log
                  (request_ref,actor_id,actor_role,action,old_value,new_value,metadata,created_at,prev_hash,entry_hash)
                  VALUES (?,?,?,?,?,?,?,?,?,?)""",
               (request_ref or "", actor_id, actor_role, action, _json(old_value), _json(new_value),
                _json(metadata), created_at, prev_hash, digest))
    return digest


def verify_chain(db):
    previous = GENESIS
    for row in db.execute("""SELECT request_ref,actor_id,actor_role,action,old_value,new_value,metadata,
                            created_at,prev_hash,entry_hash FROM audit_log ORDER BY id"""):
        if row["prev_hash"] != previous:
            return False
        payload = _payload(row["request_ref"], row["actor_id"], row["actor_role"], row["action"],
                           json.loads(row["old_value"]), json.loads(row["new_value"]),
                           json.loads(row["metadata"]), row["created_at"], row["prev_hash"])
        expected = hashlib.sha256((previous + "\n" + _json(payload)).encode("utf-8")).hexdigest()
        if not hmac.compare_digest(expected, row["entry_hash"]):
            return False
        previous = row["entry_hash"]
    return True
