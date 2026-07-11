from datetime import timedelta, time
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from profiles.models import MentorProfile, MenteeProfile
from interests.models import Interest, MenteeInterest
from bookings.models import WeeklyAvailability, AvailabilitySlot, Booking
from bookings.services import generate_slots_from_pattern, confirmable_slots, create_booking, confirm_payment


def make_mentor():
    u = User.objects.create_user(email="men@b.com", password="X!2345678", full_name="Men Tor")
    u.is_mentor = True; u.is_email_verified = True; u.save()
    MentorProfile.objects.create(user=u, current_role="Eng", company="Co",
        years_experience=5, bio="B", hourly_rate=20, status="approved", is_available=True)
    return u


class WeeklyAvailabilityTest(TestCase):
    def test_generate_creates_unconfirmed_slots(self):
        mentor = make_mentor()
        # available every day at 10:00 for the next 2 weeks
        for wd in range(7):
            WeeklyAvailability.objects.create(mentor=mentor, weekday=wd, start_time=time(10, 0))
        n = generate_slots_from_pattern(mentor, days=14)
        self.assertGreater(n, 0)
        # all generated slots start UNCONFIRMED
        slots = AvailabilitySlot.objects.filter(mentor=mentor)
        self.assertTrue(all(not s.is_confirmed for s in slots))

    def test_generate_is_idempotent(self):
        mentor = make_mentor()
        WeeklyAvailability.objects.create(mentor=mentor, weekday=timezone.localdate().weekday(), start_time=time(23, 59))
        n1 = generate_slots_from_pattern(mentor, days=14)
        n2 = generate_slots_from_pattern(mentor, days=14)
        self.assertEqual(n2, 0)  # nothing new the second time

    def test_unconfirmed_slot_not_bookable(self):
        mentor = make_mentor()
        start = timezone.now() + timedelta(days=2)
        slot = AvailabilitySlot.objects.create(
            mentor=mentor, start=start, end=start + timedelta(hours=1), is_confirmed=False)
        self.assertFalse(slot.is_bookable)
        slot.is_confirmed = True
        slot.save()
        self.assertTrue(slot.is_bookable)

    def test_session_length_is_60_min(self):
        mentor = make_mentor()
        WeeklyAvailability.objects.create(
            mentor=mentor, weekday=(timezone.localdate() + timedelta(days=1)).weekday(), start_time=time(9, 0))
        generate_slots_from_pattern(mentor, days=14)
        slot = AvailabilitySlot.objects.filter(mentor=mentor).first()
        self.assertEqual((slot.end - slot.start), timedelta(minutes=60))


class AvailabilityViewTest(TestCase):
    def setUp(self):
        self.mentor = make_mentor()
        self.client.login(username="men@b.com", password="X!2345678")

    def test_add_pattern(self):
        self.client.post("/availability/", {
            "action": "add_pattern", "weekday": "2", "start_time": "18:00"})
        self.assertEqual(WeeklyAvailability.objects.filter(mentor=self.mentor).count(), 1)

    def test_generate_then_confirm_flow(self):
        WeeklyAvailability.objects.create(
            mentor=self.mentor, weekday=(timezone.localdate() + timedelta(days=1)).weekday(), start_time=time(14, 0))
        self.client.post("/availability/", {"action": "generate"})
        slot = AvailabilitySlot.objects.filter(mentor=self.mentor).first()
        self.assertIsNotNone(slot)
        self.assertFalse(slot.is_confirmed)
        # confirm it
        self.client.post("/availability/", {"action": "confirm_slots", "confirm": [str(slot.id)]})
        slot.refresh_from_db()
        self.assertTrue(slot.is_confirmed)
        # unconfirm (untick = not in list)
        self.client.post("/availability/", {"action": "confirm_slots", "confirm": []})
        slot.refresh_from_db()
        self.assertFalse(slot.is_confirmed)

    def test_booked_slot_stays_confirmed_when_unticking(self):
        # a booked slot must never be un-confirmed by the confirm action
        me = User.objects.create_user(email="tee@b.com", password="X!2345678", full_name="Tee")
        me.is_email_verified = True; me.save()
        MenteeProfile.objects.create(user=me, current_role="S", career_goals="G")
        start = timezone.now() + timedelta(days=2)
        slot = AvailabilitySlot.objects.create(
            mentor=self.mentor, start=start, end=start + timedelta(hours=1), is_confirmed=True)
        b = create_booking(mentee=me, slot_id=slot.id); confirm_payment(booking_id=b.id)
        # mentor submits confirm with empty list (tries to untick everything)
        self.client.post("/availability/", {"action": "confirm_slots", "confirm": []})
        slot.refresh_from_db()
        self.assertTrue(slot.is_confirmed)  # protected because booked


class MenteeSeesConfirmedOnlyTest(TestCase):
    def test_directory_profile_shows_confirmed_only(self):
        mentor = make_mentor()
        now = timezone.now()
        confirmed = AvailabilitySlot.objects.create(
            mentor=mentor, start=now + timedelta(days=1), end=now + timedelta(days=1, hours=1), is_confirmed=True)
        unconfirmed = AvailabilitySlot.objects.create(
            mentor=mentor, start=now + timedelta(days=2), end=now + timedelta(days=2, hours=1), is_confirmed=False)
        r = self.client.get(f"/mentors/{mentor.id}/")
        self.assertEqual(r.status_code, 200)
        # bookable_slots should include confirmed, exclude unconfirmed
        ids = [s.id for s in r.context["bookable_slots"]]
        self.assertIn(confirmed.id, ids)
        self.assertNotIn(unconfirmed.id, ids)
