# AI Student Request Routing and Support System <3

A campus support portal for student requests, staff routing, service-level tracking, and privacy-aware administration. The supplied workbook's 16 stories are implemented across student, support, and administrator workflows.
<img width="1870" height="1007" alt="image" src="https://github.com/user-attachments/assets/592fe08a-441c-4653-8a8a-0d5cf209d48a" />


## Requirements

- Python 3.11 or newer
- No `pip install` and no Node.js needed

## Run

1. Open a terminal in the project folder (the one containing `run.py`).
2. Start the server:

   ```bash
   # Windows
   py -3 run.py --demo

   # macOS / Linux
   python3 run.py --demo
   ```

   On Windows you can also double-click `start_windows.bat`.
3. Open http://127.0.0.1:8000 in your browser.
4. Stop the server with `Ctrl+C`.

If port 8000 is busy, run with `--port 8001` and open that port instead.

The `--demo` flag creates the demo accounts below. Without it there are no accounts to sign in with.

## Demo accounts

| Role | Email | Password |
| --- | --- | --- |
| Karakat Maxutova | 240103030@sdu.edu.kz | Student123! |
| Second student | 250103031@sdu.edu.kz | Student123! |
| Mira Khaiitboyeva | 240103173@sdu.edu.kz | Student123! |
| Korkem Baigozha | 240103103@sdu.edu.kz | Student123! |
| Dina Zhumatay | 240107023@sdu.edu.kz | Student123! |
| Asselya Imanmadinova | 240103026@sdu.edu.kz | Student123! |
| Support officer | helpdesk@sdu.edu.kz | Support123! |
| Administrator | admin@sdu.edu.kz | Admin12345! |

`--demo` also creates one resolved campus Wi-Fi request per named student and records sample ratings from 1 to 5. The default admin analytics view shows an IT Helpdesk average rating of **3.0** across those five synthetic ratings. The sample data is dated on the previous complete business day so it appears in the dashboard's default date range.

- **Student** submits and tracks requests.
- **Support** works the review queue and can change a request's department and status.
- **Administrator** changes the confidence threshold (0.50–0.99, default 0.65). Requests scored below it go to staff review.

New users can register with a 9-digit ID at `@sdu.edu.kz` (for example `240103030@sdu.edu.kz`). Registration always creates a student account.

## AI modes

| Setup | Behavior |
| --- | --- |
| No `.env` file (default) | Local Naive Bayes classifier, works offline, with English and a Russian/Kazakh routing vocabulary |
| `.env` with `AI_ROUTER=gemini` and a key | Gemini classifies requests and returns a separate English translation for staff |
| `python run.py --demo --ai local` | Forces local mode even if a key exists |

### Enable Gemini

1. Create a free API key at https://aistudio.google.com/apikey.
2. Run the setup script (the key is entered hidden):

   ```bash
   # Windows
   setup_gemini_windows.bat

   # macOS / Linux
   python3 scripts/configure_gemini.py
   ```

   Or create a `.env` file in the project root by hand:

   ```
   AI_ROUTER=gemini
   GEMINI_API_KEY=your_key_here
   GEMINI_MODEL=gemini-3.1-flash-lite
   GEMINI_TIMEOUT_SECONDS=15
   ```
3. Restart the server. The portal should show **Gemini · configured**.
4. Optional check: `python scripts/check_ai.py`

**Never commit `.env` or share your API key.** Use only fictional text with the free tier. If `.env` is hidden on macOS, press `Cmd + Shift + .` in Finder.

## Try it

Sign in as the student and submit, for example:

> I forgot my portal password and cannot login to my email account

It should be routed to IT. Very short or unclear requests, or any error from the AI provider, go to staff review. The request text is the only thing the AI reads; the subject line is not classified.

## Student and staff workflows

- **Student request search (US10)**: on **My requests**, search by reference, subject, message, or department and combine status and department filters. Search updates immediately, filters survive list refreshes, and **Clear filters** restores the full list.
- **Local model maintenance**: the retraining CLI and scheduler remain available to developers (`python scripts/retrain_model.py --status | --run | --due | --rollback VERSION`; use `--no-scheduler` to disable the scheduler). These controls are not exposed in the admin interface. Gemini is pretrained.
- **Resolution feedback and reopening**: students can rate a resolved request once and reopen it within 48 hours. A reopen returns it to the same department.
- **Messages (US11)**: students open **My requests** → **Open request & messages** → **Messages**. Support staff open **Support queue** → **Details and messages**. Threads are read-only while the request is resolved and reopen with the request.
- **Attachments**: up to three PNG, JPG, or PDF files per request, at most 5 MB each. Files are stored in SQLite and downloaded only by the request owner or support staff.
- **Admin analytics**: request volume, categories, labeled routing accuracy, first-response times, and average feedback by date range. The report ends at the previous full business day.
- **SLA calendar**: administrators set each department's response target, business hours, time zone, and school holidays. Staff see requests due within one hour and overdue reminders.
- **Student profile**: students have a dedicated profile page with their account name, SDU email and ID, admission year, current academic year, and estimated course.
- **Urgent alerts**: the support queue receives live alerts. Optional SMTP email can notify department contacts after two minutes, then escalate after five more minutes.
- **Audit and privacy**: administrators can search and export an append-only hash-chained audit log, set a retention period, and approve student data-deletion requests. Scheduled anonymization clears request text, messages, translations, internal routing labels, feedback comments, and attachments while retaining request metrics.

Optional urgent-alert email uses SMTP. Set the SMTP variables from `.env.example` in the local `.env` file and restart the server. Add email contacts in **Service operations**. The interface shows whether SMTP is configured; credentials are never displayed. No external contact is notified unless an administrator adds the contact and SMTP is configured.

For multilingual operation, the offline classifier uses a small term mapping for common Russian and Kazakh support topics. Gemini provides a separate English translation when configured. In offline mode, the original non-English request remains intact and staff see that a translation is unavailable.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Project structure

| Folder | Contents |
| --- | --- |
| `app/` | Backend API, routing logic, database, AI classifiers |
| `static/` | Web interface |
| `data/` | Training and evaluation data for the local model |
| `tests/` | Automated tests |
| `scripts/` | Helper scripts (Gemini setup, checks, evaluation) |
| `docs/` | Project documentation |

This is a classroom prototype that runs on Python's development server and a local SQLite database. It includes authorization and privacy controls for the demo, but still needs an institutional security review, real department contacts, a school-approved retention period, and representative multilingual validation before any real student data is used.
