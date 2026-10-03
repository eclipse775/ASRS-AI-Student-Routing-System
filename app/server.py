"""Small JSON API and static frontend on Python's WSGI development server."""
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
import hmac
import json
import logging
import mimetypes
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from urllib.parse import parse_qs

from app.database import connection, initialize, utc_now
from app.llm import build_classifier
from app.security import hash_password, token_hash, verify_password
from app.university import STUDENT_EMAIL, student_profile, university_info
from app.service import (APIError, check_version, clean_text, create_request, edit_request,
                         get_request, require_role, route_request, serialize, update_status)

ROOT = Path(__file__).resolve().parents[1]
LOG = logging.getLogger("routing")


def public_user(row):
    if not row:
        return None
    result = {k: row[k] for k in ("id", "name", "email", "role")}
    result["student_profile"] = student_profile(row["email"]) if row["role"] == "student" else None
    return result


class Application:
    def __init__(self, database_path, sprint=2, secure_cookies=False, classifier=None):
        self.database_path = Path(database_path)
        self.sprint = sprint
        self.secure_cookies = secure_cookies
        initialize(self.database_path)
        self.classifier = classifier if classifier is not None else build_classifier(ROOT)
        self.failed_logins = {}
        self.login_lock = threading.Lock()
        self.dummy_hash = hash_password(secrets.token_urlsafe(16))

    def __call__(self, environ, start_response):
        headers = [("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "same-origin"),
                   ("X-Frame-Options", "DENY"), ("Cache-Control", "no-store"),
                   ("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")]
        status = 200
        db = None
        try:
            path = environ.get("PATH_INFO", "/")
            method = environ.get("REQUEST_METHOD", "GET")
            if path.startswith("/api/"):
                db = connection(self.database_path)
                session, user = self.session(db, environ)
                if method not in ("GET", "HEAD"):
                    if not session or not hmac.compare_digest(environ.get("HTTP_X_CSRF_TOKEN", ""), session["csrf_token"]):
                        raise APIError(403, "Your session changed. Refresh the page and try again.")
                    if environ.get("CONTENT_TYPE", "").split(";")[0].strip() != "application/json":
                        raise APIError(415, "Use application/json.")
                data = self.read_json(environ) if method not in ("GET", "HEAD") else {}
                # Authenticate and validate before paying for AI. Never hold SQLite's
                # write lock while waiting on a network provider.
                prepared = self.prepare_routing(db, path, method, data, user)
                if method not in ("GET", "HEAD"):
                    db.execute("BEGIN IMMEDIATE")
                    # Recheck a session that could have been logged out during AI work.
                    session, user = self.session(db, environ)
                    if not session or not hmac.compare_digest(environ.get("HTTP_X_CSRF_TOKEN", ""), session["csrf_token"]):
                        raise APIError(403, "Your session changed. Refresh the page and try again.")
                payload, status = self.api(db, environ, path, method, data, session, user, headers, prepared)
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                headers.append(("Content-Type", "application/json; charset=utf-8"))
                db.commit()
            else:
                if method not in ("GET", "HEAD"):
                    raise APIError(405, "Method not allowed.")
                file_path = self.static_file(path)
                body = file_path.read_bytes()
                mime = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
                headers.append(("Content-Type", mime + ("; charset=utf-8" if mime.startswith("text/") or mime == "application/javascript" else "")))
        except APIError as error:
            status = error.status
            body = json.dumps({"error": error.message}).encode()
            headers.append(("Content-Type", "application/json; charset=utf-8"))
            if db:
                db.rollback()
        except sqlite3.OperationalError:
            if db:
                db.rollback()
            status, body = 503, b'{"error":"The database is busy. Please try again."}'
            headers.append(("Content-Type", "application/json; charset=utf-8"))
        except Exception:
            if db:
                db.rollback()
            LOG.exception("Unhandled application error")
            status, body = 500, b'{"error":"An unexpected error occurred. Please try again."}'
            headers.append(("Content-Type", "application/json; charset=utf-8"))
        finally:
            if db:
                db.close()
        headers.append(("Content-Length", str(len(body))))
        labels = {200: "OK", 201: "Created", 400: "Bad Request", 401: "Unauthorized",
                  403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed",
                  409: "Conflict", 413: "Payload Too Large", 415: "Unsupported Media Type",
                  429: "Too Many Requests", 500: "Internal Server Error", 503: "Service Unavailable"}
        start_response(f"{status} {labels.get(status, 'Error')}", headers)
        return [b"" if environ.get("REQUEST_METHOD") == "HEAD" else body]

    @staticmethod
    def read_json(environ):
        try:
            size = int(environ.get("CONTENT_LENGTH") or 0)
            if not 0 <= size <= 20000:
                raise APIError(413, "The request is too large.")
            data = json.loads(environ["wsgi.input"].read(size) or b"{}")
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except (ValueError, UnicodeDecodeError):
            raise APIError(400, "Send a valid JSON object.") from None

    @staticmethod
    def static_file(path):
        if path in ("/", "/staff", "/notifications", "/settings"):
            return ROOT / "static" / "index.html"
        candidate = (ROOT / "static" / path.lstrip("/")).resolve()
        if not candidate.is_relative_to((ROOT / "static").resolve()) or not candidate.is_file():
            raise APIError(404, "Page not found.")
        return candidate

    @staticmethod
    def session(db, environ):
        cookie = SimpleCookie()
        try:
            cookie.load(environ.get("HTTP_COOKIE", ""))
            token = cookie["routing_session"].value if "routing_session" in cookie else ""
        except Exception:
            token = ""
        row = db.execute("SELECT * FROM sessions WHERE token_hash=? AND expires_at>?", (token_hash(token), utc_now())).fetchone()
        user = db.execute("SELECT * FROM users WHERE id=?", (row["user_id"],)).fetchone() if row and row["user_id"] else None
        return row, user

    def new_session(self, db, user_id, headers, previous=None):
        if previous:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (previous["token_hash"],))
        db.execute("DELETE FROM sessions WHERE expires_at<?", (utc_now(),))
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        expiry = (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat(timespec="microseconds")
        db.execute("INSERT INTO sessions VALUES (?,?,?,?)", (token_hash(token), user_id, csrf, expiry))
        cookie = f"routing_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=28800"
        if self.secure_cookies:
            cookie += "; Secure"
        headers.append(("Set-Cookie", cookie))
        return csrf

    def require_sprint2(self):
        if self.sprint < 2:
            raise APIError(403, "This feature is available in the Sprint 2 increment.")

    def prepare_routing(self, db, path, method, data, user):
        creating = path == "/api/requests" and method == "POST"
        editing = re.fullmatch(r"/api/requests/(\d+)", path) if method == "PUT" else None
        if not creating and not editing:
            return None
        require_role(user, "student")
        if editing:
            row = get_request(db, int(editing[1]), user)
            if row["status"] not in ("Received", "Escalated"):
                raise APIError(409, "A request can be edited only before staff starts working on it.")
            check_version(data, row)
        clean_text(data, "title", 3, 120)
        message = clean_text(data, "message", 10, 4000)
        if creating and data.get("priority", "normal") not in ("normal", "urgent"):
            raise APIError(400, "Choose a valid priority.")
        return self.classifier.classify(message)

    def api(self, db, env, path, method, data, session, user, headers, prepared=None):
        if path == "/api/health" and method == "GET":
            return {"ok": True, "sprint": self.sprint}, 200
        if path == "/api/session" and method == "GET":
            csrf = session["csrf_token"] if session else self.new_session(db, None, headers)
            return {"user": public_user(user), "csrf_token": csrf, "sprint": self.sprint,
                    "ai": self.classifier.status(), "university": university_info()}, 200
        if path == "/api/auth/register" and method == "POST":
            name = clean_text(data, "name", 2, 80).strip()
            email = self.valid_student_email(data)
            password = clean_text(data, "password", 10, 128)
            if db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
                raise APIError(409, "An account with this email already exists.")
            cursor = db.execute("INSERT INTO users (name,email,password_hash,role,created_at) VALUES (?,?,?,'student',?)", (name, email, hash_password(password), utc_now()))
            registered = db.execute("SELECT * FROM users WHERE id=?", (cursor.lastrowid,)).fetchone()
            csrf = self.new_session(db, cursor.lastrowid, headers, session)
            return {"user": public_user(registered), "csrf_token": csrf}, 201
        if path == "/api/auth/login" and method == "POST":
            email = self.valid_email(data)
            password = data.get("password")
            if not isinstance(password, str) or len(password) > 128:
                raise APIError(400, "Enter a valid password.")
            key = (env.get("REMOTE_ADDR", "local"), email)
            with self.login_lock:
                now = time.monotonic()
                self.failed_logins = {k: [t for t in ts if now - t < 600] for k, ts in self.failed_logins.items() if any(now-t < 600 for t in ts)}
                if len(self.failed_logins.get(key, [])) >= 8:
                    raise APIError(429, "Too many sign-in attempts. Try again in 10 minutes.")
            account = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            valid = verify_password(password, account["password_hash"] if account else self.dummy_hash)
            if not account or not valid or (account["role"] == "student" and not student_profile(email)):
                with self.login_lock:
                    self.failed_logins.setdefault(key, []).append(time.monotonic())
                raise APIError(401, "Email or password is incorrect.")
            with self.login_lock:
                self.failed_logins.pop(key, None)
            csrf = self.new_session(db, account["id"], headers, session)
            return {"user": public_user(account), "csrf_token": csrf}, 200
        if path == "/api/auth/logout" and method == "POST":
            csrf = self.new_session(db, None, headers, session)
            return {"user": None, "csrf_token": csrf}, 200
        require_role(user, "student", "support", "admin")
        if path == "/api/ai/status" and method == "GET":
            return {"ai": self.classifier.status()}, 200
        if path == "/api/departments" and method == "GET":
            return {"departments": [dict(r) for r in db.execute("SELECT * FROM departments ORDER BY id")]}, 200
        if path == "/api/requests" and method == "POST":
            return {"request": create_request(db, user, data, self.classifier, prepared)}, 201
        if path == "/api/requests" and method == "GET":
            require_role(user, "student")
            rows = db.execute("""SELECT r.*,d.name department_name,d.code department_code FROM requests r
                          LEFT JOIN departments d ON d.id=r.department_id WHERE r.student_id=?
                          ORDER BY r.created_at DESC,r.id DESC""", (user["id"],)).fetchall()
            return {"requests": [serialize(r) for r in rows]}, 200
        if path == "/api/staff/requests" and method == "GET":
            self.require_sprint2()
            require_role(user, "support")
            query = parse_qs(env.get("QUERY_STRING", ""))
            where, params = [], []
            for key, column, allowed in [("status", "r.status", {"Received", "In Progress", "Resolved", "Escalated"}),
                                         ("priority", "r.priority", {"normal", "urgent"}),
                                         ("department", "d.code", {"it", "finance", "academic", "health"})]:
                value = query.get(key, [""])[0]
                if value:
                    if value not in allowed:
                        raise APIError(400, "Invalid queue filter.")
                    where.append(column + "=?")
                    params.append(value)
            if query.get("open", [""])[0] == "1":
                where.append("r.status!='Resolved'")
            clause = " WHERE " + " AND ".join(where) if where else ""
            rows = db.execute("""SELECT r.*,d.name department_name,d.code department_code,u.name student_name
                                FROM requests r LEFT JOIN departments d ON d.id=r.department_id
                                JOIN users u ON u.id=r.student_id""" + clause + " ORDER BY r.created_at ASC,r.id ASC", params).fetchall()
            return {"requests": [serialize(r) for r in rows]}, 200
        match = re.fullmatch(r"/api/requests/(\d+)(?:/(route|status))?", path)
        if match:
            request_id, action = int(match[1]), match[2]
            if user["role"] == "admin":
                raise APIError(403, "Request content is limited to its owner and support staff.")
            if user["role"] == "support":
                self.require_sprint2()
            row = get_request(db, request_id, user)
            if method == "GET" and not action:
                events = [dict(r) for r in db.execute("SELECT kind,status,detail,created_at FROM request_events WHERE request_id=? ORDER BY id", (request_id,))]
                return {"request": serialize(row), "history": events}, 200
            if method == "PUT" and not action:
                return {"request": edit_request(db, user, row, data, self.classifier, prepared)}, 200
            if method == "DELETE" and not action:
                require_role(user, "student")
                check_version(data, row)
                if row["status"] not in ("Received", "Escalated"):
                    raise APIError(409, "A request can be deleted only before staff starts working on it.")
                db.execute("DELETE FROM requests WHERE id=?", (request_id,))
                return {"deleted": True}, 200
            if method == "POST" and action in ("route", "status"):
                self.require_sprint2()
                updated = route_request(db, user, row, data) if action == "route" else update_status(db, user, row, data)
                return {"request": updated}, 200
        if path == "/api/notifications" and method == "GET":
            require_role(user, "student")
            rows = db.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC,id DESC", (user["id"],))
            return {"notifications": [dict(r) for r in rows]}, 200
        match = re.fullmatch(r"/api/notifications/(\d+)/read", path)
        if match and method == "POST":
            require_role(user, "student")
            cursor = db.execute("UPDATE notifications SET read_at=COALESCE(read_at,?) WHERE id=? AND user_id=?", (utc_now(), int(match[1]), user["id"]))
            if cursor.rowcount == 0:
                raise APIError(404, "Notification not found.")
            return {"read": True}, 200
        if path == "/api/admin/settings" and method in ("GET", "PUT"):
            self.require_sprint2()
            require_role(user, "admin")
            if method == "PUT":
                threshold = data.get("confidence_threshold")
                if type(threshold) not in (int, float) or not 0.5 <= threshold <= 0.99:
                    raise APIError(400, "Confidence threshold must be between 0.50 and 0.99.")
                db.execute("UPDATE settings SET value=?,updated_by=?,updated_at=? WHERE key='confidence_threshold'", (str(threshold), user["id"], utc_now()))
            return {"confidence_threshold": float(db.execute("SELECT value FROM settings WHERE key='confidence_threshold'").fetchone()[0]),
                    "model_version": self.classifier.version, "training_examples": self.classifier.training_size,
                    "ai": self.classifier.status()}, 200
        if path == "/api/admin/corrections" and method == "GET":
            self.require_sprint2()
            require_role(user, "admin")
            # No student names or request text in the administrative summary.
            return {"corrections": [dict(r) for r in db.execute("SELECT id,request_id,original_code,corrected_code,original_confidence,reason,created_at FROM routing_corrections ORDER BY id DESC")]}, 200
        raise APIError(404, "Endpoint not found.")

    @staticmethod
    def valid_email(data):
        email = clean_text(data, "email", 5, 254).strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise APIError(400, "Enter a valid email address.")
        return email

    @classmethod
    def valid_student_email(cls, data):
        email = cls.valid_email(data)
        if not STUDENT_EMAIL.fullmatch(email):
            raise APIError(400, "Use your SDU student email: 9 digits followed by @sdu.edu.kz (e.g. 240103030@sdu.edu.kz).")
        if not student_profile(email):
            raise APIError(400, "The admission year cannot be later than the current academic year.")
        return email
