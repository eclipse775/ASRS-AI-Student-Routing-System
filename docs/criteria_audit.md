# Criteria audit

This audit maps the supplied coursework guidance and the current 16-story source workbook to the delivered project. Implementation status and acceptance evidence are reported separately; completing code does not invent instructor acceptance, actual team ceremonies, or live external service configuration.

| Source criterion | Result in this package | Evidence / boundary |
| --- | --- | --- |
| Clear goal, scope, epics, stories, and tasks | Included | `proposal.md`, `requirements.md`, `product_backlog.csv` |
| Original source material preserved | Included unchanged | Current 16-story and original 10-story workbooks plus course references in `source/`; hashes in `source_manifest.json` |
| Sprint planning, reports, and progress board | Included | Sprint 1-2 reports, seven-sprint roadmap, editable `kanban.html`; later reports are not fabricated |
| Scrum roles, events, review, and retrospective | Prepared | `team_and_process.md`; actual attendance, team names, and instructor acceptance remain human records |
| Authentication and role separation | Implemented | Student, support, and admin; scrypt passwords, rotating sessions, CSRF checks, owner and role authorization |
| SDU registration and course profile | Implemented and included in historical checks | Exact-domain student signup, derived cohort/course, provisioned support access; mailbox ownership is not verified |
| Backend, database, UI, and documentation | Included | Modular Python WSGI API, SQLite migrations/schema, responsive browser workspaces, API/architecture/operations docs |
| US1-US5: classification, receipt, review, queue, and status | Implemented; earlier automated evidence exists | `app/service.py`, `app/server.py`, existing acceptance evidence in `testing.md` |
| US6-US7: urgency and multilingual intake | Implemented | `app/urgency.py`, `app/language.py`, `app/ml.py`, `app/llm.py`; common local vocabulary works offline, Gemini translation requires configuration |
| US8-US9: feedback, reopening, analytics | Implemented in the current delivery | `app/features.py`, `static/features.js`; latest acceptance paths are not yet run |
| US10-US12: student request search/filters, request message threads, and student profile panel | Implemented in the current source; latest acceptance paths are not run | `static/app.js`, `static/style.css`, `app/messaging.py`, student-only `/profile`; admin UI has no correction/retraining panel |
| US13: SLA reminders | Implemented | Persistent scheduler, managed business calendar, and overdue queue/reminder views |
| US14-US16: attachments, tamper-evident audit, retention/deletion | Implemented | Private file endpoint, append-only hash-chain audit, scheduled anonymization and admin-approved deletion |
| Security, validation, and data ownership | Implemented; latest additions need fresh acceptance checks | Role/owner checks, bounded input, CSRF, parameterized SQL, immutable audit triggers, file signatures and size limits |
| Testing evidence | Historical evidence is scoped clearly | `testing.md` records the earlier baseline and explicitly marks the new US8-US16 increment as not run |
| Demo and final product | Included for local classroom use | `README.md`, `demo_guide.md`; no production deployment or external course submission is claimed |
| Institutional privacy and retention approval | Pending institution | Retention default is 365 days; school policy, approved contacts, and real calendar must be supplied before real student use |

## Source and delivery notes

The revised 16-story workbook is the current scope source. The original 16-story workbook and earlier 10-story workbook are retained unchanged for provenance. The readable backlog preserves source planning fields and records US10 search/filter and US12 profile-panel estimates, roles, and prerequisites; course sprint assignments follow `roadmap.md`.

The current code covers all 16 revised user stories. Historical test results do not verify the latest feature increment: `testing.md` marks the US8-US16 paths as not run in this delivery. Live Gemini and optional SMTP behavior depend on credentials and were not exercised here. External team/course actions remain open until the team records them.
