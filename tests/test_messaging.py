"""US11 - Student-Staff Messaging on a Request: acceptance, access-control and reliability checks."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from app.database import connection, seed_demo
from app.ml import Classifier
from app.server import Application
from tests.test_acceptance import Client

TRAINING = Path(__file__).parents[1] / "data" / "training.json"


class CountingClassifier(Classifier):
    calls = 0

    def classify(self, text):
        type(self).calls += 1
        return super().classify(text)


class MessagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite3"
        self.app = Application(self.path, classifier=Classifier(TRAINING))
        seed_demo(self.path)
        self.student, self.other, self.support, self.admin = [Client(self.app) for _ in range(4)]
        for client, email, password in [(self.student, "240103030@sdu.edu.kz", "Student123!"),
                                        (self.other, "250103031@sdu.edu.kz", "Student123!"),
                                        (self.support, "helpdesk@sdu.edu.kz", "Support123!"),
                                        (self.admin, "admin@sdu.edu.kz", "Admin12345!")]:
            self.assertEqual(client.login(email, password)[0], 200)

    def tearDown(self):
        self.temp.cleanup()

    def open_request(self, **extra):
        status, data = self.student.create(**extra)
        self.assertEqual(status, 201, data)
        return data["request"]

    def post(self, client, request, body, **extra):
        return client.call("POST", f"/api/requests/{request['id']}/messages", {"body": body, **extra})

    def thread(self, client, request, after=0):
        return client.call("GET", f"/api/requests/{request['id']}/messages?after={after}")

    def resolve(self, request):
        r = self.support.call("POST", f"/api/requests/{request['id']}/status", {"status": "In Progress", "version": request["version"]})[1]["request"]
        status, result = self.support.call("POST", f"/api/requests/{request['id']}/status",
                                           {"status": "Resolved", "resolution": "Your wireless access was restored.", "version": r["version"]})
        self.assertEqual(status, 200, result)
        return result["request"]

    # ------------------------------------------------------------------ acceptance scenarios
    def test_US11_staff_asks_student_is_notified_and_reply_reaches_staff(self):
        r = self.open_request()
        status, sent = self.post(self.support, r, "Which building are you in when the Wi-Fi drops?")
        self.assertEqual(status, 201, sent)
        notes = self.student.call("GET", "/api/notifications")[1]["notifications"]
        message_notes = [n for n in notes if "New message" in n["message"]]
        self.assertEqual(len(message_notes), 1)
        self.assertIn(r["reference"], message_notes[0]["message"])
        self.assertNotIn("building", message_notes[0]["message"])  # the text is not copied into the notice
        delta = datetime.fromisoformat(message_notes[0]["created_at"]) - datetime.fromisoformat(sent["message"]["created_at"])
        self.assertLess(abs(delta.total_seconds()), 60)
        seen = self.thread(self.student, r)[1]
        self.assertEqual([m["body"] for m in seen["messages"]], ["Which building are you in when the Wi-Fi drops?"])
        self.assertEqual((seen["messages"][0]["sender_role"], seen["messages"][0]["mine"]), ("support", False))
        self.assertEqual(self.post(self.student, r, "Library, second floor.")[0], 201)
        staff_view = self.thread(self.support, r)[1]
        self.assertEqual([m["body"] for m in staff_view["messages"]],
                         ["Which building are you in when the Wi-Fi drops?", "Library, second floor."])
        self.assertTrue(staff_view["messages"][0]["mine"] and not staff_view["messages"][1]["mine"])

    def test_US11_other_students_cannot_read_post_or_mark_read(self):
        r = self.open_request()
        self.post(self.support, r, "Private question for the owner of this request.")
        status, body = self.thread(self.other, r)
        self.assertEqual(status, 404)
        self.assertNotIn("Private question", str(body))
        self.assertEqual(self.post(self.other, r, "I should not be able to write here.")[0], 404)
        self.assertEqual(self.other.call("POST", f"/api/requests/{r['id']}/messages/read", {})[0], 404)
        with connection(self.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM request_messages").fetchone()[0], 1)
            self.assertIsNone(db.execute("SELECT read_at FROM request_messages").fetchone()[0])

    def test_US11_administrator_and_anonymous_users_are_denied(self):
        r = self.open_request()
        self.post(self.support, r, "Operational question about the request.")
        self.assertEqual(self.thread(self.admin, r)[0], 403)
        self.assertEqual(self.post(self.admin, r, "Administrators do not join request threads.")[0], 403)
        anonymous = Client(self.app)
        self.assertEqual(self.thread(anonymous, r)[0], 401)

    def test_US11_sender_role_cannot_be_forged(self):
        r = self.open_request()
        status, sent = self.post(self.student, r, "Posting as a student.", sender_role="support", sender_id=3, read_at="x")
        self.assertEqual(status, 201)
        self.assertEqual(sent["message"]["sender_role"], "student")
        with connection(self.path) as db:
            row = db.execute("SELECT sender_role,read_at,sender_id FROM request_messages").fetchone()
            student_id = db.execute("SELECT id FROM users WHERE email='240103030@sdu.edu.kz'").fetchone()[0]
        self.assertEqual((row["sender_role"], row["read_at"], row["sender_id"]), ("student", None, student_id))
        # A student cannot trigger a student notification by pretending to be staff.
        self.assertEqual([n for n in self.student.call("GET", "/api/notifications")[1]["notifications"] if "New message" in n["message"]], [])

    def test_US11_messages_keep_order_and_none_is_lost_under_concurrency(self):
        r = self.open_request()
        clients = [Client(self.app) for _ in range(8)]
        for i, client in enumerate(clients):
            if i % 2:
                client.login("240103030@sdu.edu.kz", "Student123!")
            else:
                client.login("helpdesk@sdu.edu.kz", "Support123!")

        def send(i):
            return self.post(clients[i], r, f"message number {i}")[0]

        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(send, range(8)))
        self.assertEqual(statuses, [201] * 8)
        messages = self.thread(self.student, r)[1]["messages"]
        self.assertEqual(sorted(m["body"] for m in messages), sorted(f"message number {i}" for i in range(8)))
        ids = [m["id"] for m in messages]
        self.assertEqual(ids, sorted(ids))
        stamps = [m["created_at"] for m in messages]
        self.assertEqual(stamps, sorted(stamps))

    def test_US11_polling_with_after_returns_only_new_messages(self):
        r = self.open_request()
        first = self.post(self.support, r, "First question.")[1]["message"]
        second = self.post(self.student, r, "First answer.")[1]["message"]
        newer = self.thread(self.student, r, after=first["id"])[1]["messages"]
        self.assertEqual([m["id"] for m in newer], [second["id"]])
        self.assertEqual(self.thread(self.student, r, after=second["id"])[1]["messages"], [])
        self.assertEqual(self.thread(self.student, r, after="abc")[0], 400)
        self.assertEqual(self.call_raw_after("-1", r), 400)

    def call_raw_after(self, value, r):
        return self.student.call("GET", f"/api/requests/{r['id']}/messages?after={value}")[0]

    def test_US11_thread_is_read_only_when_resolved_and_opens_again_on_reopen(self):
        r = self.open_request()
        self.post(self.support, r, "Do you still see the problem?")
        resolved = self.resolve(r)
        for client in (self.student, self.support):
            status, body = self.post(client, r, "One more thing.")
            self.assertEqual(status, 409, body)
        thread = self.thread(self.student, r)[1]
        self.assertFalse(thread["open"])
        self.assertEqual(len(thread["messages"]), 1)  # history stays readable
        reopened = self.support.call("POST", f"/api/requests/{r['id']}/status", {"status": "In Progress", "version": resolved["version"]})
        self.assertEqual(reopened[0], 200)
        self.assertTrue(self.thread(self.student, r)[1]["open"])
        self.assertEqual(self.post(self.student, r, "Yes, it came back after lunch.")[0], 201)

    def test_US11_escalated_request_can_be_clarified_before_routing(self):
        r = self.open_request(message="Something unusual happened and I would like someone to look into it.")
        self.assertEqual(r["status"], "Escalated")
        self.assertEqual(self.post(self.support, r, "Could you tell us which office you need?")[0], 201)
        self.assertEqual(self.post(self.student, r, "I need the scholarship office.")[0], 201)

    # ------------------------------------------------------------------ unread and notification state
    def test_US11_unread_counts_for_both_sides_clear_when_thread_is_read(self):
        r = self.open_request()
        self.post(self.support, r, "Question one?")
        self.post(self.support, r, "Question two?")
        mine = self.student.call("GET", "/api/requests")[1]["requests"][0]
        self.assertEqual((mine["unread_messages"], mine["message_count"]), (2, 2))
        self.assertEqual(self.student.call("POST", f"/api/requests/{r['id']}/messages/read", {})[1], {"read": 2})
        self.assertEqual(self.student.call("GET", "/api/requests")[1]["requests"][0]["unread_messages"], 0)
        self.assertEqual(self.student.call("POST", f"/api/requests/{r['id']}/messages/read", {})[1], {"read": 0})
        self.post(self.student, r, "Answer to both.")
        queue = self.support.call("GET", "/api/staff/requests")[1]
        self.assertEqual(queue["unread_messages"], 1)
        self.assertEqual(queue["requests"][0]["unread_messages"], 1)
        self.support.call("POST", f"/api/requests/{r['id']}/messages/read", {})
        self.assertEqual(self.support.call("GET", "/api/staff/requests")[1]["unread_messages"], 0)

    def test_US11_each_staff_message_is_notified_once_and_refresh_does_not_duplicate(self):
        r = self.open_request()
        self.post(self.support, r, "First staff message.")
        self.post(self.support, r, "Second staff message.")
        for _ in range(3):
            self.student.call("GET", "/api/requests")
            self.thread(self.student, r)
        notes = [n for n in self.student.call("GET", "/api/notifications")[1]["notifications"] if "New message" in n["message"]]
        self.assertEqual(len(notes), 2)

    def test_US11_student_messages_do_not_create_student_notifications(self):
        r = self.open_request()
        before = len(self.student.call("GET", "/api/notifications")[1]["notifications"])
        self.post(self.student, r, "Adding a detail.")
        self.assertEqual(len(self.student.call("GET", "/api/notifications")[1]["notifications"]), before)

    def test_US11_messages_do_not_change_request_version_or_appear_in_the_status_timeline(self):
        r = self.open_request()
        self.post(self.support, r, "Do you have the error code?")
        self.post(self.student, r, "It says 0x80.")
        detail = self.student.call("GET", f"/api/requests/{r['id']}")[1]
        self.assertEqual(detail["request"]["version"], r["version"])  # staff forms stay valid
        self.assertEqual([e["kind"] for e in detail["history"]], ["submitted"])

    # ------------------------------------------------------------------ validation and reliability
    def test_US11_validation_and_exact_text_is_preserved(self):
        r = self.open_request()
        for bad in ["", "   ", "x" * 1001, 5, None]:
            self.assertEqual(self.student.call("POST", f"/api/requests/{r['id']}/messages", {"body": bad})[0], 400, bad)
        self.assertEqual(self.student.call("POST", f"/api/requests/{r['id']}/messages", {})[0], 400)
        self.assertEqual(self.post(self.student, r, "ok", client_id="bad id!")[0], 400)
        text = "<script>alert(1)</script> & Привет, Қайырлы күн 'quotes'"
        status, sent = self.post(self.student, r, "  " + text + "  ")
        self.assertEqual(status, 201)
        self.assertEqual(sent["message"]["body"], text)
        self.assertEqual(self.thread(self.support, r)[1]["messages"][0]["body"], text)
        self.assertEqual(self.post(self.student, r, "x" * 1000)[0], 201)

    def test_US11_retrying_the_same_send_does_not_duplicate_the_message(self):
        r = self.open_request()
        first = self.post(self.student, r, "Sent once.", client_id="client-token-0001")
        again = self.post(self.student, r, "Sent once.", client_id="client-token-0001")
        self.assertEqual((first[0], again[0]), (201, 200))
        self.assertEqual(first[1]["message"]["id"], again[1]["message"]["id"])
        self.assertEqual(len(self.thread(self.student, r)[1]["messages"]), 1)
        # The same token from the other side or on another request is a different message.
        self.assertEqual(self.post(self.support, r, "Reply.", client_id="client-token-0001")[0], 201)

    def test_US11_thread_has_a_message_limit(self):
        r = self.open_request()
        with connection(self.path) as db:
            student_id = db.execute("SELECT id FROM users WHERE email='240103030@sdu.edu.kz'").fetchone()[0]
            db.executemany("INSERT INTO request_messages (request_id,sender_id,sender_role,body,created_at) VALUES (?,?,?,?,?)",
                           [(r["id"], student_id, "student", f"filler {i}", datetime.now(timezone.utc).isoformat()) for i in range(300)])
        self.assertEqual(self.post(self.student, r, "One too many.")[0], 409)

    def test_US11_csrf_json_and_method_rules(self):
        r = self.open_request()
        self.assertEqual(self.student.call("POST", f"/api/requests/{r['id']}/messages", {"body": "hi there"}, csrf=False)[0], 403)
        self.assertEqual(self.student.call("DELETE", f"/api/requests/{r['id']}/messages", {})[0], 405)
        self.assertEqual(self.student.call("PUT", f"/api/requests/{r['id']}/messages", {"body": "edit"})[0], 405)

    def test_US11_deleting_a_request_removes_its_thread_and_notices(self):
        r = self.open_request()
        self.post(self.support, r, "Hello?")
        self.assertEqual(self.student.call("DELETE", f"/api/requests/{r['id']}", {"version": r["version"]})[0], 200)
        with connection(self.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM request_messages").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM notifications").fetchone()[0], 0)
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_US11_message_text_is_never_sent_to_the_classifier(self):
        app = Application(Path(self.temp.name) / "count.sqlite3", classifier=CountingClassifier(TRAINING))
        seed_demo(Path(self.temp.name) / "count.sqlite3")
        student, support = Client(app), Client(app)
        student.login("240103030@sdu.edu.kz", "Student123!")
        support.login("helpdesk@sdu.edu.kz", "Support123!")
        r = student.create()[1]["request"]
        calls = CountingClassifier.calls
        student.call("POST", f"/api/requests/{r['id']}/messages", {"body": "Here is my student ID and phone number."})
        support.call("POST", f"/api/requests/{r['id']}/messages", {"body": "Thank you."})
        self.assertEqual(CountingClassifier.calls, calls)

    def test_US11_messaging_is_a_sprint_2_feature(self):
        r = self.open_request()
        app = Application(self.path, sprint=1, classifier=Classifier(TRAINING))
        student = Client(app)
        student.login("240103030@sdu.edu.kz", "Student123!")
        self.assertEqual(student.call("GET", f"/api/requests/{r['id']}/messages")[0], 403)


if __name__ == "__main__":
    unittest.main()
