"""User Story 6: urgent request detection, immediate routing, department alerts, escalation."""
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from app.database import connection, seed_demo
from app.llm import INSTRUCTIONS, GeminiClassifier
from app.ml import Classifier
from app.server import Application
from app.urgency import detect_urgency
from tests.test_acceptance import Client

EMERGENCY = "I have severe chest pain and I cannot breathe, please send help to the library."
NORMAL = "My laptop cannot connect to campus wifi and the wireless network is unavailable."


class UrgentRequestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite3"
        self.app = Application(self.path, classifier=Classifier(Path(__file__).parents[1] / "data/training.json"))
        seed_demo(self.path)
        self.student, self.other, self.support, self.admin = [Client(self.app) for _ in range(4)]
        for client, email, password in [(self.student, "240103030@sdu.edu.kz", "Student123!"),
                                        (self.other, "250103031@sdu.edu.kz", "Student123!"),
                                        (self.support, "helpdesk@sdu.edu.kz", "Support123!"),
                                        (self.admin, "admin@sdu.edu.kz", "Admin12345!")]:
            self.assertEqual(client.login(email, password)[0], 200)

    def tearDown(self):
        self.temp.cleanup()

    def submit(self, message, **extra):
        status, data = self.student.create(message, **extra)
        self.assertEqual(status, 201, data)
        return data["request"]

    # --- Scenario 1: flagged, routed immediately, bypasses the review queue, department alerted
    def test_US6_emergency_is_flagged_routed_and_alerted(self):
        r = self.submit(EMERGENCY)
        self.assertEqual(r["priority"], "urgent")
        self.assertEqual(r["status"], "Received")          # not Escalated: bypassed the review queue
        self.assertEqual(r["department_code"], "health")
        self.assertIsNone(r["review_due_at"])
        self.assertTrue(r["classification"]["urgency"]["detected"])
        alerts = self.support.call("GET", "/api/staff/alerts")[1]["alerts"]
        self.assertEqual(len(alerts), 1)
        self.assertEqual((alerts[0]["request_id"], alerts[0]["department_code"], alerts[0]["kind"]),
                         (r["id"], "health", "urgent"))
        self.assertLess(alerts[0]["age_seconds"], 30)       # story: alert within 30 seconds
        self.assertFalse(alerts[0]["overdue"])

    def test_US6_emergency_bypasses_review_even_when_ai_is_unavailable(self):
        class Down:
            version, training_size = "down", 0
            def status(self): return {"provider": "gemini", "model": "x", "configured": True}
            def classify(self, text):
                return {"suggested_code": "review", "confidence": 0.0, "reason": "down", "review_required": True,
                        "provider": "gemini", "provider_result": "unavailable", "provider_error": "timeout",
                        "model_version": "down", "matched_terms": [], "probabilities": {}}
        app = Application(self.path, classifier=Down())
        student = Client(app); student.login("240103030@sdu.edu.kz", "Student123!")
        status, data = student.create(EMERGENCY)
        self.assertEqual(status, 201)
        self.assertEqual((data["request"]["status"], data["request"]["priority"]), ("Received", "urgent"))
        self.assertEqual(data["request"]["department_code"], "health")

    def test_US6_safety_emergency_goes_to_campus_security(self):
        r = self.submit("Someone attacked me near the dormitory and I am scared, please send security.")
        self.assertEqual(r["department_code"], "security")

    def test_US6_student_is_told_in_notification(self):
        r = self.submit(EMERGENCY)
        note = self.student.call("GET", "/api/notifications")[1]["notifications"][0]
        self.assertIn("urgent", note["message"].lower())
        self.assertIn(f"REQ-{r['id']:05d}", note["message"])

    # --- Fail cases from the story
    def test_US6_normal_request_is_not_urgent_and_creates_no_alert(self):
        r = self.submit(NORMAL)
        self.assertEqual((r["priority"], r["department_code"]), ("normal", "it"))
        self.assertEqual(self.support.call("GET", "/api/staff/alerts")[1]["alerts"], [])

    def test_US6_negated_wording_does_not_trigger(self):
        self.assertFalse(detect_urgency("Grades", "This is not an emergency, I just have a question about grades.")["detected"])

    def test_US6_manual_urgent_label_is_kept_but_is_not_an_emergency_alert(self):
        r = self.submit(NORMAL, priority="urgent")
        self.assertEqual((r["priority"], r["department_code"]), ("urgent", "it"))
        self.assertEqual(self.support.call("GET", "/api/staff/alerts")[1]["alerts"], [])

    # --- Scenario 2: visible to staff above normal requests
    def test_US6_urgent_requests_sort_above_older_normal_requests(self):
        normal = self.submit(NORMAL)
        urgent = self.submit(EMERGENCY)
        rows = self.support.call("GET", "/api/staff/requests?open=1")[1]["requests"]
        self.assertEqual([x["id"] for x in rows], [urgent["id"], normal["id"]])
        self.assertEqual(self.support.call("GET", "/api/staff/requests?priority=urgent")[1]["requests"][0]["id"], urgent["id"])

    # --- Alert lifecycle and permissions
    def test_US6_alert_can_be_acknowledged_once_and_disappears(self):
        self.submit(EMERGENCY)
        alert = self.support.call("GET", "/api/staff/alerts")[1]["alerts"][0]
        self.assertEqual(self.support.call("POST", f"/api/staff/alerts/{alert['id']}/ack", {})[0], 200)
        self.assertEqual(self.support.call("POST", f"/api/staff/alerts/{alert['id']}/ack", {})[0], 200)  # idempotent
        self.assertEqual(self.support.call("GET", "/api/staff/alerts")[1]["alerts"], [])
        self.assertEqual(self.support.call("POST", "/api/staff/alerts/9999/ack", {})[0], 404)

    def test_US6_deferred_alert_is_marked_overdue_after_two_minutes(self):
        self.submit(EMERGENCY)
        old = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat(timespec="microseconds")
        with connection(self.path) as db:
            db.execute("UPDATE urgent_alerts SET created_at=?", (old,))
        self.assertTrue(self.support.call("GET", "/api/staff/alerts")[1]["alerts"][0]["overdue"])

    def test_US6_alert_endpoints_are_staff_only(self):
        self.submit(EMERGENCY)
        for client in (self.student, self.admin):
            self.assertEqual(client.call("GET", "/api/staff/alerts")[0], 403)
            self.assertEqual(client.call("POST", "/api/staff/alerts/1/ack", {})[0], 403)

    # --- Constraint: a missed emergency reported afterward is escalated to a human immediately
    def test_US6_missed_emergency_is_escalated_by_the_student(self):
        r = self.submit(NORMAL)
        self.assertEqual(self.support.call("GET", "/api/staff/alerts")[1]["alerts"], [])
        status, data = self.student.call("POST", f"/api/requests/{r['id']}/emergency",
                                         {"version": r["version"], "note": "I am actually feeling very unwell"})
        self.assertEqual(status, 200, data)
        self.assertEqual(data["request"]["priority"], "urgent")
        alert = self.support.call("GET", "/api/staff/alerts")[1]["alerts"][0]
        self.assertEqual((alert["kind"], alert["request_id"]), ("escalation", r["id"]))
        self.assertIn("very unwell", alert["reason"])
        # repeating while the alert is open does not create duplicates
        again = self.student.call("POST", f"/api/requests/{r['id']}/emergency", {"version": data["request"]["version"]})
        self.assertEqual(again[0], 200)
        self.assertEqual(len(self.support.call("GET", "/api/staff/alerts")[1]["alerts"]), 1)

    def test_US6_missed_emergency_on_review_queue_request_gets_routed(self):
        r = self.submit("I need some assistance with something unclear.")  # too little evidence, so it waits in staff review
        self.assertEqual(r["status"], "Escalated")
        status, data = self.student.call("POST", f"/api/requests/{r['id']}/emergency", {"version": r["version"]})
        self.assertEqual(status, 200, data)
        self.assertEqual((data["request"]["status"], data["request"]["department_code"]), ("Received", "health"))
        self.assertIsNone(data["request"]["review_due_at"])

    def test_US6_support_can_escalate_to_a_chosen_department(self):
        r = self.submit(NORMAL)
        status, data = self.support.call("POST", f"/api/requests/{r['id']}/emergency",
                                         {"version": r["version"], "department_code": "security"})
        self.assertEqual(status, 200, data)
        self.assertEqual(self.support.call("GET", "/api/staff/alerts")[1]["alerts"][0]["department_code"], "security")

    def test_US6_missed_emergency_rules(self):
        r = self.submit(NORMAL)
        self.assertEqual(self.other.call("POST", f"/api/requests/{r['id']}/emergency", {"version": 1})[0], 404)  # not the owner
        self.assertEqual(self.admin.call("POST", f"/api/requests/{r['id']}/emergency", {"version": 1})[0], 403)
        self.assertEqual(self.student.call("POST", f"/api/requests/{r['id']}/emergency", {"version": 99})[0], 409)
        self.assertEqual(self.student.call("POST", f"/api/requests/{r['id']}/emergency", {})[0], 400)

    # --- Editing
    def test_US6_editing_in_an_emergency_flags_and_alerts_but_never_downgrades(self):
        r = self.submit(NORMAL)
        status, data = self.student.call("PUT", f"/api/requests/{r['id']}",
                                         {"title": "Support request", "message": EMERGENCY, "version": r["version"]})
        self.assertEqual(status, 200, data)
        self.assertEqual((data["request"]["priority"], data["request"]["department_code"]), ("urgent", "health"))
        self.assertEqual(len(self.support.call("GET", "/api/staff/alerts")[1]["alerts"]), 1)
        back = self.student.call("PUT", f"/api/requests/{r['id']}",
                                 {"title": "Support request", "message": NORMAL, "version": data["request"]["version"]})
        self.assertEqual(back[1]["request"]["priority"], "urgent")

    # --- Constraint: detection must not slow classification by more than 1 second
    def test_US6_detection_adds_far_less_than_one_second(self):
        start = time.perf_counter()
        for _ in range(100):
            detect_urgency("Support request", EMERGENCY * 5)
        self.assertLess((time.perf_counter() - start) / 100, 0.05)  # per call, with a wide margin

    def test_US6_russian_and_kazakh_emergencies_are_flagged(self):
        r = self.submit("У меня сильная боль в груди, пожалуйста вызовите скорую помощь")
        self.assertEqual((r["priority"], r["status"], r["department_code"]), ("urgent", "Received", "health"))
        self.assertTrue(detect_urgency("Көмек", "Мен тыныстай алмай жатырмын")["detected"])
        self.assertFalse(detect_urgency("Портал", "Не могу войти в портал")["detected"])

    # --- Supervisor re-notification for deferred alerts (> 2 minutes without acknowledgement)
    def age_alerts(self, minutes):
        old = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat(timespec="microseconds")
        with connection(self.path) as db:
            db.execute("UPDATE urgent_alerts SET created_at=?", (old,))

    def test_US6_administrator_sees_only_overdue_alerts_without_request_content(self):
        self.submit(EMERGENCY)
        self.assertEqual(self.admin.call("GET", "/api/admin/alerts")[1]["alerts"], [])   # fresh: not overdue
        self.age_alerts(3)
        status, data = self.admin.call("GET", "/api/admin/alerts")
        self.assertEqual(status, 200)
        item = data["alerts"][0]
        self.assertEqual(set(item), {"id", "reference", "kind", "department_name", "age_seconds"})
        self.assertGreater(item["age_seconds"], 120)
        self.assertNotIn("chest", str(data))                      # no message text, title or student name
        self.assertNotIn("Demo Student", str(data))
        alert_id = self.support.call("GET", "/api/staff/alerts")[1]["alerts"][0]["id"]
        self.support.call("POST", f"/api/staff/alerts/{alert_id}/ack", {})
        self.assertEqual(self.admin.call("GET", "/api/admin/alerts")[1]["alerts"], [])   # acknowledged: cleared

    def test_US6_supervisor_endpoint_is_admin_only(self):
        for client in (self.student, self.support):
            self.assertEqual(client.call("GET", "/api/admin/alerts")[0], 403)

    # --- End-to-end timing targets from the story
    def test_US6_alert_is_visible_to_staff_within_30_seconds_end_to_end(self):
        start = time.perf_counter()
        r = self.submit(EMERGENCY)
        alerts = self.support.call("GET", "/api/staff/alerts")[1]["alerts"]
        elapsed = time.perf_counter() - start
        self.assertEqual(alerts[0]["request_id"], r["id"])
        self.assertLess(elapsed, 30)
        self.assertLess(alerts[0]["age_seconds"], 30)

    def test_US6_urgency_handling_adds_less_than_one_second_to_request_creation(self):
        def average(message, runs=5):
            total = 0.0
            for _ in range(runs):
                start = time.perf_counter()
                self.submit(message)
                total += time.perf_counter() - start
            return total / runs
        self.assertLess(average(EMERGENCY) - average(NORMAL), 1.0)


def gemini_reply(department="review", confidence=0.0, urgent=None, reason="Model explanation."):
    route = {"department": department, "confidence": confidence, "reason": reason}
    if urgent is not None:
        route["urgent"] = urgent
    payload = {"modelVersion": "gemini-3.1-flash-lite", "candidates": [
        {"finishReason": "STOP", "content": {"role": "model", "parts": [{"text": json.dumps(route)}]}}]}
    return io.BytesIO(json.dumps(payload).encode())


# Student wording the keyword rules do NOT recognise, so only the AI can flag it.
INDIRECT = "My roommate has not moved or answered since this morning and her lips look blue."


class GeminiUrgencyTests(unittest.TestCase):
    """The AI's `urgent` flag is merged with the keyword rules: urgent if EITHER says so."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "gemini.sqlite3"
        self.app = Application(self.path, classifier=GeminiClassifier("test-key-not-a-real-api-secret"))
        seed_demo(self.path)
        self.student, self.support = Client(self.app), Client(self.app)
        self.student.login("240103030@sdu.edu.kz", "Student123!")
        self.support.login("helpdesk@sdu.edu.kz", "Support123!")

    def tearDown(self):
        self.temp.cleanup()

    def submit(self, message, reply):
        with patch("app.llm.urlopen", return_value=reply):
            status, data = self.student.create(message)
        self.assertEqual(status, 201, data)
        return data["request"]

    def alerts(self):
        return self.support.call("GET", "/api/staff/alerts")[1]["alerts"]

    def test_rules_do_not_recognise_the_indirect_wording(self):
        self.assertFalse(detect_urgency("Support request", INDIRECT)["detected"])

    def test_ai_flag_catches_what_the_keyword_rules_miss(self):
        r = self.submit(INDIRECT, gemini_reply("health", 0.9, urgent=True))
        self.assertEqual((r["priority"], r["status"], r["department_code"]), ("urgent", "Received", "health"))
        self.assertTrue(r["classification"]["urgency"]["ai_flagged"])
        self.assertIn("AI router", r["classification"]["urgency"]["reason"])
        self.assertEqual(len(self.alerts()), 1)

    def test_ai_flag_with_unclear_department_still_bypasses_review_and_alerts_health(self):
        r = self.submit(INDIRECT, gemini_reply("review", 0.0, urgent=True))
        self.assertEqual((r["priority"], r["status"], r["department_code"]), ("urgent", "Received", "health"))
        self.assertIsNone(r["review_due_at"])

    def test_prompt_sends_medical_emergencies_to_health_and_only_safety_threats_to_security(self):
        self.assertIn("ALL medical emergencies", INSTRUCTIONS)
        self.assertIn("Never choose security for a medical emergency", INSTRUCTIONS)
        self.assertIn("a medical emergency is health", INSTRUCTIONS)

    def test_ai_can_route_a_safety_emergency_to_campus_security(self):
        r = self.submit("A man outside my dorm keeps following me and will not leave.",
                        gemini_reply("security", 0.9, urgent=True))
        self.assertEqual((r["department_code"], r["priority"]), ("security", "urgent"))
        self.assertEqual(self.alerts()[0]["department_code"], "security")

    def test_ai_saying_not_urgent_never_suppresses_the_keyword_rules(self):
        r = self.submit(EMERGENCY, gemini_reply("it", 0.9, urgent=False))
        self.assertEqual((r["priority"], r["status"], r["department_code"]), ("urgent", "Received", "health"))
        self.assertEqual(len(self.alerts()), 1)

    def test_ai_not_urgent_and_no_keywords_stays_a_normal_request(self):
        r = self.submit(NORMAL, gemini_reply("it", 0.94, urgent=False))
        self.assertEqual((r["priority"], r["department_code"]), ("normal", "it"))
        self.assertEqual(self.alerts(), [])

    def test_missing_urgent_field_is_tolerated_and_rules_still_apply(self):
        r = self.submit(NORMAL, gemini_reply("it", 0.94))
        self.assertEqual(r["priority"], "normal")
        r2 = self.submit(EMERGENCY, gemini_reply("it", 0.94))
        self.assertEqual(r2["priority"], "urgent")

    def test_non_boolean_urgent_value_is_rejected_and_sent_to_human_review(self):
        for bad in ("yes", 1, "true"):
            with patch("app.llm.urlopen", return_value=gemini_reply("it", 0.9, urgent=bad)):
                result = GeminiClassifier("test-key-not-a-real-api-secret").classify(NORMAL)
            self.assertEqual((result["provider_result"], result["provider_error"]), ("unavailable", "invalid_response"), bad)

    def test_gemini_outage_still_flags_a_keyword_emergency(self):
        with patch("app.llm.urlopen", side_effect=TimeoutError()):
            status, data = self.student.create(EMERGENCY)
        self.assertEqual(status, 201)
        self.assertEqual((data["request"]["priority"], data["request"]["status"]), ("urgent", "Received"))
        self.assertEqual(len(self.alerts()), 1)


if __name__ == "__main__":
    unittest.main()
