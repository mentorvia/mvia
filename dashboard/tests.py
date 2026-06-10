from django.test import TestCase
from accounts.models import User


class StaffDashboardTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="admin@mvia.in", password="Admin!2345", full_name="Admin")
        self.member = User.objects.create_user(
            email="m@example.com", password="StrongPass!234", full_name="Member")
        self.member.is_email_verified = True
        self.member.save()

    def test_non_staff_cannot_access(self):
        self.client.login(username="m@example.com", password="StrongPass!234")
        r = self.client.get("/staff/")
        self.assertEqual(r.status_code, 302)  # bounced to login

    def test_anonymous_cannot_access(self):
        self.assertEqual(self.client.get("/staff/").status_code, 302)

    def test_staff_overview_loads(self):
        self.client.login(username="admin@mvia.in", password="Admin!2345")
        r = self.client.get("/staff/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Overview", r.content)
        self.assertIn(b"Total users", r.content)

    def test_users_list_and_search(self):
        self.client.login(username="admin@mvia.in", password="Admin!2345")
        r = self.client.get("/staff/users/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Member", r.content)
        r = self.client.get("/staff/users/?q=member")
        self.assertIn(b"m@example.com", r.content)
        r = self.client.get("/staff/users/?q=nobody-xyz")
        self.assertIn(b"No users found", r.content)

    def test_user_detail(self):
        self.client.login(username="admin@mvia.in", password="Admin!2345")
        r = self.client.get(f"/staff/users/{self.member.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Email history", r.content)

    def test_email_log(self):
        self.client.login(username="admin@mvia.in", password="Admin!2345")
        r = self.client.get("/staff/emails/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Email log", r.content)

    def test_staff_login_redirects_to_console(self):
        r = self.client.post("/accounts/login/",
            {"email": "admin@mvia.in", "password": "Admin!2345"}, follow=True)
        self.assertIn(b"Staff console", r.content)
