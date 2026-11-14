<div align="center">

# AI Student Request Routing and Support System

A campus support portal that routes student requests to the appropriate department using Google Gemini, with staff review for unclear cases.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Dependencies](https://img.shields.io/badge/dependencies-none-2ea44f)
![AI](https://img.shields.io/badge/AI-Google%20Gemini-8E75B2)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![Status](https://img.shields.io/badge/status-classroom%20prototype-orange)

<img width="900" alt="Application screenshot" src="https://github.com/user-attachments/assets/592fe08a-441c-4653-8a8a-0d5cf209d48a" />

</div>

---

## Table of Contents

1. [Overview](#overview)
2. [Installation and First Login](#installation-and-first-login)
   - [Windows](#windows)
   - [macOS](#macos)
3. [Demo Accounts](#demo-accounts)
4. [Gemini Configuration Reference](#gemini-configuration-reference)
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

## Installation and First Login

**You will need:**

- Python 3.11 or newer
- A free Gemini API key from <https://aistudio.google.com/apikey> (sign in with a Google account, select **Create API key**; no payment card is required)
- The project folder (the one containing `run.py`)

No `pip install` and no Node.js are required.

### Windows

**Step 1. Install Python.**
Download the installer from <https://www.python.org/downloads/>. On the first installer screen, select **Add python.exe to PATH**, then choose **Install Now**.
To verify, open **Command Prompt** (press `Win`, type `cmd`, press Enter) and run:

```bat
py -3 --version
```

The output must be `Python 3.11` or higher.

**Step 2. Get the project.**
On the GitHub page select **Code > Download ZIP**, then right-click the downloaded file and choose **Extract All**. Open the extracted folder until you see `run.py`.
Alternatively, with Git installed: `git clone https://github.com/eclipse775/ASRS-AI-Student-Routing-System.git`

**Step 3. Configure Gemini.**
Double-click `setup_gemini_windows.bat`. A console window opens:

1. Paste your API key when prompted (right-click in the window to paste). The key is **not displayed** while typing or pasting; this is expected. Press Enter.
2. When asked for the model, press Enter to accept the default (`gemini-3.1-flash-lite`).
3. The message `Saved.` confirms that a `.env` file was created next to `run.py`.

**Step 4. Start the server.**
Double-click `start_windows.bat`. Keep the console window open while using the portal. If Windows SmartScreen or a firewall prompt appears, allow the application for private networks.
The console should show `AI mode: gemini` and `Open http://127.0.0.1:8000`.

Manual alternative: in Command Prompt, change to the project folder (`cd path\to\ASRS-AI-Student-Routing-System-main`) and run `py -3 run.py --demo`.

**Step 5. Sign in.**
Open <http://127.0.0.1:8000> in a browser and sign in with a [demo account](#demo-accounts), for example `240103030@sdu.edu.kz` / `Student123!`.

**Step 6. Verify Gemini.**
The top banner should read **Gemini · gemini-3.1-flash-lite · configured**. Submit a request such as `I cannot connect to campus Wi-Fi in the dormitory`. It should be routed to IT Helpdesk, and the banner changes to **response verified**.
For a check without the browser, run `py -3 scripts\check_ai.py`.

**Step 7. Stop the server.**
Press `Ctrl+C` in the console window.

### macOS

**Step 1. Install Python.**
Download the macOS installer from <https://www.python.org/downloads/> and run it. Alternatively, with Homebrew: `brew install python`.
Open **Terminal** (press `Cmd + Space`, type `Terminal`, press Enter) and verify:

```bash
python3 --version
```

The output must be `Python 3.11` or higher. If macOS offers to install Command Line Developer Tools, accept the prompt and repeat the command afterwards.

**Step 2. Get the project.**
On the GitHub page select **Code > Download ZIP**. Safari extracts the archive automatically; otherwise double-click the ZIP file. Move the extracted folder to a convenient location, for example your Documents folder.
Alternatively, with Git: `git clone https://github.com/eclipse775/ASRS-AI-Student-Routing-System.git`

**Step 3. Open the project in Terminal.**
Type `cd ` (with a trailing space) in Terminal, drag the project folder from Finder into the Terminal window, and press Enter. Confirm you are in the right place:

```bash
ls run.py
```

The command must print `run.py`.

**Step 4. Configure Gemini.**

```bash
python3 scripts/configure_gemini.py
```

1. Paste your API key when prompted. The key is **not displayed** while typing or pasting; this is expected. Press Enter.
2. When asked for the model, press Enter to accept the default (`gemini-3.1-flash-lite`).
3. The message `Saved.` confirms that a `.env` file was created in the project folder.

The `.env` file is hidden by default. To view it in Finder, press `Cmd + Shift + .`.

**Step 5. Start the server.**

```bash
python3 run.py --demo
```

Keep the Terminal window open while using the portal. If macOS asks whether Python may accept incoming network connections, choose **Allow**.
The output should show `AI mode: gemini` and `Open http://127.0.0.1:8000`.
Alternatively, run `sh start_mac_linux.sh`.

**Step 6. Sign in.**
Open <http://127.0.0.1:8000> in a browser and sign in with a [demo account](#demo-accounts), for example `240103030@sdu.edu.kz` / `Student123!`.

**Step 7. Verify Gemini.**
The top banner should read **Gemini · gemini-3.1-flash-lite · configured**. Submit a request such as `I cannot connect to campus Wi-Fi in the dormitory`. It should be routed to IT Helpdesk, and the banner changes to **response verified**.
For a check without the browser, run `python3 scripts/check_ai.py`.

**Step 8. Stop the server.**
Press `Ctrl+C` in Terminal.

### Notes for both systems

- The `--demo` flag creates the demo accounts. Without it, no accounts exist to sign in with.
- If port 8000 is in use, add `--port 8001` to the start command and open `http://127.0.0.1:8001` instead.
- Without an API key the portal still starts, but every request is sent to the staff review queue.
- Never commit `.env` or share the API key. Use only fictional data with the free tier.

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

## Gemini Configuration Reference

The setup scripts create a `.env` file in the project root. It can also be written by hand:

```env
AI_ROUTER=gemini
GEMINI_API_KEY=your_key_without_quotes
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_TIMEOUT_SECONDS=15
```

| Variable | Description |
| --- | --- |
| `AI_ROUTER` | Must be `gemini` |
| `GEMINI_API_KEY` | API key from Google AI Studio; no quotes or spaces |
| `GEMINI_MODEL` | Model code, default `gemini-3.1-flash-lite` |
| `GEMINI_TIMEOUT_SECONDS` | Request timeout, from 2 to 30 seconds |

Each variable must appear exactly once. A non-empty environment variable set in the operating system takes precedence over `.env`; an empty variable does not.

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

Common startup problems:

| Symptom | Resolution |
| --- | --- |
| `'py' is not recognized` (Windows) | Reinstall Python with **Add python.exe to PATH** selected, or use `python` instead of `py -3` |
| `command not found: python3` (macOS) | Install Python as described in Step 1 and reopen Terminal |
| `Could not start the server` | The port is busy. Add `--port 8001` |
| Setup script asks to run in a local terminal | Run it from Command Prompt or Terminal, not from an editor's embedded console |
| Cannot sign in | The server was started without `--demo`. Restart it with that flag |

---

## Testing

```bash
python3 -m unittest discover -s tests -v      # Windows: py -3 -m unittest discover -s tests -v
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
