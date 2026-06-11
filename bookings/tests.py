from datetime import timedelta
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from profiles.models import MentorProfile, MenteeProfile
from interests.models import Interest, MenteeInterest
from bookings.models import AvailabilitySlot, Booking
from bookings.services import create_booking, confirm_payment, cancel_booking, complete_booking, BookingError
from payments.models import Payment


def make_mentor(email="mentor@b.com", rate=1500):
    u = User.objects.create_user(email=email, password="StrongPass!234", full_name="Mentor M")
    u.is_email_verified = True; u.is_mentor = True; u.save()
    MentorProfile.objects.create(user=u, current_role="Eng", company="Co",
        years_experience=5, bio="Bio", hourly_rate=rate, status="approved")
    return u

def make_complete_mentee(email="mentee@b.com"):
    u = User.objects.create_user(email=email, password="StrongPass!234", full_name="Mentee M")
    u.is_email_verified = True; u.save()
    p = MenteeProfile.objects.create(user=u, current_role="Student", career_goals="Grow")
    i = Interest.objects.create(name="Career")
    MenteeInterest.objects.create(user=u, interest=i)
    return u

def future_slot(mentor, hours=24):
    start = timezone.now() + timedelta(hours=hours)
    return AvailabilitySlot.objects.create(mentor=mentor, start=start, end=start + timedelta(hours=1))


class BookingFlowTest(TestCase):
    def setUp(self):
        self.mentor = make_mentor()
        self.mentee = make_complete_mentee()
        self.slot = future_slot(self.mentor)

    def test_create_booking_pending(self):
        b = create_booking(mentee=self.mentee, slot_id=self.slot.id)
        self.assertEqual(b.status, "pending_payment")
        self.assertEqual(b.amount, self.mentor.mentor_profile.hourly_rate)
        self.assertEqual(b.payments.count(), 1)
        self.assertTrue(b.payments.first().is_simulated)

    def test_confirm_payment_confirms_booking(self):
        b = create_booking(mentee=self.mentee, slot_id=self.slot.id)
        confirm_payment(booking_id=b.id, simulated=True)
        b.refresh_from_db()
        self.assertEqual(b.status, "confirmed")
        self.assertIsNotNone(b.confirmed_at)
        self.assertEqual(b.payments.first().status, "paid")
        self.assertTrue(self.slot.is_taken)

    def test_cannot_book_own_slot(self):
        with self.assertRaises(BookingError):
            create_booking(mentee=self.mentor, slot_id=self.slot.id)

    def test_double_booking_prevented(self):
        other = make_complete_mentee("other@b.com")
        b1 = create_booking(mentee=self.mentee, slot_id=self.slot.id)
        confirm_payment(booking_id=b1.id)
        # Once the slot is confirmed-taken, a second mentee can't even create a booking.
        with self.assertRaises(BookingError):
            create_booking(mentee=other, slot_id=self.slot.id)
        # only one active booking on the slot
        self.assertEqual(Booking.objects.filter(slot=self.slot, status="confirmed").count(), 1)

    def test_concurrent_pending_then_confirm_race(self):
        # Two pending bookings exist; only the first to confirm wins.
        other = make_complete_mentee("other2@b.com")
        b1 = create_booking(mentee=self.mentee, slot_id=self.slot.id)
        b2 = create_booking(mentee=other, slot_id=self.slot.id)  # allowed: slot not yet taken
        confirm_payment(booking_id=b1.id)
        with self.assertRaises(BookingError):
            confirm_payment(booking_id=b2.id)
        b2.refresh_from_db()
        self.assertEqual(b2.status, "pending_payment")
        self.assertEqual(Booking.objects.filter(slot=self.slot, status="confirmed").count(), 1)

    def test_state_machine_illegal_transition(self):
        b = create_booking(mentee=self.mentee, slot_id=self.slot.id)
        # pending -> completed is illegal
        self.assertFalse(b.can_transition_to("completed"))
        with self.assertRaises(BookingError):
            complete_booking(booking_id=b.id)

    def test_cancel_confirmed(self):
        b = create_booking(mentee=self.mentee, slot_id=self.slot.id)
        confirm_payment(booking_id=b.id)
        cancel_booking(booking_id=b.id, actor=self.mentee, reason="Conflict")
        b.refresh_from_db()
        self.assertEqual(b.status, "cancelled")
        self.assertEqual(b.cancelled_by, self.mentee)
        # slot is free again
        self.assertFalse(self.slot.is_taken)

    def test_complete_after_confirm(self):
        b = create_booking(mentee=self.mentee, slot_id=self.slot.id)
        confirm_payment(booking_id=b.id)
        complete_booking(booking_id=b.id)
        b.refresh_from_db()
        self.assertEqual(b.status, "completed")
        self.assertIsNotNone(b.completed_at)

    def test_cancelled_cannot_complete(self):
        b = create_booking(mentee=self.mentee, slot_id=self.slot.id)
        confirm_payment(booking_id=b.id)
        cancel_booking(booking_id=b.id, actor=self.mentor)
        with self.assertRaises(BookingError):
            complete_booking(booking_id=b.id)


class BookingViewTest(TestCase):
    def setUp(self):
        self.mentor = make_mentor()
        self.mentee = make_complete_mentee()
        self.slot = future_slot(self.mentor)

    def test_incomplete_profile_blocked_from_booking(self):
        bare = User.objects.create_user(email="bare@b.com", password="StrongPass!234", full_name="Bare")
        bare.is_email_verified = True; bare.save()
        self.client.login(username="bare@b.com", password="StrongPass!234")
        r = self.client.get(f"/book/{self.slot.id}/", follow=True)
        self.assertFalse(Booking.objects.filter(mentee=bare).exists())

    def test_full_booking_and_pay_flow_via_views(self):
        self.client.login(username="mentee@b.com", password="StrongPass!234")
        # book -> redirected to pay
        self.client.get(f"/book/{self.slot.id}/", follow=True)
        b = Booking.objects.get(mentee=self.mentee)
        self.assertEqual(b.status, "pending_payment")
        # pay (simulated) -> confirmed
        self.client.post(f"/pay/{b.id}/", follow=True)
        b.refresh_from_db()
        self.assertEqual(b.status, "confirmed")

    def test_only_mentor_sets_availability(self):
        self.client.login(username="mentee@b.com", password="StrongPass!234")
        r = self.client.get("/availability/", follow=True)
        # mentee redirected away
        self.assertNotIn(b"Publish time slots", r.content)
