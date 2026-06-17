from datetime import timedelta
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from profiles.models import MentorProfile, MenteeProfile
from interests.models import Interest, MenteeInterest
from bookings.models import AvailabilitySlot, Booking
from bookings.services import create_booking, confirm_payment, complete_booking
from reviews.models import Review


def completed_booking(mentor, email="me@b.com"):
    i = Interest.objects.filter(name="Career").first() or Interest.objects.create(name="Career")
    me = User.objects.create_user(email=email, password="X!2345678", full_name="Mentee X")
    me.is_email_verified = True; me.save()
    MenteeProfile.objects.create(user=me, current_role="S", career_goals="G")
    MenteeInterest.objects.create(user=me, interest=i)
    start = timezone.now() + timedelta(days=1)
    slot = AvailabilitySlot.objects.create(mentor=mentor, start=start, end=start+timedelta(hours=1))
    b = create_booking(mentee=me, slot_id=slot.id)
    confirm_payment(booking_id=b.id)
    complete_booking(booking_id=b.id)
    return b, me


class ReviewTest(TestCase):
    def setUp(self):
        self.mentor = User.objects.create_user(email="men@b.com", password="X!2345678", full_name="Men Tor")
        self.mentor.is_mentor = True; self.mentor.is_email_verified = True; self.mentor.save()
        self.mp = MentorProfile.objects.create(user=self.mentor, current_role="Eng", company="Co",
            years_experience=5, bio="B", hourly_rate=2000, status="approved")

    def test_mentee_can_review_completed(self):
        b, me = completed_booking(self.mentor)
        self.client.login(username=me.email, password="X!2345678")
        r = self.client.post(f"/review/{b.id}/", {"rating": "5", "review_text": "Great!", "private_note": ""})
        self.assertTrue(Review.objects.filter(booking=b).exists())
        self.assertEqual(Review.objects.get(booking=b).rating, 5)

    def test_cannot_review_twice(self):
        b, me = completed_booking(self.mentor)
        Review.objects.create(booking=b, mentee=me, mentor=self.mentor, rating=4)
        self.client.login(username=me.email, password="X!2345678")
        r = self.client.post(f"/review/{b.id}/", {"rating": "1"}, follow=True)
        self.assertEqual(Review.objects.filter(booking=b).count(), 1)  # unchanged

    def test_cannot_review_others_booking(self):
        b, me = completed_booking(self.mentor)
        other = User.objects.create_user(email="other@b.com", password="X!2345678", full_name="Other")
        other.is_email_verified = True; other.save()
        self.client.login(username="other@b.com", password="X!2345678")
        self.client.post(f"/review/{b.id}/", {"rating": "1"})
        self.assertFalse(Review.objects.filter(booking=b).exists())

    def test_cannot_review_non_completed(self):
        i = Interest.objects.create(name="X")
        me = User.objects.create_user(email="m2@b.com", password="X!2345678", full_name="M2")
        me.is_email_verified = True; me.save()
        MenteeProfile.objects.create(user=me, current_role="S", career_goals="G")
        MenteeInterest.objects.create(user=me, interest=i)
        start = timezone.now() + timedelta(days=1)
        slot = AvailabilitySlot.objects.create(mentor=self.mentor, start=start, end=start+timedelta(hours=1))
        b = create_booking(mentee=me, slot_id=slot.id)
        confirm_payment(booking_id=b.id)  # confirmed, NOT completed
        self.client.login(username="m2@b.com", password="X!2345678")
        self.client.post(f"/review/{b.id}/", {"rating": "5"})
        self.assertFalse(Review.objects.filter(booking=b).exists())

    def test_rating_aggregates_on_profile(self):
        b1, m1 = completed_booking(self.mentor, "a@b.com")
        b2, m2 = completed_booking(self.mentor, "b@b.com")
        Review.objects.create(booking=b1, mentee=m1, mentor=self.mentor, rating=5)
        Review.objects.create(booking=b2, mentee=m2, mentor=self.mentor, rating=3)
        mp = MentorProfile.objects.get(user=self.mentor)
        self.assertEqual(mp.review_count, 2)
        self.assertEqual(mp.avg_rating, 4.0)
        self.assertEqual(mp.rating_display, "4.0")

    def test_unrated_mentor_shows_new(self):
        self.assertEqual(self.mp.rating_display, "New")
        self.assertEqual(self.mp.review_count, 0)

    def test_private_note_not_on_public_profile(self):
        b, me = completed_booking(self.mentor)
        Review.objects.create(booking=b, mentee=me, mentor=self.mentor, rating=5,
            review_text="Public text", private_note="SECRET admin note")
        r = self.client.get(f"/mentors/{self.mentor.id}/")
        self.assertNotIn(b"SECRET admin note", r.content)
        self.assertNotIn(b"Public text", r.content)  # written reviews admin-only for now

    def test_staff_can_see_reviews_and_notes(self):
        admin = User.objects.create_superuser(email="admin@mvia.in", password="Admin!2345", full_name="Admin")
        b, me = completed_booking(self.mentor)
        Review.objects.create(booking=b, mentee=me, mentor=self.mentor, rating=2,
            review_text="meh", private_note="SECRET admin note")
        self.client.login(username="admin@mvia.in", password="Admin!2345")
        r = self.client.get("/staff/reviews/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"SECRET admin note", r.content)
