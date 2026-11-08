"""US10 - AI Model Retraining Pipeline: data collection, validation gate, no downtime, versioning, rollback."""
from datetime import datetime, timedelta, timezone
import itertools
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

from app.database import connection, initialize, seed_demo, utc_now
from app.ml import Classifier
from app.retraining import ModelManager, is_holdout, normalize
from app.server import Application
from tests.test_acceptance import Client

ROOT = Path(__file__).parents[1]
TRAINING = ROOT / "data" / "training.json"
EVALUATION = ROOT / "data" / "evaluation.json"

# One informative English keyword per department. "Kindly regarding my <keyword> thingy <suffix>" has a single
# word the local model knows, so it is unsure and escalates the request to staff, who then label it.
KEYWORDS = {"it": ["wifi", "password", "laptop", "printer", "software"],
            "finance": ["tuition", "scholarship", "refund", "payment", "invoice"],
            "academic": ["transcript", "timetable", "exam", "grades", "enrollment"],
            "health": ["clinic", "doctor", "nurse", "counseling", "medical"]}


# Realistic, varied requests used as consistent staff labels (none appears in data/training.json or evaluation.json).
LABELED = {
    "it": ["The lecture hall projector will not detect my laptop through the HDMI cable.",
           "I keep getting a login failed message when I open the university portal.",
           "My student email account was locked after too many password attempts.",
           "The shared computer lab machines freeze whenever I start the design software.",
           "Wifi in the north dormitory disconnects every few minutes in the evening.",
           "I need antivirus software installed on my new laptop for classes.",
           "Two factor authentication code never arrives on my phone when I sign in.",
           "The library printer jams and prints blank pages for every document.",
           "My laptop cannot reach the campus network after the system update.",
           "I forgot the password for the online learning platform and need access restored.",
           "The eduroam wireless network rejects my credentials on every device.",
           "I cannot download the licensed software because the account verification fails."],
    "finance": ["My tuition invoice shows a late fee even though I paid before the deadline.",
                "When will the scholarship money be transferred to my bank account this semester?",
                "I want to know whether I can pay my tuition in monthly installments.",
                "The refund for my cancelled course has not arrived after three weeks.",
                "I was charged twice for the dormitory payment on the same day.",
                "Please explain why my financial aid award was reduced this term.",
                "I need a payment confirmation receipt to submit to my sponsor.",
                "How do I apply for a tuition discount for siblings studying at the university?",
                "The grant payment is missing from my account balance statement.",
                "I need a financial aid appeal form because my family income changed.",
                "Can my scholarship cover the summer semester tuition fees?",
                "My bank transfer for the fees is pending and the invoice still shows unpaid."],
    "academic": ["I want to drop a course and need to know the deadline for withdrawal.",
                 "Please help me register for the elective that shows as full in the schedule.",
                 "My final exam grade looks wrong and I would like to request a review.",
                 "I need an official transcript sent to another university for my exchange application.",
                 "The timetable has two lectures at the same time on Wednesday.",
                 "Which advisor should approve my change of major to computer science?",
                 "I missed the midterm exam because of travel and want to schedule a makeup.",
                 "How many credits do I still need to complete before graduation?",
                 "My enrollment confirmation is not showing the course I registered for.",
                 "I would like to know the prerequisites for the advanced algorithms course.",
                 "Please check my degree audit because a completed course is not counted.",
                 "I need a letter confirming my enrollment status for a visa application."],
    "health": ["I need to book an appointment with the campus doctor for a persistent cough.",
               "Where can I get a medical certificate for my absence last week?",
               "I would like to speak with a counselor because I feel very stressed before exams.",
               "The nurse told me to bring vaccination records, and I do not know where to upload them.",
               "I injured my ankle during the sports class and need to see someone at the clinic.",
               "Can the medical center issue a certificate allowing me to skip physical education?",
               "I need information about the student health insurance coverage at the clinic.",
               "How do I schedule a counseling session about sleep problems and anxiety?",
               "I have a fever and a sore throat and need advice from the campus nurse.",
               "The clinic opening hours on Saturday are not listed anywhere, please confirm.",
               "I need a flu vaccine and want to know if the university clinic provides it.",
               "Please arrange a medical checkup required for my dormitory contract."]}


def suffixes():
    """Distinct letter-only words, because the tokenizer ignores digits."""
    for a, b, c in itertools.product("bcdfghjklmnpqrstvwxz", "aeiou", "bcdfghjklmnpqrstvwxz"):
        yield a + b + c + "on"


class SlowClassifier(Classifier):
    """Stands in for a long training job so a run overlaps live routing."""
    delay = 0.0

    def __init__(self, path):
        time.sleep(type(self).delay)
        super().__init__(path)


class RetrainingBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite3"
        self.app = Application(self.path, classifier=Classifier(TRAINING))
        seed_demo(self.path)
        self.student, self.support, self.admin = [Client(self.app) for _ in range(3)]
        for client, email, password in [(self.student, "240103030@sdu.edu.kz", "Student123!"),
                                        (self.support, "helpdesk@sdu.edu.kz", "Support123!"),
                                        (self.admin, "admin@sdu.edu.kz", "Admin12345!")]:
            self.assertEqual(client.login(email, password)[0], 200)
        with connection(self.path) as db:
            self.admin_id = db.execute("SELECT id FROM users WHERE role='admin'").fetchone()[0]
        self.words = suffixes()

    def tearDown(self):
        self.app.stop_scheduler()
        self.temp.cleanup()

    @property
    def manager(self):
        return self.app.models

    def label(self, department, keyword=None, message=None):
        """Student submits a vague request, staff routes it: one labeled example."""
        keyword = keyword or KEYWORDS[department][0]
        message = message or f"Kindly regarding my {keyword} thingy {next(self.words)}"
        status, data = self.student.create(message=message)
        self.assertEqual(status, 201, data)
        request = data["request"]
        self.assertEqual(request["status"], "Escalated", request["classification"])
        status, result = self.support.call("POST", f"/api/requests/{request['id']}/route",
                                           {"department_code": department, "version": request["version"]})
        self.assertEqual(status, 200, result)
        return result["request"]

    def add_label(self, department, index, source="escalation_outcome"):
        """Insert a correct staff label for a realistic text (the API hooks are covered by their own tests)."""
        text = LABELED[department][index]
        status, data = self.student.create(message=text)
        self.assertEqual(status, 201, data)
        with connection(self.path) as db:
            db.execute("INSERT INTO training_samples (request_id,source,label,text,created_at) VALUES (?,?,?,?,?)",
                       (data["request"]["id"], source, department, text, utc_now()))

    def label_consistent(self, per_department=8):
        for department in LABELED:
            for i in range(per_department):
                self.add_label(department, i)

    def label_poison(self, copies=2):
        """Authored training texts with rotated, wrong labels: staff 'corrections' that would harm the model."""
        order = ["it", "finance", "academic", "health"]
        rotated = {order[i]: order[(i + 1) % 4] for i in range(4)}
        rows = json.loads(TRAINING.read_text())
        for row in rows:
            for _ in range(copies):
                status, data = self.student.create(message=f"{row['text']} {next(self.words)}")
                self.assertEqual(status, 201, data)
                request = data["request"]
                wrong = rotated[row["label"]]
                if request["department_code"] == wrong:
                    continue
                status, result = self.support.call("POST", f"/api/requests/{request['id']}/route",
                                                   {"department_code": wrong, "version": request["version"]})
                self.assertEqual(status, 200, result)

    def active(self):
        with connection(self.path) as db:
            return db.execute("SELECT * FROM model_versions WHERE status='active'").fetchone()

    def versions(self):
        with connection(self.path) as db:
            return [dict(r) for r in db.execute("SELECT * FROM model_versions ORDER BY id")]

    def events(self):
        with connection(self.path) as db:
            return [dict(r) for r in db.execute("SELECT * FROM model_events ORDER BY id")]


class LabeledDataCollectionTests(RetrainingBase):
    def sample_rows(self):
        with connection(self.path) as db:
            return [dict(r) for r in db.execute("SELECT * FROM training_samples ORDER BY id")]

    def test_US10_staff_routing_of_an_escalated_request_is_stored_as_a_label(self):
        r = self.label("finance", "tuition")
        rows = self.sample_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["source"], rows[0]["label"], rows[0]["request_id"]), ("escalation_outcome", "finance", r["id"]))
        self.assertIn("tuition", rows[0]["text"])

    def test_US10_staff_reassignment_of_an_ai_route_is_a_correction_label(self):
        status, data = self.student.create()
        request = data["request"]
        self.assertEqual(request["department_code"], "it")
        self.support.call("POST", f"/api/requests/{request['id']}/route", {"department_code": "academic", "version": request["version"]})
        rows = self.sample_rows()
        self.assertEqual([(r["source"], r["label"]) for r in rows], [("staff_correction", "academic")])

    def test_US10_repeating_the_same_route_does_not_add_a_label(self):
        r = self.label("it", "wifi")
        self.support.call("POST", f"/api/requests/{r['id']}/route", {"department_code": "it", "version": r["version"]})
        self.assertEqual(len(self.sample_rows()), 1)

    def test_US10_reopened_request_is_stored_as_a_weaker_label_with_its_department(self):
        status, data = self.student.create()
        request = data["request"]
        in_progress = self.support.call("POST", f"/api/requests/{request['id']}/status", {"status": "In Progress", "version": request["version"]})[1]["request"]
        resolved = self.support.call("POST", f"/api/requests/{request['id']}/status",
                                     {"status": "Resolved", "resolution": "Your wireless access was restored.", "version": in_progress["version"]})[1]["request"]
        self.assertEqual(self.sample_rows(), [])  # resolving alone is not a label
        self.support.call("POST", f"/api/requests/{request['id']}/status", {"status": "In Progress", "version": resolved["version"]})
        rows = self.sample_rows()
        self.assertEqual([(r["source"], r["label"]) for r in rows], [("reopened", "it")])

    def test_US10_deleting_a_request_removes_its_labels(self):
        r = self.label("health", "clinic")
        self.assertEqual(len(self.sample_rows()), 1)
        # Routed requests are 'Received', so the student may still delete them.
        self.assertEqual(self.student.call("DELETE", f"/api/requests/{r['id']}", {"version": r["version"]})[0], 200)
        self.assertEqual(self.sample_rows(), [])

    def test_US10_older_corrections_are_backfilled_once(self):
        r = self.label("it", "printer")
        with connection(self.path) as db:
            db.execute("DELETE FROM training_samples")  # simulate a database created before US10
        initialize(self.path)
        initialize(self.path)
        rows = self.sample_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["label"], rows[0]["request_id"], rows[0]["source"]), ("it", r["id"], "staff_correction"))

    def test_US10_dataset_excludes_unusable_text_and_never_mixes_validation_into_training(self):
        self.label_consistent(per_department=10)
        self.label("it", message="Не могу подключиться к интернету в университете.")
        with connection(self.path) as db:
            data = self.manager.build_dataset(db)
        train = {normalize(r["text"]) for r in data["train"]}
        validation = {normalize(r["text"]) for r in data["validation"]}
        self.assertFalse(train & validation)
        self.assertTrue(all(is_holdout(t) for t in validation))
        self.assertFalse(any(is_holdout(t) for t in train))
        base = {normalize(r["text"]) for r in json.loads(TRAINING.read_text())}
        evaluation = {normalize(r["text"]) for r in json.loads(EVALUATION.read_text())}
        self.assertFalse((train | validation) & (base | evaluation))
        self.assertEqual(data["skipped"].get("not_usable_by_local_model"), 1)
        self.assertEqual(len(train) + len(validation), 40)
        self.assertGreater(len(validation), 0)

    def test_US10_a_later_staff_decision_replaces_an_earlier_label_for_the_same_request(self):
        status, data = self.student.create(message="Kindly regarding my wifi thingy zeton")
        request = data["request"]
        first = self.support.call("POST", f"/api/requests/{request['id']}/route", {"department_code": "finance", "version": request["version"]})[1]["request"]
        self.support.call("POST", f"/api/requests/{request['id']}/route", {"department_code": "it", "version": first["version"]})
        with connection(self.path) as db:
            data = self.manager.build_dataset(db)
        used = data["train"] + data["validation"]
        self.assertEqual([r["label"] for r in used], ["it"])


class RetrainingPipelineTests(RetrainingBase):
    def test_US10_baseline_version_is_registered_and_served(self):
        active = self.active()
        self.assertEqual(active["origin"], "baseline")
        self.assertEqual(active["version"], Classifier(TRAINING).version)
        self.assertTrue((Path(self.temp.name) / "models" / f"{active['version']}.json").is_file())
        self.assertEqual(self.student.call("GET", "/api/ai/status")[1]["ai"]["model"], active["version"])
        self.assertEqual([e["action"] for e in self.events()], ["baseline"])
        self.assertEqual(Application(self.path).models.live.version, active["version"])  # second start is idempotent
        self.assertEqual(len(self.versions()), 1)

    def test_US10_retrained_model_is_validated_and_deployed_when_not_worse(self):
        old = self.active()["version"]
        self.label_consistent()
        result = self.manager.retrain("manual", self.admin_id)
        self.assertEqual(result["outcome"], "deployed", result)
        self.assertGreaterEqual(result["candidate_accuracy"], result["live_accuracy"])
        active = self.active()
        self.assertNotEqual(active["version"], old)
        self.assertEqual((active["parent_version"], active["origin"], active["new_examples"]), (old, "manual", 32))
        self.assertGreater(active["training_examples"], 96)
        self.assertGreaterEqual(active["validation_size"], 40)
        self.assertEqual([v["status"] for v in self.versions()], ["archived", "active"])
        self.assertEqual(self.events()[-1]["action"], "retrain_deployed")
        # New requests are routed with the new version straight away.
        status, data = self.student.create()
        self.assertEqual(data["request"]["classification"]["model_version"], active["version"])
        self.assertEqual(self.student.call("GET", "/api/ai/status")[1]["ai"]["model"], active["version"])

    def test_US10_candidate_trained_on_staff_labels_learns_them(self):
        """The new knowledge actually reaches the live model: staff teach it a campus term it did not know."""
        text = "Kindly regarding my kaspi thingy"
        before = self.app.classifier.classify(text)
        self.assertNotEqual(before["suggested_code"], "finance")
        for i in range(12):
            self.label("finance", message=f"Kindly regarding my kaspi thingy {next(self.words)}")
        self.assertEqual(self.manager.retrain("manual", self.admin_id)["outcome"], "deployed")
        after = self.app.classifier.classify(text)
        self.assertEqual(after["suggested_code"], "finance")
        self.assertIn("kaspi", self.manager.live.model.vocabulary)

    def test_US10_underperforming_candidate_is_rejected_and_the_live_model_stays(self):
        old = self.active()["version"]
        self.label_poison()
        result = self.manager.retrain("manual", self.admin_id)
        self.assertEqual(result["outcome"], "rejected", result)
        self.assertLess(result["candidate_accuracy"], result["live_accuracy"])
        self.assertEqual(self.active()["version"], old)
        self.assertEqual(self.app.classifier.version, old)
        statuses = {v["version"]: v["status"] for v in self.versions()}
        self.assertEqual(sorted(statuses.values()), ["active", "rejected"])
        self.assertEqual(self.events()[-1]["action"], "retrain_rejected")
        status, data = self.student.create()
        self.assertEqual(data["request"]["classification"]["model_version"], old)
        # A rejected version was never live and cannot be restored.
        rejected = [v for v, s in statuses.items() if s == "rejected"][0]
        self.assertEqual(self.admin.call("POST", f"/api/admin/models/{rejected}/activate", {})[0], 409)
        # Running again without new data does not re-evaluate the same rejected model.
        again = self.manager.retrain("manual", self.admin_id)
        self.assertEqual(again["outcome"], "skipped")

    def test_US10_equal_accuracy_deploys(self):
        self.label_consistent(per_department=2)
        with mock.patch("app.retraining.evaluate", side_effect=lambda model, rows: {"correct": 30, "total": 40, "accuracy": .75, "per_department": {}}):
            self.assertEqual(self.manager.retrain("manual", self.admin_id)["outcome"], "deployed")

    def test_US10_one_fewer_correct_answer_is_rejected(self):
        self.label_consistent(per_department=2)
        scores = iter([{"correct": 40, "total": 40, "accuracy": 1.0, "per_department": {}},
                       {"correct": 39, "total": 40, "accuracy": .975, "per_department": {}}])
        with mock.patch("app.retraining.evaluate", side_effect=lambda model, rows: next(scores)):
            self.assertEqual(self.manager.retrain("manual", self.admin_id)["outcome"], "rejected")

    def test_US10_run_without_new_labeled_data_is_skipped_and_logged(self):
        result = self.manager.retrain("manual", self.admin_id)
        self.assertEqual(result["outcome"], "skipped")
        self.assertEqual(len(self.versions()), 1)
        self.assertEqual(self.events()[-1]["action"], "retrain_skipped")

    def test_US10_failure_during_training_leaves_the_live_model_untouched(self):
        old = self.active()["version"]
        self.label_consistent(per_department=2)
        with mock.patch("app.retraining.Classifier", side_effect=RuntimeError("disk full")), \
                self.assertLogs("routing.retraining", level="ERROR"):
            result = self.manager.retrain("manual", self.admin_id)
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(self.active()["version"], old)
        self.assertEqual(self.app.classifier.version, old)
        self.assertEqual(self.events()[-1]["action"], "retrain_failed")
        self.assertNotIn("disk full", self.events()[-1]["detail"])
        self.assertEqual(self.student.create()[0], 201)  # routing still works
        # The lock is released, so the next run can succeed.
        self.assertEqual(self.manager.retrain("manual", self.admin_id)["outcome"], "deployed")

    def test_US10_retraining_does_not_interrupt_live_routing(self):
        old = self.active()["version"]
        self.label_consistent()
        SlowClassifier.delay = 0.8
        try:
            with mock.patch("app.retraining.Classifier", SlowClassifier):
                status, data = self.admin.call("POST", "/api/admin/retraining/run", {})
                self.assertEqual((status, data), (202, {"started": True}))
                served, errors, versions = 0, [], set()
                deadline = time.monotonic() + 20
                while self.manager.running is not None and time.monotonic() < deadline:
                    started = time.perf_counter()
                    status, result = self.student.create()
                    if status != 201:
                        errors.append((status, result))
                    else:
                        served += 1
                        versions.add(result["request"]["classification"]["model_version"])
                    self.assertLess(time.perf_counter() - started, 3)
                self.assertTrue(self.manager.wait(20))
        finally:
            SlowClassifier.delay = 0.0
        self.assertEqual(errors, [])
        self.assertGreaterEqual(served, 3, "requests should be served while the model trains")
        self.assertIn(old, versions)
        self.assertNotEqual(self.active()["version"], old)
        self.assertEqual(self.events()[-1]["action"], "retrain_deployed")
        self.assertEqual(self.student.create()[1]["request"]["classification"]["model_version"], self.active()["version"])

    def test_US10_only_one_run_at_a_time(self):
        self.label_consistent(per_department=2)
        SlowClassifier.delay = 0.6
        try:
            with mock.patch("app.retraining.Classifier", SlowClassifier):
                self.assertEqual(self.admin.call("POST", "/api/admin/retraining/run", {})[0], 202)
                status, body = self.admin.call("POST", "/api/admin/retraining/run", {})
                self.assertEqual(status, 409, body)
                self.assertTrue(self.manager.wait(20))
        finally:
            SlowClassifier.delay = 0.0
        self.assertEqual(len(self.versions()), 2)
        self.assertEqual(self.admin.call("POST", "/api/admin/retraining/run", {})[0], 202)  # lock was released
        self.manager.wait(20)

    def test_US10_rollback_restores_a_previous_version_quickly_and_survives_restart(self):
        old = self.active()["version"]
        self.label_consistent()
        self.manager.retrain("manual", self.admin_id)
        new = self.active()["version"]
        started = time.perf_counter()
        status, result = self.admin.call("POST", f"/api/admin/models/{old}/activate", {})
        elapsed = time.perf_counter() - started
        self.assertEqual((status, result["changed"], result["version"]), (200, True, old), result)
        self.assertLess(elapsed, 15 * 60)
        self.assertLess(elapsed, 5)  # in practice milliseconds
        self.assertEqual(self.active()["version"], old)
        self.assertEqual({v["version"]: v["status"] for v in self.versions()}, {old: "active", new: "archived"})
        self.assertEqual(self.app.classifier.version, old)
        self.assertEqual(self.student.create()[1]["request"]["classification"]["model_version"], old)
        last = self.events()[-1]
        self.assertEqual((last["action"], last["version"], last["actor_id"]), ("rolled_back", old, self.admin_id))
        self.assertEqual(json.loads(last["detail"])["from_version"], new)
        self.assertEqual(Application(self.path).models.live.version, old)  # a restart keeps the restored model
        # The newer version can be restored again (roll forward) and activating the live one is a no-op.
        self.assertEqual(self.admin.call("POST", f"/api/admin/models/{new}/activate", {})[1]["changed"], True)
        self.assertEqual(self.app.classifier.version, new)
        self.assertEqual(self.admin.call("POST", f"/api/admin/models/{new}/activate", {})[1]["changed"], False)

    def test_US10_rollback_refuses_missing_or_damaged_files_and_unknown_versions(self):
        old = self.active()["version"]
        self.label_consistent()
        self.manager.retrain("manual", self.admin_id)
        new = self.active()["version"]
        artifact = Path(self.temp.name) / "models" / f"{old}.json"
        artifact.write_text("[]")  # damaged
        status, body = self.admin.call("POST", f"/api/admin/models/{old}/activate", {})
        self.assertEqual(status, 409, body)
        self.assertEqual(self.active()["version"], new)
        artifact.unlink()
        self.assertEqual(self.admin.call("POST", f"/api/admin/models/{old}/activate", {})[0], 409)
        self.assertEqual(self.admin.call("POST", "/api/admin/models/nb-000000000000/activate", {})[0], 404)
        self.assertEqual(self.admin.call("POST", "/api/admin/models/..%2f..%2fetc/activate", {})[0], 404)
        self.assertEqual(self.app.classifier.version, new)

    def test_US10_deployed_model_survives_restart_and_another_process_picks_up_changes(self):
        self.label_consistent()
        self.manager.retrain("manual", self.admin_id)
        deployed = self.active()["version"]
        restarted = Application(self.path, classifier=Classifier(TRAINING))
        self.assertEqual(restarted.classifier.version, deployed)
        # Another process (for example scripts/retrain_model.py) restores the baseline; this server follows.
        baseline = Classifier(TRAINING).version
        other = ModelManager(self.path, TRAINING, EVALUATION)
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            other.activate(db, baseline, None)
            db.commit()
        self.assertEqual(self.app.classifier.version, deployed)  # not yet noticed
        status, data = self.student.create()
        self.assertEqual(data["request"]["classification"]["model_version"], baseline)
        self.assertEqual(self.app.classifier.version, baseline)

    def test_US10_missing_active_artifact_falls_back_without_crashing(self):
        self.label_consistent()
        self.manager.retrain("manual", self.admin_id)
        (Path(self.temp.name) / "models" / f"{self.active()['version']}.json").unlink()
        with self.assertLogs("routing.retraining", level="ERROR"):
            restarted = Application(self.path, classifier=Classifier(TRAINING))
        self.assertEqual(restarted.classifier.version, Classifier(TRAINING).version)
        student = Client(restarted)
        student.login("240103030@sdu.edu.kz", "Student123!")
        self.assertEqual(student.create()[0], 201)


class ScheduleTests(RetrainingBase):
    def due(self, now=None):
        with connection(self.path) as db:
            return self.manager.due(db, now)

    def test_US10_retraining_is_due_only_after_the_interval_with_enough_new_data(self):
        later = datetime.now(timezone.utc) + timedelta(days=31)
        self.assertFalse(self.due(later))  # interval elapsed, but no new data
        for i in range(4):
            self.add_label("it", i)
        self.assertFalse(self.due(later))  # 4 new examples, 5 needed
        self.add_label("finance", 0)
        self.assertFalse(self.due())  # enough data, interval not elapsed
        self.assertTrue(self.due(later))
        self.assertIsNone(self.manager.run_if_due())  # nothing runs early
        self.assertEqual(len(self.versions()), 1)
        result = self.manager.run_if_due(later)
        self.assertEqual(result["outcome"], "deployed", result)
        self.assertEqual(self.active()["origin"], "scheduled")
        # The clock restarts after a cycle.
        self.assertFalse(self.due(later + timedelta(days=1)))

    def test_US10_schedule_settings_are_adjustable_without_code_changes(self):
        later = datetime.now(timezone.utc) + timedelta(days=8)
        self.label_consistent(per_department=2)
        self.assertFalse(self.due(later))
        status, data = self.admin.call("PUT", "/api/admin/retraining/settings", {"interval_days": 7, "min_new_samples": 3})
        self.assertEqual((status, data["settings"]), (200, {"enabled": True, "interval_days": 7, "min_new_samples": 3}))
        self.assertTrue(self.due(later))
        self.admin.call("PUT", "/api/admin/retraining/settings", {"enabled": False})
        self.assertFalse(self.due(later))
        self.assertIsNone(self.manager.run_if_due(later))
        self.assertEqual(Application(self.path).models.settings(connection(self.path)), {"enabled": False, "interval_days": 7, "min_new_samples": 3})

    def test_US10_scheduler_thread_starts_and_stops_cleanly(self):
        self.app.start_scheduler(poll_seconds=0.05)
        self.app.start_scheduler(poll_seconds=0.05)  # idempotent
        time.sleep(0.2)
        self.app.stop_scheduler()
        self.assertEqual(len(self.versions()), 1)  # nothing was due


class AdministrationTests(RetrainingBase):
    def test_US10_only_administrators_can_use_the_retraining_endpoints(self):
        for client, expected in [(self.student, 403), (self.support, 403), (Client(self.app), 401)]:
            self.assertEqual(client.call("GET", "/api/admin/retraining")[0], expected)
            self.assertEqual(client.call("PUT", "/api/admin/retraining/settings", {"enabled": False})[0], expected)
            self.assertEqual(client.call("POST", "/api/admin/retraining/run", {})[0], expected)
            self.assertEqual(client.call("POST", f"/api/admin/models/{self.active()['version']}/activate", {})[0], expected)
        self.assertEqual(self.admin.call("GET", "/api/admin/retraining")[0], 200)

    def test_US10_mutations_need_a_csrf_token(self):
        self.assertEqual(self.admin.call("POST", "/api/admin/retraining/run", {}, csrf=False)[0], 403)
        self.assertEqual(self.admin.call("PUT", "/api/admin/retraining/settings", {"enabled": False}, csrf=False)[0], 403)

    def test_US10_overview_has_counts_and_versions_but_no_student_content(self):
        self.label_consistent(per_department=3)
        self.label("it", message="Kindly regarding my secretwordzzz laptop thingy")  # sent through the real routing hook
        self.manager.retrain("manual", self.admin_id)
        status, data = self.admin.call("GET", "/api/admin/retraining")
        self.assertEqual(status, 200)
        text = json.dumps(data)
        for private in ["secretwordzzz", "Kindly regarding", "Demo Student", "240103030"]:
            self.assertNotIn(private, text)
        self.assertEqual(data["data"]["by_source"], {"staff_correction": 0, "escalation_outcome": 13, "reopened": 0})
        self.assertEqual(data["data"]["collected"], 13)
        self.assertEqual(data["data"]["evaluation_examples"], 40)
        self.assertEqual(data["active_version"], self.active()["version"])
        self.assertEqual([v["status"] for v in data["versions"]], ["active", "archived"])
        self.assertTrue(data["serving"])
        self.assertEqual(data["events"][0]["action"], "retrain_deployed")
        self.assertEqual(data["events"][0]["actor_name"], "Administrator")
        self.assertEqual(data["data"]["new_since_live_model"], 0)

    def test_US10_settings_are_validated(self):
        for bad in [{}, {"enabled": "yes"}, {"interval_days": 0}, {"interval_days": 366}, {"interval_days": True},
                    {"interval_days": 1.5}, {"min_new_samples": 0}, {"min_new_samples": "5"}]:
            self.assertEqual(self.admin.call("PUT", "/api/admin/retraining/settings", bad)[0], 400, bad)

    def test_US10_retraining_is_a_sprint_2_feature(self):
        app = Application(self.path, sprint=1, classifier=Classifier(TRAINING))
        admin = Client(app)
        admin.login("admin@sdu.edu.kz", "Admin12345!")
        self.assertEqual(admin.call("GET", "/api/admin/retraining")[0], 403)

    def test_US10_gemini_mode_is_not_replaced_by_the_local_model(self):
        class FakeGemini:
            provider, version, training_size = "gemini", "gemini:test", 0

            def status(self):
                return {"provider": "gemini", "model": "test", "configured": True, "connection_verified": False,
                        "last_error": None, "training_examples": None}

            def classify(self, text):
                return {"suggested_code": "it", "confidence": 0.9, "reason": "test", "model_version": "gemini:test",
                        "provider": "gemini", "provider_result": "success"}

        app = Application(Path(self.temp.name) / "gemini.sqlite3", classifier=FakeGemini())
        seed_demo(Path(self.temp.name) / "gemini.sqlite3")
        admin, student = Client(app), Client(app)
        admin.login("admin@sdu.edu.kz", "Admin12345!")
        student.login("240103030@sdu.edu.kz", "Student123!")
        self.assertEqual(app.classifier.version, "gemini:test")
        overview = admin.call("GET", "/api/admin/retraining")[1]
        self.assertEqual((overview["provider"], overview["serving"]), ("gemini", False))
        self.assertEqual(student.create()[1]["request"]["classification"]["model_version"], "gemini:test")


class CommandLineTests(RetrainingBase):
    def test_US10_command_line_status_run_and_rollback(self):
        from scripts import retrain_model
        base = self.active()["version"]
        self.label_consistent(per_department=3)
        import contextlib
        import io

        def run(*args):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = retrain_model.main(["--database", str(self.path), *args])
            return code, out.getvalue()

        code, out = run("--status")
        self.assertEqual(code, 0)
        self.assertIn(base, out)
        code, out = run("--run")
        self.assertEqual(code, 0, out)
        self.assertIn("deployed", out)
        deployed = self.active()["version"]
        self.assertNotEqual(deployed, base)
        code, out = run("--rollback", base)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.active()["version"], base)
        self.assertEqual(run("--rollback", "nb-000000000000")[0], 1)
        self.assertEqual(run("--due")[0], 0)


if __name__ == "__main__":
    unittest.main()
