"""Forms for mentee profiles and mentor applications."""

from decimal import Decimal
from django import forms

from .models import MenteeProfile, MentorProfile
from interests.models import Interest


class MenteeProfileForm(forms.ModelForm):
    class Meta:
        model = MenteeProfile
        fields = ["current_role", "company", "years_experience", "career_goals"]
        widgets = {
            "career_goals": forms.Textarea(attrs={"rows": 4,
                "placeholder": "What do you want guidance on? Where are you headed?"}),
            "current_role": forms.TextInput(attrs={"placeholder": "e.g. Final-year CS student"}),
            "company": forms.TextInput(attrs={"placeholder": "e.g. NIT Trichy (or your employer)"}),
        }


class MentorApplicationForm(forms.ModelForm):
    class Meta:
        model = MentorProfile
        fields = ["current_role", "company", "years_experience", "bio", "hourly_rate"]
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 5,
                "placeholder": "Tell mentees about your background and how you can help."}),
            "hourly_rate": forms.NumberInput(attrs={"placeholder": "e.g. 1500", "min": "0", "step": "1"}),
        }
        labels = {"hourly_rate": "Rate per session (₹)"}

    def clean_hourly_rate(self):
        rate = self.cleaned_data["hourly_rate"]
        if rate is not None and rate < 0:
            raise forms.ValidationError("Rate can't be negative.")
        return rate
