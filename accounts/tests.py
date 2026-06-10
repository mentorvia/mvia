from django.test import TestCase
from accounts.models import User, EmailToken, EmailLog


class AuthFlowTest(TestCase):
    def test_full_flow(self):
        # 1. Signup
        self.client.post("/accounts/signup/", {
            "full_name": "Test Mentee", "email": "test@example.com",
            "password": "StrongPass!234", "password_confirm": "StrongPass!234",
        }, follow=True)
        user = User.objects.filter(email="test@example.com").first()
        self.assertIsNotNone(user, "signup creates user")
        self.assertTrue(user.password.startswith("pbkdf2_"), "password is hashed")
        self.assertFalse(user.is_email_verified, "starts unverified")
        self.assertTrue(user.is_mentee, "starts as mentee")
        self.assertFalse(user.is_mentor, "not a mentor yet")

        # 2. Email audit log
        log = EmailLog.objects.filter(recipient="test@example.com", template="welcome_verify").first()
        self.assertIsNotNone(log, "email audit logged")
        self.assertEqual(log.status, "safe_mode", "email in safe mode")

        # 3. Login blocked before verification
        r = self.client.post("/accounts/login/", {"email": "test@example.com", "password": "StrongPass!234"})
        self.assertIn(b"verify your email", r.content.lower(), "login blocked pre-verify")

        # 4. Verify
        token = EmailToken.objects.filter(user=user, purpose="verify").first()
        self.assertIsNotNone(token, "verify token issued")
        self.client.get(f"/accounts/verify/{token.token}/", follow=True)
        user.refresh_from_db()
        self.assertTrue(user.is_email_verified, "email now verified")

        # 5. Login works
        r = self.client.post("/accounts/login/", {"email": "test@example.com", "password": "StrongPass!234"}, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Dashboard", r.content, "login works post-verify")

        # 6. Dashboard loads
        self.assertEqual(self.client.get("/dashboard/").status_code, 200, "dashboard loads")

        # 7. Logout protects dashboard
        self.client.get("/accounts/logout/")
        self.assertEqual(self.client.get("/dashboard/").status_code, 302, "dashboard protected after logout")

        # 8. Duplicate email rejected
        r = self.client.post("/accounts/signup/", {
            "full_name": "Dup", "email": "test@example.com",
            "password": "StrongPass!234", "password_confirm": "StrongPass!234",
        })
        self.assertIn(b"already exists", r.content, "duplicate rejected")

        # 9. Password reset
        self.client.post("/accounts/password-reset/", {"email": "test@example.com"}, follow=True)
        rtoken = EmailToken.objects.filter(user=user, purpose="reset").first()
        self.assertIsNotNone(rtoken, "reset token issued")
        self.client.post(f"/accounts/password-reset/{rtoken.token}/", {
            "password": "NewPass!5678", "password_confirm": "NewPass!5678",
        }, follow=True)
        user.refresh_from_db()
        self.assertTrue(user.check_password("NewPass!5678"), "password changed")

    def test_weak_password_rejected(self):
        r = self.client.post("/accounts/signup/", {
            "full_name": "Weak", "email": "weak@example.com",
            "password": "123", "password_confirm": "123",
        })
        self.assertFalse(User.objects.filter(email="weak@example.com").exists())
