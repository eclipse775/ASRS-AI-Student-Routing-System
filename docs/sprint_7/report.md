# Sprint 7 report

**Project:** AI Student Request Routing and Support System  
**Increment:** Tamper-evident audit log with search and CSV export, and personal-data retention and deletion  
**Duration:** 29.11.2026 to the sprint deadline 06.12.2026 (one week)  
**Source scope:** US15 and US16, 10 total source effort points  
**Readiness:** Implemented increment; backend suite and browser check run 16.11.2026, see Acceptance and testing  
**Human acceptance:** Not recorded; actual team/teacher acceptance must be recorded after the defence

## Sprint goal

Let the school administrator explain who did what and when on any request, with a log that shows if it was altered. Keep personal data no longer than necessary: anonymize old requests automatically and let a student ask for their data to be deleted, with the administrator's approval.

## Planning and selected backlog

| Story | Source effort | Owner role | Dependency | Completion evidence |
| --- | --- | --- | --- | --- |
| US15. Audit log of routing and status changes | 4 | Backend Developer and QA Tester | US5 status history, US3-US4 routing, US6 alerts | 9 backend tests; audit page, hash-chain check and CSV export in the browser check |
| US16. Personal data retention and deletion | 6 | Backend Developer and QA Tester | US15 audit log, retention period from the data-protection policy | 7 backend tests; deletion request, approval and anonymization in the browser check |

The team's deadline for Sprint 7 is 06.12.2026, recorded in the product backlog and the revised workbook for US15 and US16. It is a planning date, not evidence of completed course work. The task breakdown is in `sprint_7/backlog.csv`.

## Increment delivered

**US15 - Audit log**

- Every routing decision, status change, urgent alert, rating, reopening, attachment upload, staff message, calendar or retention change, anonymization and deletion step is appended to an audit log (21 action types). Each entry has the request reference, the actor and role, old and new values, a time, and a SHA-256 hash that includes the previous entry's hash.
- The database refuses UPDATE and DELETE on the log. Editing entries by bypassing that rule breaks the chain, and the audit page shows "Hash chain verified" or a warning every time it is opened.
- Request text and message bodies are never written to the log, only references, states and counts, so the log itself holds no free-text personal data.
- The administrator-only Audit log page searches by request reference, user ID, action and date range, pages through the results, and exports the filtered entries as CSV (up to 10,000 rows). Cells that begin with =, +, - or @ are prefixed so spreadsheets do not run them as formulas.
- Actions taken by the system itself (for example an overdue reminder) are labelled "System (automatic)". The first browser run showed them as "Former or removed user"; this was corrected and a test was added.

**US16 - Retention and deletion**

- The administrator sets the retention period in Service operations, Data and deletion (30 to 36,500 days; the default of 365 days is a classroom value). A scheduled job anonymizes requests older than the period, up to 100 per run.
- Anonymizing a request replaces the owner with a placeholder account, sets the title to "Anonymized request", and clears the message, resolution, thread messages, correction snapshots, training text and feedback comments. Attachments and notifications are deleted, urgent alert text is replaced, and classification details are redacted. Department, category, status, dates and ratings stay, so statistics still work. Each anonymization is audited.
- A student can ask for deletion from "Your data" on the home page. Only one request can be open at a time, and the page shows its status.
- The administrator sees pending requests with the student's name and request count and chooses "Approve and erase" or "Deny". Approval anonymizes all the student's requests, ends their sessions, removes notifications, renames the account to "Former student" with a placeholder address, disables it and sets a random password. Denial changes nothing. Both are audited, and the audit trail keeps pseudonymous IDs and request references.

## Acceptance and testing

Executed on 16.11.2026 with Python 3.12 (`python3 -m unittest discover -s tests`, local mode):

| Check | Result | Boundary |
| --- | --- | --- |
| US15 audit tests (`test_sprint6_7`, AuditTests) | 9 passed | Hash chain, no request text, database refuses edits, tampering detected, search filters and bad input, system label, pagination, CSV and formula protection, administrator only |
| US16 privacy tests (`test_sprint6_7`, PrivacyTests) | 7 passed | One open request, approval removes data everywhere, denial keeps data, roles, retention of old requests only, retention bounds, anonymized request refuses files |
| Full backend suite | 206 run, 206 passed | Includes the 33 new Sprint 6-7 tests and 10 feedback and analytics tests |
| Sprint 6-7 browser check (`scripts/sprint6_7_ui_check.py`) | 16 of 16 passed | Chromium, throwaway demo database, local classifier; 8 checks cover this sprint |
| Deliberate-defect check | 4 of 4 caught | The audit chain check and the attachment removal on anonymization were among the defects broken on purpose and caught |

The tamper test removes the database rule and edits one entry; the page then reports a broken chain. It does not cover someone who can write to the database and recompute every hash after the edit. The retention job is tested with a request dated 400 days back, not by waiting for real time to pass.

## Sprint review / demo

1. Sign in as administrator and open Audit log. Show "Hash chain verified", the system-labelled entries, and search by request reference, action and date range. Export the CSV and open it in a spreadsheet.
2. Show the automated tests that the database refuses edits to the log and that an edit with the rule removed is detected.
3. Open Service operations, Data and deletion. Show the retention period and save a new value.
4. Sign in as a student, open "Your data" and press "Request data deletion". Show the pending status.
5. As administrator open Data and deletion, show the pending request and press "Approve and erase".
6. Show that the student's requests now read "Anonymized request" and their files are gone, and that the student cannot sign in again.
7. Open the Audit log again: the anonymization and deletion events are there and the chain is still verified.
8. Show the automated test that anonymizes only requests older than the retention period.

This is a prepared review sequence. It is not evidence that a Product Owner attended or approved a meeting.

## Technical retrospective

What worked: database triggers plus a hash chain give two layers, and the page verifies the chain each time it is opened. Keeping request text out of the log by design means the log does not need to be erased with the data. Anonymizing in one function lets retention and approved deletion share the same code, so both are tested together. A test showed what the log looked like for automatic actions, and the label was corrected.

Challenges: "tamper-evident" is not "tamper-proof": someone with write access who recomputes the whole chain would not be caught, and nothing stores the latest hash outside the database. No institutional retention period was supplied, so 365 days is a placeholder. Deletion is irreversible and manual, and copies of the database file or backups are not covered. The audit trail keeps pseudonymous user IDs and request references after deletion, which the policy must accept. Sprint 7 covers one week, so US15 and US16 were tested rather than run in a recorded live session.

Action items: obtain the official retention period and data-protection wording; decide whether to store the newest log hash somewhere outside the database; agree who may approve deletions and within what time; decide how backups are handled; record the actual review, retrospective and acceptance outcomes.

## Current boundary

This is the last planned sprint. Search is by exact reference, numeric user ID, action and date, not free text. Anonymization removes personal and free-text data but keeps counts, categories, departments, dates and ratings. No legal or production-compliance certification, approved retention policy or external log anchoring is claimed.

## Evidence

Evidence screenshots

Captured on 16.11.2026 from a local run with synthetic demo data (local classifier, not Gemini) by `scripts/sprint6_7_ui_check.py`. The result is in `evidence/sprint6_7_ui_check.json`; the images are in `evidence/sprint7/`.

![Audit log page with "Hash chain verified", search filters, CSV export and a system-labelled entry (US15).](../evidence/sprint7/01_admin_audit_log.png)

![Student "Your data" panel showing the deletion request as pending (US16).](../evidence/sprint7/02_student_deletion_pending.png)

![Administrator's pending deletion request with Approve and erase, and the retention period (US16).](../evidence/sprint7/03_admin_deletion_pending.png)

![After approval: the deletion queue is empty and the confirmation is shown (US16).](../evidence/sprint7/04_admin_deletion_done.png)

![Audit log after the deletion: anonymization and deletion events, chain still verified (US15, US16).](../evidence/sprint7/05_audit_after_deletion.png)
