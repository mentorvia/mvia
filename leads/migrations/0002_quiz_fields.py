from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("leads", "0001_initial"),
    ]

    operations = [
        # Step 1 registration additions
        migrations.AddField(
            model_name="lead",
            name="whatsapp",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="lead",
            name="email_or_linkedin",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="lead",
            name="domain",
            field=models.CharField(blank=True, choices=[
                ("technology", "Technology / IT"), ("engineering", "Engineering"),
                ("finance", "Finance"), ("consulting", "Consulting"),
                ("product", "Product"), ("operations", "Operations"),
                ("marketing", "Marketing"), ("healthcare", "Healthcare"),
                ("other", "Other"),
            ], max_length=30),
        ),
        migrations.AddField(
            model_name="lead",
            name="domain_other",
            field=models.CharField(blank=True, max_length=120),
        ),
        # Step 2 quiz fields
        migrations.AddField(
            model_name="lead",
            name="quiz_completed",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(model_name="lead", name="q1_stage", field=models.CharField(blank=True, max_length=80)),
        migrations.AddField(model_name="lead", name="q2_help", field=models.CharField(blank=True, max_length=120)),
        migrations.AddField(model_name="lead", name="q2_help_other", field=models.CharField(blank=True, max_length=160)),
        migrations.AddField(model_name="lead", name="q3_challenge", field=models.TextField(blank=True)),
        migrations.AddField(model_name="lead", name="q4_goal", field=models.TextField(blank=True)),
        migrations.AddField(model_name="lead", name="q6_intent", field=models.CharField(blank=True, max_length=60)),
        migrations.AddField(model_name="lead", name="q7_time", field=models.CharField(blank=True, max_length=40)),
        migrations.AddField(model_name="lead", name="q8_mentor_type", field=models.CharField(blank=True, max_length=120)),
        migrations.AddField(model_name="lead", name="q9_decisions", field=models.CharField(blank=True, max_length=120)),
        migrations.AddField(model_name="lead", name="q10_contact_pref", field=models.CharField(blank=True, max_length=40)),
        migrations.AddField(
            model_name="lead",
            name="priority",
            field=models.CharField(default="new", max_length=10, choices=[
                ("hot", "Hot"), ("warm", "Warm"), ("cold", "Cold"), ("new", "New (quiz pending)"),
            ]),
        ),
        migrations.AddField(
            model_name="lead",
            name="quiz_completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
