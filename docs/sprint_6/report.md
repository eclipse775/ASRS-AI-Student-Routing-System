# Sprint 6 report

**Project:** AI Student Request Routing and Support System  
**Increment:** Business-hours response targets with overdue reminders, and private request attachments  
**Duration:** Two weeks (15.11.2026 to the sprint deadline 29.11.2026), as required by the lab sheet  
**Source scope:** US13 and US14, 10 total source effort points  
**Readiness:** Implemented increment; backend suite and browser check run 16.11.2026, see Acceptance and testing  
**Human acceptance:** Not recorded; actual team/teacher acceptance must be recorded after the defence

## Sprint goal

Make sure no request waits longer than its department's agreed response time: compute deadlines in business hours, show which requests are due soon or overdue, and remind staff once. Let a student attach a screenshot or document to a request so the department can see the problem without asking again, while keeping every file private to the student and the support staff.

## Planning and selected backlog

| Story | Source effort | Owner role | Dependency | Completion evidence |
| --- | --- | --- | --- | --- |
| US13. SLA tracking and overdue reminders | 6 | Backend Developer and Frontend Developer | US4 staff dashboard, US5 status tracking, department response targets | 9 backend tests; queue badges, filter and reminder panel in the browser check |
| US14. Request attachments | 4 | Full-stack Developer | US1 request submission, private file storage | 8 backend tests; upload, listing and identical download in the browser check |

The team's deadline for Sprint 6 is 29.11.2026, recorded in the product backlog and the revised workbook for US13 and US14. It is a planning date, not evidence of completed course work. The task breakdown is in `sprint_6/backlog.csv`.

## Increment delivered

**US13 - Response targets and reminders**

- Each routed request gets a start time and a due time. The due time is the start plus the department's response target in business hours (defaults: IT Helpdesk 8, Financial Aid 24, Academic Advising 24, Health Services 4, Campus Security 1). Business hours default to 09:00-17:00 in Asia/Almaty and skip weekends and the school holidays entered by the administrator.
- A request in the Received state is on track, due soon (one hour or less left) or overdue. The staff queue shows an "Overdue" or "Due in N min" badge, has a Response target filter (All, Due soon, Overdue), and lists overdue requests first.
- A scheduled job (every 15 seconds while the scheduler runs) creates one staff reminder when a request becomes overdue: for the assigned officer, or for all support officers when nobody is assigned. A marker on the request prevents repeats; it is cleared when the deadline is recalculated, so a new overdue cycle can remind again. The support queue shows a "Staff reminders" panel with Open and Mark read, and an unread count in the navigation.
- Starting work on a request stops reminders for it. Each reminder is written to the audit log.
- Optional extras: when SMTP is configured, reminders are also emailed, and a once-a-day overdue summary goes to each department lead on business days. Both stay off without SMTP and contacts.
- Administrators edit the business hours, time zone, department targets (1 to 720 hours) and holidays in Service operations, Response targets. Saving recalculates the deadlines of open requests and is written to the audit log.

**US14 - Attachments**

- A student can attach up to 3 files to a request, 5 MB each, either while submitting or later from the request details dialog. Accepted types are PNG, JPG and PDF.
- The server checks the extension, the declared type and the file signature (PNG header, JPEG header, PDF header with an end marker). A renamed program or a mismatched file is refused. Paths in file names are stripped.
- Files are stored with a SHA-256 checksum and are never served from a public folder. Only the owning student and support staff can download them (another student gets 404, administrators 403, signed-out visitors 401). Downloads are sent as attachments with `nosniff`, so the browser does not open or run them.
- New files are refused once the request is Resolved or anonymized. Each upload is written to the audit log with the file count and total size, not the file content.
- The request dialog lists the files with a Download button for both the student and the support officer.

## Acceptance and testing

Executed on 16.11.2026 with Python 3.12 (`python3 -m unittest discover -s tests`, local mode):

| Check | Result | Boundary |
| --- | --- | --- |
| US13 SLA tests (`test_sprint6_7`, SlaTests) | 9 passed | Weekend and holiday skipping, state boundaries, queue filters and order, one reminder per cycle, no reminder after work starts, admin recalculation, daily summary off without email |
| US14 attachment tests (`test_sprint6_7`, AttachmentTests) | 8 passed | Round trip, owner and role checks, type and signature checks, size and count limits, file-name paths, resolved request, audit entry, attachment count |
| Full backend suite | 206 run, 206 passed | Includes the 33 new Sprint 6-7 tests and 10 feedback and analytics tests |
| Sprint 6-7 browser check (`scripts/sprint6_7_ui_check.py`) | 16 of 16 passed | Chromium, throwaway demo database, local classifier; 8 checks cover this sprint |
| Deliberate-defect check | 4 of 4 caught | Attachment limit, audit chain check, attachment removal and reminder marker were broken on purpose; the tests failed, then the code was restored |

Before this sprint the project had no automated tests for US13 to US16; the 33 tests were written during Sprint 6 and 7. The browser check moves a deadline in the demo database and runs the reminder job directly, so it does not wait for real elapsed time. The daily summary email and the email reminders were not run, because no SMTP server is configured.

## Sprint review / demo

1. Sign in as a student and submit a Wi-Fi request with a PNG screenshot attached. Open the request and show the Attachments list with its Download button.
2. Try a fourth file, and a file renamed to .png that is not an image, to show the refusals. Add a second file from "Add an attachment".
3. Sign in as support, open the same request and download the file. Sign in as a second student and show that the file and request are not reachable.
4. As administrator open Service operations, Response targets. Show the business hours, department targets and holidays; change a target and save.
5. Move the deadline of a request into the past in the demo database. Within 15 seconds the support queue shows the Staff reminders panel and an Overdue badge. Use the Response target filter.
6. Show a request marked "Due in N min", press Start work, and show that no reminder follows.
7. Show the test results and the browser check result.

This is a prepared review sequence. It is not evidence that a Product Owner attended or approved a meeting.

## Technical retrospective

What worked: review deadlines and department deadlines share one business-time function, so weekends, holidays and the time zone are handled in one place. A notified marker per overdue cycle keeps reminders from repeating. File checks happen on the server (extension, declared type and signature), and ownership is checked before any file bytes are returned. The reminder job and the checks are small enough to test directly.

Challenges: no tests existed for these stories, so most of the sprint's quality work was writing them. The tests set the time zone to UTC, because the real calendar depends on the time zone data of the machine. Email reminders and the daily summary need SMTP and department lead contacts, which were not available, so only the "off without email" boundary is tested. Attachments are stored in the database and are not scanned for malware. The holiday calendar is entered by hand.

Action items: agree with the Product Owner the due-soon threshold (now one hour) and who counts as the owner of an unassigned reminder; configure SMTP and a lead contact for a recorded email reminder run; decide whether files need a malware scan; record the actual review, retrospective and acceptance outcomes.

## Current boundary

US15 and US16 (audit log, retention and deletion) are covered in Sprint 7. Reminders are in-app unless SMTP is configured. Only the first response is tracked, not the time to resolve. Attachments are limited to PNG, JPG and PDF, three per request, 5 MB each, and only students add them. No malware scanning, preview of files in the browser, or institutional service-level agreement is claimed.

## Evidence

Evidence screenshots

Captured on 16.11.2026 from a local run with synthetic demo data (local classifier, not Gemini) by `scripts/sprint6_7_ui_check.py`. The result is in `evidence/sprint6_7_ui_check.json`; the images are in `evidence/sprint6/`.

![Student request dialog with the attached screenshot and its Download button (US14).](../evidence/sprint6/01_student_attachment.png)

![Support queue with the Staff reminders panel, an Overdue badge and a "Due in … min" badge (US13).](../evidence/sprint6/02_support_queue_overdue.png)

![Response target filter set to Overdue: only the overdue request is listed (US13).](../evidence/sprint6/03_support_overdue_filter.png)

![Support officer's request details with the attachment and its Download button (US14).](../evidence/sprint6/04_support_attachment.png)

![Administrator's business calendar and department response targets (US13).](../evidence/sprint6/05_admin_response_targets.png)
