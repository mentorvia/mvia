"""
Remove the Stage 1 columns that Stage 2 replaced.

Stage 1 created: phone, current_role, goal, field_of_interest.
Stage 2 replaced them with: whatsapp, email_or_linkedin, domain, and the q*
quiz fields. The old columns are now unused and 'phone' is NOT NULL, which
blocks new inserts. This migration drops the four orphaned columns.

Safe: the leads table has no real data yet, and these columns are unused.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("leads", "0002_quiz_fields"),
    ]

    operations = [
        migrations.RemoveField(model_name="lead", name="phone"),
        migrations.RemoveField(model_name="lead", name="current_role"),
        migrations.RemoveField(model_name="lead", name="goal"),
        migrations.RemoveField(model_name="lead", name="field_of_interest"),
    ]
