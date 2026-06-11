from django.test import TestCase
from accounts.models import User
from profiles.models import MentorProfile, MenteeProfile
from interests.models import Interest, MentorInterest, MenteeInterest


def make_mentor(email, name, role="Engineer", rate=1500, status="approved", available=True):
    u = User.objects.create_user(email=email, password="StrongPass!234", full_name=name)
    u.is_email_verified = True; u.is_mentor = (status == "approved"); u.save()
    m = MentorProfile.objects.create(user=u, current_role=role, company="Co",
        years_experience=5, bio="Experienced mentor.", hourly_rate=rate,
        status=status, is_available=available)
    return u, m


class DirectoryTest(TestCase):
    def setUp(self):
        self.ml = Interest.objects.create(name="Machine Learning")
        self.be = Interest.objects.create(name="Backend")
        self.u1, self.m1 = make_mentor("a@b.com", "Alice Approved", role="ML Lead", rate=2000)
        MentorInterest.objects.create(user=self.u1, interest=self.ml)
        self.u2, self.m2 = make_mentor("b@b.com", "Bob Backend", role="Backend Dev", rate=1000)
        MentorInterest.objects.create(user=self.u2, interest=self.be)
        # pending mentor should NOT appear
        self.u3, self.m3 = make_mentor("c@b.com", "Carol Pending", status="pending")
        # unavailable approved mentor should NOT appear
        self.u4, self.m4 = make_mentor("d@b.com", "Dave Away", available=False)

    def test_only_approved_available_listed(self):
        r = self.client.get("/mentors/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Alice Approved", r.content)
        self.assertIn(b"Bob Backend", r.content)
        self.assertNotIn(b"Carol Pending", r.content)
        self.assertNotIn(b"Dave Away", r.content)

    def test_search(self):
        r = self.client.get("/mentors/?q=backend")
        self.assertIn(b"Bob Backend", r.content)
        self.assertNotIn(b"Alice Approved", r.content)

    def test_interest_filter(self):
        r = self.client.get(f"/mentors/?interest={self.ml.id}")
        self.assertIn(b"Alice Approved", r.content)
        self.assertNotIn(b"Bob Backend", r.content)

    def test_max_rate_filter(self):
        r = self.client.get("/mentors/?max_rate=1200")
        self.assertIn(b"Bob Backend", r.content)      # 1000 <= 1200
        self.assertNotIn(b"Alice Approved", r.content) # 2000 > 1200

    def test_recommendations_for_mentee(self):
        mentee = User.objects.create_user(email="learner@b.com", password="StrongPass!234", full_name="Learner")
        mentee.is_email_verified = True; mentee.save()
        MenteeInterest.objects.create(user=mentee, interest=self.ml)
        self.client.login(username="learner@b.com", password="StrongPass!234")
        r = self.client.get("/mentors/")
        self.assertIn(b"Recommended", r.content)  # Alice (ML) recommended

    def test_mentor_profile_page(self):
        r = self.client.get(f"/mentors/{self.u1.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Alice Approved", r.content)
        self.assertIn(b"ML Lead", r.content)

    def test_pending_mentor_profile_404(self):
        r = self.client.get(f"/mentors/{self.u3.id}/")
        self.assertEqual(r.status_code, 404)

    def test_homepage_loads_with_nav(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Get started", r.content)  # signup CTA for anon
        self.assertIn(b"Find a mentor", r.content)
