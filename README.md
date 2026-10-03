# AI Student Request Routing and Support System

**INF 451 - Project Management IS | Sprint 1 and Sprint 2**

A working campus support portal with **Gemini API routing** and a local offline mode. Students send a request, the configured AI model suggests a department, and uncertain requests enter a human review queue. Students receive in-app confirmations and follow their request through resolution.

This package implements **US1-US5** from the supplied workbook. Sprint 1 contains US1-US2 (8 source effort points). Sprint 2 adds US3-US5 (15 source effort points). Authentication, database setup, validation, and security are enabling work. US6-US10 remain in the documented roadmap.

## Connect Gemini (Windows)

1. Create your own API key at [Google AI Studio API keys](https://aistudio.google.com/apikey). The free tier needs no card; check its current limits in AI Studio.
2. Extract this updated ZIP and install Python 3.11 or newer if necessary.
3. Double-click **`setup_gemini_windows.bat`**. Paste the key when asked; the input is hidden. Press Enter to keep `gemini-3.1-flash-lite` as the model.
4. Double-click **`start_windows.bat`** and open **http://127.0.0.1:8000**.
5. The portal shows **Gemini · configured**. Submit a fictional campus Wi-Fi request; after a valid API response it shows **response verified**.

The setup creates a server-only `.env` file. **Never upload `.env` to GitHub, put the key in frontend JavaScript, or send your key in a chat.** Upload `.env.example` instead. If uploading through GitHub's browser, explicitly leave `.env` out: the browser does not apply `.gitignore` for you.

The API uses your Google AI Studio account and its free-tier quota. On the free tier Google may use submitted prompts to improve its products, so send only fictional or non-sensitive text. The project has no bundled key. External routing requires internet access. The integration is tested with mocked HTTP responses; a real Gemini call has not been claimed because no key was supplied.

For a live check, run `python scripts/check_ai.py` from the project folder. It sends one fictional Wi-Fi issue and prints the result without revealing the key. [Russian step-by-step instructions](API_START_RU.md) include troubleshooting and a manual `.env` alternative.

On macOS/Linux, run `python3 scripts/configure_gemini.py`, then `python3 run.py --demo`.

## Start on Windows

1. Extract the ZIP. Open the `AI_Student_Routing_Sprints_1_2` folder.
2. Install Python 3.11 or newer if needed. Choose **Add Python to PATH** in the installer.
3. Double-click **`start_windows.bat`**. Keep the terminal open.
4. Open **http://127.0.0.1:8000** in your browser.

You can also open a terminal in the project folder and run:

```powershell
py -3 run.py --demo
```

On macOS/Linux:

```bash
python3 run.py --demo
```

**No pip installation or Node.js is needed to run the app.** Without AI configuration it uses the local classifier; that mode works offline and needs no API key. With `.env` set to Gemini, it calls the external API. The first run creates `instance/routing.sqlite3` automatically. Restarting preserves your accounts and requests. Press Ctrl+C in the terminal to stop the server. If port 8000 is occupied, run `python run.py --demo --port 8001` and open port 8001 instead.

## Demonstration accounts

These accounts are created only with the explicit `--demo` option. They contain synthetic data.

| Role | Email | Password |
| --- | --- | --- |
| Student | 240103030@sdu.edu.kz | Student123! |
| Second student, for privacy checks | 250103031@sdu.edu.kz | Student123! |
| Support officer | helpdesk@sdu.edu.kz | Support123! |
| Administrator | admin@sdu.edu.kz | Admin12345! |

New registrations always create a **student** account. Only the `support` role can use the staff queue or change request routes and statuses. Administrators adjust routing settings and see correction summaries; they cannot browse student request content.

## SDU student registration

Only addresses of the form **`240103030@sdu.edu.kz`** can register: exactly nine ASCII digits and the exact `sdu.edu.kz` domain. Gmail, other universities, subdomains, aliases and future admission cohorts are rejected on the server, even if browser validation is bypassed. Public registration always creates a student account; helpdesk/admin accounts are provisioned separately.

The first two digits encode admission year. For `240103030@sdu.edu.kz`, this is **2024**, giving **Year 3 in 2026-2027**. Admission year/course appear in the registration preview and student portal. The academic year rolls over on 1 September at UTC+5, not 1 January. This is a documented calendar assumption and a derived course, not a university enrollment lookup.

The helpdesk address is **`helpdesk@sdu.edu.kz`**. Old recognized demo accounts are migrated on demo startup while retaining requests/passwords. Address validation does **not** send verification email or prove mailbox ownership. Details and acceptance evidence are in [SDU registration](docs/SDU_REGISTRATION.md).

## Included behavior

| Feature | Behavior |
| --- | --- |
| Authentication | SDU-only student signup, derived admission/course profile, sign in/out, salted scrypt, rotating sessions |
| Request CRUD | Create, read, edit, and delete your own requests before staff begins work |
| AI classification and routing | Gemini API (generateContent) with a strict routing schema, or a local Naive Bayes model trained on 96 English examples |
| Notifications | Immediate in-app routing receipts, estimated response times, history, and read state |
| Confidence escalation | Uncertain requests remain in the staff queue with a 4-business-hour review deadline |
| Staff dashboard | Oldest-first queue, department/status/priority filters, manual routing, reassignment |
| Status tracking | Received, Escalated, In Progress, Resolved; student-visible resolution and history |
| Admin configuration | Change the threshold without editing code; persist staff routing decisions for future training |

Urgency in this increment is set manually by the student. Automatic emergency detection/alerts are US6. The local mode sends Russian/Kazakh messages to staff review. The Gemini prompt permits these languages, but representative live multilingual acceptance/translation for US7 remains unverified.

## Reproduce the two increments

```bash
python run.py --demo --ai local --sprint 1 --database instance/sprint1.sqlite3
python run.py --demo --ai local --sprint 2 --database instance/sprint2.sqlite3
```

Run one command at a time, or use different ports. `--sprint 1` exposes student request intake, AI routing, and notifications. Staff/admin endpoints are disabled. `--sprint 2` enables the final combined increment. Sprint 1 uses the shared foundation and safe escalation storage; interactive human review is delivered in Sprint 2.

## Select an AI mode

| Configuration | Behavior |
| --- | --- |
| No `.env`, no key (`auto`) | Local Naive Bayes, offline |
| `AI_ROUTER=gemini` with a key | Server calls Gemini for each valid new/edited request |
| `AI_ROUTER=gemini` without a key | Save requests for staff review; visibly report missing configuration |
| `python run.py --demo --ai local` | Force the local mode even if a key exists |

Timeouts, invalid responses, refusals, quota/access failures and unclear routes go to staff review. The cloud mode does not silently pretend that the local model's answer came from Gemini. Scores are estimates, not calibrated accuracy probabilities. The schema remains compatible. Recognized legacy demo accounts migrate to SDU addresses on demo startup; other non-SDU student accounts cannot sign in under the new policy. See the SDU registration notes before reusing an older database.

## Check the submission

```bash
python -m unittest discover -s tests -v
python scripts/evaluate_model.py
python scripts/audit_package.py
```

Read [the criteria audit](docs/criteria_audit.md), [Sprint 1 report](docs/sprint_1/report.md), and [Sprint 2 report](docs/sprint_2/report.md). Printable reports are in `docs/reports/`. [The demo guide](docs/demo_guide.md) explains exactly what to show at the defence.

The editable [Sprint 1–2 planning workbook](docs/Sprint_1_2_Plan.xlsx) includes calculated scope totals, task states, and honest burndown plans. See [testing notes](docs/testing.md) for measured results and optional browser-test commands.

Open **`docs/kanban.html`** to view and update the progress board. The original 21-sheet user-story workbook is preserved in `docs/source/`. A searchable source backlog is in `docs/product_backlog.csv`; sprint task tables are in `docs/sprint_1/backlog.csv` and `docs/sprint_2/backlog.csv`.

## Upload to GitHub

**Extract the ZIP first. Upload the contents of the project folder, so `README.md` and `run.py` appear at the repository root.** Uploading only the ZIP does not create a usable source repository.

If updating an existing repository, review and replace the older implementation with this coherent package. Do not mix two different backends or leave an older launch script as the default.

The browser upload path is **Add file -> Upload files**. Include `app/`, `static/`, `data/`, `tests/`, `scripts/`, `docs/`, `.github/`, `.gitignore`, `.env.example`, and the root files. Exclude `.env`, `instance/`, `node_modules/` and `__pycache__/` when selecting files for browser upload. Commit the upload. The supplied Actions workflow runs acceptance tests automatically. GitHub Pages hosts static files and cannot run this Python backend.

For Git users, in the extracted project folder:

```bash
git init
git add .
git commit -m "Deliver AI student routing Sprint 1 and Sprint 2"
git branch -M main
```

Then add your repository's actual remote URL and push. No remote repository has been created or changed by this package.

## Technical structure

| Directory | Contents |
| --- | --- |
| app/ | JSON API, routing services, database schema, session/password security, ML classifier |
| static/ | Responsive HTML, CSS, and JavaScript interface |
| data/ | Separate authored training and evaluation datasets |
| tests/ | Executable acceptance, authorization, validation, and concurrency tests |
| scripts/ | Model evaluation, verification evidence, package audit, staff-account creation |
| docs/ | Proposal, requirements, architecture, ERD, backlog, board, sprint reports, testing and demo guide |

This is a classroom prototype running on the Python development server. The documented security controls protect the demo, but production deployment needs HTTPS, an appropriate production server, institutional identity verification, privacy-policy review, backups, and validation on representative authorized data. A small synthetic evaluation does not establish real campus accuracy or FERPA compliance.

Team member names, course defence dates, and Product Owner acceptance were not supplied. Owners remain the source workbook's role assignments; the reports explicitly separate technical readiness from actual team/teacher acceptance. Use your real meeting records and course dates when presenting process history.
