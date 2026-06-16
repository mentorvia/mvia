from django.test import TestCase
from accounts.models import User
from profiles.models import MentorProfile, ProfileSection, ProfileSectionItem


class RichProfileTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email="admin@mvia.in", password="Admin!2345", full_name="Admin")
        self.u = User.objects.create_placeholder_mentor(full_name="R Chandrasekar")
        self.m = MentorProfile.objects.create(user=self.u, current_role="Leader", company="Ex-IBM",
            years_experience=34, bio="Bio here.", hourly_rate=3000, status="approved",
            headline="34+ years", gst_note="Exclusive of 18% GST")

    def test_rich_fields_render_on_public_page(self):
        r = self.client.get(f"/mentors/{self.u.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"34+ years", r.content)
        self.assertIn(b"Exclusive of 18% GST", r.content)

    def test_sections_and_items_render(self):
        sec = ProfileSection.objects.create(mentor=self.m, heading="Core Expertise", order=0)
        ProfileSectionItem.objects.create(section=sec, title="Cloud and AI", description="Deep expertise.")
        r = self.client.get(f"/mentors/{self.u.id}/")
        self.assertIn(b"Core Expertise", r.content)
        self.assertIn(b"Cloud and AI", r.content)
        self.assertIn(b"Deep expertise.", r.content)

    def test_staff_can_add_section_and_item(self):
        self.client.login(username="admin@mvia.in", password="Admin!2345")
        # add section
        self.client.post(f"/staff/mentors/{self.m.id}/edit-profile/", {
            "action": "add_section", "heading": "Focus Areas", "intro": "intro text"})
        sec = ProfileSection.objects.get(mentor=self.m, heading="Focus Areas")
        self.assertEqual(sec.intro, "intro text")
        # add item
        self.client.post(f"/staff/mentors/{self.m.id}/edit-profile/", {
            "action": "add_item", "section_id": sec.id, "title": "Leadership", "description": "Guiding leaders."})
        self.assertTrue(sec.items.filter(title="Leadership").exists())

    def test_staff_can_edit_profile_fields(self):
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
