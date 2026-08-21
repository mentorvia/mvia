"""Forms for mentee profiles and mentor applications."""

from decimal import Decimal
from django import forms

from .models import MenteeProfile, MentorProfile, MentorApplication
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


class MentorApplicationPublicForm(forms.ModelForm):
    """
    The public, no-account-needed /become-a-mentor/ form. A separate pipeline
    from MentorApplicationForm above (which is the existing logged-in-mentee
    upgrade path) — see MentorApplication's docstring.
    """
    class Meta:
        model = MentorApplication
        fields = [
            "name", "email", "linkedin_url", "current_role", "current_company",
            "industry", "experience_years", "why_mentor", "bio", "expertise",
        ]
        widgets = {
            "linkedin_url": forms.URLInput(attrs={"placeholder": "https://linkedin.com/in/…"}),
            "current_role": forms.TextInput(attrs={"placeholder": "e.g. VP Engineering"}),
            "current_company": forms.TextInput(attrs={"placeholder": "e.g. Acme Corp"}),
            "industry": forms.TextInput(attrs={"placeholder": "e.g. Technology, Finance, Consulting"}),
            "experience_years": forms.NumberInput(attrs={"min": "0", "max": "60"}),
            "why_mentor": forms.Textarea(attrs={"rows": 4,
                "placeholder": "What draws you to mentoring on mVia?"}),
            "bio": forms.Textarea(attrs={"rows": 5,
                "placeholder": "Tell us about your career background."}),
            "expertise": forms.Textarea(attrs={"rows": 3,
                "placeholder": "Optional — any specific areas you'd want to focus on."}),
        }
        labels = {
            "linkedin_url": "LinkedIn URL",
            "current_company": "Current company",
            "experience_years": "Years of experience",
            "why_mentor": "Why do you want to mentor?",
            "bio": "Brief bio / background",
            "expertise": "Any specific areas of expertise or interests (optional)",
        }

    def clean_experience_years(self):
        years = self.cleaned_data["experience_years"]
        if years is not None and years > 60:
            raise forms.ValidationError("Please enter a realistic number of years (0–60).")
        return years


class MentorApplicationApprovalForm(forms.Form):
    """Collected in the staff 'Approve' modal — the two inputs the free-text
    application can't supply on its own: a rate, and structured specializations."""
    hourly_rate = forms.IntegerField(min_value=0, label="Rate per session (₹)")
