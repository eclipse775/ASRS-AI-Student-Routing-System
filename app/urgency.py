"""Rule-based emergency detection for User Story 6 (standard library only).

Runs on the server before and independently of the AI router, so a provider
outage can never hide an emergency. Rules live in urgency_rules.json so they
can be tuned (the story's volatility is High) without code changes.
"""
import json
import re
import unicodedata
from pathlib import Path

RULES_PATH = Path(__file__).with_name("urgency_rules.json")
# Used only when an emergency is detected but neither the rules nor the AI name a department.
URGENT_FALLBACK_CODE = "health"
_cache = None


def load_rules():
    global _cache
    if _cache is None:
        raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        signals = [{**s, "regex": re.compile(s["pattern"], re.IGNORECASE | re.UNICODE)} for s in raw["signals"]]
        _cache = {"threshold": float(raw["threshold"]),
                  "negations": [n.lower() for n in raw["negations"]], "signals": signals}
    return _cache


def _normalize(text):
    text = unicodedata.normalize("NFKC", text or "").lower().replace("ё", "е")
    return re.sub(r"\s+", " ", text).strip()


def detect_urgency(title, message):
    """Return a small JSON-safe dict. Title and message are both scanned."""
    rules = load_rules()
    text = _normalize(f"{title or ''}. {message or ''}")
    negated = any(n in text for n in rules["negations"])
    signals, score, by_department = [], 0.0, {}
    for s in rules["signals"]:
        if negated and s["kind"] == "stated":
            continue  # "this is not an emergency" cancels only stated-urgency wording
        if s["regex"].search(text):
            signals.append(s["id"])
            score += s["weight"]
            if s.get("department"):
                by_department[s["department"]] = by_department.get(s["department"], 0.0) + s["weight"]
    detected = score >= rules["threshold"]
    department = max(by_department, key=by_department.get) if detected and by_department else None
    return {"detected": detected, "score": round(score, 2), "signals": signals, "department": department,
            "reason": ("Emergency signals detected: " + ", ".join(signals)) if detected else ""}


def merge_ai_flag(urgency, classification):
    """Safety-biased merge: urgent if the rules OR the classifier (when it reports `urgent`) say so."""
    ai_flagged = classification.get("urgent") is True
    if ai_flagged and not urgency["detected"]:
        return {**urgency, "detected": True, "ai_flagged": True, "signals": urgency["signals"] + ["ai_flag"],
                "reason": "The AI router flagged this request as an emergency."}
    return {**urgency, "ai_flagged": ai_flagged}
