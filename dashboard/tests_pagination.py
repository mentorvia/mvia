from datetime import timedelta
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from profiles.models import MentorProfile, MenteeProfile
from interests.models import Interest, MenteeInterest
from bookings.models import AvailabilitySlot
from bookings.services import create_booking, confirm_payment


class PaginationSearchTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(email="admin@mvia.in", password="Admin!2345", full_name="Admin")
        i = Interest.objects.create(name="Career")
        # create 30 mentors + 30 paid bookings to force multiple pages
        mentor = User.objects.create_user(email="m@b.com", password="X!2345678", full_name="Searchable Mentor")
        mentor.is_mentor = True; mentor.is_email_verified = True; mentor.save()
        MentorProfile.objects.create(user=mentor, current_role="Eng", company="Acme",
            years_experience=5, bio="B", hourly_rate=2000, status="approved")
        for n in range(30):
            me = User.objects.create_user(email=f"u{n}@b.com", password="X!2345678", full_name=f"Mentee {n}")
            me.is_email_verified = True; me.save()
            MenteeProfile.objects.create(user=me, current_role="S", career_goals="G")
            MenteeInterest.objects.create(user=me, interest=i)
            start = timezone.now() + timedelta(days=n+1)
            slot = AvailabilitySlot.objects.create(mentor=mentor, start=start, end=start+timedelta(hours=1))
            b = create_booking(mentee=me, slot_id=slot.id)
            confirm_payment(booking_id=b.id)

    def setUp(self):
        self.client.login(username="admin@mvia.in", password="Admin!2345")

    def test_bookings_paginated(self):
        r = self.client.get("/staff/bookings/")
        self.assertEqual(r.status_code, 200)
        # 30 bookings, 25/page -> page 1 has 25
        self.assertEqual(len(r.context["page_obj"].object_list), 25)
        r2 = self.client.get("/staff/bookings/?page=2")
        self.assertEqual(len(r2.context["page_obj"].object_list), 5)

    def test_bookings_search(self):
        r = self.client.get("/staff/bookings/?q=Mentee 7")
        self.assertEqual(r.status_code, 200)
        # "Mentee 7" matches "Mentee 7" only (not 17/27 since space) -> 1
        names = [b.mentee.full_name for b in r.context["page_obj"].object_list]
        self.assertIn("Mentee 7", names)

    def test_ledger_paginated_and_filtered(self):
        r = self.client.get("/staff/ledger/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context["page_obj"].object_list), 25)
        # filter by type=platform_fee -> 30 entries total, 25 on page 1
        r2 = self.client.get("/staff/ledger/?type=platform_fee")
        for e in r2.context["page_obj"].object_list:
            self.assertEqual(e.entry_type, "platform_fee")

    def test_ledger_summary_uses_all_not_page(self):
        r = self.client.get("/staff/ledger/")
        # 30 bookings x 400 fee = 12000 regardless of pagination
        self.assertEqual(r.context["summary"]["platform_fee"], 12000)

    def test_mentors_search(self):
        r = self.client.get("/staff/mentors/?q=Searchable")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["page_obj"].paginator.count, 1)

    def test_email_search_param_accepted(self):
        r = self.client.get("/staff/emails/?q=test&status=sent")
        self.assertEqual(r.status_code, 200)

    def test_audit_search_param_accepted(self):
        r = self.client.get("/staff/audit/?q=mentor")
        self.assertEqual(r.status_code, 200)

    def test_interests_search(self):
        r = self.client.get("/staff/interests/?q=Career")
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(r.context["search_results"])

    def test_pagination_preserves_filter(self):
        r = self.client.get("/staff/ledger/?type=mentor_earning&page=1")
        self.assertIn("type=mentor_earning", r.context["qs"])
