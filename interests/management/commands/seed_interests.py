"""
Seed a starter interest taxonomy (requirement 4.4 / Section 10).

Safe to run repeatedly: it only creates interests that don't already exist,
so it never duplicates or overwrites admin edits. The taxonomy here is a
sensible STARTER — the product owner will refine the final taxonomy later.
"""

from django.core.management.base import BaseCommand
from interests.models import Interest

# category -> { sub-domain -> [deeper sub-domains] }
TAXONOMY = {
    "Tech": {
        "Software Engineering": ["Frontend", "Backend", "Mobile", "DevOps"],
        "Data & AI": ["Machine Learning", "Data Science", "Data Engineering", "Deep Learning"],
        "Cybersecurity": [],
        "Cloud & Infrastructure": [],
        "Product Management": [],
    },
    "Business": {
        "Entrepreneurship": ["Fundraising", "Startups"],
        "Marketing": ["Digital Marketing", "Brand Strategy", "Growth"],
        "Sales": [],
        "Finance": ["Investment Banking", "Venture Capital", "Personal Finance"],
        "Operations": [],
        "Consulting": [],
    },
    "Career": {
        "Resume & Interview Prep": [],
        "Career Switching": [],
        "Leadership": [],
        "Public Speaking": [],
        "Negotiation": [],
        "Work-Life Balance": [],
    },
    "Design": {
        "UX/UI Design": [],
        "Product Design": [],
        "Graphic Design": [],
    },
    "Academics": {
        "Higher Studies / MS": [],
        "Research": [],
        "Study Abroad": [],
    },
}


class Command(BaseCommand):
    help = "Seed a starter interest taxonomy (idempotent)."

    def handle(self, *args, **options):
        created = 0

        def ensure(name, parent=None):
            nonlocal created
            obj = Interest.objects.filter(name=name, parent=parent).first()
            if obj:
                return obj
            obj = Interest.objects.create(name=name, parent=parent, is_custom=False, is_approved=True)
            created += 1
            return obj

        for category, subs in TAXONOMY.items():
            cat = ensure(category)
            for sub, deepers in subs.items():
                sub_obj = ensure(sub, parent=cat)
                for deep in deepers:
                    ensure(deep, parent=sub_obj)

        self.stdout.write(self.style.SUCCESS(
            f"seed_interests: done. Created {created} new interest(s); "
            f"total now {Interest.objects.count()}."
        ))
