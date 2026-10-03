"""University registration boundaries, academic-year rollover and staff isolation."""
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.database import connection, seed_demo, utc_now
from app.ml import Classifier
from app.security import hash_password
from app.server import Application
from app.service import create_request
from app.university import current_academic_year, staff_email_allowed, student_profile
from tests.test_acceptance import Client

ROOT = Path(__file__).resolve().parents[1]


class AcademicYearTests(unittest.TestCase):
    def test_requested_2024_student_is_year_three_in_2026_2027(self):
        now = datetime(2026, 10, 3, tzinfo=timezone.utc)
        profile = student_profile('240103030@sdu.edu.kz', now)
        self.assertEqual(profile, {'student_id': '240103030', 'admission_year': 2024,
                                  'academic_year': '2026-2027', 'course': 3})

    def test_rollover_is_september_first_at_campus_utc_plus_five(self):
        before = datetime(2026, 8, 31, 18, 59, 59, tzinfo=timezone.utc)
        after = datetime(2026, 8, 31, 19, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(current_academic_year(before), 2025)
        self.assertEqual(current_academic_year(after), 2026)
        self.assertEqual(student_profile('240103030@sdu.edu.kz', before)['course'], 2)
        self.assertEqual(student_profile('240103030@sdu.edu.kz', after)['course'], 3)

    def test_january_stays_in_same_academic_year(self):
        now = datetime(2027, 1, 2, tzinfo=timezone.utc)
        self.assertEqual(student_profile('240103030@sdu.edu.kz', now)['course'], 3)
        self.assertEqual(student_profile('260103030@sdu.edu.kz', now)['course'], 1)
        self.assertIsNone(student_profile('270103030@sdu.edu.kz', now))

    def test_staff_addresses_are_separate_from_student_ids(self):
        self.assertTrue(staff_email_allowed('helpdesk@sdu.edu.kz', 'support'))
        self.assertTrue(staff_email_allowed('admin@sdu.edu.kz', 'admin'))
        for email, role in [('operator@sdu.edu.kz', 'support'), ('helpdesk@gmail.com', 'support'),
                            ('240103030@sdu.edu.kz', 'admin'), ('admin@gmail.com', 'admin')]:
            self.assertFalse(staff_email_allowed(email, role))


class SDURegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'test.sqlite3'
        self.year = patch('app.university.current_academic_year', return_value=2026)
        self.year.start()
        self.app = Application(self.path, classifier=Classifier(ROOT / 'data/training.json'))
        self.client = Client(self.app)

    def tearDown(self):
        self.year.stop()
        self.temp.cleanup()

    def register(self, email, **extra):
        return self.client.call('POST', '/api/auth/register',
                                {'name': 'SDU Test Student', 'email': email,
                                 'password': 'StrongPassword123!', **extra})

    def test_valid_student_registration_derives_course_and_survives_sign_in(self):
        status, result = self.register('240103030@sdu.edu.kz')
        self.assertEqual(status, 201, result)
        self.assertEqual(result['user']['student_profile']['course'], 3)
        self.client.call('POST', '/api/auth/logout', {})
        status, result = self.client.login('240103030@sdu.edu.kz', 'StrongPassword123!')
        self.assertEqual(status, 200)
        self.assertEqual(result['user']['student_profile']['admission_year'], 2024)
        session = self.client.call('GET', '/api/session')[1]
        self.assertEqual(session['university']['academic_year'], '2026-2027')
        self.assertEqual(session['university']['helpdesk_email'], 'helpdesk@sdu.edu.kz')

    def test_other_domains_subdomains_and_suffix_spoofing_are_rejected_on_server(self):
        for email in ['240103030@gmail.com', '240103030@other.edu.kz', '240103030@students.sdu.edu.kz',
                      '240103030@sdu.edu.kz.attacker.example', '240103030@sdu.edu.kz@evil.example']:
            with self.subTest(email=email):
                self.assertEqual(self.register(email)[0], 400)
        with connection(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0], 0)

    def test_exact_nine_ascii_digits_required(self):
        for email in ['student@sdu.edu.kz', '24010303@sdu.edu.kz', '2401030300@sdu.edu.kz',
                      '24010303a@sdu.edu.kz', '240103030+test@sdu.edu.kz', '２４０１０３０３０@sdu.edu.kz',
                      '240103030 @sdu.edu.kz']:
            with self.subTest(email=email):
                self.assertEqual(self.register(email)[0], 400)

    def test_future_admission_year_rejected_and_current_cohort_accepted(self):
        self.assertEqual(self.register('270103030@sdu.edu.kz')[0], 400)
        status, result = self.register('260103030@sdu.edu.kz')
        self.assertEqual(status, 201)
        self.assertEqual(result['user']['student_profile']['course'], 1)

    def test_case_and_outer_whitespace_normalized_and_duplicates_blocked(self):
        status, result = self.register('  240103030@SDU.EDU.KZ  ')
        self.assertEqual(status, 201)
        self.assertEqual(result['user']['email'], '240103030@sdu.edu.kz')
        self.assertEqual(self.register('240103030@sdu.edu.kz')[0], 409)
        with connection(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0], 1)

    def test_role_course_and_admission_year_cannot_be_forged_by_client(self):
        status, result = self.register('240103030@sdu.edu.kz', role='support', course=1,
                                       admission_year=2026, student_profile={'course': 1})
        self.assertEqual(status, 201)
        self.assertEqual(result['user']['role'], 'student')
        self.assertEqual(result['user']['student_profile']['course'], 3)
        self.assertEqual(self.client.call('GET', '/api/staff/requests')[0], 403)

    def test_helpdesk_cannot_register_publicly_but_provisioned_account_can_sign_in(self):
        self.assertEqual(self.register('helpdesk@sdu.edu.kz', role='support')[0], 400)
        self.assertEqual(self.register('admin@sdu.edu.kz', role='admin')[0], 400)
        seed_demo(self.path)
        status, result = self.client.login('helpdesk@sdu.edu.kz', 'Support123!')
        self.assertEqual(status, 200)
        self.assertEqual(result['user']['role'], 'support')
        self.assertIsNone(result['user']['student_profile'])
        self.assertEqual(self.client.call('GET', '/api/staff/requests')[0], 200)

    def test_old_demo_migration_preserves_account_id_password_and_request_ownership(self):
        with connection(self.path) as db:
            cursor = db.execute("INSERT INTO users (name,email,password_hash,role,created_at) VALUES (?,?,?,'student',?)",
                                ('Demo Student', 'student@demo.edu', hash_password('PreservedPassword123!'), utc_now()))
            original_id = cursor.lastrowid
            old_user = db.execute('SELECT * FROM users WHERE id=?', (original_id,)).fetchone()
            request = create_request(db, old_user, {'title': 'Existing Wi-Fi request',
                                     'message': 'My laptop cannot connect to campus wifi.'}, self.app.classifier)
        seed_demo(self.path)
        status, result = self.client.login('240103030@sdu.edu.kz', 'PreservedPassword123!')
        self.assertEqual(status, 200)
        self.assertEqual(result['user']['id'], original_id)
        detail = self.client.call('GET', f"/api/requests/{request['id']}")[1]
        self.assertEqual(detail['request']['student_id'], original_id)
        self.assertEqual(detail['request']['title'], 'Existing Wi-Fi request')
        with connection(self.path) as db:
            self.assertIsNone(db.execute("SELECT id FROM users WHERE email='student@demo.edu'").fetchone())


if __name__ == '__main__':
    unittest.main()
