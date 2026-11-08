"""US10: retrain, inspect or roll back the local routing model without the web server.

Examples
  python scripts/retrain_model.py --status
  python scripts/retrain_model.py --run                    # retrain now, deploy only if not worse
  python scripts/retrain_model.py --due                    # run only if the schedule says so (cron / Task Scheduler)
  python scripts/retrain_model.py --rollback nb-1a2b3c4d5e6f

A running server notices a deployment or rollback made here on its next routing request.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.database import connection, initialize
from app.retraining import ModelManager
from app.service import APIError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database", default=str(ROOT / "instance" / "routing.sqlite3"))
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--status", action="store_true", help="Show the live version, saved versions and new labeled data.")
    action.add_argument("--run", action="store_true", help="Retrain now and deploy only if validation is not worse.")
    action.add_argument("--due", action="store_true", help="Retrain only if the configured schedule is due.")
    action.add_argument("--rollback", metavar="VERSION", help="Restore a previously deployed version.")
    args = parser.parse_args(argv)
    database = Path(args.database)
    initialize(database)
    manager = ModelManager(database, ROOT / "data" / "training.json", ROOT / "data" / "evaluation.json")
    if args.status:
        with closing(connection(database)) as db:
            overview = manager.overview(db, "local", True)
        print(f"Live model: {overview['active_version']}")
        print(f"Labeled data: {overview['data']['collected']} collected, {overview['data']['usable']} usable, "
              f"{overview['data']['new_since_live_model']} new since the live model")
        print(f"Schedule: {overview['settings']} | next due: {overview['next_due_at']}")
        for v in overview["versions"]:
            accuracy = "n/a" if v["accuracy"] is None else f"{v['accuracy']:.1%}"
            print(f"  {v['version']}  {v['status']:<8} {v['origin']:<8} examples={v['training_examples']:<5} "
                  f"validation={v['validation_size']:<4} accuracy={accuracy}  {v['created_at']}")
        return 0
    if args.rollback:
        with closing(connection(database)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                result = manager.activate(db, args.rollback, None)
                db.commit()
            except APIError as error:
                db.rollback()
                print(f"Rollback refused: {error.message}")
                return 1
        print(json.dumps(result))
        return 0
    result = manager.retrain("manual") if args.run else manager.run_if_due()
    if result is None:
        print("Retraining is not due.")
        return 0
    print(json.dumps(result, indent=2))
    return 1 if result["outcome"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
