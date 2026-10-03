"""Set up Gemini locally. Never print, upload or send the API key to the browser."""
import getpass
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import ALLOWED
from app.llm import DEFAULT_MODEL


def save_config(root, key, model=DEFAULT_MODEL):
    if not re.fullmatch(r"[A-Za-z0-9._-]{10,512}", key):
        raise ValueError("Paste a valid API key, without spaces or quotes.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,99}", model):
        raise ValueError("Enter a valid model identifier.")
    target = Path(root) / ".env"
    existing = target.read_text(encoding="utf-8-sig").splitlines() if target.exists() else []
    kept = [line for line in existing if line.partition('=')[0].strip() not in ALLOWED]
    contents = "\n".join(kept + ["AI_ROUTER=gemini", "GEMINI_API_KEY=" + key,
                                  "GEMINI_MODEL=" + model, "GEMINI_TIMEOUT_SECONDS=15", ""])
    descriptor, temporary = tempfile.mkstemp(prefix=".env-", dir=root, text=True)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(contents)
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()


def main():
    print("Gemini setup for Campus Route. A free Google AI Studio API key is enough.")
    print("The key stays in this computer's .env file. Never upload .env to GitHub.")
    print("Create your key at https://aistudio.google.com/apikey")
    if not sys.stdin.isatty():
        print("Run setup in a local terminal so your API key can be entered without echoing it.")
        raise SystemExit(1)
    if (ROOT / '.env').exists():
        if input("Replace the AI settings in the existing .env file? [y/N]: ").strip().lower() != 'y':
            print("No changes made."); return
    key = getpass.getpass("Paste your API key (hidden): ").strip()
    model = input(f"Model [{DEFAULT_MODEL}]: ").strip() or DEFAULT_MODEL
    save_config(ROOT, key, model)
    print("Saved. Restart the application with start_windows.bat or python run.py --demo.")
    print("To verify a real API response: python scripts/check_ai.py")


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        print(str(error) if isinstance(error, ValueError) else 'Could not save the local configuration.')
        raise SystemExit(1) from None
    except (KeyboardInterrupt, EOFError):
        print("\nSetup cancelled.")
        raise SystemExit(1) from None
