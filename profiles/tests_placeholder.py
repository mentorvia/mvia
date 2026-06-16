from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from accounts.models import User
from profiles.models import MentorProfile, MenteeProfile
from interests.models import Interest, MentorInterest, MenteeInterest
from bookings.models import AvailabilitySlot
from bookings.services import create_booking, BookingError


class PlaceholderMentorTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="admin@mvia.in", password="Admin!2345", full_name="Admin")
        self.ml = Interest.objects.create(name="Machine Learning")

    def test_create_placeholder_no_login(self):
        u = User.objects.create_placeholder_mentor(full_name="Ghost Mentor")
        self.assertTrue(u.is_placeholder)
        self.assertTrue(u.is_mentor)
        self.assertFalse(u.has_real_email())
        self.assertFalse(u.has_usable_password())  # cannot ever authenticate

    def test_placeholder_appears_in_directory(self):
        u = User.objects.create_placeholder_mentor(full_name="Directory Mentor")
        MentorProfile.objects.create(user=u, current_role="Eng", company="Co",
            years_experience=5, bio="Bio", hourly_rate=2000, status="approved")
        MentorInterest.objects.create(user=u, interest=self.ml)
        r = self.client.get("/mentors/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Directory Mentor", r.content)

    def test_placeholder_cannot_be_booked(self):
        # placeholder mentor with a slot (shouldn't normally have one, but guard anyway)
        ghost = User.objects.create_placeholder_mentor(full_name="Ghost")
        MentorProfile.objects.create(user=ghost, current_role="Eng", company="Co",
            years_experience=5, bio="Bio", hourly_rate=2000, status="approved")
        start = timezone.now() + timedelta(days=1)
        slot = AvailabilitySlot.objects.create(mentor=ghost, start=start, end=start+timedelta(hours=1))
        # a real mentee tries to book
        mentee = User.objects.create_user(email="m@b.com", password="StrongPass!234", full_name="M")
        mentee.is_email_verified = True; mentee.save()
        MenteeProfile.objects.create(user=mentee, current_role="Student", career_goals="Grow")
        MenteeInterest.objects.create(user=mentee, interest=self.ml)
        with self.assertRaises(BookingError):
            create_booking(mentee=mentee, slot_id=slot.id)

    def test_staff_can_add_placeholder_via_form(self):
        self.client.login(username="admin@mvia.in", password="Admin!2345")
        r = self.client.post("/staff/mentors/add-placeholder/", {
            "full_name": "Added By Admin", "current_role": "CTO", "company": "Acme",
            "years_experience": "10", "bio": "Seasoned leader.", "hourly_rate": "2500",
            "interests": [self.ml.id],
        }, follow=True)
        u = User.objects.filter(full_name="Added By Admin").first()
        self.assertIsNotNone(u)
        self.assertTrue(u.is_placeholder)
        self.assertTrue(u.mentor_profile.status == "approved")
        self.assertEqual(u.mentor_interests.count(), 1)

    def test_placeholder_requires_specialization(self):
        self.client.login(username="admin@mvia.in", password="Admin!2345")
        self.client.post("/staff/mentors/add-placeholder/", {
            "full_name": "No Specs", "current_role": "X", "company": "Y",
            "years_experience": "3", "bio": "Bio", "hourly_rate": "1000",
        })
        self.assertFalse(User.objects.filter(full_name="No Specs").exists())

    def test_placeholder_cannot_login(self):
        u = User.objects.create_placeholder_mentor(full_name="No Login")
        # even trying to authenticate with any password fails
        from django.contrib.auth import authenticate
        self.assertIsNone(authenticate(username=u.email, password="anything"))
