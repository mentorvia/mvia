from django.test import TestCase
from accounts.models import User
from profiles.models import MentorProfile


class MentorListTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email="admin@mvia.in", password="Admin!2345", full_name="Admin")
        g = User.objects.create_placeholder_mentor(full_name="Chandra Approved")
        MentorProfile.objects.create(user=g, current_role="Leader", company="Ex-IBM",
            years_experience=34, bio="Bio", hourly_rate=3000, status="approved")
        self.gid = g.mentor_profile.id
        p = User.objects.create_user(email="pend@b.com", password="StrongPass!234", full_name="Pending Person")
        p.is_email_verified = True; p.save()
        MentorProfile.objects.create(user=p, current_role="Eng", company="Co",
            years_experience=5, bio="Bio", hourly_rate=1500, status="pending")
        self.client.login(username="admin@mvia.in", password="Admin!2345")

    def test_page_shows_pending_and_approved_with_edit(self):
        r = self.client.get("/staff/mentors/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Pending Person", r.content)       # pending section
        self.assertIn(b"Chandra Approved", r.content)     # approved section
        self.assertIn(b"No email yet", r.content)         # placeholder badge
        self.assertIn(f"/staff/mentors/{self.gid}/edit-profile/".encode(), r.content)  # edit link
