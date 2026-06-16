from django.test import TestCase
from accounts.models import User
from profiles.models import MentorProfile, ProfilePoint


class RichProfileTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email="admin@mvia.in", password="Admin!2345", full_name="Admin")
        self.u = User.objects.create_placeholder_mentor(full_name="R Chandrasekar")
        self.m = MentorProfile.objects.create(user=self.u, current_role="Leader", company="Ex-IBM",
            years_experience=34, bio="Bio here.", hourly_rate=3000, status="approved",
            headline="34+ years", gst_note="Exclusive of 18% GST")

    def test_rich_fields_render(self):
        r = self.client.get(f"/mentors/{self.u.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"34+ years", r.content)
        self.assertIn(b"Exclusive of 18% GST", r.content)
        self.assertIn(b"About the Mentor", r.content)

    def test_expertise_and_focus_render_in_right_sections(self):
        ProfilePoint.objects.create(mentor=self.m, category="expertise", title="Cloud Solutions", description="Deep cloud expertise.")
        ProfilePoint.objects.create(mentor=self.m, category="focus", title="Career Guidance", description="Helping mentees.")
        r = self.client.get(f"/mentors/{self.u.id}/")
        c = r.content.decode()
        self.assertIn("Core Industry Expertise", c)
        self.assertIn("Cloud Solutions", c)
        self.assertIn("Mentorship Focus Areas", c)
        self.assertIn("Career Guidance", c)
        # expertise heading appears before focus heading
        self.assertLess(c.index("Core Industry Expertise"), c.index("Mentorship Focus Areas"))

    def test_staff_add_expertise_point(self):
        self.client.login(username="admin@mvia.in", password="Admin!2345")
        self.client.post(f"/staff/mentors/{self.m.id}/edit-profile/", {
            "action": "add_point", "category": "expertise",
            "title": "Enterprise Sales", "description": "Scaling businesses."})
        self.assertTrue(self.m.points.filter(category="expertise", title="Enterprise Sales").exists())

    def test_staff_add_focus_point(self):
        self.client.login(username="admin@mvia.in", password="Admin!2345")
        self.client.post(f"/staff/mentors/{self.m.id}/edit-profile/", {
            "action": "add_point", "category": "focus",
            "title": "Leadership", "description": "Guiding leaders."})
        self.assertTrue(self.m.points.filter(category="focus", title="Leadership").exists())

    def test_staff_delete_point(self):
        p = ProfilePoint.objects.create(mentor=self.m, category="expertise", title="Temp")
        self.client.login(username="admin@mvia.in", password="Admin!2345")
        self.client.post(f"/staff/mentors/{self.m.id}/edit-profile/", {
            "action": "delete_point", "point_id": p.id})
        self.assertFalse(ProfilePoint.objects.filter(id=p.id).exists())

    def test_staff_edit_profile_fields(self):
        self.client.login(username="admin@mvia.in", password="Admin!2345")
        self.client.post(f"/staff/mentors/{self.m.id}/edit-profile/", {
            "action": "save_profile", "headline": "New headline", "bio": "New bio",
            "current_role": "CTO", "company": "Acme", "years_experience": "20",
            "hourly_rate": "3500", "gst_note": "Exclusive of 18% GST", "is_available": "on",
            "photo_url": "", "linkedin_url": "", "website_url": "",
        })
        self.m.refresh_from_db()
        self.assertEqual(self.m.headline, "New headline")
        self.assertEqual(self.m.hourly_rate, 3500)

    def test_display_photo_falls_back_to_url(self):
        self.m.photo_url = "https://example.com/photo.jpg"
        self.m.save()
        self.assertEqual(self.m.display_photo, "https://example.com/photo.jpg")

    def test_non_staff_cannot_edit(self):
        member = User.objects.create_user(email="x@b.com", password="StrongPass!234", full_name="X")
        member.is_email_verified = True; member.save()
        self.client.login(username="x@b.com", password="StrongPass!234")
        r = self.client.get(f"/staff/mentors/{self.m.id}/edit-profile/")
        self.assertEqual(r.status_code, 302)
