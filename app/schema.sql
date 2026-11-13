PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL,
 email TEXT NOT NULL UNIQUE COLLATE NOCASE,
 password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('student','support','admin')),
 created_at TEXT NOT NULL,
 disabled_at TEXT
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
 resolved_at TEXT,
 sla_started_at TEXT,
 sla_due_at TEXT,
 sla_notified_at TEXT,
 assigned_staff_id INTEGER REFERENCES users(id),
 anonymized_at TEXT,
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
CREATE TABLE IF NOT EXISTS urgent_alerts (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
 department_id INTEGER NOT NULL REFERENCES departments(id),
 kind TEXT NOT NULL CHECK(kind IN ('urgent','escalation')),
 reason TEXT NOT NULL,
 created_at TEXT NOT NULL,
 acknowledged_at TEXT,
 acknowledged_by INTEGER REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_alerts_open ON urgent_alerts(acknowledged_at, created_at);
-- US10: labeled examples collected from staff decisions (one row per labeling event).
CREATE TABLE IF NOT EXISTS training_samples (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
 correction_id INTEGER UNIQUE REFERENCES routing_corrections(id) ON DELETE CASCADE,
 source TEXT NOT NULL CHECK(source IN ('staff_correction','escalation_outcome','reopened')),
 label TEXT NOT NULL REFERENCES departments(code),
 text TEXT NOT NULL,
 predicted_code TEXT,
 created_at TEXT NOT NULL
);
-- US10: registry of trained model versions. Exactly one version may be active.
CREATE TABLE IF NOT EXISTS model_versions (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 version TEXT NOT NULL UNIQUE,
 parent_version TEXT,
 status TEXT NOT NULL CHECK(status IN ('active','archived','rejected')),
 origin TEXT NOT NULL CHECK(origin IN ('baseline','scheduled','manual')),
 training_examples INTEGER NOT NULL,
 new_examples INTEGER NOT NULL DEFAULT 0,
 data_cutoff_id INTEGER NOT NULL DEFAULT 0,
 validation_size INTEGER NOT NULL DEFAULT 0,
 accuracy REAL,
 previous_accuracy REAL,
 artifact TEXT NOT NULL,
 created_by INTEGER REFERENCES users(id),
 created_at TEXT NOT NULL,
 deployed_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_model ON model_versions(status) WHERE status='active';
-- US10: append-only log of every retraining outcome, deployment and rollback.
CREATE TABLE IF NOT EXISTS model_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 action TEXT NOT NULL CHECK(action IN ('baseline','retrain_deployed','retrain_rejected','retrain_skipped','retrain_failed','rolled_back')),
 version TEXT,
 actor_id INTEGER REFERENCES users(id),
 detail TEXT NOT NULL,
 created_at TEXT NOT NULL
);
-- US11: one message thread per request.
CREATE TABLE IF NOT EXISTS request_messages (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
 sender_id INTEGER NOT NULL REFERENCES users(id),
 sender_role TEXT NOT NULL CHECK(sender_role IN ('student','support')),
 body TEXT NOT NULL,
 client_id TEXT,
 read_at TEXT,
 created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_client ON request_messages(request_id, sender_id, client_id) WHERE client_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_messages_thread ON request_messages(request_id, id);
CREATE INDEX IF NOT EXISTS idx_messages_unread ON request_messages(request_id, sender_role, read_at);
CREATE INDEX IF NOT EXISTS idx_samples_request ON training_samples(request_id, id);
CREATE INDEX IF NOT EXISTS idx_requests_owner ON requests(student_id, created_at);
CREATE INDEX IF NOT EXISTS idx_requests_queue ON requests(status, department_id, created_at);
CREATE INDEX IF NOT EXISTS idx_notifications_owner ON notifications(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);

-- US8: one optional rating per request; department is snapshotted for reporting.
CREATE TABLE IF NOT EXISTS request_feedback (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 request_id INTEGER NOT NULL UNIQUE REFERENCES requests(id) ON DELETE CASCADE,
 department_id INTEGER REFERENCES departments(id),
 rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
 comment TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_department ON request_feedback(department_id, created_at);

-- Urgent-alert email escalation and an at-most-once delivery outbox.
CREATE TABLE IF NOT EXISTS on_call_contacts (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 department_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
 escalation_level INTEGER NOT NULL CHECK(escalation_level IN (1,2)),
 contact_name TEXT NOT NULL,
 email TEXT NOT NULL DEFAULT '',
 is_lead INTEGER NOT NULL DEFAULT 0 CHECK(is_lead IN (0,1)),
 enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 CHECK(email != '')
);
CREATE INDEX IF NOT EXISTS idx_on_call_department ON on_call_contacts(department_id, escalation_level, enabled);
CREATE TABLE IF NOT EXISTS alert_deliveries (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 alert_id INTEGER NOT NULL REFERENCES urgent_alerts(id) ON DELETE CASCADE,
 escalation_level INTEGER NOT NULL CHECK(escalation_level IN (1,2)),
 channel TEXT NOT NULL CHECK(channel = 'email'),
 target TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','sending','sent','failed','cancelled')),
 error_code TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 sent_at TEXT,
 UNIQUE(alert_id, escalation_level, channel, target)
);
CREATE INDEX IF NOT EXISTS idx_alert_delivery_pending ON alert_deliveries(status, id);

-- US13: staff-only reminders are separate from student request notifications.
CREATE TABLE IF NOT EXISTS staff_notifications (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
 kind TEXT NOT NULL,
 message TEXT NOT NULL,
 created_at TEXT NOT NULL,
 read_at TEXT,
 UNIQUE(user_id, request_id, kind)
);
CREATE INDEX IF NOT EXISTS idx_staff_notifications ON staff_notifications(user_id, read_at, created_at);

-- US13: administrator-managed school holidays, skipped by business-hour calculations.
CREATE TABLE IF NOT EXISTS school_holidays (
 day TEXT PRIMARY KEY,
 label TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS sla_daily_summaries (
 day TEXT NOT NULL,
 department_id INTEGER NOT NULL REFERENCES departments(id),
 status TEXT NOT NULL CHECK(status IN ('sending','sent','failed')),
 created_at TEXT NOT NULL,
 PRIMARY KEY(day,department_id)
);

-- US15: request references are retained independently from request rows for audit continuity.
-- Values are compact metadata only; request text and message bodies are prohibited.
CREATE TABLE IF NOT EXISTS audit_log (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 request_ref TEXT NOT NULL DEFAULT '',
 actor_id INTEGER,
 actor_role TEXT NOT NULL,
 action TEXT NOT NULL,
 old_value TEXT NOT NULL DEFAULT '{}',
 new_value TEXT NOT NULL DEFAULT '{}',
 metadata TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL,
 prev_hash TEXT NOT NULL,
 entry_hash TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_audit_request_ref ON audit_log(request_ref, id DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action, id DESC);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at, id DESC);
CREATE TRIGGER IF NOT EXISTS audit_log_no_update BEFORE UPDATE ON audit_log
 BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete BEFORE DELETE ON audit_log
 BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;

-- US14: bytes stay in SQLite and are served only through role/ownership-checked endpoints.
CREATE TABLE IF NOT EXISTS request_attachments (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
 original_name TEXT NOT NULL,
 content_type TEXT NOT NULL CHECK(content_type IN ('image/png','image/jpeg','application/pdf')),
 byte_length INTEGER NOT NULL CHECK(byte_length BETWEEN 1 AND 5242880),
 sha256 TEXT NOT NULL,
 content BLOB NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attachments_request ON request_attachments(request_id, id);

-- US16: removal requests require an explicit administrator decision.
CREATE TABLE IF NOT EXISTS deletion_requests (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES users(id),
 status TEXT NOT NULL CHECK(status IN ('pending','approved','denied','completed')),
 requested_at TEXT NOT NULL,
 decided_at TEXT,
 decided_by INTEGER REFERENCES users(id),
 completed_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_pending_deletion ON deletion_requests(user_id) WHERE status IN ('pending','approved');
