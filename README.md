# AI Student Request Routing and Support System <3

A campus support portal. A student submits a request, an AI model suggests the right department (IT, Finance, Academic, Health), and unclear requests go to a staff review queue.

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
| Student | 240103030@sdu.edu.kz | Student123! |
| Second student | 250103031@sdu.edu.kz | Student123! |
| Support officer | helpdesk@sdu.edu.kz | Support123! |
| Administrator | admin@sdu.edu.kz | Admin12345! |

- **Student** submits and tracks requests.
- **Support** works the review queue and can change a request's department and status.
- **Administrator** changes the confidence threshold (0.50–0.99, default 0.65). Requests scored below it go to staff review.

New users can register with a 9-digit ID at `@sdu.edu.kz` (for example `240103030@sdu.edu.kz`). Registration always creates a student account.

## AI modes

| Setup | Behavior |
| --- | --- |
| No `.env` file (default) | Local Naive Bayes classifier, works offline, English only |
| `.env` with `AI_ROUTER=gemini` and a key | Requests are classified by the Gemini API (supports Russian and Kazakh) |
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

This is a classroom prototype that runs on the Python development server. It is not intended for production use.
