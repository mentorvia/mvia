"""
Expand the interest taxonomy to an 8-umbrella structure with 27 nested
sub-items, per product direction.

Safety design (data migration touching a live, user-referenced tree):
- New nodes are created via a get-or-create pattern keyed on (name, parent),
  matching Interest's own uniqueness constraint — safe to run repeatedly.
- Two existing top-level categories are RENAMED in place ("Tech" ->
  "Information Technology", "Business" -> "Business & Consulting") by
  updating the `name` field on the existing row. The row's primary key never
  changes, so every MentorInterest/MenteeInterest FK pointing at it (and
  every existing child's `parent` FK) stays valid throughout.
- The brief also asked to move an existing top-level "AI/ML" node under the
  new "Information Technology" umbrella. No such node exists anywhere in
  this taxonomy (verified directly against the database before writing this
  migration) — so there is nothing to preserve by updating in place. This
  migration creates "AI/ML" fresh under Information Technology instead, and
  is written to still prefer an update-in-place move if a top-level "AI/ML"
  row is ever found (e.g. if this migration runs against a database where
  one does exist), so the safe behavior holds either way.
- Everything else the brief listed against an "(existing, keep)" node
  (Software Engineering, Data & AI, Cybersecurity, Cloud & Infrastructure
  under Tech/IT; Consulting under Business/Business & Consulting) already
  exists with that exact name under the renamed parent, so the get-or-create
  calls for those are no-ops — nothing is touched.
- This migration does NOT infer or perform any other reparenting beyond the
  one explicitly specified (AI/ML). Several new nodes share a name with an
  existing node that now sits in a different, thematically-related category
  (e.g. a new "Marketing" under "Sales, Marketing & Growth" alongside the
  pre-existing "Marketing" under "Business & Consulting"; likewise "Product
  Management", "Operations" vs. "Operations & Supply Chain", and the
  existing nested "Finance" vs. the new top-level "Finance"). Rather than
  guess at unstated moves in a migration explicitly scoped around not losing
  data, these are left as-is; see the PR description for the full list.
- Reverse migration undoes the two renames and the AI/ML move (the only
  operations against pre-existing rows), but does not delete the newly
  created nodes — per the brief, forward-only for the additive part is
  acceptable when a full reverse isn't warranted. Because every forward
  operation is itself idempotent (get-or-create / defensive existence
  checks), running forwards -> backwards -> forwards again is safe and
  produces no duplicates.
"""

from django.db import migrations
from django.utils.text import slugify


NEW_TOP_LEVEL = {
    "Engineering & Manufacturing": [
        "Aerospace & Aviation",
        "Automotive & Electric Vehicles (EV)",
        "Civil & Infrastructure",
        "Electrical Engineering",
        "Mechanical Engineering",
        "Manufacturing & Industrial Engineering",
        "Robotics & Automation",
    ],
    "Electronics & Hardware": [
        "Electronics & Semiconductor",
        "Biomedical & Medical Devices",
        "Telecommunications & Networking",
    ],
    "Energy & Environment": [
        "Oil & Gas / Energy",
        "Renewable Energy",
    ],
    "Finance": [
        "Finance & Banking",
        "FinTech",
    ],
    "Sales, Marketing & Growth": [
        "Marketing",
        "Sales & Business Development",
        "Customer Success & Support",
        "Product Management",
    ],
    "Leadership & People": [
        "Leadership & General Management",
        "Human Resources (HR)",
        "Project & Program Management",
        "Entrepreneurship & Startups",
    ],
}

# Existing top-level renames: old name -> new name. Update-in-place only.
RENAMES = {
    "Tech": "Information Technology",
    "Business": "Business & Consulting",
}

# New children to ensure exist under the just-renamed categories, in
# addition to whatever already lives there (which is left untouched).
RENAMED_EXTRA_CHILDREN = {
    "Information Technology": ["Information Technology (IT)"],
    "Business & Consulting": ["Business Analysis", "Operations & Supply Chain", "Legal & Compliance"],
}


def _unique_slug(Interest, name):
    """
    Historical models from apps.get_model() don't carry Interest's custom
    save() (where slug auto-generation normally happens), so migration-created
    rows need it computed by hand — same algorithm as the real model.
    """
    base = slugify(name)
    slug = base
    n = 1
    while Interest.objects.filter(slug=slug).exists():
        n += 1
        slug = f"{base}-{n}"
    return slug


def forwards(apps, schema_editor):
    Interest = apps.get_model("interests", "Interest")

    def ensure(name, parent=None):
        existing = Interest.objects.filter(name=name, parent=parent).first()
        if existing:
            return existing
        return Interest.objects.create(
            name=name, parent=parent, slug=_unique_slug(Interest, name),
            is_custom=False, is_approved=True,
        )

    # 1. Rename existing top-level categories in place.
    renamed = {}
    for old_name, new_name in RENAMES.items():
        node = Interest.objects.filter(parent=None, name=old_name).first()
        if node is None:
            # Already renamed by a prior run of this migration, or the old
            # name genuinely isn't there — fall back to get-or-create so
            # forwards() stays idempotent either way.
            node = ensure(new_name, parent=None)
        elif node.name != new_name:
            node.name = new_name
            node.save(update_fields=["name"])
        renamed[new_name] = node

    it = renamed["Information Technology"]
    business = renamed["Business & Consulting"]

    # 2. Move (or create) AI/ML under Information Technology.
    ai_ml = Interest.objects.filter(parent=None, name="AI/ML").first()
    if ai_ml is not None:
        if ai_ml.parent_id != it.id:
            ai_ml.parent = it
            ai_ml.save(update_fields=["parent"])
    else:
        ensure("AI/ML", parent=it)

    # 3. Extra children for the renamed categories.
    for child_name in RENAMED_EXTRA_CHILDREN["Information Technology"]:
        ensure(child_name, parent=it)
    for child_name in RENAMED_EXTRA_CHILDREN["Business & Consulting"]:
        ensure(child_name, parent=business)

    # 4. Brand-new top-level umbrellas + their children.
    for top_name, children in NEW_TOP_LEVEL.items():
        top_obj = ensure(top_name, parent=None)
        for child_name in children:
            ensure(child_name, parent=top_obj)


def backwards(apps, schema_editor):
    Interest = apps.get_model("interests", "Interest")

    it = Interest.objects.filter(parent=None, name="Information Technology").first()
    if it is not None:
        ai_ml = Interest.objects.filter(parent=it, name="AI/ML").first()
        if ai_ml is not None:
            ai_ml.parent = None
            ai_ml.save(update_fields=["parent"])
        it.name = "Tech"
        it.save(update_fields=["name"])

    business = Interest.objects.filter(parent=None, name="Business & Consulting").first()
    if business is not None:
        business.name = "Business"
        business.save(update_fields=["name"])


class Migration(migrations.Migration):

    dependencies = [
        ("interests", "0002_menteeinterest_mentorinterest"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
