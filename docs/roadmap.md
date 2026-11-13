# User story delivery roadmap

All 16 stories in the revised workbook have an implementation in the project. The original workbook is preserved unchanged, and the revised workbook replaces the urgent-alert escalation story with a student profile panel. The sprint grouping below follows the course plan; it does not claim that team ceremonies, instructor acceptance, or a real-campus deployment occurred.

| Course sprint | Stories | Implemented workflows |
| --- | --- | --- |
| 1 | US1-US2 | AI request classification and routing, human fallback, in-app receipt and notification history |
| 2 | US3-US5 | Low-confidence review, support queue and reassignment, request status and owner checks |
| 3 | US6 | Urgency detection, immediate support alert, missed-emergency escalation |
| 4 | US7 | English/Russian/Kazakh language detection, offline topic vocabulary, optional Gemini translation |
| 5 | US8-US9 | Resolution feedback, 48-hour reopen, date-filtered administration analytics |
| 6 | US10-US12 | Student request search and filters, message threads, student profile page |
| 7 | US13-US16 | Business-hours SLA and reminders, secure attachments, tamper-evident audit export, retention and deletion |

Estimates, priority flags, stakeholders, source iterations, and source deadlines are retained where applicable in the revised workbook and readable `product_backlog.csv`. US12's effort and role were updated for the profile-page scope. Course sprint assignments group the stories into seven course sprints. Source deadlines are planning data, not evidence of completed course defences.

## Delivery boundaries

- Gemini translation requires a server-side Gemini API key. The offline classifier can route common Russian and Kazakh support vocabulary but does not translate arbitrary text.
- Optional email escalation for urgent alerts requires administrator-entered contacts and configured SMTP credentials. No gateway is configured by default; queued jobs on unsupported legacy channels are cancelled during initialization.
- The default retention period is 365 days. An administrator must replace it with the institution's approved period and enter the real holiday calendar.
- Routing accuracy in analytics is agreement with staff corrections, escalation outcomes, and reopened-request labels. It is not an independently verified production accuracy score.
- The database and included Python development server are suitable for a classroom demo. A production deployment needs institutional hosting, security review, monitored gateway delivery, backups, and approved data-protection procedures.

`team_and_process.md` describes Scrum responsibilities and the meeting record convention. Record actual team attendance, rotating Scrum Master assignments, sprint reviews, and instructor acceptance separately.
