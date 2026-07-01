from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from profiles.models import MentorProfile, MenteeProfile
from interests.models import Interest, MenteeInterest
from bookings.models import AvailabilitySlot, Booking
from bookings.services import create_booking, confirm_payment, reschedule_booking, BookingError


def setup():
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


def slot(mentor, start):
    return AvailabilitySlot.objects.create(mentor=mentor, start=start, end=start + timedelta(hours=1))


@patch("accounts.emails.send_email")
class RescheduleTest(TestCase):
    def test_basic_reschedule(self, _m):
        mentor, mentee = setup()
        s1 = slot(mentor, timezone.now() + timedelta(days=3))
        s2 = slot(mentor, timezone.now() + timedelta(days=4))
        b = create_booking(mentee=mentee, slot_id=s1.id); confirm_payment(booking_id=b.id)
        reschedule_booking(booking_id=b.id, new_slot_id=s2.id, actor=mentee)
        b.refresh_from_db()
        self.assertEqual(b.slot_id, s2.id)
        self.assertEqual(b.reschedule_count, 1)
        self.assertEqual(b.status, Booking.STATUS_CONFIRMED)

    def test_cutoff_enforced(self, _m):
        mentor, mentee = setup()
        s1 = slot(mentor, timezone.now() + timedelta(hours=12))  # within 24h
        s2 = slot(mentor, timezone.now() + timedelta(days=4))
        b = create_booking(mentee=mentee, slot_id=s1.id); confirm_payment(booking_id=b.id)
        with self.assertRaises(BookingError):
            reschedule_booking(booking_id=b.id, new_slot_id=s2.id, actor=mentee)

    def test_max_two_reschedules(self, _m):
        mentor, mentee = setup()
        s1 = slot(mentor, timezone.now() + timedelta(days=10))
        s2 = slot(mentor, timezone.now() + timedelta(days=11))
        s3 = slot(mentor, timezone.now() + timedelta(days=12))
        s4 = slot(mentor, timezone.now() + timedelta(days=13))
        b = create_booking(mentee=mentee, slot_id=s1.id); confirm_payment(booking_id=b.id)
        reschedule_booking(booking_id=b.id, new_slot_id=s2.id, actor=mentee)
        reschedule_booking(booking_id=b.id, new_slot_id=s3.id, actor=mentee)
        with self.assertRaises(BookingError):
            reschedule_booking(booking_id=b.id, new_slot_id=s4.id, actor=mentee)

    def test_cannot_move_to_other_mentor_slot(self, _m):
        mentor, mentee = setup()
        other = User.objects.create_user(email="o@b.com", password="X!2345678", full_name="Other M")
        other.is_mentor = True; other.is_email_verified = True; other.save()
        MentorProfile.objects.create(user=other, current_role="X", company="Y",
            years_experience=3, bio="B", hourly_rate=1000, status="approved")
        s1 = slot(mentor, timezone.now() + timedelta(days=3))
        s_other = slot(other, timezone.now() + timedelta(days=4))
        b = create_booking(mentee=mentee, slot_id=s1.id); confirm_payment(booking_id=b.id)
        with self.assertRaises(BookingError):
            reschedule_booking(booking_id=b.id, new_slot_id=s_other.id, actor=mentee)

    def test_cannot_move_to_taken_slot(self, _m):
        mentor, mentee = setup()
        mentee2 = User.objects.create_user(email="t2@b.com", password="X!2345678", full_name="Tee 2")
        mentee2.is_email_verified = True; mentee2.save()
        MenteeProfile.objects.create(user=mentee2, current_role="S", career_goals="G")
        s1 = slot(mentor, timezone.now() + timedelta(days=3))
        s2 = slot(mentor, timezone.now() + timedelta(days=4))
        b1 = create_booking(mentee=mentee, slot_id=s1.id); confirm_payment(booking_id=b1.id)
        b2 = create_booking(mentee=mentee2, slot_id=s2.id); confirm_payment(booking_id=b2.id)
        # s2 is taken by b2 — b1 can't move there
        with self.assertRaises(BookingError):
            reschedule_booking(booking_id=b1.id, new_slot_id=s2.id, actor=mentee)

    def test_old_slot_freed_after_reschedule(self, _m):
        mentor, mentee = setup()
        mentee2 = User.objects.create_user(email="t2@b.com", password="X!2345678", full_name="Tee 2")
        mentee2.is_email_verified = True; mentee2.save()
        MenteeProfile.objects.create(user=mentee2, current_role="S", career_goals="G")
        s1 = slot(mentor, timezone.now() + timedelta(days=3))
        s2 = slot(mentor, timezone.now() + timedelta(days=4))
        b1 = create_booking(mentee=mentee, slot_id=s1.id); confirm_payment(booking_id=b1.id)
        reschedule_booking(booking_id=b1.id, new_slot_id=s2.id, actor=mentee)
        # now s1 is free — mentee2 can book it
        b2 = create_booking(mentee=mentee2, slot_id=s1.id)
        confirm_payment(booking_id=b2.id)  # should succeed, no clash
        b2.refresh_from_db()
        self.assertEqual(b2.status, Booking.STATUS_CONFIRMED)

    def test_cannot_reschedule_completed(self, _m):
        mentor, mentee = setup()
        s1 = slot(mentor, timezone.now() + timedelta(days=3))
        s2 = slot(mentor, timezone.now() + timedelta(days=4))
        b = create_booking(mentee=mentee, slot_id=s1.id); confirm_payment(booking_id=b.id)
        Booking.objects.filter(pk=b.pk).update(status=Booking.STATUS_COMPLETED)
        with self.assertRaises(BookingError):
            reschedule_booking(booking_id=b.id, new_slot_id=s2.id, actor=mentee)

    def test_reminders_reset_on_reschedule(self, _m):
        mentor, mentee = setup()
        s1 = slot(mentor, timezone.now() + timedelta(days=3))
        s2 = slot(mentor, timezone.now() + timedelta(days=4))
        b = create_booking(mentee=mentee, slot_id=s1.id); confirm_payment(booking_id=b.id)
        Booking.objects.filter(pk=b.pk).update(reminder_24h_sent_at=timezone.now())
        reschedule_booking(booking_id=b.id, new_slot_id=s2.id, actor=mentee)
        b.refresh_from_db()
        self.assertIsNone(b.reminder_24h_sent_at)


class ActivateLoginTest(TestCase):
    def test_activate_placeholder(self):
        admin = User.objects.create_superuser(email="admin@mvia.in", password="Admin!2345", full_name="Admin")
        ph = User.objects.create_placeholder_mentor(full_name="Placeholder Person")
        MentorProfile.objects.create(user=ph, current_role="X", company="Y",
            years_experience=3, bio="B", hourly_rate=1000, status="approved")
        self.assertTrue(ph.is_placeholder)
        self.client.login(username="admin@mvia.in", password="Admin!2345")
        mp = ph.mentor_profile
        r = self.client.post(f"/staff/mentors/{mp.id}/activate-login/", {
            "email": "newmentor@example.com", "password": "SecurePass123"})
        ph.refresh_from_db()
        self.assertFalse(ph.is_placeholder)
        self.assertEqual(ph.email, "newmentor@example.com")
        self.assertTrue(ph.is_email_verified)
        # can now authenticate
        self.assertTrue(self.client.login(username="newmentor@example.com", password="SecurePass123"))

    def test_duplicate_email_rejected(self):
        admin = User.objects.create_superuser(email="admin@mvia.in", password="Admin!2345", full_name="Admin")
        existing = User.objects.create_user(email="taken@example.com", password="X!2345678", full_name="Taken")
        ph = User.objects.create_placeholder_mentor(full_name="PH")
        mp = MentorProfile.objects.create(user=ph, current_role="X", company="Y",
            years_experience=3, bio="B", hourly_rate=1000, status="approved")
        self.client.login(username="admin@mvia.in", password="Admin!2345")
        self.client.post(f"/staff/mentors/{mp.id}/activate-login/", {
            "email": "taken@example.com", "password": "SecurePass123"})
        ph.refresh_from_db()
        self.assertTrue(ph.is_placeholder)  # unchanged — rejected
