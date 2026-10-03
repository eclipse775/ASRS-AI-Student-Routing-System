"""Evaluate against a separate, authored holdout set, with no evaluation training."""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.ml import Classifier


def evaluate():
    model = Classifier(ROOT / "data" / "training.json")
    rows = json.loads((ROOT / "data" / "evaluation.json").read_text())
    training = json.loads((ROOT / "data" / "training.json").read_text())
    assert not {r["text"].lower() for r in rows} & {r["text"].lower() for r in training}, "Evaluation/training overlap"
    results = []
    started = time.perf_counter()
    for row in rows:
        predicted = model.classify(row["text"])
        results.append({**row, "predicted": predicted["suggested_code"],
                        "confidence": predicted["confidence"],
                        "auto_routed": predicted["confidence"] >= 0.65,
                        "correct": predicted["suggested_code"] == row["label"]})
    duration = time.perf_counter() - started
    correct = sum(r["correct"] for r in results)
    auto = [r for r in results if r["auto_routed"]]
    report = {"model_version": model.version, "training_examples": len(training), "test_examples": len(rows),
              "correct": correct, "accuracy": correct / len(rows),
              "auto_routing_coverage": len(auto) / len(rows),
              "auto_routing_accuracy": sum(r["correct"] for r in auto) / len(auto) if auto else None,
              "elapsed_seconds": round(duration, 6), "results": results,
              "limitation": "Small synthetic English dataset. This does not establish real-world accuracy or multilingual support."}
    print(f"Classification: {correct}/{len(rows)} correct ({report['accuracy']:.1%}); auto-routing: {len(auto)}/{len(rows)}")
    if "--save" in sys.argv:
        out = ROOT / "docs" / "evidence" / "model_evaluation.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n")
    if report["accuracy"] < 0.90 or len(auto) < 0.90 * len(rows) or report["auto_routing_accuracy"] < 0.90:
        raise SystemExit("The supplied 90% acceptance target did not pass.")
    return report


if __name__ == "__main__":
    evaluate()
