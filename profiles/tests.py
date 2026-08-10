from django.test import TestCase
from accounts.models import User
from interests.models import Interest, MenteeInterest, MentorInterest
from profiles.models import MenteeProfile, MentorProfile
from auditlog.models import AdminAuditLog


def make_user(email, **kw):
    u = User.objects.create_user(email=email, password="StrongPass!234", full_name=kw.pop("name","User"))
    u.is_email_verified = True
    for k,v in kw.items(): setattr(u,k,v)
    u.save()
    return u


class MenteeProfileTest(TestCase):
    def test_completeness_gate(self):
        u = make_user("m@b.com")
        p = MenteeProfile.objects.create(user=u)
        self.assertFalse(p.is_complete())  # empty
        p.current_role = "Student"; p.career_goals = "Grow"; p.save()
        self.assertFalse(p.is_complete())  # no interest yet
        i = Interest.objects.create(name="Leadership")
        MenteeInterest.objects.create(user=u, interest=i)
        self.assertTrue(p.is_complete())   # now complete

    def test_profile_save_and_interest_selection(self):
        u = make_user("m2@b.com")
        self.client.login(username="m2@b.com", password="StrongPass!234")
        i1 = Interest.objects.create(name="ML")
        i2 = Interest.objects.create(name="Design")
        self.client.post("/profile/me/", {
            "current_role": "Analyst", "company": "X", "years_experience": "2",
            "career_goals": "Switch to data science", "interests": [i1.id, i2.id],
        }, follow=True)
        self.assertEqual(u.mentee_interests.count(), 2)
        p = MenteeProfile.objects.get(user=u)
        self.assertEqual(p.current_role, "Analyst")
        self.assertTrue(p.is_complete())

    def test_custom_interest_submission(self):
        u = make_user("m3@b.com")
        self.client.login(username="m3@b.com", password="StrongPass!234")
        self.client.post("/profile/me/", {
            "current_role": "Dev", "company": "Y", "years_experience": "3",
            "career_goals": "Lead a team", "custom_interest": "Robotics",
        }, follow=True)
        custom = Interest.objects.filter(name="Robotics").first()
        self.assertIsNotNone(custom)
        self.assertTrue(custom.is_custom)
        self.assertFalse(custom.is_approved)
        self.assertEqual(custom.submitted_by, u)


class MentorFlowTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email="admin@mvia.in", password="Admin!2345", full_name="Admin")
        self.spec = Interest.objects.create(name="Backend")

    def test_apply_creates_pending(self):
        u = make_user("cand@b.com")
        self.client.login(username="cand@b.com", password="StrongPass!234")
        self.client.post("/profile/become-a-mentor/", {
            "current_role": "Senior Eng", "company": "BigCo", "years_experience": "8",
            "bio": "I help people grow.", "hourly_rate": "1500", "interests": [self.spec.id],
        }, follow=True)
        m = MentorProfile.objects.get(user=u)
        self.assertEqual(m.status, "pending")
        self.assertFalse(u.is_mentor)  # not a mentor until approved
        self.assertEqual(u.mentor_interests.count(), 1)

    def test_apply_without_specialization_is_soft_not_blocked(self):
        # The minimum-3-specializations rule is a client-side soft nudge only
        # (see templates/profiles/_interest_picker.html) — the server never
        # hard-blocks, so an application with zero interests still succeeds.
        u = make_user("cand2@b.com")
        self.client.login(username="cand2@b.com", password="StrongPass!234")
        r = self.client.post("/profile/become-a-mentor/", {
            "current_role": "Eng", "company": "Co", "years_experience": "5",
            "bio": "Bio", "hourly_rate": "1000",
        })
        self.assertTrue(MentorProfile.objects.filter(user=u).exists())
        self.assertEqual(u.mentor_interests.count(), 0)

    def test_approval_flow_with_audit(self):
        u = make_user("cand3@b.com")
        m = MentorProfile.objects.create(user=u, current_role="Eng", company="Co",
            years_experience=5, bio="Bio", hourly_rate=1200, status="pending")
        self.client.login(username="admin@mvia.in", password="Admin!2345")
        self.client.post(f"/staff/mentors/{m.id}/", {"action": "approve"}, follow=True)
        m.refresh_from_db(); u.refresh_from_db()
        self.assertEqual(m.status, "approved")
        self.assertTrue(u.is_mentor)
        self.assertTrue(m.is_listable)
        # audit log entry created
        self.assertTrue(AdminAuditLog.objects.filter(action="mentor.approve", actor=self.admin).exists())

    def test_rejection_flow_with_audit(self):
        u = make_user("cand4@b.com")
        m = MentorProfile.objects.create(user=u, current_role="Eng", company="Co",
            years_experience=2, bio="Bio", hourly_rate=900, status="pending")
        self.client.login(username="admin@mvia.in", password="Admin!2345")
        self.client.post(f"/staff/mentors/{m.id}/", {"action": "reject", "reason": "Not enough experience"}, follow=True)
        m.refresh_from_db(); u.refresh_from_db()
        self.assertEqual(m.status, "rejected")
        self.assertFalse(u.is_mentor)
        self.assertFalse(m.is_listable)
        log = AdminAuditLog.objects.get(action="mentor.reject")
        self.assertEqual(log.reason, "Not enough experience")

    def test_queue_requires_staff(self):
        u = make_user("notstaff@b.com")
        self.client.login(username="notstaff@b.com", password="StrongPass!234")
        self.assertEqual(self.client.get("/staff/mentors/").status_code, 302)
