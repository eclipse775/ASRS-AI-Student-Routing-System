"""Explicitly test one real Gemini request using a fictional Wi-Fi issue."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import load_env
from app.llm import build_classifier


def main():
    load_env(ROOT)
    router = build_classifier(ROOT, 'gemini')
    if not router.status()['configured']:
        print('No Gemini key configured. Run setup_gemini_windows.bat or python scripts/configure_gemini.py.')
        raise SystemExit(2)
    result = router.classify('My laptop cannot connect to campus Wi-Fi and the wireless network keeps dropping.')
    passed = result['provider_result'] == 'success' and result['suggested_code'] == 'it'
    report = {'status': 'passed' if passed else 'failed', 'generated_at_utc': datetime.now(timezone.utc).isoformat(),
              'model': result['model_version'], 'department': result['suggested_code'],
              'confidence': result['confidence'], 'reason': result['reason'],
              'provider_error': result.get('provider_error'), 'scope': 'One live request with fictional text; not an accuracy evaluation.'}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if '--save' in sys.argv:
        path = ROOT / 'docs/evidence/live_gemini_check.json'
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    try:
        main()
    except ValueError as error:
        print(str(error)); raise SystemExit(1) from None
