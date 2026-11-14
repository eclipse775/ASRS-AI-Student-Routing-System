<div align="center">

# AI Student Request Routing and Support System

A campus support portal that routes student requests to the appropriate department using Google Gemini, with staff review for unclear cases.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Dependencies](https://img.shields.io/badge/dependencies-none-2ea44f)
![AI](https://img.shields.io/badge/AI-Google%20Gemini-8E75B2)
![Status](https://img.shields.io/badge/status-classroom%20prototype-orange)

<img width="900" alt="Application screenshot" src="https://github.com/user-attachments/assets/592fe08a-441c-4653-8a8a-0d5cf209d48a" />

</div>

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Gemini Setup](#gemini-setup)
4. [Demo Accounts](#demo-accounts)
5. [Troubleshooting](#troubleshooting)
6. [Testing](#testing)
7. [Project Structure](#project-structure)

---

## Overview

A student submits a request through the web portal. Gemini classifies it and routes it to one of five departments: IT, Finance, Academic, Health or Security. Requests that are unclear, or that fall below the confidence threshold, are placed in a staff review queue.

| Capability | Description |
| --- | --- |
| Department routing | Automatic classification into IT, Finance, Academic, Health and Security |
| Urgent request handling | Emergency requests bypass the review queue and alert staff immediately |
| Staff review queue | Unclear or low-confidence requests are reviewed by a support officer |
| Multilingual input | English, Russian and Kazakh; Gemini also provides an English translation for staff |
| Graceful degradation | If Gemini is unavailable or not configured, the request is saved and sent to staff review |

---

## Quick Start

**Requirements:** Python 3.11 or newer and a free Gemini API key. No `pip install` and no Node.js are required.

1. Configure Gemini (see [Gemini Setup](#gemini-setup)).
2. Start the server:

   ```bash
   # macOS / Linux
   python3 run.py --demo

   # Windows
   py -3 run.py --demo
   ```

   On Windows, `start_windows.bat` can be used instead.
3. Open <http://127.0.0.1:8000> in a browser. If port 8000 is in use, start the server with `--port 8001`.

The `--demo` flag creates the demo accounts listed below. Without it, no accounts exist.

---

## Gemini Setup

1. Create a free API key at <https://aistudio.google.com/apikey>.
2. Run `setup_gemini_windows.bat` (Windows) or `python3 scripts/configure_gemini.py`, or create a `.env` file manually in the project root:

   ```env
   AI_ROUTER=gemini
   GEMINI_API_KEY=your_key_without_quotes
   GEMINI_MODEL=gemini-3.1-flash-lite
   GEMINI_TIMEOUT_SECONDS=15
   ```

3. Restart the server. The portal displays **Gemini · configured**, and **response verified** after the first successful response.
4. Verify with one live request: `python scripts/check_ai.py`.

Without a key, the system still runs, but every request is sent to the staff review queue.

> **Security notice.** Never commit `.env` or share the API key. Use only fictional data with the free tier.

---

## Demo Accounts

| Role | Email | Password |
| --- | --- | --- |
| Student | `240103030@sdu.edu.kz` | `Student123!` |
| Support officer | `helpdesk@sdu.edu.kz` | `Support123!` |
| Administrator | `admin@sdu.edu.kz` | `Admin12345!` |

Additional demo students are listed in `docs/demo_guide.md`.

- **Student** submits and tracks requests.
- **Support officer** works the review queue and can change a request's department and status.
- **Administrator** sets the confidence threshold (0.50 to 0.99, default 0.65). Requests scored below it go to staff review.

New users may register with a 9-digit ID at `@sdu.edu.kz`. Registration always creates a student account.

---

## Troubleshooting

`scripts/check_ai.py` prints `provider_error` and `provider_detail` (for example, `HTTP 400 INVALID_ARGUMENT API_KEY_INVALID`). The same fields are stored with each request's classification and are visible to staff.

| `provider_error` | Cause and resolution |
| --- | --- |
| `missing_api_key` | No key found. Ensure `.env` is located next to `run.py` and `GEMINI_API_KEY=` is set |
| `authentication` | The key is invalid, expired or blocked. Create a new key |
| `region` | Gemini is unavailable from this location or project. Use a different network or project |
| `rate_limit` | Free quota exhausted. Wait, or select another Flash model |
| `configuration` | Incorrect model name (HTTP 404) or malformed request. Copy the model code from AI Studio |
| `timeout`, `network` | Connectivity problem. Check internet, VPN and proxy settings; increase the timeout (maximum 30) |
| `invalid_response`, `refusal`, `incomplete` | Unusable response. The request is safely routed to staff review |

A non-empty environment variable set in the operating system takes precedence over `.env`. An empty variable does not.

---

## Testing

```bash
python -m unittest discover -s tests -v
```

---

## Project Structure

| Directory | Contents |
| --- | --- |
| `app/` | Backend API, routing logic, database and the Gemini classifier |
| `static/` | Web interface |
| `tests/` | Automated tests |
| `scripts/` | Gemini setup and verification, administrative utilities |
| `docs/` | Project documentation |

---

<div align="center">

This is a classroom prototype running on the Python development server. It is not intended for production use.

</div>
