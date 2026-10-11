from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Lead",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150)),
                ("email", models.EmailField(max_length=254)),
                ("phone", models.CharField(blank=True, max_length=30)),
                ("current_role", models.CharField(blank=True, help_text="e.g. Final-year student, Working professional, Career switcher.", max_length=160)),
                ("goal", models.TextField(blank=True, help_text="What the person wants help with.")),
                ("field_of_interest", models.CharField(blank=True, help_text="Free text — the area they're interested in.", max_length=160)),
                ("is_contacted", models.BooleanField(default=False)),
                ("contacted_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True, help_text="Internal ops notes.")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("contacted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="leads_contacted", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
