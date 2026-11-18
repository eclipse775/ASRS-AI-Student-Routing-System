"""Support access to student feedback (US8) and live administrator analytics (US9)."""
from datetime import datetime, timezone
import unittest

from app.business_time import calendar
from app.database import connection
from tests.test_sprint6_7 import Base


class FeedbackAnalyticsTests(Base):
    def rated_request(self, rating=4, comment="Quick and friendly help.", client=None):
        request = self.open_request(client=client)
        resolved = self.resolve(request)
        status, result = (client or self.student).call("POST", f"/api/requests/{request['id']}/feedback",
                                                       {"rating": rating, "comment": comment})
        self.assertEqual(status, 201, result)
        return resolved

    def local_today(self):
        db = connection(self.path)
        try:
            zone = calendar(db)[2]
        finally:
            db.close()
        return datetime.now(timezone.utc).astimezone(zone).date().isoformat()

    # ---------------------------------------------------------------- support sees feedback
    def test_support_reads_rating_and_comment_on_a_request(self):
        request = self.open_request(); resolved = self.resolve(request)
        self.assertIsNone(self.support.call("GET", f"/api/requests/{request['id']}/feedback")[1]["feedback"])
        self.student.call("POST", f"/api/requests/{request['id']}/feedback", {"rating": 2, "comment": "Slow reply."})
        feedback = self.support.call("GET", f"/api/requests/{request['id']}/feedback")[1]["feedback"]
        self.assertEqual((feedback["rating"], feedback["comment"]), (2, "Slow reply."))
        self.assertEqual(self.other.call("GET", f"/api/requests/{request['id']}/feedback")[0], 404)
        self.assertEqual(self.admin.call("GET", f"/api/requests/{request['id']}/feedback")[0], 403)
        self.assertEqual(resolved["status"], "Resolved")

    def test_support_feedback_page_lists_ratings_with_summary(self):
        self.rated_request(5, "Excellent."); self.rated_request(1, "Nobody answered for days.")
        status, data = self.support.call("GET", "/api/staff/feedback")
        self.assertEqual(status, 200, data)
        self.assertEqual((data["summary"]["count"], data["summary"]["low_count"], data["summary"]["with_comment"]), (2, 1, 2))
        self.assertEqual(data["summary"]["average"], 3.0)
        newest = data["feedback"][0]
        self.assertEqual((newest["rating"], newest["comment"]), (1, "Nobody answered for days."))
        self.assertTrue(newest["reference"].startswith("REQ-") and newest["student_name"] and newest["department"])
        self.assertTrue(data["by_department"] and data["by_department"][0]["count"] == 2)

    def test_support_feedback_filters_and_validation(self):
        self.rated_request(5); self.rated_request(2)
        low = self.support.call("GET", "/api/staff/feedback?rating=low")[1]["feedback"]
        self.assertEqual([f["rating"] for f in low], [2])
        self.assertEqual([f["rating"] for f in self.support.call("GET", "/api/staff/feedback?rating=5")[1]["feedback"]], [5])
        dept = self.support.call("GET", "/api/staff/feedback")[1]["feedback"][0]["department_code"]
        self.assertEqual(len(self.support.call("GET", f"/api/staff/feedback?department={dept}")[1]["feedback"]), 2)
        for bad in ("?rating=9", "?department=nope", "?limit=abc"):
            self.assertEqual(self.support.call("GET", "/api/staff/feedback" + bad)[0], 400, bad)
        page = self.support.call("GET", "/api/staff/feedback?limit=1")[1]
        self.assertEqual((len(page["feedback"]), page["has_more"], page["next_offset"]), (1, True, 1))

    def test_feedback_page_is_for_support_only(self):
        self.rated_request()
        for client in (self.student, self.admin):
            self.assertEqual(client.call("GET", "/api/staff/feedback")[0], 403)
        from tests.test_acceptance import Client
        self.assertEqual(Client(self.app).call("GET", "/api/staff/feedback")[0], 401)

    def test_queue_row_carries_the_rating(self):
        resolved = self.rated_request(4)
        rows = self.support.call("GET", "/api/staff/requests?status=Resolved")[1]["requests"]
        self.assertEqual(next(r for r in rows if r["id"] == resolved["id"])["feedback_rating"], 4)

    def test_feedback_of_an_anonymized_student_is_blank(self):
        self.rated_request(3, "Private comment 9931")
        deletion = self.student.call("POST", "/api/privacy/deletion", {})[1]["deletion_request"]["id"]
        self.admin.call("POST", f"/api/admin/deletions/{deletion}/approve", {})
        entry = self.support.call("GET", "/api/staff/feedback")[1]["feedback"][0]
        self.assertEqual((entry["comment"], entry["student_name"], entry["rating"]), ("", "Anonymized student", 3))

    # ---------------------------------------------------------------- live analytics
    def test_analytics_includes_requests_created_today(self):
        before = self.admin.call("GET", "/api/admin/analytics")[1]
        self.open_request(); self.open_request()
        after = self.admin.call("GET", "/api/admin/analytics")[1]
        self.assertEqual(after["total_requests"], before["total_requests"] + 2)
        self.assertEqual(after["data_through"], self.local_today())
        self.assertEqual(after["to"], self.local_today())
        self.assertEqual(sum(x["total"] for x in after["by_department"]), after["total_requests"])

    def test_analytics_today_only_and_future_dates_are_clamped(self):
        self.open_request()
        today = self.local_today()
        only_today = self.admin.call("GET", f"/api/admin/analytics?from={today}&to={today}")[1]
        self.assertEqual(only_today["total_requests"], 1)
        future = self.admin.call("GET", f"/api/admin/analytics?from={today}&to=2999-01-01")[1]
        self.assertEqual((future["to"], future["total_requests"]), (today, 1))

    def test_analytics_includes_new_ratings_and_first_responses_today(self):
        self.rated_request(5); self.rated_request(3)
        data = self.admin.call("GET", "/api/admin/analytics")[1]
        self.assertEqual(sum(x["feedback_count"] for x in data["feedback"]), 2)
        self.assertEqual(data["feedback"][0]["average_rating"], 4.0)
        self.assertTrue(data["response_times"])
        self.assertNotIn("Nobody", str(data))

    def test_analytics_stays_administrator_only(self):
        for client in (self.student, self.support):
            self.assertEqual(client.call("GET", "/api/admin/analytics")[0], 403)


if __name__ == "__main__":
    unittest.main()
