"""US10: scheduled retraining, held-out validation, model versioning and rollback.

How it works
------------
* Staff routing decisions and reopened requests are stored as labeled examples in ``training_samples``
  (see ``app/labels.py``; the hooks live in ``app/service.py``).
* A retraining run trains a *candidate* Naive Bayes model on ``data/training.json`` plus all usable
  collected examples, then scores the candidate and the live model on the same held-out validation
  set (``data/evaluation.json`` plus the held-out slice of the collected staff labels).
* The candidate replaces the live model only if it is at least as accurate. Otherwise it is stored as
  ``rejected`` and the live model is not touched.
* Training happens outside any database write transaction and the live model is swapped by assigning
  one reference, so routing never waits for a retraining run (no downtime).
* Every trained version is saved as an immutable artifact and registered in ``model_versions``;
  ``activate`` restores any previously deployed version in milliseconds.
"""
from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import threading
import time

from app.database import connection, utc_now
from app.labels import SOURCES, STRONG_SOURCES
from app.ml import Classifier, tokenize
from app.service import APIError

LOG = logging.getLogger("routing.retraining")
VERSION_PATTERN = re.compile(r"nb-[0-9a-f]{12}")
HOLDOUT_PERCENT = 20  # share of collected texts that is never trained on and used only for validation
SETTING_KEYS = {"enabled": "retrain_enabled", "interval_days": "retrain_interval_days",
                "min_new_samples": "retrain_min_new_samples"}


def normalize(text):
    return " ".join(text.lower().split())


def is_holdout(text):
    """Deterministic, text-based split: a text is held out in every cycle or in none of them."""
    digest = hashlib.sha256(normalize(text).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % 100 < HOLDOUT_PERCENT


def usable_text(text):
    """The local model reads English words; anything with fewer than two of them carries no signal."""
    return len([t for t in tokenize(text) if "_" not in t]) >= 2


def load_rows(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate(model, rows):
    per = {}
    correct = 0
    for row in rows:
        hit = model.classify(row["text"])["suggested_code"] == row["label"]
        entry = per.setdefault(row["label"], {"correct": 0, "total": 0})
        entry["total"] += 1
        entry["correct"] += hit
        correct += hit
    return {"correct": correct, "total": len(rows), "accuracy": correct / len(rows) if rows else None,
            "per_department": per}


class LiveClassifier:
    """The classifier the router calls. ``swap`` replaces the model with a single atomic assignment."""
    provider = "local"

    def __init__(self, model):
        self._model = model

    @property
    def model(self):
        return self._model

    @property
    def version(self):
        return self._model.version

    @property
    def training_size(self):
        return self._model.training_size

    def classify(self, text):
        return self._model.classify(text)

    def status(self):
        return self._model.status()

    def swap(self, model):
        self._model = model


class ModelManager:
    def __init__(self, database_path, training_path, evaluation_path, models_dir=None):
        self.database_path = Path(database_path)
        self.training_path = Path(training_path)
        self.evaluation_path = Path(evaluation_path)
        self.models_dir = Path(models_dir) if models_dir else self.database_path.parent / "models"
        self._run_lock = threading.Lock()
        self._sync_lock = threading.Lock()
        self._bad = set()
        self._running = None
        self._thread = None
        self.live = LiveClassifier(self._bootstrap())

    # ------------------------------------------------------------------ registry and artifacts
    def _artifact(self, version):
        if not VERSION_PATTERN.fullmatch(version):
            raise ValueError("Invalid model version.")
        return self.models_dir / f"{version}.json"

    def _write_artifact(self, version, raw):
        self.models_dir.mkdir(parents=True, exist_ok=True)
        target = self._artifact(version)
        temporary = target.with_name(target.name + f".{os.getpid()}.{threading.get_ident()}.tmp")
        temporary.write_bytes(raw)
        os.replace(temporary, target)  # readers never see a half-written artifact

    def _load_artifact(self, version):
        model = Classifier(self._artifact(version))
        if model.version != version:
            raise ValueError("The saved model file does not match its version.")
        return model

    def _event(self, db, action, version, actor_id, detail):
        db.execute("INSERT INTO model_events (action,version,actor_id,detail,created_at) VALUES (?,?,?,?,?)",
                   (action, version, actor_id, json.dumps(detail, ensure_ascii=False), utc_now()))

    def _bootstrap(self):
        """Register the packaged training file as the baseline the first time, then load the active model."""
        base = Classifier(self.training_path)
        with closing(connection(self.database_path)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                active = db.execute("SELECT * FROM model_versions WHERE status='active'").fetchone()
                if active is None:
                    self._write_artifact(base.version, self.training_path.read_bytes())
                    accuracy = None
                    if self.evaluation_path.is_file():
                        accuracy = evaluate(base, load_rows(self.evaluation_path))["accuracy"]
                    now = utc_now()
                    db.execute("""INSERT INTO model_versions (version,status,origin,training_examples,validation_size,
                                  accuracy,artifact,created_at,deployed_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                               (base.version, "active", "baseline", base.training_size,
                                len(load_rows(self.evaluation_path)) if self.evaluation_path.is_file() else 0,
                                accuracy, f"{base.version}.json", now, now))
                    self._event(db, "baseline", base.version, None,
                                {"training_examples": base.training_size, "accuracy": accuracy})
                    db.commit()
                    return base
                db.commit()
            except Exception:
                db.rollback()
                raise
        try:
            return self._load_artifact(active["version"])
        except Exception:
            LOG.exception("The active model %s could not be loaded; serving the packaged baseline.", active["version"])
            self._bad.add(active["version"])
            return base

    def sync(self, db):
        """Pick up a deployment or rollback made by another process or request."""
        row = db.execute("SELECT version FROM model_versions WHERE status='active'").fetchone()
        if row is None or row["version"] == self.live.version or row["version"] in self._bad:
            return
        with self._sync_lock:
            if row["version"] == self.live.version:
                return
            try:
                self.live.swap(self._load_artifact(row["version"]))
            except Exception:
                LOG.exception("The active model %s could not be loaded; keeping the current model.", row["version"])
                self._bad.add(row["version"])

    def sync_from_database(self):
        with closing(connection(self.database_path)) as db:
            self.sync(db)

    # ------------------------------------------------------------------ settings
    def settings(self, db):
        values = {r["key"]: r["value"] for r in db.execute("SELECT key,value FROM settings WHERE key LIKE 'retrain_%'")}
        return {"enabled": values.get("retrain_enabled", "1") == "1",
                "interval_days": int(values.get("retrain_interval_days", "30")),
                "min_new_samples": int(values.get("retrain_min_new_samples", "5"))}

    def update_settings(self, db, user, data):
        updates = {}
        if "enabled" in data:
            if type(data["enabled"]) is not bool:
                raise APIError(400, "Automatic retraining must be on or off.")
            updates["retrain_enabled"] = "1" if data["enabled"] else "0"
        if "interval_days" in data:
            if type(data["interval_days"]) is not int or not 1 <= data["interval_days"] <= 365:
                raise APIError(400, "The retraining interval must be 1-365 days.")
            updates["retrain_interval_days"] = str(data["interval_days"])
        if "min_new_samples" in data:
            if type(data["min_new_samples"]) is not int or not 1 <= data["min_new_samples"] <= 1000:
                raise APIError(400, "The minimum number of new examples must be 1-1000.")
            updates["retrain_min_new_samples"] = str(data["min_new_samples"])
        if not updates:
            raise APIError(400, "Send at least one retraining setting.")
        for key, value in updates.items():
            db.execute("UPDATE settings SET value=?,updated_by=?,updated_at=? WHERE key=?",
                       (value, user["id"], utc_now(), key))
        return self.settings(db)

    # ------------------------------------------------------------------ labeled data
    def build_dataset(self, db):
        """Turn collected labels into a training slice and a held-out validation slice (never overlapping)."""
        base_rows = load_rows(self.training_path)
        evaluation_rows = load_rows(self.evaluation_path)
        raw = [dict(r) for r in db.execute("SELECT id,request_id,source,label,text FROM training_samples ORDER BY id")]

        def prefer(current, row):
            # A later staff decision replaces anything; a later "reopened" label never replaces a staff decision.
            return current is None or row["source"] in STRONG_SOURCES or current["source"] not in STRONG_SOURCES

        per_request = {}
        for row in raw:
            if prefer(per_request.get(row["request_id"]), row):
                per_request[row["request_id"]] = row
        per_text = {}
        for row in sorted(per_request.values(), key=lambda r: r["id"]):
            key = normalize(row["text"])
            if prefer(per_text.get(key), row):
                per_text[key] = row
        base_texts = {normalize(r["text"]) for r in base_rows}
        evaluation_texts = {normalize(r["text"]) for r in evaluation_rows}
        train, validation, skipped = [], [], Counter()
        for key, row in sorted(per_text.items()):
            if key in base_texts:
                skipped["already_in_base_data"] += 1
            elif key in evaluation_texts:
                skipped["overlaps_evaluation_set"] += 1
            elif not usable_text(row["text"]):
                skipped["not_usable_by_local_model"] += 1  # e.g. Russian/Kazakh text or fewer than two words
            elif is_holdout(key):
                if row["source"] in STRONG_SOURCES:
                    validation.append(row)
                else:
                    skipped["weak_label_held_out"] += 1
            else:
                train.append(row)
        return {"base_rows": base_rows, "evaluation_rows": evaluation_rows, "train": train,
                "validation": validation, "skipped": dict(skipped),
                "by_source": {s: sum(r["source"] == s for r in raw) for s in SOURCES}, "total": len(raw),
                "cutoff": max((r["id"] for r in raw), default=0)}

    @staticmethod
    def _new_examples(data, cutoff):
        return [r for r in data["train"] + data["validation"] if r["id"] > cutoff]

    # ------------------------------------------------------------------ retraining
    @property
    def running(self):
        return self._running

    def _guarded(self, origin, actor_id, background):
        if not self._run_lock.acquire(blocking=False):
            raise APIError(409, "A retraining run is already in progress.")
        self._running = {"origin": origin, "started_at": utc_now()}

        def work():
            try:
                return self._execute(origin, actor_id)
            finally:
                self._running = None
                self._run_lock.release()

        if not background:
            return work()
        self._thread = threading.Thread(target=work, name="model-retraining", daemon=True)
        self._thread.start()
        return None

    def retrain(self, origin="manual", actor_id=None):
        """Run one cycle and wait for the result."""
        return self._guarded(origin, actor_id, background=False)

    def start(self, origin="manual", actor_id=None):
        """Run one cycle in a background thread; routing keeps working while it trains."""
        self._guarded(origin, actor_id, background=True)

    def wait(self, timeout=60):
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        return not (thread is not None and thread.is_alive())

    def _finish(self, action, version, actor_id, detail, candidate_row=None):
        with closing(connection(self.database_path)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                if candidate_row:
                    self._insert_candidate(db, candidate_row)
                self._event(db, action, version, actor_id, detail)
                db.commit()
            except Exception:
                db.rollback()
                raise

    @staticmethod
    def _insert_candidate(db, row):
        db.execute("""INSERT INTO model_versions (version,parent_version,status,origin,training_examples,new_examples,
                      data_cutoff_id,validation_size,accuracy,previous_accuracy,artifact,created_by,created_at,deployed_at)
                      VALUES (:version,:parent_version,:status,:origin,:training_examples,:new_examples,:data_cutoff_id,
                      :validation_size,:accuracy,:previous_accuracy,:artifact,:created_by,:created_at,:deployed_at)""", row)

    def _execute(self, origin, actor_id):
        started = time.perf_counter()
        try:
            self.sync_from_database()
            with closing(connection(self.database_path)) as db:
                active = db.execute("SELECT * FROM model_versions WHERE status='active'").fetchone()
                data = self.build_dataset(db)
                settings = self.settings(db)
            live = self.live.model
            if active is None or live.version != active["version"]:
                raise RuntimeError("The live model does not match the registry.")
            new = self._new_examples(data, active["data_cutoff_id"])
            needed = settings["min_new_samples"] if origin == "scheduled" else 1
            if len(new) < needed:
                reason = f"{len(new)} new usable labeled example(s) since the live model; {needed} needed."
                self._finish("retrain_skipped", live.version, actor_id,
                             {"origin": origin, "reason": reason, "new_examples": len(new), "skipped": data["skipped"]})
                return {"outcome": "skipped", "reason": reason, "new_examples": len(new)}

            rows = ([{"text": r["text"], "label": r["label"]} for r in data["base_rows"]] +
                    [{"text": r["text"], "label": r["label"]} for r in sorted(data["train"], key=lambda r: normalize(r["text"]))])
            raw = json.dumps(rows, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8")
            version = "nb-" + hashlib.sha256(raw).hexdigest()[:12]
            with closing(connection(self.database_path)) as db:
                existing = db.execute("SELECT status FROM model_versions WHERE version=?", (version,)).fetchone()
            if existing:
                reason = f"The retrained model is identical to version {version}, which is already {existing['status']}."
                self._finish("retrain_skipped", live.version, actor_id,
                             {"origin": origin, "reason": reason, "new_examples": len(new)})
                return {"outcome": "skipped", "reason": reason, "new_examples": len(new)}

            self._write_artifact(version, raw)
            candidate = Classifier(self._artifact(version))
            if candidate.version != version:
                raise RuntimeError("The trained model does not match its saved file.")
            validation_rows = data["evaluation_rows"] + [{"text": r["text"], "label": r["label"]} for r in data["validation"]]
            before = evaluate(live, validation_rows)
            after = evaluate(candidate, validation_rows)
            # Equal or better deploys; any drop in correct answers on the same held-out set is rejected.
            deploy = after["correct"] >= before["correct"]
            now = utc_now()
            row = {"version": version, "parent_version": live.version, "status": "active" if deploy else "rejected",
                   "origin": origin, "training_examples": candidate.training_size, "new_examples": len(new),
                   "data_cutoff_id": data["cutoff"], "validation_size": len(validation_rows),
                   "accuracy": after["accuracy"], "previous_accuracy": before["accuracy"],
                   "artifact": f"{version}.json", "created_by": actor_id, "created_at": now,
                   "deployed_at": now if deploy else None}
            detail = {"origin": origin, "new_examples": len(new), "training_examples": candidate.training_size,
                      "validation_size": len(validation_rows), "candidate_accuracy": after["accuracy"],
                      "live_accuracy": before["accuracy"], "live_version": live.version}
            with closing(connection(self.database_path)) as db:
                db.execute("BEGIN IMMEDIATE")
                try:
                    current = db.execute("SELECT version FROM model_versions WHERE status='active'").fetchone()
                    if current is None or current["version"] != live.version:
                        db.rollback()
                        reason = "The live model changed while this run was validating; run retraining again."
                        self._finish("retrain_failed", live.version, actor_id, {"origin": origin, "reason": reason})
                        return {"outcome": "failed", "reason": reason}
                    if deploy:
                        db.execute("UPDATE model_versions SET status='archived' WHERE status='active'")
                    self._insert_candidate(db, row)
                    detail["duration_ms"] = round((time.perf_counter() - started) * 1000)
                    self._event(db, "retrain_deployed" if deploy else "retrain_rejected", version, actor_id, detail)
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
            if deploy:
                self.live.swap(candidate)
                LOG.info("Model %s deployed (%s -> %s correct of %s).", version, before["correct"], after["correct"], len(validation_rows))
            return {"outcome": "deployed" if deploy else "rejected", "version": version,
                    "live_version": live.version, "candidate_accuracy": after["accuracy"],
                    "live_accuracy": before["accuracy"], "validation_size": len(validation_rows),
                    "new_examples": len(new)}
        except Exception as error:
            LOG.exception("Retraining failed")
            try:
                self._finish("retrain_failed", None, actor_id,
                             {"origin": origin, "error": type(error).__name__,
                              "reason": "Retraining failed. The live model was not changed."})
            except Exception:
                LOG.exception("Could not log the retraining failure")
            return {"outcome": "failed", "reason": "Retraining failed. The live model was not changed."}

    # ------------------------------------------------------------------ scheduling
    def _last_cycle(self, db):
        row = db.execute("""SELECT MAX(created_at) FROM model_events WHERE action IN
                            ('baseline','retrain_deployed','retrain_rejected','retrain_failed')""").fetchone()
        return datetime.fromisoformat(row[0]) if row and row[0] else None

    def next_due_at(self, db):
        settings = self.settings(db)
        last = self._last_cycle(db)
        if not settings["enabled"] or last is None:
            return None
        return (last + timedelta(days=settings["interval_days"])).isoformat(timespec="microseconds")

    def due(self, db, now=None):
        settings = self.settings(db)
        if not settings["enabled"]:
            return False
        now = now or datetime.now(timezone.utc)
        last = self._last_cycle(db)
        if last is not None and now < last + timedelta(days=settings["interval_days"]):
            return False
        active = db.execute("SELECT data_cutoff_id FROM model_versions WHERE status='active'").fetchone()
        new = self._new_examples(self.build_dataset(db), active["data_cutoff_id"] if active else 0)
        return len(new) >= settings["min_new_samples"]

    def run_if_due(self, now=None):
        """Called by the scheduler thread or by ``scripts/retrain_model.py`` (for example from cron)."""
        with closing(connection(self.database_path)) as db:
            if not self.due(db, now):
                return None
        try:
            return self.retrain("scheduled")
        except APIError:
            return None  # another run is already in progress

    # ------------------------------------------------------------------ rollback / restore
    def activate(self, db, version, actor_id):
        """Make a previously deployed version live again. Runs inside the caller's transaction."""
        if not VERSION_PATTERN.fullmatch(version):
            raise APIError(404, "Model version not found.")
        row = db.execute("SELECT * FROM model_versions WHERE version=?", (version,)).fetchone()
        if row is None:
            raise APIError(404, "Model version not found.")
        if row["status"] == "rejected":
            raise APIError(409, "This version failed validation and was never live, so it cannot be restored.")
        if row["status"] == "active":
            return {"changed": False, "version": version}
        started = time.perf_counter()
        try:
            self._load_artifact(version)  # prove the saved model is intact before touching the registry
        except Exception:
            raise APIError(409, "The saved files for this version are missing or damaged. The live model was not changed.") from None
        current = db.execute("SELECT version FROM model_versions WHERE status='active'").fetchone()
        db.execute("UPDATE model_versions SET status='archived' WHERE status='active'")
        db.execute("UPDATE model_versions SET status='active',deployed_at=? WHERE version=?", (utc_now(), version))
        self._event(db, "rolled_back", version, actor_id,
                    {"from_version": current["version"] if current else None, "to_version": version,
                     "duration_ms": round((time.perf_counter() - started) * 1000)})
        self._bad.discard(version)
        return {"changed": True, "version": version, "previous_version": current["version"] if current else None}

    # ------------------------------------------------------------------ administrator overview
    def overview(self, db, provider, serving):
        """Counts and metrics only. Student names and request text are never included."""
        data = self.build_dataset(db)
        active = db.execute("SELECT * FROM model_versions WHERE status='active'").fetchone()
        cutoff = active["data_cutoff_id"] if active else 0
        columns = ("version", "parent_version", "status", "origin", "training_examples", "new_examples",
                   "validation_size", "accuracy", "previous_accuracy", "created_at", "deployed_at")
        versions = [{k: r[k] for k in columns} for r in db.execute("SELECT * FROM model_versions ORDER BY id DESC")]
        events = []
        for r in db.execute("""SELECT e.id,e.action,e.version,e.detail,e.created_at,u.name actor_name FROM model_events e
                               LEFT JOIN users u ON u.id=e.actor_id ORDER BY e.id DESC LIMIT 25"""):
            events.append({"id": r["id"], "action": r["action"], "version": r["version"], "created_at": r["created_at"],
                           "actor_name": r["actor_name"], "detail": json.loads(r["detail"])})
        return {"provider": provider, "serving": serving, "running": self._running,
                "active_version": active["version"] if active else None, "versions": versions, "events": events,
                "settings": self.settings(db), "next_due_at": self.next_due_at(db),
                "data": {"collected": data["total"], "by_source": data["by_source"],
                         "usable": len(data["train"]) + len(data["validation"]), "training": len(data["train"]),
                         "validation_held_out": len(data["validation"]),
                         "new_since_live_model": len(self._new_examples(data, cutoff)),
                         "skipped": data["skipped"], "base_examples": len(data["base_rows"]),
                         "evaluation_examples": len(data["evaluation_rows"])}}
