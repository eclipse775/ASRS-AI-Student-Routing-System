# Criteria audit

This audit covers the supplied practices, lab instructions, project-size guidance, US1-US5 story/QA sheets, and the linked course grading workbook. It records concrete implementation/evidence and separates current sprint work from later project stages or real human actions.

| Source criterion | Result in this package | Evidence / boundary |
| --- | --- | --- |
| Clear project goal and user scope | Included | `proposal.md`, `requirements.md` |
| Epics -> stories -> technical features/tasks | Included | Proposal epic mapping, source backlog, sprint task trackers |
| Product backlog in supplied template | Preserved, with readable derived tracker | Original 21-sheet XLSX in `source/`; `product_backlog.csv`, `Sprint_1_2_Plan.xlsx` |
| Story IDs, benefit, estimates, flags, roles, prerequisites, QA, owners, iteration, deadline | All supplied fields retained | Source workbook and derived backlog; names were supplied as role owners |
| Progress board in one place | Included | Offline, editable `kanban.html`; JSON export; actual team names can replace role owners |
| Sprint 1 planning and progress | Included | `sprint_1/report.md`, `backlog.csv`, burndown plan |
| Sprint 1 report | Included in Markdown and printable PDF | `reports/Sprint_1_Report.pdf` |
| Sprint 2 planning/report | Included in Markdown and printable PDF | `sprint_2/report.md`, `reports/Sprint_2_Report.pdf` |
| Seven two-week sprints | Planned | `roadmap.md`; source four-iteration grouping preserved separately |
| Scrum roles, events, review, retrospective | Responsibilities, ceremony plan, prepared demos, technical retrospectives included | `team_and_process.md`; actual attendance/PO acceptance not invented |
| Burndown/progress tracking | Plan plus current snapshot | No fabricated daily history or accepted team velocity |
| 4-10 meaningful features | Eight delivered capabilities | README feature table |
| At least two user roles | Three | Student, support, admin; role-specific API/UI |
| Approximately 3-8 related tables | Eight | `app/schema.sql`, ERD in `architecture.md` |
| Authentication | Implemented and tested | Password hashing, registration/login/logout, rotating sessions |
| SDU-only student signup | Implemented and tested on server and browser | Nine ASCII digits at exact `sdu.edu.kz`; other domains/aliases and future cohorts rejected |
| Admission year and current course | Implemented and tested | `240103030@sdu.edu.kz` -> 2024 -> Year 3 in 2026-2027; academic rollover test |
| Helpdesk address and permissions | Implemented and tested | `helpdesk@sdu.edu.kz`; support-only queue; public signup cannot grant staff roles |
| Verification of mailbox ownership | Not implemented or claimed | Domain/format restriction does not prove mailbox control; see `SDU_REGISTRATION.md` |
| CRUD where appropriate | Implemented | Owner-only early request create/read/update/delete; work-in-progress edit/delete blocked |
| Backend/API and database | Implemented | Modular Python WSGI JSON backend + SQLite |
| External AI integration extension | Implemented; live account activation pending | Gemini API and JSON response schema; `tests/test_gemini.py`; setup script and credential-free mode status |
| Functional consistent UI | Implemented; actual verification state recorded | HTML/CSS/JS role workspaces; see browser evidence and testing notes |
| Requirements/design/architecture/testing docs | Included | Requirements, ERD, component/state diagrams, API, AI explanation, test evidence |
| Version control | Ready for GitHub source upload | `.gitignore`, `.gitattributes`, Actions, issue/PR templates; no invented remote commits |
| US1 correct routing >=90% of 10, <30s | Executed backend acceptance target | Named ten-request test and recorded synthetic evaluation |
| US2 receipt ID/department/response estimate, <60s, no duplicates | Implemented and tested | Immediate in-app event-linked receipts; email/SMS not implemented |
| US3 confidence, escalation, staff label, configurable threshold | Implemented and tested | Review deadline, threshold API/UI, correction records |
| US3 staff review within 4 business hours | Software target instrumented | Deadline/overdue visibility tested; actual human response requires staffing |
| US4 role restriction, filters/sorting, reassignment | Implemented and tested | Support-only API, oldest-first list, status/department/priority filters |
| US4 routing under three clicks | Direct two-action route controls | Department selector + Route on visible queue card; actual UI execution recorded separately |
| US4 queue up to 500, <3s | API retrieval and real browser rendering passed | `verification.json`, `browser_checks.json`; see measured timings in `testing.md` |
| US5 status/timestamp/history, <1min, owner-only | Implemented and tested | Immediate commit/read; active student list polls every 15s |
| Security/validation/reliability | Implemented and tested | Role/owner checks, CSRF, scrypt, SQL parameters, transactions, version conflicts |
| Privacy policy / FERPA example | Technical controls implemented, institutional approval not established | Actual policy/legal review not provided; no certification claimed |
| Periodic real-data model review/retraining | Planned | US10, authorized datasets and retraining in later sprint |
| Final working product/report/presentation/demo | Later course stage planned; Sprint 1-2 demo supplied | `demo_guide.md`, seven-sprint roadmap; later stories are not marked complete |
| Moodle submission / actual defence / late deductions | Human course action | Package ready for upload; no external submission or grade claimed |

Read the measured outcomes in `evidence/verification.json` and `testing.md`. The original source files are protected by SHA-256 hashes in `source_manifest.json`. The programmatic completeness audit is `python scripts/audit_package.py`.

## Important source conflicts resolved

The workbook assigns US1-US2 to iteration 1 and US3-US5 to iteration 2; that selection is retained. Later source iterations are mapped to seven course sprints without changing the original. The source deadlines do not fit two-week iteration spans, so they remain labeled source deadlines. The source US9 HC&LV flag remains unchanged and is flagged for later Product Owner review.

No extra features are quietly reported as completed: manual urgency is not US6, the local Cyrillic guard and an unverified external multilingual prompt are not full US7 acceptance, correction storage is not US10, and the admin settings page is not US9 analytics.
