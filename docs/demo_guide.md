# Defence and user guide

## Prepare

Extract the project, start `start_windows.bat` or `python run.py --demo`, and open http://127.0.0.1:8000. Keep the terminal open. If you want a fresh demonstration, use a new database filename rather than deleting existing work: `python run.py --demo --database instance/defence.sqlite3`.

The exact demonstration examples below are intentionally predictable. Broader model validation is separate in the 40-example holdout. Notifications are in-app. The five named student accounts use `Student123!`; demo mode seeds one resolved Wi-Fi request and synthetic rating per account. Ratings are dated on the previous complete business day so default analytics includes them. For deterministic offline examples, use `--ai local`. For a real Gemini demonstration, complete the setup in `../API_START_RU.md` and verify the response first.

## Sprint 1, approximately four minutes

1. Sign in as `240103030@sdu.edu.kz` / `Student123!`.
2. Submit subject **Campus Wi-Fi** with this message:

   “My laptop cannot connect to campus wifi and the wireless network keeps dropping.”

3. Show that the destination is **IT Helpdesk**, status **Received**. Open Notifications: the receipt includes request ID, department, and estimated response time.
4. Refresh the page and show the same receipt without duplicates.
5. Submit subject **A confusing issue**:

   “I have a confusing situation and would like somebody to look into it.”

6. Show **Escalated** and the staff review queue message. Explain that the system does not guess when evidence is weak.
7. Show the preserved user-story workbook, Sprint 1 task CSV, report, and model/test evidence.

To display just the first increment, use `--sprint 1` with its own database and stop the default server first.

## Sprint 2, approximately six minutes

1. Sign out; sign in as `helpdesk@sdu.edu.kz` / `Support123!`.
2. Show the ambiguous request, original message, suggested department, confidence, and review deadline.
3. Select **Academic Advising** on its card and click **Route**. There is no intermediate edit screen.
4. Filter by department/status/priority, then remove filters.
5. Click **Start work** on the IT request. Click **Resolve request**, enter “Your wireless account has been restored. Please reconnect to campus Wi-Fi.” and save.
6. Sign in as the first student again. Show **Resolved**, last-updated time, resolution, and history. Status refreshes automatically when the list is active.
7. Sign in as `250103031@sdu.edu.kz` / `Student123!`. Show that the first student's requests are absent.
8. Sign in as `admin@sdu.edu.kz` / `Admin12345!`. Change the threshold to 0.70 and save it. The current admin page shows routing status and the confidence threshold; it has no correction table or model-retraining page.

## Explain the architecture

The browser talks to a JSON backend. The backend authenticates the session and checks roles. SQLite stores users, sessions, departments, requests, events, notifications, correction labels, and settings. The supervised classifier learns word/topic relationships from labeled examples. Routing and receipts are committed together. See `architecture.md` for diagrams.

## Demonstrate stories US6-US16

The project implements all 16 stories. The original Sprint 1-2 demo above remains useful for the core intake and support flow. For the complete workflow, use the same demo accounts and show:

1. Submit a normal English request and a Russian or Kazakh request. Explain that the local classifier recognizes common support vocabulary and preserves the original; Gemini adds an English translation when configured.
2. On **My requests**, search by request reference or a word from the subject/message. Combine a status and department filter, then choose **Clear filters**. The list refreshes without losing the filters.
3. Click **Open request & messages** on a request card. The request details dialog contains the **Messages** thread. A reply can be sent while the request is open.
4. Open **My profile** as the student and show the name, SDU email/ID, admission year, academic year, and estimated course. Explain that the course year is derived from the student ID, not verified against university enrollment records.
5. Submit a clearly urgent safety/health request. Show the urgent queue alert. Optional email escalation requires SMTP settings and department contacts in **Service operations**.
6. As support, open **Support queue** and choose **Details and messages** on a request. Exchange a message and change the request status. Attachments are added by the student from the same request details dialog and are limited to three files of 5 MB each.
7. Resolve a student request, return as the student, submit one rating, and reopen within 48 hours. The request returns to its prior department.
8. As admin, open **Analytics** and show the seeded five-student example: the IT Helpdesk row has five synthetic ratings (1–5) and an average of **3.0**. Then review request volume, response times, and agreement with saved staff labels. This agreement is an operational estimate, not a verified production accuracy score.
9. In **Service operations**, set response targets, business hours, time zone, holidays, and retention period. Show due-soon/overdue filters and deletion requests. In **Audit**, search and export the hash-chained event log.

The historical test results in `testing.md` describe an earlier baseline. Acceptance checks for the latest US8-US16 increment have not yet been run. The included model holdout is synthetic and does not establish accuracy on real university requests.

## User actions

- Create a student account using the registration form. No elevated role can be chosen.
- Submit an English, Russian, or Kazakh description with enough detail. The offline classifier recognizes common mapped topics; when a request remains unclear, it goes to staff review. Gemini can provide a staff-facing English translation when configured.
- On **My requests**, search by reference or text and filter by status and department. Click **Open request & messages** to view request history and the **Messages** thread. **Edit** and **Delete** are available before work starts.
- Staff chooses the correct route and updates progress; students cannot change operational status.
- Administrators tune the threshold on **Routing settings**. A higher value increases human review; existing requests are not automatically rewritten. AI-routing corrections and model retraining are not exposed in the current admin interface.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `python` is not recognized | Install Python 3.11+ with PATH enabled, or use `py -3` on Windows |
| Double-click launch closes / cannot find Python | Open a terminal in the project folder and run `py -3 run.py --demo` to read the message |
| Browser says connection refused | Keep the terminal running and use the port printed there |
| Port already occupied | Start with `--port 8001`; open http://127.0.0.1:8001 |
| Demo login fails | Use `--demo` and the exact role-specific password from the README |
| Urgent alert email was not delivered | Check the SMTP settings and email contact in **Service operations** |
| Request says refresh before saving | Another update changed its version; refresh and repeat the intended action |
| An unusual request is escalated | This is the safe fallback; sign in as support to select the route |
| Analytics is empty | Choose a range with request data; reporting excludes the current partial business day |

## What remains human work

Upload the extracted files to your actual repository, submit required files/links to Moodle, record real team names and meetings, and perform the defence. The package does not claim to have completed those external course actions.

## Gemini demonstration extension

Run the setup script locally, restart, and confirm the portal displays Gemini. A valid provider response changes the mode label to response verified and appears with its model/explanation in request detail. Test a fictional Wi-Fi issue; then show the staff workflow. Do not describe the local 40/40 evaluation as an Gemini benchmark. Real API availability depends on the configured account, quota and network.

## SDU registration demonstration

Open Create an account. Try a Gmail address: browser validation rejects it; direct API calls are also blocked. Enter a nine-digit ID at `sdu.edu.kz`: the preview shows admission year and course. For 2026-2027, a 24-prefix ID displays Year 3. After registration the same derived metadata appears in the student portal. The pre-seeded example ID is already registered, so use another ID for new-signup demonstrations. Helpdesk signs in with `helpdesk@sdu.edu.kz`; public signup cannot create that account. Explain that this checks the address format/domain and does not verify control of a real mailbox.
