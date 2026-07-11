from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from profiles.models import MentorProfile, MenteeProfile
from interests.models import Interest, MenteeInterest
from bookings.models import AvailabilitySlot, Booking
from bookings.services import create_booking, confirm_payment, record_refund, cancel_booking, BookingError
from bookings.services import approve_booking
from payments.models import LedgerEntry


def setup_booking(rate=2000):
    mentor = User.objects.create_user(email="men@b.com", password="StrongPass!234", full_name="Men Tor")
    mentor.is_email_verified = True; mentor.is_mentor = True; mentor.save()
    MentorProfile.objects.create(user=mentor, current_role="Eng", company="Co",
        years_experience=5, bio="Bio", hourly_rate=rate, status="approved")
    mentee = User.objects.create_user(email="tee@b.com", password="StrongPass!234", full_name="Men Tee")
    mentee.is_email_verified = True; mentee.save()
    MenteeProfile.objects.create(user=mentee, current_role="Student", career_goals="Grow")
    i = Interest.objects.create(name="Career"); MenteeInterest.objects.create(user=mentee, interest=i)
    start = timezone.now() + timedelta(days=1)
    slot = AvailabilitySlot.objects.create(mentor=mentor, start=start, end=start+timedelta(hours=1))
    return mentor, mentee, slot


class LedgerTest(TestCase):
    def test_confirm_writes_three_ledger_entries(self):
        mentor, mentee, slot = setup_booking(rate=2000)
        b = create_booking(mentee=mentee, slot_id=slot.id)
        confirm_payment(booking_id=b.id)
        approve_booking(booking_id=b.id, actor=b.mentor)
        entries = {e.entry_type: e.amount for e in b.ledger_entries.all()}
        self.assertEqual(entries["booking_payment"], Decimal("2400.00"))  # 2000 + 20%
        self.assertEqual(entries["platform_fee"], Decimal("400.00"))
        self.assertEqual(entries["mentor_earning"], Decimal("2000.00"))

    def test_pending_booking_has_no_ledger(self):
        mentor, mentee, slot = setup_booking()
        b = create_booking(mentee=mentee, slot_id=slot.id)
        self.assertEqual(b.ledger_entries.count(), 0)  # only on confirm

    def test_refund_writes_negative_entry_and_marks_booking(self):
        mentor, mentee, slot = setup_booking(rate=2000)
        b = create_booking(mentee=mentee, slot_id=slot.id)
        confirm_payment(booking_id=b.id)
        approve_booking(booking_id=b.id, actor=b.mentor)
        record_refund(booking_id=b.id, actor=mentor, reason="Mentor unavailable", reference="rzp_123")
        b.refresh_from_db()
        self.assertTrue(b.is_refunded)
        self.assertEqual(b.refund_reference, "rzp_123")
        refund = b.ledger_entries.get(entry_type="refund")
        self.assertEqual(refund.amount, Decimal("-2400.00"))

    def test_cannot_refund_unpaid_booking(self):
        mentor, mentee, slot = setup_booking()
        b = create_booking(mentee=mentee, slot_id=slot.id)  # pending_payment
        with self.assertRaises(BookingError):
            record_refund(booking_id=b.id, actor=mentor, reason="x")

    def test_cannot_refund_twice(self):
        mentor, mentee, slot = setup_booking()
        b = create_booking(mentee=mentee, slot_id=slot.id)
        confirm_payment(booking_id=b.id)
        approve_booking(booking_id=b.id, actor=b.mentor)
        record_refund(booking_id=b.id, actor=mentor, reason="once")
        with self.assertRaises(BookingError):
            record_refund(booking_id=b.id, actor=mentor, reason="twice")

    def test_refund_requires_reason(self):
        mentor, mentee, slot = setup_booking()
        b = create_booking(mentee=mentee, slot_id=slot.id)
        confirm_payment(booking_id=b.id)
        approve_booking(booking_id=b.id, actor=b.mentor)
        with self.assertRaises(BookingError):
            record_refund(booking_id=b.id, actor=mentor, reason="   ")

    def test_ledger_entries_immutable_append_only(self):
        # We never edit/delete; confirm there's no code path that mutates.
        # This is a design guard: entries exist only via create.
        mentor, mentee, slot = setup_booking()
        b = create_booking(mentee=mentee, slot_id=slot.id)
        confirm_payment(booking_id=b.id)
        approve_booking(booking_id=b.id, actor=b.mentor)
        count_before = LedgerEntry.objects.count()
        record_refund(booking_id=b.id, actor=mentor, reason="test")
        # refund ADDS an entry, never removes
        self.assertEqual(LedgerEntry.objects.count(), count_before + 1)

    def test_refunded_booking_excluded_from_earnings(self):
        mentor, mentee, slot = setup_booking(rate=2000)
        b = create_booking(mentee=mentee, slot_id=slot.id)
        confirm_payment(booking_id=b.id)
        approve_booking(booking_id=b.id, actor=b.mentor)
        record_refund(booking_id=b.id, actor=mentor, reason="cancelled")
        # earnings report filters is_refunded=False
        owed = LedgerEntry.objects.filter(
            entry_type="mentor_earning", booking__is_refunded=False).count()
        self.assertEqual(owed, 0)


class StaffRefundViewTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email="admin@mvia.in", password="Admin!2345", full_name="Admin")
        self.mentor, self.mentee, self.slot = setup_booking(rate=2000)
        self.b = create_booking(mentee=self.mentee, slot_id=self.slot.id)
        confirm_payment(booking_id=self.b.id)
        approve_booking(booking_id=self.b.id, actor=self.b.mentor)
        self.client.login(username="admin@mvia.in", password="Admin!2345")

    def test_staff_can_record_refund(self):
        self.client.post(f"/staff/bookings/{self.b.id}/", {
            "action": "record_refund", "reason": "Mentor cancelled", "reference": "rzp_999"})
        self.b.refresh_from_db()
        self.assertTrue(self.b.is_refunded)
        self.assertEqual(self.b.refund_reference, "rzp_999")

    def test_ledger_page_loads(self):
        r = self.client.get("/staff/ledger/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Platform fee", r.content)

    def test_earnings_report_loads(self):
        # Earnings only appear after completion (per payout design).
        from bookings.services import complete_booking
        complete_booking(booking_id=self.b.id)
        r = self.client.get("/staff/earnings/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Men Tor", r.content)
