PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL,
 email TEXT NOT NULL UNIQUE COLLATE NOCASE,
 password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('student','support','admin')),
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS departments (
 id INTEGER PRIMARY KEY,
 code TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL,
 response_hours INTEGER NOT NULL CHECK(response_hours > 0)
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY,
 user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
 csrf_token TEXT NOT NULL,
 expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS requests (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 student_id INTEGER NOT NULL REFERENCES users(id),
 title TEXT NOT NULL,
 message TEXT NOT NULL,
 department_id INTEGER REFERENCES departments(id),
 suggested_code TEXT NOT NULL,
 confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
 classification_json TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('Received','In Progress','Resolved','Escalated')),
 priority TEXT NOT NULL CHECK(priority IN ('normal','urgent')),
 resolution TEXT NOT NULL DEFAULT '',
 version INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 review_due_at TEXT,
 CHECK((status = 'Escalated' AND department_id IS NULL) OR
       (status != 'Escalated' AND department_id IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS request_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
 actor_id INTEGER REFERENCES users(id),
 kind TEXT NOT NULL,
 status TEXT NOT NULL,
 detail TEXT NOT NULL,
 version INTEGER NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(request_id, version, kind)
);
CREATE TABLE IF NOT EXISTS notifications (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
 event_id INTEGER NOT NULL UNIQUE REFERENCES request_events(id) ON DELETE CASCADE,
 message TEXT NOT NULL,
 read_at TEXT,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS routing_corrections (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
 staff_id INTEGER NOT NULL REFERENCES users(id),
 original_code TEXT NOT NULL,
 corrected_code TEXT NOT NULL REFERENCES departments(code),
 original_confidence REAL NOT NULL,
 message_snapshot TEXT NOT NULL,
 reason TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
 key TEXT PRIMARY KEY,
 value TEXT NOT NULL,
 updated_by INTEGER REFERENCES users(id),
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_requests_owner ON requests(student_id, created_at);
CREATE INDEX IF NOT EXISTS idx_requests_queue ON requests(status, department_id, created_at);
CREATE INDEX IF NOT EXISTS idx_notifications_owner ON notifications(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);
