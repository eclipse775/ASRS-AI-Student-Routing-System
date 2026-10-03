"""Executable acceptance and security checks for the Sprint 1-2 increment."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from wsgiref.util import setup_testing_defaults

from app.database import connection, review_deadline, seed_demo
from app.ml import Classifier
from app.security import verify_password
from app.server import Application


class Client:
    def __init__(self, app):
        self.app, self.cookie, self.csrf = app, "", ""
        _, data = self.call("GET", "/api/session")
        self.csrf = data["csrf_token"]

    def call(self, method, path, data=None, csrf=True, raw=None):
        env = {}
        setup_testing_defaults(env)
        env["REQUEST_METHOD"] = method
        env["PATH_INFO"], _, env["QUERY_STRING"] = path.partition("?")
        env["HTTP_COOKIE"] = self.cookie
        env["REMOTE_ADDR"] = "127.0.0.1"
        if csrf:
            env["HTTP_X_CSRF_TOKEN"] = self.csrf
        body = raw if raw is not None else json.dumps(data or {}).encode()
        env["CONTENT_TYPE"] = "application/json"
        env["CONTENT_LENGTH"] = str(len(body))
        env["wsgi.input"] = io.BytesIO(body)
        captured = {}
        def start_response(status, headers):
            captured["status"] = int(status.split()[0])
            captured["headers"] = dict(headers)
            for name, value in headers:
                if name == "Set-Cookie":
                    cookie = SimpleCookie(value)
                    self.cookie = f"routing_session={cookie['routing_session'].value}"
        result = b"".join(self.app(env, start_response))
        self.headers = captured["headers"]
        payload = json.loads(result) if "application/json" in self.headers.get("Content-Type", "") else result
        if isinstance(payload, dict) and "csrf_token" in payload:
            self.csrf = payload["csrf_token"]
        return captured["status"], payload

    def login(self, email, password):
        return self.call("POST", "/api/auth/login", {"email": email, "password": password})

    def create(self, message="My laptop cannot connect to campus wifi and the wireless network is unavailable.", **extra):
        return self.call("POST", "/api/requests", {"title": "Support request", "message": message, **extra})


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite3"
        self.app = Application(self.path, classifier=Classifier(Path(__file__).parents[1]/"data/training.json"))
        seed_demo(self.path)
        self.student, self.other, self.support, self.admin = [Client(self.app) for _ in range(4)]
        for client, email, password in [(self.student,"240103030@sdu.edu.kz","Student123!"), (self.other,"250103031@sdu.edu.kz","Student123!"),
                                         (self.support,"helpdesk@sdu.edu.kz","Support123!"), (self.admin,"admin@sdu.edu.kz","Admin12345!")]:
            self.assertEqual(client.login(email,password)[0],200)

    def tearDown(self):
        self.temp.cleanup()

    def one_request(self, **extra):
        status, data = self.student.create(**extra)
        self.assertEqual(status,201,data)
        return data["request"]

    def route(self, request, code="academic"):
        return self.support.call("POST",f"/api/requests/{request['id']}/route",{"department_code":code,"version":request["version"]})

    def test_US1_high_confidence_routes_to_correct_department(self):
        r=self.one_request()
        self.assertEqual((r["department_code"],r["status"]),("it","Received"))
        self.assertGreaterEqual(r["confidence"],0.65)

    def test_US1_at_least_90_percent_of_ten_requests_routed_correctly(self):
        rows=json.loads((Path(__file__).parents[1]/"data/evaluation.json").read_text())
        selected=[rows[i] for i in [0,1,2,10,11,20,21,22,30,31]]
        correct=0
        for row in selected:
            r=self.one_request(message=row["text"])
            correct+=r["department_code"]==row["label"]
        self.assertGreaterEqual(correct,9)

    def test_US1_routing_completes_within_30_seconds(self):
        started=time.perf_counter();self.one_request();self.assertLess(time.perf_counter()-started,30)

    def test_US2_notification_has_request_department_and_response_estimate(self):
        r=self.one_request()
        notes=self.student.call("GET","/api/notifications")[1]["notifications"]
        self.assertEqual(len(notes),1)
        self.assertIn(r["reference"],notes[0]["message"])
        self.assertIn("IT Helpdesk",notes[0]["message"])
        self.assertIn("8 business hours",notes[0]["message"])
        delta=datetime.fromisoformat(notes[0]["created_at"])-datetime.fromisoformat(r["created_at"])
        self.assertLess(delta.total_seconds(),60)

    def test_US2_refresh_does_not_duplicate_notification(self):
        self.one_request()
        for _ in range(3):self.student.call("GET","/api/requests");self.student.call("GET","/api/notifications")
        self.assertEqual(len(self.student.call("GET","/api/notifications")[1]["notifications"]),1)

    def test_US3_unknown_request_escalates_without_assigning_department(self):
        r=self.one_request(message="Something unusual happened and I would like someone to look into it.")
        self.assertEqual(r["status"],"Escalated");self.assertIsNone(r["department_id"])
        self.assertLess(r["confidence"],0.65)
        self.assertIsNotNone(r["review_due_at"])
        self.assertIn("staff review",self.student.call("GET","/api/notifications")[1]["notifications"][0]["message"])

    def test_US3_admin_threshold_changes_without_code_changes(self):
        initially=self.one_request(message="I have a question about tuition fees.")
        self.assertEqual(initially["department_code"],"finance")
        self.assertEqual(self.admin.call("PUT","/api/admin/settings",{"confidence_threshold":0.99})[0],200)
        escalated=self.one_request(message="I have a question about tuition fees.")
        self.assertEqual(escalated["status"],"Escalated")
        with connection(self.path) as db:self.assertEqual(db.execute("SELECT value FROM settings WHERE key='confidence_threshold'").fetchone()[0],"0.99")
        new_app=Application(self.path)
        self.assertEqual(Client(new_app).login("admin@sdu.edu.kz","Admin12345!")[0],200)

    def test_US3_staff_decision_logged_for_future_retraining(self):
        r=self.one_request(message="I need someone to check a complicated situation for me.")
        status,result=self.route(r,"academic");self.assertEqual(status,200,result)
        self.assertEqual(result["request"]["department_code"],"academic")
        with connection(self.path) as db:
            correction=db.execute("SELECT * FROM routing_corrections").fetchone()
            self.assertEqual(correction["corrected_code"],"academic")
            self.assertEqual(correction["message_snapshot"],r["message"])

    def test_US3_business_hour_deadline_crosses_weekend(self):
        start=datetime(2026,10,2,11,0,tzinfo=timezone.utc) # Friday 16:00 UTC+5
        self.assertEqual(datetime.fromisoformat(review_deadline(start)),datetime(2026,10,5,7,0,tzinfo=timezone.utc))

    def test_US3_out_of_hours_review_starts_next_business_day(self):
        start=datetime(2026,10,3,15,0,tzinfo=timezone.utc)
        self.assertEqual(datetime.fromisoformat(review_deadline(start)),datetime(2026,10,5,8,0,tzinfo=timezone.utc))

    def test_US3_overdue_review_is_visible(self):
        r=self.one_request(message="I have something unclear to ask and would appreciate assistance.")
        with connection(self.path) as db:db.execute("UPDATE requests SET review_due_at=? WHERE id=?",((datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(),r["id"]))
        queue=self.support.call("GET","/api/staff/requests")[1]["requests"]
        self.assertTrue(queue[0]["review_overdue"])

    def test_US4_queue_has_original_text_suggestion_confidence_oldest_first(self):
        a=self.one_request(message="Please let somebody investigate this confusing situation for me.")
        b=self.one_request(message="There is another confusing matter and I cannot explain it clearly.")
        rows=self.support.call("GET","/api/staff/requests?status=Escalated")[1]["requests"]
        self.assertEqual([r["id"] for r in rows],[a["id"],b["id"]])
        self.assertIn("suggested_code",rows[0]);self.assertIn("confidence",rows[0]);self.assertEqual(rows[0]["message"],a["message"])

    def test_US4_student_and_admin_cannot_open_support_queue(self):
        self.assertEqual(self.student.call("GET","/api/staff/requests")[0],403)
        self.assertEqual(self.admin.call("GET","/api/staff/requests")[0],403)

    def test_US4_filters_by_department_status_and_urgency(self):
        r=self.one_request(priority="urgent")
        rows=self.support.call("GET","/api/staff/requests?department=it&status=Received&priority=urgent")[1]["requests"]
        self.assertEqual([x["id"] for x in rows],[r["id"]])
        self.assertEqual(self.support.call("GET","/api/staff/requests?department=finance")[1]["requests"],[])

    def test_US4_reassignment_changes_queue_and_records_history(self):
        r=self.one_request();status,result=self.route(r,"finance");self.assertEqual(status,200)
        self.assertEqual(result["request"]["department_code"],"finance")
        self.assertEqual(self.support.call("GET","/api/staff/requests?department=it")[1]["requests"],[])
        self.assertEqual(len(self.support.call("GET","/api/staff/requests?department=finance")[1]["requests"]),1)
        self.assertEqual(len(self.student.call("GET",f"/api/requests/{r['id']}")[1]["history"]),2)

    def test_US4_repeated_route_to_same_department_is_idempotent(self):
        r=self.one_request();self.assertEqual(self.route(r,"it")[0],200)
        self.assertEqual(len(self.student.call("GET","/api/notifications")[1]["notifications"]),1)

    def test_US4_queue_with_500_open_requests_under_3_seconds(self):
        r=self.one_request()
        with connection(self.path) as db:
            source=db.execute("SELECT * FROM requests WHERE id=?",(r["id"],)).fetchone()
            columns=[k for k in source.keys() if k!="id"]
            sql="INSERT INTO requests ("+",".join(columns)+") VALUES ("+",".join("?"*len(columns))+")"
            db.executemany(sql,[tuple(source[k] for k in columns)]*499)
        started=time.perf_counter();status,data=self.support.call("GET","/api/staff/requests?open=1")
        self.assertEqual(status,200);self.assertEqual(len(data["requests"]),500)
        self.assertLess(time.perf_counter()-started,3)

    def test_US5_student_only_sees_own_requests_and_history(self):
        r=self.one_request()
        self.assertEqual(self.other.call("GET","/api/requests")[1]["requests"],[])
        self.assertEqual(self.other.call("GET",f"/api/requests/{r['id']}")[0],404)
        self.assertEqual(self.other.call("PUT",f"/api/requests/{r['id']}",{"version":1,"title":"Malicious edit","message":"My tuition payment failed and I need financial aid."})[0],404)

    def test_US5_status_update_is_immediate_and_has_timestamp(self):
        r=self.one_request();started=time.perf_counter()
        status,data=self.support.call("POST",f"/api/requests/{r['id']}/status",{"status":"In Progress","version":r["version"]})
        self.assertEqual(status,200,data)
        updated=self.student.call("GET",f"/api/requests/{r['id']}")[1]["request"]
        self.assertEqual(updated["status"],"In Progress");self.assertGreater(updated["updated_at"],r["updated_at"])
        self.assertLess(time.perf_counter()-started,60)

    def test_US5_resolution_and_reopen(self):
        r=self.one_request()
        r=self.support.call("POST",f"/api/requests/{r['id']}/status",{"status":"In Progress","version":1})[1]["request"]
        status,result=self.support.call("POST",f"/api/requests/{r['id']}/status",{"status":"Resolved","resolution":"Your wireless account has been restored.","version":r["version"]})
        self.assertEqual(status,200,result);r=result["request"]
        self.assertEqual(r["status"],"Resolved")
        self.assertEqual(self.support.call("POST",f"/api/requests/{r['id']}/status",{"status":"In Progress","version":r["version"]})[0],200)

    def test_US5_cannot_resolve_escalated_request_before_routing(self):
        r=self.one_request(message="I have a situation that is difficult to describe and need assistance.")
        self.assertEqual(self.support.call("POST",f"/api/requests/{r['id']}/status",{"status":"Resolved","resolution":"Fixed the matter.","version":1})[0],409)

    def test_CRUD_edit_reclassifies_and_delete_cascades_related_data(self):
        r=self.one_request();status,result=self.student.call("PUT",f"/api/requests/{r['id']}",{"title":"Tuition invoice","message":"My tuition payment invoice has duplicate fees and I need a refund.","version":1})
        self.assertEqual(status,200,result);self.assertEqual(result["request"]["department_code"],"finance")
        self.assertEqual(self.student.call("DELETE",f"/api/requests/{r['id']}",{"version":2})[0],200)
        with connection(self.path) as db:
            for table in ["requests","request_events","notifications"]:self.assertEqual(db.execute("SELECT count(*) FROM "+table).fetchone()[0],0)

    def test_CRUD_work_in_progress_cannot_be_edited_or_deleted(self):
        r=self.one_request();self.support.call("POST",f"/api/requests/{r['id']}/status",{"status":"In Progress","version":1})
        self.assertEqual(self.student.call("DELETE",f"/api/requests/{r['id']}",{"version":2})[0],409)
        self.assertEqual(self.student.call("PUT",f"/api/requests/{r['id']}",{"version":2,"title":"New subject","message":"Please edit this request anyway."})[0],409)

    def test_security_csrf_required_for_mutations(self):
        self.assertEqual(self.student.call("POST","/api/requests",{"title":"An issue","message":"I cannot connect my laptop to wifi."},csrf=False)[0],403)

    def test_security_registration_cannot_promote_role(self):
        client=Client(self.app);status,result=client.call("POST","/api/auth/register",{"name":"New Student","email":"260999991@sdu.edu.kz","password":"StrongPassword123!","role":"admin"})
        self.assertEqual(status,201,result);self.assertEqual(result["user"]["role"],"student")
        self.assertEqual(client.call("GET","/api/admin/settings")[0],403)

    def test_security_password_hash_and_session_cookie(self):
        with connection(self.path) as db:
            password=db.execute("SELECT password_hash FROM users WHERE email='240103030@sdu.edu.kz'").fetchone()[0]
        self.assertNotEqual(password,"Student123!");self.assertTrue(verify_password("Student123!",password))
        client=Client(self.app);client.login("240103030@sdu.edu.kz","Student123!")
        self.assertIn("HttpOnly",client.headers["Set-Cookie"]);self.assertIn("SameSite=Lax",client.headers["Set-Cookie"])

    def test_security_login_rotates_session_and_logout_invalidates_it(self):
        client=Client(self.app);old=client.cookie;client.login("240103030@sdu.edu.kz","Student123!");self.assertNotEqual(old,client.cookie)
        stolen=client.cookie;client.call("POST","/api/auth/logout",{})
        replay=Client(self.app);replay.cookie=stolen
        self.assertEqual(replay.call("GET","/api/requests")[0],401)

    def test_security_failed_login_rate_limit(self):
        client=Client(self.app)
        for _ in range(8):self.assertEqual(client.login("240103030@sdu.edu.kz","bad-password")[0],401)
        self.assertEqual(client.login("240103030@sdu.edu.kz","bad-password")[0],429)

    def test_security_student_cannot_route_or_change_status(self):
        r=self.one_request()
        self.assertEqual(self.student.call("POST",f"/api/requests/{r['id']}/route",{"department_code":"finance","version":1})[0],403)
        self.assertEqual(self.student.call("POST",f"/api/requests/{r['id']}/status",{"status":"In Progress","version":1})[0],403)

    def test_security_admin_summary_does_not_expose_request_content(self):
        r=self.one_request();self.route(r,"finance")
        self.assertEqual(self.admin.call("GET",f"/api/requests/{r['id']}")[0],403)
        correction=self.admin.call("GET","/api/admin/corrections")[1]["corrections"][0]
        self.assertNotIn("message_snapshot",correction);self.assertNotIn("student_name",correction)

    def test_reliability_failed_resolution_leaves_status_and_history_unchanged(self):
        r=self.one_request()
        self.support.call("POST",f"/api/requests/{r['id']}/status",{"status":"In Progress","version":1})
        self.assertEqual(self.support.call("POST",f"/api/requests/{r['id']}/status",{"status":"Resolved","resolution":"","version":2})[0],400)
        detail=self.student.call("GET",f"/api/requests/{r['id']}")[1]
        self.assertEqual(detail["request"]["status"],"In Progress");self.assertEqual(len(detail["history"]),2)

    def test_security_cross_owner_notification_denied(self):
        self.one_request();note=self.student.call("GET","/api/notifications")[1]["notifications"][0]
        self.assertEqual(self.other.call("POST",f"/api/notifications/{note['id']}/read",{})[0],404)
        self.assertEqual(self.other.call("GET","/api/notifications")[1]["notifications"],[])

    def test_validation_handles_invalid_json_and_fields(self):
        self.assertEqual(self.student.call("POST","/api/requests",raw=b'{bad json')[0],400)
        self.assertEqual(self.student.create(message="short")[0],400)
        self.assertEqual(self.student.create(message="x"*4001)[0],400)
        self.assertEqual(self.admin.call("PUT","/api/admin/settings",{"confidence_threshold":1.1})[0],400)
        self.assertEqual(self.admin.call("PUT","/api/admin/settings",{"confidence_threshold":True})[0],400)

    def test_security_sql_injection_stays_data_and_static_traversal_denied(self):
        self.assertEqual(Client(self.app).login("x'OR'1'='1@example.edu","bad-password")[0],401)
        self.assertEqual(self.student.call("GET","/../app/schema.sql")[0],404)
        self.assertEqual(self.student.call("GET","/app.js")[0],200)
        self.assertIn("default-src 'self'",self.student.headers["Content-Security-Policy"])

    def test_reliability_stale_updates_are_rejected(self):
        r=self.one_request();self.route(r,"finance")
        self.assertEqual(self.route(r,"academic")[0],409)

    def test_reliability_concurrent_routes_do_not_overwrite(self):
        r=self.one_request()
        clients=[Client(self.app),Client(self.app)]
        for c in clients:c.login("helpdesk@sdu.edu.kz","Support123!")
        def save(index):return clients[index].call("POST",f"/api/requests/{r['id']}/route",{"version":1,"department_code":["finance","academic"][index]})[0]
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(save,[0,1]))
        self.assertEqual(sorted(results),[200,409])

    def test_database_has_eight_related_entities_and_foreign_keys(self):
        with connection(self.path) as db:
            names={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='sqlite_sequence'")}
            self.assertEqual(len(names),8);self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(),[])

    def test_sprint1_disables_sprint2_endpoints(self):
        app=Application(self.path,sprint=1,classifier=Classifier(Path(__file__).parents[1]/"data/training.json"));support=Client(app);support.login("helpdesk@sdu.edu.kz","Support123!")
        self.assertEqual(support.call("GET","/api/staff/requests")[0],403)
        admin=Client(app);admin.login("admin@sdu.edu.kz","Admin12345!")
        self.assertEqual(admin.call("GET","/api/admin/settings")[0],403)
        student=Client(app);student.login("240103030@sdu.edu.kz","Student123!")
        self.assertEqual(student.create()[0],201)

    def test_multilingual_is_preserved_and_safely_escalated_for_future_sprint(self):
        message="Не могу подключиться к интернету в университете."
        r=self.one_request(message=message);self.assertEqual(r["message"],message);self.assertEqual(r["status"],"Escalated")


class ModelTests(unittest.TestCase):
    def test_training_and_evaluation_are_separate_and_holdout_accuracy(self):
        from scripts.evaluate_model import evaluate
        report=evaluate();self.assertGreaterEqual(report["accuracy"],.9)

    def test_unknown_and_repeated_generic_text_abstains(self):
        model=Classifier(Path(__file__).parents[1]/"data/training.json")
        for text in ["please help me with something strange", "wifi "*40, "zxqvj mysterious unrelated topic"]:
            self.assertLess(model.classify(text)["confidence"],.5)


if __name__ == "__main__":
    unittest.main()
