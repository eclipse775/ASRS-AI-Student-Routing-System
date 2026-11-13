# Requirements and acceptance criteria

## Source hierarchy

The revised 16-story workbook defines current feature scope and acceptance behavior. It replaces the earlier US12 urgent-alert delivery story with a student profile panel. The original 16-story workbook and the archive's 10-story workbook are retained unchanged for provenance; the revised workbook is also in `source/`. The project-size PDF defines system-level expectations. Practices 1-4 define Scrum artifacts and submissions. The lab PDF specifies seven two-week labs/sprints and late-defence deductions. The linked grading workbook was also read; it contains progress/defence records and reinforces reports, user stories with QA, a progress board, and rotating Scrum Master responsibilities. Other students' personal records are not copied into this repository.

The original 16-story and 10-story workbooks are preserved unchanged in `docs/source/`. The revised 16-story workbook is the current scope source; US10 is student request search and filtering, while US12 is the student profile panel. Source iteration and deadline values remain intact; the workbook records the revised US10 estimate, priority, prerequisites, and owner. Course sprint assignments follow the seven-sprint adaptation in `roadmap.md`; source deadlines are planning inputs, not records of completed course work.

## Functional requirements

| ID | Requirement | Sprint |
| --- | --- | --- |
| FR01 | SDU student registration (nine-digit ID at sdu.edu.kz), login/logout, helpdesk/admin authentication | 1 foundation |
| FR02 | Students create/read/edit/delete their own requests before staff starts work | 1 foundation |
| FR03 / US1 | Classify and route to a configured department queue; the project has IT, Finance, Academic Advising, Health Services, and Campus Security, plus staff review for unclear requests | 1 |
| FR04 / US2 | Send immediate in-app confirmation and retain notification history | 1 |
| FR05 / US3 | Escalate uncertain routes, configure the threshold, record staff decisions | 2 |
| FR06 / US4 | Show oldest-first support queue and route/reassign using filters | 2 |
| FR07 / US5 | Persist status, timestamp, resolution, and history; update student portal | 2 |
| FR08 | Mark notification read, enforce ownership, and avoid duplicate routing-event notices | 1 |
| FR09 | Support staff resolve only routed requests and can reopen a resolution | 2 |
| FR10 | Derive admission year and estimated course from student ID and current academic year | 1 foundation |
| FR11 / US6 | Detect urgent requests, bypass uncertain routing, and alert the responsible team | 3 |
| FR12 / US7 | Detect English/Russian/Kazakh and preserve original text with optional staff translation | 4 |
| FR13 / US8 | Collect one resolution rating and allow student reopening within 48 hours | 5 |
| FR14 / US9 | Show date-filtered request, label-agreement, response-time, and feedback metrics | 5 |
| FR15 / US10 | Search owned requests by reference or text and combine status and department filters | 6 |
| FR16 / US11 | Provide an owner/support-only message thread in request details; close sending while resolved | 6 |
| FR17 / US12 | Give authenticated students a dedicated panel showing account and derived academic profile details | 6 |
| FR18 / US13 | Apply department response targets using business hours, weekdays, and holidays | 7 |
| FR19 / US14 | Accept private PNG/JPG/PDF attachments with size and ownership checks | 7 |
| FR20 / US15 | Keep a hash-chained append-only routing and request audit log with CSV export | 7 |
| FR21 / US16 | Anonymize old request data and support administrator-approved deletion | 7 |

## Given/When/Then acceptance matrix

| ID | Given | When | Then | Evidence |
| --- | --- | --- | --- | --- |
| AC1.1 | Authenticated student, configured departments | Submit a high-confidence request | Correct department receives the request | `test_US1_high_confidence_routes_to_correct_department` |
| AC1.2 | Ten distinct held-out requests | Submit and route each | At least 9/10 reach their correct department | `test_US1_at_least_90_percent_of_ten_requests_routed_correctly` |
| AC1.3 | A request has little known topic evidence | Submit it | Staff review is used instead of guessing | `test_US3_unknown_request_escalates_without_assigning_department` |
| AC2.1 | Routing completed | Retrieve notification history | ID, department, response estimate exist within 60s | `test_US2_notification_has_request_department_and_response_estimate` |
| AC2.2 | Routing receipt already exists | Refresh/reopen the portal | No duplicate notice for that event | `test_US2_refresh_does_not_duplicate_notification` |
| AC3.1 | Confidence is below configured threshold | Intake runs | Status Escalated, no assigned department, deadline, student notice | `test_US3_unknown_request_escalates_without_assigning_department` |
| AC3.2 | Staff reviews an escalation | Select a department and submit | Correct route and retraining correction record saved | `test_US3_staff_decision_logged_for_future_retraining` |
| AC3.3 | Administrator is authenticated | Save a valid threshold | Setting persists with no code edits | `test_US3_admin_threshold_changes_without_code_changes` |
| AC3.4 | Escalation awaiting staff | Four business hours pass | Deadline is available and an overdue warning appears | `test_US3_overdue_review_is_visible` |
| AC4.1 | Authenticated support officer | Open the queue | Original message, suggestion, confidence, oldest-first order | `test_US4_queue_has_original_text_suggestion_confidence_oldest_first` |
| AC4.2 | Queue entry is visible | Choose route and press Route | Manual routing takes two actions from the entry | Browser demo and UI action structure |
| AC4.3 | Student or administrator account | Request staff queue | Access denied | `test_US4_student_and_admin_cannot_open_support_queue` |
| AC4.4 | Already-routed request | Reassign department | New department queue and history reflect the change | `test_US4_reassignment_changes_queue_and_records_history` |
| AC4.5 | Up to 500 open requests | Fetch/load support queue | Queue meets target of less than 3s in measured environment | Performance evidence and queue test |
| AC5.1 | Student has submitted requests | Open My Requests | Current status and last-updated timestamp appear | `test_US5_status_update_is_immediate_and_has_timestamp` |
| AC5.2 | Support officer updates status | Student portal refreshes | Updated status is visible within 60s | Immediate API read plus 15s UI polling |
| AC5.3 | Different student owns a request | Attempt detail/history/edit access | Owner restriction denies access | `test_US5_student_only_sees_own_requests_and_history` |
| AC10.1 | Student has several requests | Search by reference, subject, or message phrase | Matching owned requests remain; search ignores letter case | Browser workflow; automated acceptance not recorded |
| AC10.2 | Student has requests in different states/departments | Apply status and department, then clear filters | Both filters combine; clear restores the full owned list | Browser workflow; automated acceptance not recorded |
| AC10.3 | Student is viewing a filtered request list | The list refreshes | Search and selected filters remain active | Browser workflow; automated acceptance not recorded |
| AC11.1 | Student or support opens a request they may access | Open request details | The Messages thread appears in the dialog and allows authorized replies | `tests/test_messaging.py`; UI acceptance not recorded in this delivery |

The US1-US5 tests above are in `tests/test_acceptance.py`. External AI provider behavior is tested in `tests/test_gemini.py`, including failure review, key privacy, output validation, delayed-session invalidation and concurrent versions. Real-provider accuracy/latency is pending a configured API account.

Stories US8-US16 are implemented in the API and browser interface. Feedback is a single rating per request; reopening is limited to 48 hours. Analytics uses labeled-example agreement and only includes data through the previous full business day. The student profile page shows server-derived account and academic details. Optional urgent email escalation requires configured SMTP and contacts. SLA calculations use the administrator-managed time zone, 09:00-17:00 defaults, weekdays, and the holiday table. Attachments use request-owner/support authorization and fixed MIME/size limits. Audit records are append-only in the application and verified through a SHA-256 hash chain. Retention defaults to 365 days until the administrator sets the institution's approved period.

| Story | Acceptance behavior implemented |
| --- | --- |
| US8 | One 1-5 rating after resolution; student can reopen within 48 hours to the same department |
| US9 | Admin-only date filters; department/category volume, labeled-example agreement, first response time, and feedback average |
| US10 | Student searches own requests by reference/subject/message, combines status and department filters, and clears filters |
| US11 | Student and support exchange request messages from the request details dialog; sending closes while resolved |
| US12 | Student can view account name, SDU email and ID, admission year, current academic year, and estimated course from the profile page |
| US13 | Business-time deadline, due-soon/overdue filters, one staff reminder per overdue cycle, daily lead summary |
| US14 | Up to 3 files, 5 MB each, PNG/JPG/PDF with file signature checks; private download endpoint |
| US15 | Search by request reference, user ID, action, and date; CSV export; update/delete triggers and hash verification |
| US16 | Scheduled retention anonymization; student deletion request and admin approval; free-text, identifiers, and attachments removed |

SDU-specific acceptance is in `tests/test_university.py`: only nine ASCII digits at the exact student domain can register; `240103030@sdu.edu.kz` is Year 3 in 2026-2027; January preserves the academic year; future cohorts and forged roles/course values are rejected; helpdesk cannot sign up publicly but can sign in when provisioned. Browser checks exercise the profile page and registration preview. See `SDU_REGISTRATION.md` for the academic-calendar assumption, demo migration and mailbox-ownership boundary.

Browser evidence is marked by its actual execution state in `docs/evidence/verification.json`; it is not assumed to have passed.

## Non-functional requirements

| ID | Expectation | Implementation/check |
| --- | --- | --- |
| NFR01 | Privacy and authorization | Owner-filtered student queries, support-only queue, admin summaries without message text |
| NFR02 | Authentication security | Salted scrypt, HttpOnly/SameSite cookies, CSRF header, session rotation, login attempt limit |
| NFR03 | Input validation | Bounds on messages, titles, emails, thresholds; enum checks; parameterized SQL |
| NFR04 | Reliability | Atomic request/event/notification writes; version conflicts; foreign keys; safe errors |
| NFR05 | Usability | Consistent responsive UI, visible routing results, history, filters, loading/empty/error states |
| NFR06 | Maintainability | Separate modules, datasets, schema, test suite, documented API and constraints |
| NFR07 | Reasonable performance | Routing <30s, notice <60s, status <60s, queue target <3s for 500 |

No institutional privacy policy, approved retention period, authorized real support data, live SMTP server, or real on-call roster was supplied. Defaults are for the classroom demo and must be reviewed by the institution. Gemini translation and external email alert delivery are optional configuration paths. No legal or production-compliance certification is claimed.

## Definition of Ready

A story has a user/benefit, an estimate, source priority flag, dependencies, acceptance scenarios, a responsible role, and a sprint assignment. External policy/operational assumptions are visible. A story fits an independently demonstrable increment.

## Definition of Done

Implementation exists, acceptance checks pass, data persists, role/owner restrictions hold, relevant tests are recorded, documentation matches behavior, and the increment runs from a fresh extraction. Product Owner/teacher acceptance and actual team ceremonies are separate human events and must be recorded when they occur.
