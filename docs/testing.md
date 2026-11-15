# Testing and verification

## Verification status

The archived evidence below records an earlier US1-US11 baseline and predates the current US10 search/filter scope. It does not cover the US8-US16 additions or the revised US12 profile-panel scope in this source version. Apart from the Sprint 5 browser check recorded below, those feature paths have not been browser-tested in this delivery, so the historical results below must not be treated as verification of the complete 16-story release.

**Backend re-run, 15 November 2026:** `python3 -m unittest discover -s tests` ran 163 tests and all passed (Python 3.12, local mode). This includes the US11 messaging suite (19 tests), the SDU profile-derivation tests (12), and the schema test updated to the current 22 tables.

**Sprint 5 browser check, 15 November 2026:** `scripts/sprint5_ui_check.py` (Python Playwright, Chromium, clean demo database, local classifier) passed 17 of 17 checks: US10 search and filters, US11 message thread, US12 profile for student, support and administrator, copy-on-click detail rows, pressable summary cards on the student home, profile and support queue, and no horizontal overflow at 390x844. Result: `evidence/sprint5_ui_check.json`; screenshots: `evidence/sprint5/`. The older Node script `scripts/browser_checks.mjs` was not re-run (Playwright for Node is not installed here), and the Sprint 5 browser check is not part of the GitHub workflow.

**Current source checks:** Python AST syntax parsed all 22 application/entry modules; `node --check` passed for both frontend scripts and the browser-check script; the sprint board's embedded JavaScript parsed successfully; `app/schema.sql` executed against an empty in-memory SQLite database. These are syntax/schema checks only and do not replace the acceptance checks below. No acceptance suite was run for the current US10 search/filter UI, US11 messaging UI, profile page, support-queue fix, or demo-account name migration.

**Earlier baseline:** 76 backend tests and 21 browser checks passed. That suite covered Sprint 1-2 acceptance/security, SDU address/course rules, legacy demo migration, and the external Gemini contract, privacy, failure and concurrency. No live or paid Gemini call was made; provider HTTP responses were simulated.

| Check | Recorded outcome | Boundary |
| --- | --- | --- |
| Backend suite | 76 passed, 0 failures, 0 errors | Actual Python execution |
| SDU-only registration | Wrong domains/subdomains/suffixes, malformed IDs and future cohorts rejected | Server and browser checks |
| Admission year/course | 24-prefix -> 2024 -> Year 3 in 2026-2027; January and September boundary tested | Derived from ID, not university enrollment lookup |
| Helpdesk access | Provisioned helpdesk@sdu.edu.kz can sign in; public signup cannot create staff | Local account, no actual mailbox accessed |
| Legacy demo migration | Account ID, password and request ownership retained | Executed migration test |
| Gemini API contract | Response schema, issue-text-only input, key in header only, no client key | Mocked HTTP; real provider access pending |
| Provider failures/refusal/bad JSON | Request persists in staff review with receipt and deadline | No silent substitution of local output for cloud output |
| Key privacy/concurrency | Credential-free status, redacted echoes, blocked redirects; staff version/logout wins | Executed contract and threaded tests |
| Local model holdout | 40/40 synthetic English examples correct | Local model only; not Gemini or real-campus accuracy |
| Local routing maximum | 0.000814s | In-process local classifier; cloud latency unmeasured |
| Local 500-request API | 0.010079s | Synthetic SQLite fixture |
| 500-request browser render | 0.134s | Real Chromium and local HTTP |
| Student status visibility | 13.358s | Active polling preserves draft text |
| Browser flows | 21 checks, no console errors | Local mode explicitly selected |
| Mobile | 390x844, no horizontal overflow | Student portal including SDU profile inspected |
| US8-US16 increment | Backend suite passed (163 tests); Sprint 5 browser check passed (17/17) | US10-US12 are covered by the Sprint 5 browser check; feedback, analytics, optional email escalation, SLA calendar, attachments, audit, and retention/deletion still need current browser acceptance checks |

Evidence: `evidence/verification.json`, `test_results.txt`, `browser_checks.json`, eight screenshots, package audit and a fresh-extraction smoke check. Native Windows execution and remote GitHub Actions were not performed. The workflow in `.github/workflows/tests.yml` uses actions/checkout@v6 and actions/setup-python@v6; its remote execution on GitHub is not claimed.

## Reproduce checks

```bash
python -m unittest discover -s tests -v
python scripts/evaluate_model.py
python scripts/audit_package.py
```

`python scripts/verify.py` regenerates backend/local-model/performance evidence and imports the most recent browser results. Tests force local mode or inject simulated Gemini transport; they do not use your real key. Optional browser checks need Node 22+, `npm install`, `npx playwright install chromium`, then `npm run test:browser`. They use an isolated temporary database and explicitly select local mode.

## Verify your real Gemini connection

After setup, run `python scripts/check_ai.py`. It sends one fictional Wi-Fi request and succeeds only if a real valid API response routes to IT. The `--save` option records this in `evidence/live_gemini_check.json`. No live result is included or claimed. Real-provider ten-request accuracy/latency and full multilingual US7 acceptance remain unverified until an API account and representative validation are available.

Domain restriction does not verify mailbox ownership. The academic year starts on 1 September at UTC+5 as a documented implementation assumption. Provider confidence is uncalibrated. Mocked responses, a small local holdout and one live smoke check do not establish real-campus accuracy, institutional privacy approval or a staffed four-hour SLA.

Official workflow references: https://github.com/actions/checkout and https://github.com/actions/setup-python.
