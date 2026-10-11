"""The public free-consultation survey form."""

from django import forms

from .models import Lead


class LeadForm(forms.ModelForm):
    # Honeypot: a field real visitors never see (hidden via CSS in the template),
    # but scripted bots fill. If it has content, we silently drop the submission.
    # Mirrors the pattern already used on the public mentor-application form.
    company_site = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Lead
        fields = ["name", "email", "phone", "current_role", "goal", "field_of_interest"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Your name"}),
            "email": forms.EmailInput(attrs={"placeholder": "you@example.com"}),
            "phone": forms.TextInput(attrs={"placeholder": "Phone (optional)"}),
            "current_role": forms.TextInput(attrs={"placeholder": "e.g. Final-year student, Working professional"}),
            "goal": forms.Textarea(attrs={"rows": 2, "placeholder": "What would you like help with?"}),
            "field_of_interest": forms.TextInput(attrs={"placeholder": "e.g. Tech, Healthcare, Management"}),
        }

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if len(name) < 2:
            raise forms.ValidationError("Please enter your name.")
        if len(name) > 100:
            raise forms.ValidationError("Please keep the name under 100 characters.")
        return name
