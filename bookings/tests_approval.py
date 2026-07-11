from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from profiles.models import MentorProfile, MenteeProfile
from interests.models import Interest, MenteeInterest
from bookings.models import AvailabilitySlot, Booking
from bookings.services import (
    create_booking, confirm_payment, approve_booking, decline_booking,
    suggest_new_slot, accept_suggested_slot, set_meet_link,
    auto_decline_expired_approvals, BookingError,
)
from payments.models import LedgerEntry


def setup():
    mentor = User.objects.create_user(email="men@b.com", password="X!2345678", full_name="Men Tor")
    mentor.is_mentor = True; mentor.is_email_verified = True; mentor.save()
    MentorProfile.objects.create(user=mentor, current_role="Eng", company="Co",
        years_experience=5, bio="B", hourly_rate=20, status="approved", is_available=True)
    i = Interest.objects.create(name="Career")
    mentee = User.objects.create_user(email="tee@b.com", password="X!2345678", full_name="Men Tee")
    mentee.is_email_verified = True; mentee.save()
    MenteeProfile.objects.create(user=mentee, current_role="S", career_goals="G")
    MenteeInterest.objects.create(user=mentee, interest=i)
    return mentor, mentee


def slot(mentor, days=2):
    start = timezone.now() + timedelta(days=days)
    return AvailabilitySlot.objects.create(mentor=mentor, start=start, end=start + timedelta(hours=1))


@patch("accounts.emails.send_email")
class ApprovalFlowTest(TestCase):
    def test_payment_moves_to_awaiting_approval(self, _m):
        mentor, mentee = setup()
        s = slot(mentor)
        b = create_booking(mentee=mentee, slot_id=s.id)
        confirm_payment(booking_id=b.id)
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.STATUS_AWAITING_APPROVAL)
        self.assertIsNotNone(b.approval_due_at)

    def test_approve_confirms(self, _m):
        mentor, mentee = setup()
        s = slot(mentor)
        b = create_booking(mentee=mentee, slot_id=s.id); confirm_payment(booking_id=b.id)
        approve_booking(booking_id=b.id, actor=mentor)
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.STATUS_CONFIRMED)
        self.assertIsNotNone(b.approved_at)

    def test_decline_refunds_and_frees_slot(self, _m):
        mentor, mentee = setup()
        s = slot(mentor)
        b = create_booking(mentee=mentee, slot_id=s.id); confirm_payment(booking_id=b.id)
        decline_booking(booking_id=b.id, actor=mentor, reason="Can't make it")
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.STATUS_DECLINED)
        self.assertTrue(b.is_refunded)
        # a refund ledger entry (negative) was recorded
        refund = LedgerEntry.objects.filter(booking=b, entry_type=LedgerEntry.TYPE_REFUND).first()
        self.assertIsNotNone(refund)
        self.assertEqual(refund.amount, -24)  # ₹20 + 20% = ₹24
        # slot is free again (declined doesn't hold it)
        self.assertFalse(s.is_taken)

    def test_slot_held_while_awaiting(self, _m):
        mentor, mentee = setup()
        mentee2 = User.objects.create_user(email="t2@b.com", password="X!2345678", full_name="T2")
        mentee2.is_email_verified = True; mentee2.save()
        MenteeProfile.objects.create(user=mentee2, current_role="S", career_goals="G")
        s = slot(mentor)
        b = create_booking(mentee=mentee, slot_id=s.id); confirm_payment(booking_id=b.id)
        # slot is held (awaiting approval counts as taken)
        self.assertTrue(s.is_taken)
        with self.assertRaises(BookingError):
            create_booking(mentee=mentee2, slot_id=s.id)

    def test_suggest_and_accept(self, _m):
        mentor, mentee = setup()
        s1 = slot(mentor, days=2)
        s2 = AvailabilitySlot.objects.create(
            mentor=mentor, start=timezone.now() + timedelta(days=5),
            end=timezone.now() + timedelta(days=5, hours=1), is_confirmed=True)
        b = create_booking(mentee=mentee, slot_id=s1.id); confirm_payment(booking_id=b.id)
        suggest_new_slot(booking_id=b.id, new_slot_id=s2.id, actor=mentor)
        b.refresh_from_db()
        self.assertEqual(b.suggested_slot_id, s2.id)
        # mentee accepts -> booking moves to s2, still awaiting approval
        accept_suggested_slot(booking_id=b.id, actor=mentee)
        b.refresh_from_db()
        self.assertEqual(b.slot_id, s2.id)
        self.assertIsNone(b.suggested_slot)

    def test_48h_auto_decline(self, _m):
        mentor, mentee = setup()
        s = slot(mentor)
        b = create_booking(mentee=mentee, slot_id=s.id); confirm_payment(booking_id=b.id)
        # force the approval window into the past
        Booking.objects.filter(pk=b.pk).update(approval_due_at=timezone.now() - timedelta(hours=1))
        n = auto_decline_expired_approvals()
        self.assertEqual(n, 1)
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.STATUS_DECLINED)
        self.assertTrue(b.is_refunded)

    def test_set_meet_link(self, _m):
        mentor, mentee = setup()
        s = slot(mentor)
        b = create_booking(mentee=mentee, slot_id=s.id); confirm_payment(booking_id=b.id)
        set_meet_link(booking_id=b.id, link="https://meet.google.com/abc-defg-hij", actor=mentor)
        b.refresh_from_db()
        self.assertEqual(b.meet_link, "https://meet.google.com/abc-defg-hij")

    def test_cannot_approve_non_awaiting(self, _m):
        mentor, mentee = setup()
        s = slot(mentor)
        b = create_booking(mentee=mentee, slot_id=s.id)  # not paid yet
        with self.assertRaises(BookingError):
            approve_booking(booking_id=b.id, actor=mentor)
