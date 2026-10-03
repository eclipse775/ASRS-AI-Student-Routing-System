# Requirements and acceptance criteria

## Source hierarchy

The supplied user-story workbook defines feature scope and acceptance behavior. The project-size PDF defines system-level expectations. Practices 1-4 define Scrum artifacts and submissions. The lab PDF specifies seven two-week labs/sprints and late-defence deductions. The linked grading workbook was also read; it contains progress/defence records and reinforces reports, user stories with QA, a progress board, and rotating Scrum Master responsibilities. Other students' personal records are not copied into this repository.

The original workbook is preserved unchanged in `docs/source/`. US1-US2 retain source iteration 1; US3-US5 retain source iteration 2. The workbook's original future deadlines and iteration 3-4 assignments are planning inputs, not records of completed course work. See `roadmap.md` for the seven-sprint adaptation.

## Functional requirements

| ID | Requirement | Sprint |
| --- | --- | --- |
| FR01 | SDU student registration (nine-digit ID at sdu.edu.kz), login/logout, helpdesk/admin authentication | 1 foundation |
| FR02 | Students create/read/edit/delete their own requests before staff starts work | 1 foundation |
| FR03 / US1 | Classify and route to one of four configured department queues | 1 |
| FR04 / US2 | Send immediate in-app confirmation and retain notification history | 1 |
| FR05 / US3 | Escalate uncertain routes, configure the threshold, record staff decisions | 2 |
| FR06 / US4 | Show oldest-first support queue and route/reassign using filters | 2 |
| FR07 / US5 | Persist status, timestamp, resolution, and history; update student portal | 2 |
| FR08 | Mark notification read, enforce ownership, and avoid duplicate routing-event notices | 1 |
| FR09 | Support staff resolve only routed requests and can reopen a resolution | 2 |
| FR10 | Derive admission year and course from student ID and current academic year; show profile | 1 foundation, project-owner extension |

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

The US1-US5 tests above are in `tests/test_acceptance.py`. External AI provider behavior is tested in `tests/test_gemini.py`, including failure review, key privacy, output validation, delayed-session invalidation and concurrent versions. Real-provider accuracy/latency is pending a configured API account.

SDU-specific acceptance is in `tests/test_university.py`: only nine ASCII digits at the exact student domain can register; `240103030@sdu.edu.kz` is Year 3 in 2026-2027; January preserves the academic year; future cohorts and forged roles/course values are rejected; helpdesk cannot sign up publicly but can sign in when provisioned. Browser checks exercise these rules and their visible profile/preview. See `SDU_REGISTRATION.md` for the academic-calendar assumption, demo migration and mailbox-ownership boundary. These owner-supplied requirements extend the original authentication foundation without altering the source workbook.

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

No institutional privacy policy or authorized real support data was supplied. This increment implements privacy controls; it does not certify legal/policy compliance. Periodic review/retraining is planned with US10. In-app delivery fulfills the source's in-app and/or email criterion; email/SMS are not implemented.

## Definition of Ready

A story has a user/benefit, an estimate, source priority flag, dependencies, acceptance scenarios, a responsible role, and a sprint assignment. External policy/operational assumptions are visible. A story fits an independently demonstrable increment.

## Definition of Done

Implementation exists, acceptance checks pass, data persists, role/owner restrictions hold, relevant tests are recorded, documentation matches behavior, and the increment runs from a fresh extraction. Product Owner/teacher acceptance and actual team ceremonies are separate human events and must be recorded when they occur.
