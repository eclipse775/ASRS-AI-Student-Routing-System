# JSON API

All authenticated operations use the `routing_session` cookie. Start with `GET /api/session` to obtain an anonymous session and a CSRF token. Every mutation, including login/registration/logout, requires `Content-Type: application/json` and the current `X-CSRF-Token`. Login/registration rotates the cookie and returns a new CSRF token.

| Method | Endpoint | Role | Behavior |
| --- | --- | --- | --- |
| GET | /api/health | Any | Local health and selected sprint |
| GET | /api/session | Any | Current user/profile, academic-year/university metadata, CSRF token, sprint, credential-free AI status |
| GET | /api/ai/status | Authenticated | Provider/model, configured flag, response verification, safe error category |
| POST | /api/auth/register | Any with session | name, nine-digit student ID at sdu.edu.kz, password; always student |
| POST | /api/auth/login | Any with session | email, password; rotate session |
| POST | /api/auth/logout | Any with session | Invalidate authenticated session |
| GET | /api/departments | Authenticated | Configured departments |
| POST | /api/requests | Student | title (3-120), message (10-4000), priority normal/urgent |
| GET | /api/requests | Student | Own requests, newest first |
| GET | /api/requests/{id} | Owner/support | Detail and event history |
| PUT | /api/requests/{id} | Owner | title, message, version; early edit and reclassification |
| DELETE | /api/requests/{id} | Owner | version; early deletion and related-data cleanup |
| GET | /api/staff/requests | Support, Sprint 2 | Filter by status, department, priority, open=1; oldest first |
| POST | /api/requests/{id}/route | Support, Sprint 2 | department_code, version, optional reason |
| POST | /api/requests/{id}/status | Support, Sprint 2 | status, version, resolution (required to resolve) |
| GET | /api/notifications | Student | Own notification history |
| POST | /api/notifications/{id}/read | Owner | Idempotently mark notification read |
| GET / PUT | /api/admin/settings | Admin, Sprint 2 | Read/set confidence_threshold in [0.50,0.99] |
| GET | /api/admin/corrections | Admin, Sprint 2 | Correction summaries without student names/message text |

No CORS permission is configured. The browser frontend calls the API from the same origin. HTML paths are served publicly as a generic shell; user data and role actions are protected at API level. The UI redirects users away from screens outside their role.

Student user objects include `student_profile` with `student_id`, `admission_year`, `academic_year` and `course`. Staff/admin receive null for this field. Registration ignores client-supplied role, course or profile. Invalid student email/future admission year returns 400; case-normalized duplicate returns 409. Helpdesk/admin use pre-provisioned local accounts. Domain restriction does not verify mailbox ownership.

## Example request after login

```json
{"title":"Campus Wi-Fi","message":"My laptop cannot connect to campus wifi and the wireless network is unavailable.","priority":"normal"}
```

Successful creation returns HTTP 201 with a `request` object including `id`, `reference`, `status`, `department_code`, `department_name`, `confidence`, `classification`, `version`, `created_at`, and `updated_at`. Detail additionally returns `history`. Notifications are stored before the response completes.

## Error contract

Errors contain `{"error":"Readable explanation"}`. Typical statuses are 400 validation, 401 unauthenticated, 403 role/CSRF restriction, 404 missing or another student's request, 409 stale version or invalid state, 413 payload limit, 415 unsupported content type, 429 login throttling, and 503 database/routing availability. No password hashes or exception tracebacks are returned by the API.

## External routing and failure behavior

Create/edit responses include `classification.provider`, `model_version`, `reason` and `provider_result`. Gemini failure results include a safe `provider_error` category and `review_required: true`. A provider failure still returns HTTP 201 for a saved new request with Escalated status; the request, review deadline and notification persist. Scores/department selections submitted by the client are ignored. Invalid, unauthorized and already-stale edits make no provider call. A later concurrent edit is checked again before commit. Keys and raw provider errors are never returned.
