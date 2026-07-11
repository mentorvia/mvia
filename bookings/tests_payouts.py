from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from profiles.models import MentorProfile, MenteeProfile
from interests.models import Interest, MenteeInterest
from bookings.models import AvailabilitySlot, Booking
from bookings.services import create_booking, confirm_payment, complete_booking, record_refund
from bookings.services import approve_booking
from payments.models import LedgerEntry, Payout


def make_completed_booking(mentor, mentee_email, rate_slot_offset_days=1):
    i = Interest.objects.filter(name="Career").first() or Interest.objects.create(name="Career")
    me = User.objects.create_user(email=mentee_email, password="X!2345678", full_name=mentee_email.split("@")[0])
    me.is_email_verified = True; me.save()
    MenteeProfile.objects.create(user=me, current_role="S", career_goals="G")
    MenteeInterest.objects.create(user=me, interest=i)
    start = timezone.now() + timedelta(days=rate_slot_offset_days)
    slot = AvailabilitySlot.objects.create(mentor=mentor, start=start, end=start+timedelta(hours=1))
    b = create_booking(mentee=me, slot_id=slot.id)
    confirm_payment(booking_id=b.id)
    approve_booking(booking_id=b.id, actor=b.mentor)
    return b


class PayoutTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email="admin@mvia.in", password="Admin!2345", full_name="Admin")
        self.mentor = User.objects.create_user(email="men@b.com", password="X!2345678", full_name="Men Tor")
        self.mentor.is_mentor = True; self.mentor.is_email_verified = True; self.mentor.save()
        MentorProfile.objects.create(user=self.mentor, current_role="Eng", company="Co",
            years_experience=5, bio="B", hourly_rate=2000, status="approved")
        self.client.login(username="admin@mvia.in", password="Admin!2345")

    def test_confirmed_not_completed_excluded(self):
        # A confirmed-but-not-completed booking should NOT appear (earnings only on completion).
        make_completed_booking(self.mentor, "a@b.com")  # confirmed only
        r = self.client.get("/staff/earnings/")
        self.assertEqual(r.context["grand_total"], Decimal("0"))

    def test_completed_appears(self):
        b = make_completed_booking(self.mentor, "a@b.com")
        complete_booking(booking_id=b.id)
        r = self.client.get("/staff/earnings/")
        self.assertEqual(r.context["grand_total"], Decimal("2000"))
        self.assertEqual(len(r.context["report"]), 1)

    def test_refunded_excluded(self):
        b = make_completed_booking(self.mentor, "a@b.com")
        complete_booking(booking_id=b.id)
        record_refund(booking_id=b.id, actor=self.admin, reason="x")
        r = self.client.get("/staff/earnings/")
        self.assertEqual(r.context["grand_total"], Decimal("0"))

    def test_mark_paid_creates_payout_and_clears(self):
        b1 = make_completed_booking(self.mentor, "a@b.com", 1); complete_booking(booking_id=b1.id)
        b2 = make_completed_booking(self.mentor, "b@b.com", 2); complete_booking(booking_id=b2.id)
        # two completed sessions = 4000 owed
        r = self.client.get("/staff/earnings/")
        self.assertEqual(r.context["grand_total"], Decimal("4000"))
        # mark paid
        self.client.post("/staff/earnings/", {"action": "mark_paid", "mentor_ids": [str(self.mentor.id)], "reference": "UPI123"})
        # payout created
        p = Payout.objects.get(mentor=self.mentor)
        self.assertEqual(p.amount, Decimal("4000"))
        self.assertEqual(p.sessions_count, 2)
        self.assertEqual(p.reference, "UPI123")
        # report now empty
        r2 = self.client.get("/staff/earnings/")
        self.assertEqual(r2.context["grand_total"], Decimal("0"))

    def test_new_session_after_payout_not_swept(self):
        b1 = make_completed_booking(self.mentor, "a@b.com", 1); complete_booking(booking_id=b1.id)
        self.client.post("/staff/earnings/", {"action": "mark_paid", "mentor_ids": [str(self.mentor.id)]})
        # a new completed session after the payout
        b2 = make_completed_booking(self.mentor, "b@b.com", 2); complete_booking(booking_id=b2.id)
        r = self.client.get("/staff/earnings/")
        # only the new 2000 shows, the paid one stays cleared
        self.assertEqual(r.context["grand_total"], Decimal("2000"))
        # and there's still only one payout
        self.assertEqual(Payout.objects.filter(mentor=self.mentor).count(), 1)

    def test_cannot_double_pay_same_earning(self):
        b1 = make_completed_booking(self.mentor, "a@b.com", 1); complete_booking(booking_id=b1.id)
        self.client.post("/staff/earnings/", {"action": "mark_paid", "mentor_ids": [str(self.mentor.id)]})
        # try to mark paid again — nothing unpaid, so no new payout
        self.client.post("/staff/earnings/", {"action": "mark_paid", "mentor_ids": [str(self.mentor.id)]})
        self.assertEqual(Payout.objects.filter(mentor=self.mentor).count(), 1)

    def test_csv_export(self):
        b = make_completed_booking(self.mentor, "a@b.com"); complete_booking(booking_id=b.id)
        r = self.client.get("/staff/earnings/?export=csv")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "text/csv")
        self.assertIn(b"Men Tor", r.content)

    def test_payout_history_loads(self):
        b = make_completed_booking(self.mentor, "a@b.com"); complete_booking(booking_id=b.id)
        self.client.post("/staff/earnings/", {"action": "mark_paid", "mentor_ids": [str(self.mentor.id)]})
        r = self.client.get("/staff/payouts/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Men Tor", r.content)
