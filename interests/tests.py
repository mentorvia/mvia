from django.test import TestCase
from accounts.models import User
from interests.models import Interest, MenteeInterest, MentorInterest


class InterestModelTest(TestCase):
    def test_tree_and_breadcrumb(self):
        tech = Interest.objects.create(name="Tech")
        ai = Interest.objects.create(name="Data & AI", parent=tech)
        ml = Interest.objects.create(name="Machine Learning", parent=ai)
        self.assertTrue(tech.is_category)
        self.assertFalse(ml.is_category)
        self.assertEqual(ml.depth, 2)
        self.assertEqual(ml.breadcrumb(), "Tech › Data & AI › Machine Learning")

    def test_unique_name_per_parent(self):
        tech = Interest.objects.create(name="Tech")
        Interest.objects.create(name="ML", parent=tech)
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Interest.objects.create(name="ML", parent=tech)
        # same name under a DIFFERENT parent is fine
        biz = Interest.objects.create(name="Business")
        Interest.objects.create(name="ML", parent=biz)  # no error

    def test_join_models_normalized(self):
        u = User.objects.create_user(email="a@b.com", password="StrongPass!234", full_name="A")
        i = Interest.objects.create(name="Leadership")
        MenteeInterest.objects.create(user=u, interest=i)
        self.assertEqual(u.mentee_interests.count(), 1)
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError):  # no duplicate link
            with transaction.atomic():
                MenteeInterest.objects.create(user=u, interest=i)


class InterestStaffTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="admin@mvia.in", password="Admin!2345", full_name="Admin")
        self.client.login(username="admin@mvia.in", password="Admin!2345")

    def test_list_loads(self):
        Interest.objects.create(name="Tech")
        r = self.client.get("/staff/interests/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Tech", r.content)

    def test_add_interest(self):
        r = self.client.post("/staff/interests/add/", {"name": "Cybersecurity", "is_approved": "on"}, follow=True)
        self.assertTrue(Interest.objects.filter(name="Cybersecurity").exists())

    def test_add_subdomain(self):
        tech = Interest.objects.create(name="Tech")
        self.client.post("/staff/interests/add/", {"name": "DevOps", "parent": tech.id, "is_approved": "on"}, follow=True)
        dev = Interest.objects.get(name="DevOps")
        self.assertEqual(dev.parent_id, tech.id)

    def test_edit_interest(self):
        i = Interest.objects.create(name="Old Name")
        self.client.post(f"/staff/interests/{i.id}/edit/", {"name": "New Name", "is_approved": "on"}, follow=True)
        i.refresh_from_db()
        self.assertEqual(i.name, "New Name")

    def test_delete_cascades(self):
        before = Interest.objects.count()
        tech = Interest.objects.create(name="Tech Test Node")
        Interest.objects.create(name="ML Test Node", parent=tech)
        self.client.post(f"/staff/interests/{tech.id}/delete/", follow=True)
        self.assertEqual(Interest.objects.count(), before)  # both created rows gone, nothing else touched

    def test_cannot_make_self_parent(self):
        i = Interest.objects.create(name="X")
        r = self.client.post(f"/staff/interests/{i.id}/edit/", {"name": "X", "parent": i.id, "is_approved": "on"})
        i.refresh_from_db()
        self.assertIsNone(i.parent_id)  # rejected

    def test_promote_custom_interest(self):
        member = User.objects.create_user(email="u@b.com", password="StrongPass!234", full_name="U")
        custom = Interest.objects.create(name="Quantum Computing", is_custom=True, is_approved=False, submitted_by=member)
        tech = Interest.objects.create(name="Tech")
        self.client.post("/staff/interests/custom/", {
            "action": "approve", "interest_id": custom.id, "parent": tech.id,
        }, follow=True)
        custom.refresh_from_db()
        self.assertTrue(custom.is_approved)
        self.assertFalse(custom.is_custom)
        self.assertEqual(custom.parent_id, tech.id)

    def test_reject_custom_interest(self):
        custom = Interest.objects.create(name="Spam", is_custom=True, is_approved=False)
        self.client.post("/staff/interests/custom/", {"action": "reject", "interest_id": custom.id}, follow=True)
        self.assertFalse(Interest.objects.filter(name="Spam").exists())

    def test_non_staff_blocked(self):
        self.client.logout()
        member = User.objects.create_user(email="m@b.com", password="StrongPass!234", full_name="M")
        self.client.login(username="m@b.com", password="StrongPass!234")
        self.assertEqual(self.client.get("/staff/interests/").status_code, 302)
