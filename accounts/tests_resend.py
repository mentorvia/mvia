from unittest.mock import patch
from django.test import TestCase, override_settings

from accounts.emails import send_email


class ResendEmailTest(TestCase):
    @override_settings(RESEND_ENABLED=False)
    def test_safe_mode_when_no_key(self):
        log = send_email(to_email="a@b.com", subject="Hi", body="Body", template_name="test")
        self.assertEqual(log.status, "safe_mode")
        self.assertEqual(log.provider_message_id, "safe-mode-no-send")

    @override_settings(RESEND_ENABLED=True, RESEND_API_KEY="re_test", DEFAULT_FROM_EMAIL="info@mvia.in")
    @patch("resend.Emails.send")
    def test_real_send_calls_resend(self, mock_send):
        mock_send.return_value = {"id": "abc123"}
        log = send_email(to_email="user@b.com", subject="Welcome", body="Hello", template_name="welcome")
        self.assertEqual(log.status, "sent")
        self.assertEqual(log.provider_message_id, "abc123")
        # verify we called Resend with the right from/to
        args = mock_send.call_args[0][0]
        self.assertEqual(args["from"], "info@mvia.in")
        self.assertEqual(args["to"], ["user@b.com"])
        self.assertEqual(args["subject"], "Welcome")

    @override_settings(RESEND_ENABLED=True, RESEND_API_KEY="re_test", DEFAULT_FROM_EMAIL="info@mvia.in")
    @patch("resend.Emails.send")
    def test_failure_is_recorded(self, mock_send):
        mock_send.side_effect = Exception("API down")
        log = send_email(to_email="user@b.com", subject="X", body="Y", template_name="t")
        self.assertEqual(log.status, "failed")
        self.assertIn("API down", log.error_detail)
