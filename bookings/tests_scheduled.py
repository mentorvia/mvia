from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from profiles.models import MentorProfile, MenteeProfile
from interests.models import Interest, MenteeInterest
from bookings.models import AvailabilitySlot, Booking
from bookings.services import (
    create_booking, confirm_payment, approve_booking,
    expire_unpaid_bookings, auto_complete_past_sessions, send_due_reminders,
    run_scheduled_tasks,
)


def setup_people():
    mentor = User.objects.create_user(email="men@b.com", password="X!2345678", full_name="Men Tor")
    mentor.is_mentor = True; mentor.is_email_verified = True; mentor.save()
    MentorProfile.objects.create(user=mentor, current_role="Eng", company="Co",
        years_experience=5, bio="B", hourly_rate=2000, status="approved")
    i = Interest.objects.create(name="Career")
    mentee = User.objects.create_user(email="tee@b.com", password="X!2345678", full_name="Men Tee")
    mentee.is_email_verified = True; mentee.save()
    MenteeProfile.objects.create(user=mentee, current_role="S", career_goals="G")
    MenteeInterest.objects.create(user=mentee, interest=i)
    return mentor, mentee


def make_slot(mentor, start):
    return AvailabilitySlot.objects.create(mentor=mentor, start=start, end=start + timedelta(hours=1))


class ExpireUnpaidTest(TestCase):
    def test_old_unpaid_expires(self):
        mentor, mentee = setup_people()
        slot = make_slot(mentor, timezone.now() + timedelta(days=2))
        b = create_booking(mentee=mentee, slot_id=slot.id)  # pending_payment
        # backdate created_at beyond the expiry window
        Booking.objects.filter(pk=b.pk).update(
            created_at=timezone.now() - timedelta(minutes=45))
        n = expire_unpaid_bookings()
        b.refresh_from_db()
        self.assertEqual(n, 1)
        self.assertEqual(b.status, Booking.STATUS_EXPIRED)

    def test_recent_unpaid_survives(self):
        mentor, mentee = setup_people()
        slot = make_slot(mentor, timezone.now() + timedelta(days=2))
        b = create_booking(mentee=mentee, slot_id=slot.id)  # just created
        n = expire_unpaid_bookings()
        b.refresh_from_db()
        self.assertEqual(n, 0)
        self.assertEqual(b.status, Booking.STATUS_PENDING_PAYMENT)

    def test_paid_booking_never_expires(self):
        mentor, mentee = setup_people()
        slot = make_slot(mentor, timezone.now() + timedelta(days=2))
        b = create_booking(mentee=mentee, slot_id=slot.id)
        confirm_payment(booking_id=b.id)
        approve_booking(booking_id=b.id, actor=b.mentor)
        Booking.objects.filter(pk=b.pk).update(
            created_at=timezone.now() - timedelta(minutes=90))
        expire_unpaid_bookings()
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.STATUS_CONFIRMED)


class AutoCompleteTest(TestCase):
    def test_past_confirmed_completes(self):
        mentor, mentee = setup_people()
        slot = make_slot(mentor, timezone.now() + timedelta(days=1))
        b = create_booking(mentee=mentee, slot_id=slot.id)
        confirm_payment(booking_id=b.id)
        approve_booking(booking_id=b.id, actor=b.mentor)
        # move the slot into the past
        AvailabilitySlot.objects.filter(pk=slot.pk).update(
            start=timezone.now() - timedelta(hours=2),
            end=timezone.now() - timedelta(hours=1))
        n = auto_complete_past_sessions()
        b.refresh_from_db()
        self.assertEqual(n, 1)
        self.assertEqual(b.status, Booking.STATUS_COMPLETED)
        self.assertIsNotNone(b.completed_at)

    def test_future_confirmed_not_completed(self):
        mentor, mentee = setup_people()
        slot = make_slot(mentor, timezone.now() + timedelta(days=1))
        b = create_booking(mentee=mentee, slot_id=slot.id)
        confirm_payment(booking_id=b.id)
        approve_booking(booking_id=b.id, actor=b.mentor)
        n = auto_complete_past_sessions()
        b.refresh_from_db()
        self.assertEqual(n, 0)
        self.assertEqual(b.status, Booking.STATUS_CONFIRMED)

    def test_idempotent(self):
        mentor, mentee = setup_people()
        slot = make_slot(mentor, timezone.now() + timedelta(days=1))
        b = create_booking(mentee=mentee, slot_id=slot.id)
        confirm_payment(booking_id=b.id)
        approve_booking(booking_id=b.id, actor=b.mentor)
        AvailabilitySlot.objects.filter(pk=slot.pk).update(
            start=timezone.now() - timedelta(hours=2), end=timezone.now() - timedelta(hours=1))
        self.assertEqual(auto_complete_past_sessions(), 1)
        self.assertEqual(auto_complete_past_sessions(), 0)  # nothing left to do


class ReminderTest(TestCase):
    @patch("accounts.emails.send_email")
    def test_24h_reminder_sent_once(self, mock_send):
        mentor, mentee = setup_people()
        slot = make_slot(mentor, timezone.now() + timedelta(hours=20))  # within 24h
        b = create_booking(mentee=mentee, slot_id=slot.id)
        confirm_payment(booking_id=b.id)
        approve_booking(booking_id=b.id, actor=b.mentor)
        r1 = send_due_reminders()
        self.assertEqual(r1["sent_24h"], 1)
        b.refresh_from_db()
        self.assertIsNotNone(b.reminder_24h_sent_at)
        # running again does NOT re-send
        r2 = send_due_reminders()
        self.assertEqual(r2["sent_24h"], 0)

    @patch("accounts.emails.send_email")
    def test_1h_reminder_sent(self, mock_send):
        mentor, mentee = setup_people()
        slot = make_slot(mentor, timezone.now() + timedelta(minutes=45))  # within 1h
        b = create_booking(mentee=mentee, slot_id=slot.id)
        confirm_payment(booking_id=b.id)
        approve_booking(booking_id=b.id, actor=b.mentor)
        r = send_due_reminders()
        self.assertEqual(r["sent_1h"], 1)

    @patch("accounts.emails.send_email")
    def test_far_future_no_reminder(self, mock_send):
        mentor, mentee = setup_people()
        slot = make_slot(mentor, timezone.now() + timedelta(days=5))
        b = create_booking(mentee=mentee, slot_id=slot.id)
        confirm_payment(booking_id=b.id)
        approve_booking(booking_id=b.id, actor=b.mentor)
        r = send_due_reminders()
        self.assertEqual(r["sent_24h"], 0)
        self.assertEqual(r["sent_1h"], 0)

    @patch("accounts.emails.send_email")
    def test_unconfirmed_no_reminder(self, mock_send):
        mentor, mentee = setup_people()
        slot = make_slot(mentor, timezone.now() + timedelta(hours=20))
        b = create_booking(mentee=mentee, slot_id=slot.id)  # not paid
        r = send_due_reminders()
        self.assertEqual(r["sent_24h"], 0)


class RunAllTest(TestCase):
    @patch("accounts.emails.send_email")
    def test_run_scheduled_tasks_summary(self, mock_send):
        mentor, mentee = setup_people()
        # one past confirmed -> completes; one soon -> reminder
        s1 = make_slot(mentor, timezone.now() + timedelta(days=1))
        b1 = create_booking(mentee=mentee, slot_id=s1.id); confirm_payment(booking_id=b1.id)
        approve_booking(booking_id=b1.id, actor=b1.mentor)
        AvailabilitySlot.objects.filter(pk=s1.pk).update(
            start=timezone.now() - timedelta(hours=2), end=timezone.now() - timedelta(hours=1))
        result = run_scheduled_tasks()
        self.assertEqual(result["auto_completed"], 1)
        self.assertIn("reminders_24h", result)
