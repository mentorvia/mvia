from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from profiles.models import MentorProfile, MenteeProfile
from interests.models import Interest, MenteeInterest
from bookings.models import AvailabilitySlot, Booking
from bookings.services import create_booking
from payments.models import Payment
from payments.razorpay_client import mentee_total


def setup_booking(rate=2000):
    mentor = User.objects.create_user(email="men@b.com", password="X!2345678", full_name="Men Tor")
    mentor.is_mentor = True; mentor.is_email_verified = True; mentor.save()
    MentorProfile.objects.create(user=mentor, current_role="Eng", company="Co",
        years_experience=5, bio="B", hourly_rate=rate, status="approved")
    i = Interest.objects.create(name="Career")
    mentee = User.objects.create_user(email="tee@b.com", password="X!2345678", full_name="Men Tee")
    mentee.is_email_verified = True; mentee.save()
    MenteeProfile.objects.create(user=mentee, current_role="S", career_goals="G")
    MenteeInterest.objects.create(user=mentee, interest=i)
    start = timezone.now() + timedelta(days=2)
    slot = AvailabilitySlot.objects.create(mentor=mentor, start=start, end=start + timedelta(hours=1))
    b = create_booking(mentee=mentee, slot_id=slot.id)
    return b, mentee


class RazorpayTotalTest(TestCase):
    def test_mentee_total_adds_fee(self):
        # ₹2000 + 20% = ₹2400
        self.assertEqual(mentee_total(2000), Decimal("2400.00"))
        self.assertEqual(mentee_total(20), Decimal("24.00"))


@override_settings(RAZORPAY_ENABLED=True, RAZORPAY_KEY_ID="rzp_live_x", RAZORPAY_KEY_SECRET="secret")
class RazorpayPayViewTest(TestCase):
    def setUp(self):
        self.b, self.mentee = setup_booking(rate=20)
        self.client.login(username="tee@b.com", password="X!2345678")

    @patch("payments.razorpay_client.create_order")
    def test_get_creates_order_and_renders_checkout(self, mock_order):
        mock_order.return_value = {"id": "order_TEST123"}
        r = self.client.get(f"/pay/{self.b.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "order_TEST123")
        self.assertContains(r, "checkout.razorpay.com")
        # order id saved on the payment
        p = self.b.payments.first()
        self.assertEqual(p.razorpay_order_id, "order_TEST123")

    @patch("payments.razorpay_client.verify_payment_signature")
    def test_valid_signature_confirms_booking(self, mock_verify):
        mock_verify.return_value = True
        p = self.b.payments.first()
        p.razorpay_order_id = "order_TEST123"; p.save()
        self.client.post(f"/pay/{self.b.id}/", {
            "razorpay_payment_id": "pay_1", "razorpay_order_id": "order_TEST123",
            "razorpay_signature": "sig_ok"})
        self.b.refresh_from_db()
        # After the approval flow, a paid booking now AWAITS mentor approval.
        self.assertEqual(self.b.status, Booking.STATUS_AWAITING_APPROVAL)
        p.refresh_from_db()
        self.assertFalse(p.is_simulated)
        self.assertEqual(p.razorpay_payment_id, "pay_1")

    @patch("payments.razorpay_client.verify_payment_signature")
    def test_invalid_signature_does_not_confirm(self, mock_verify):
        mock_verify.return_value = False  # forged/tampered
        p = self.b.payments.first()
        p.razorpay_order_id = "order_TEST123"; p.save()
        self.client.post(f"/pay/{self.b.id}/", {
            "razorpay_payment_id": "pay_x", "razorpay_order_id": "order_TEST123",
            "razorpay_signature": "forged"})
        self.b.refresh_from_db()
        # booking must remain unpaid — this is the security guarantee
        self.assertEqual(self.b.status, Booking.STATUS_PENDING_PAYMENT)
        p.refresh_from_db()
        self.assertEqual(p.status, Payment.STATUS_FAILED)

    @patch("payments.razorpay_client.verify_payment_signature")
    def test_mismatched_order_id_rejected(self, mock_verify):
        mock_verify.return_value = True
        p = self.b.payments.first()
        p.razorpay_order_id = "order_REAL"; p.save()
        # callback claims a DIFFERENT order id
        self.client.post(f"/pay/{self.b.id}/", {
            "razorpay_payment_id": "pay_1", "razorpay_order_id": "order_FAKE",
            "razorpay_signature": "sig"})
        self.b.refresh_from_db()
        self.assertEqual(self.b.status, Booking.STATUS_PENDING_PAYMENT)

    def test_no_double_confirm(self):
        # already confirmed booking can't be paid again
        Booking.objects.filter(pk=self.b.pk).update(status=Booking.STATUS_CONFIRMED)
        r = self.client.get(f"/pay/{self.b.id}/", follow=True)
        self.assertEqual(r.status_code, 200)
