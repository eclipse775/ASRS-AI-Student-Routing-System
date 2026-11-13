"""Persistent, idempotent background work for alert escalation, SLA and data retention."""
from datetime import datetime, timedelta, timezone
import logging
import sqlite3

from app.audit import append_audit
from app.business_time import calendar
from app.database import connection, utc_now
from app.delivery import deliver, gateway_status, safe_alert_reason

LOG = logging.getLogger("routing.scheduler")
ALERT_FIRST_LEVEL_SECONDS = 120
ALERT_SECOND_LEVEL_SECONDS = 300


def _alert_body(row):
    reason = safe_alert_reason(row["kind"], row["reason"])
    return (f"Request reference: REQ-{row['request_id']:05d}\n"
            f"Department: {row['department_name']}\n"
            f"Urgency reason: {reason}")


def run_alert_escalation(database_path):
    gateways = gateway_status()
    with connection(database_path) as db:
        db.execute("BEGIN IMMEDIATE")
        now = datetime.now(timezone.utc)
        alerts = db.execute("""SELECT a.id,a.request_id,a.kind,a.reason,a.created_at,d.name department_name
                               FROM urgent_alerts a JOIN departments d ON d.id=a.department_id
                               JOIN requests r ON r.id=a.request_id
                               WHERE a.acknowledged_at IS NULL AND r.anonymized_at IS NULL
                               ORDER BY a.created_at,a.id""").fetchall()
        for alert in alerts:
            created = datetime.fromisoformat(alert["created_at"])
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age = (now - created).total_seconds()
            levels = ([1] if age >= ALERT_FIRST_LEVEL_SECONDS else [])
            if age >= ALERT_FIRST_LEVEL_SECONDS + ALERT_SECOND_LEVEL_SECONDS:
                levels.append(2)
            for level in levels:
                contacts = db.execute("""SELECT email FROM on_call_contacts
                                          WHERE department_id=(SELECT department_id FROM urgent_alerts WHERE id=?)
                                          AND escalation_level=? AND enabled=1 AND email != ''""", (alert["id"], level)).fetchall()
                emails = {c["email"].strip().lower() for c in contacts if c["email"]}
                if level == 2:
                    emails.update(r[0].strip().lower() for r in db.execute(
                        "SELECT email FROM users WHERE role='admin' AND disabled_at IS NULL"))
                targets = []
                if gateways["email_configured"]:
                    targets.extend(("email", value) for value in sorted(emails))
                for channel, target in targets:
                    db.execute("""INSERT OR IGNORE INTO alert_deliveries
                                  (alert_id,escalation_level,channel,target,status,created_at)
                                  VALUES (?,?,?,?, 'pending',?)""", (alert["id"], level, channel, target, utc_now()))
        # Claim each delivery before making a network call, so restarts or a second process cannot resend it.
        claimed = db.execute("""SELECT x.id,x.channel,x.target,a.id alert_id,a.request_id,a.kind,a.reason,d.name department_name
                               FROM alert_deliveries x JOIN urgent_alerts a ON a.id=x.alert_id
                               JOIN departments d ON d.id=a.department_id
                               JOIN requests r ON r.id=a.request_id
                               WHERE x.channel='email' AND x.status='pending'
                               AND a.acknowledged_at IS NULL AND r.anonymized_at IS NULL
                               ORDER BY x.id LIMIT 100""").fetchall()
        for row in claimed:
            db.execute("UPDATE alert_deliveries SET status='sending' WHERE id=? AND status='pending'", (row["id"],))
        db.commit()
    for row in claimed:
        with connection(database_path) as db:
            open_alert = db.execute("""SELECT 1 FROM urgent_alerts a JOIN requests r ON r.id=a.request_id
                                       WHERE a.id=? AND a.acknowledged_at IS NULL AND r.anonymized_at IS NULL""",
                                    (row["alert_id"],)).fetchone()
            if not open_alert:
                db.execute("UPDATE alert_deliveries SET status='cancelled' WHERE id=? AND status='sending'",
                           (row["id"],))
                continue
        subject = f"Urgent campus request REQ-{row['request_id']:05d}"
        ok, error_code = deliver(row["channel"], row["target"], subject, _alert_body(row))
        with connection(database_path) as db:
            db.execute("""UPDATE alert_deliveries SET status=?,error_code=?,sent_at=? WHERE id=? AND status='sending'""",
                       ("sent" if ok else "failed", error_code, utc_now(), row["id"]))


def run_sla_reminders(database_path):
    gateways = gateway_status()
    mail_jobs = []
    with connection(database_path) as db:
        db.execute("BEGIN IMMEDIATE")
        now = utc_now()
        overdue = db.execute("""SELECT r.id,r.student_id,r.department_id,r.assigned_staff_id,r.sla_due_at,
                                      d.name department_name FROM requests r
                                      JOIN departments d ON d.id=r.department_id
                                      WHERE r.status='Received' AND r.anonymized_at IS NULL AND r.sla_due_at IS NOT NULL
                                      AND r.sla_due_at<=? AND r.sla_notified_at IS NULL""", (now,)).fetchall()
        support_users = db.execute("SELECT id,email FROM users WHERE role='support' AND disabled_at IS NULL").fetchall()
        for row in overdue:
            request_ref = f"REQ-{row['id']:05d}"
            recipients = []
            if row["assigned_staff_id"]:
                staff = db.execute("SELECT id,email FROM users WHERE id=? AND role='support' AND disabled_at IS NULL",
                                   (row["assigned_staff_id"],)).fetchone()
                if staff:
                    recipients.append(staff)
            else:
                recipients.extend(support_users)
            message = f"{request_ref} is overdue for its first response in {row['department_name']}. Open the support queue."
            for staff in recipients:
                db.execute("INSERT OR IGNORE INTO staff_notifications (user_id,request_id,kind,message,created_at) VALUES (?,?,?,?,?)",
                           (staff["id"], row["id"], "sla_overdue", message, now))
                if gateways["email_configured"]:
                    mail_jobs.append((staff["email"], f"Overdue support request {request_ref}", message))
            db.execute("UPDATE requests SET sla_notified_at=? WHERE id=? AND sla_notified_at IS NULL", (now, row["id"]))
            append_audit(db, None, "sla_overdue_notified", row["id"],
                         new_value={"state": "overdue"}, metadata={"department": row["department_id"]})
        db.commit()
    for target, subject, body in mail_jobs:
        deliver("email", target, subject, body)


def run_daily_sla_summaries(database_path):
    if not gateway_status()["email_configured"]:
        return
    with connection(database_path) as db:
        opening, closing, zone, holidays = calendar(db)
        local_now = datetime.now(timezone.utc).astimezone(zone)
        day = local_now.date().isoformat()
        if local_now.weekday() >= 5 or day in holidays or local_now.time() < opening:
            return
        db.execute("BEGIN IMMEDIATE")
        rows = db.execute("""SELECT r.department_id,d.name department_name,
                                    GROUP_CONCAT('REQ-'||printf('%05d',r.id), ', ') refs,
                                    COUNT(*) total
                             FROM requests r JOIN departments d ON d.id=r.department_id
                             WHERE r.status='Received' AND r.anonymized_at IS NULL AND r.sla_due_at<=?
                             GROUP BY r.department_id,d.name""", (utc_now(),)).fetchall()
        jobs = []
        for row in rows:
            already = db.execute("SELECT 1 FROM sla_daily_summaries WHERE day=? AND department_id=?",
                                 (day, row["department_id"])).fetchone()
            if already:
                continue
            leads = db.execute("""SELECT email FROM on_call_contacts WHERE department_id=? AND enabled=1
                                  AND is_lead=1 AND email!=''""", (row["department_id"],)).fetchall()
            if not leads:
                continue
            db.execute("INSERT INTO sla_daily_summaries VALUES (?,?, 'sending',?)",
                       (day, row["department_id"], utc_now()))
            for lead in leads:
                body = (f"Department: {row['department_name']}\nOverdue open requests: {row['total']}\n"
                        f"References: {row['refs'] or 'None'}")
                jobs.append((day, row["department_id"], lead["email"],
                             f"Daily overdue summary: {row['department_name']}", body))
        db.commit()
    for day, department_id, email, subject, body in jobs:
        ok, _ = deliver("email", email, subject, body)
        with connection(database_path) as db:
            db.execute("UPDATE sla_daily_summaries SET status=? WHERE day=? AND department_id=?",
                       ("sent" if ok else "failed", day, department_id))


def run_retention(database_path):
    from app.privacy import anonymize_request
    with connection(database_path) as db:
        db.execute("BEGIN IMMEDIATE")
        raw = db.execute("SELECT value FROM settings WHERE key='retention_days'").fetchone()
        days = max(1, min(36500, int(raw[0] if raw else "365")))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="microseconds")
        rows = db.execute("SELECT id FROM requests WHERE anonymized_at IS NULL AND created_at<? ORDER BY id LIMIT 100",
                          (cutoff,)).fetchall()
        for row in rows:
            anonymize_request(db, row["id"], actor=None, reason="retention")
        db.commit()


def run_scheduled_jobs(database_path):
    for name, job in (("alert escalation", run_alert_escalation), ("SLA reminders", run_sla_reminders),
                      ("daily SLA summary", run_daily_sla_summaries), ("retention", run_retention)):
        try:
            job(database_path)
        except (sqlite3.Error, OSError, ValueError, TypeError):
            LOG.exception("Scheduled %s job failed", name)
