"""Public free-consultation funnel: registration form + quiz form."""

from django import forms

from .models import Lead


class RegistrationForm(forms.ModelForm):
    """Step 1 — basic info. Saves the lead immediately."""
    # Honeypot: hidden field real visitors never fill; bots do. If filled, drop.
    company_site = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Lead
        fields = ["name", "whatsapp", "email_or_linkedin", "domain", "domain_other"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Full name"}),
            "whatsapp": forms.TextInput(attrs={"placeholder": "WhatsApp number"}),
            "email_or_linkedin": forms.TextInput(attrs={"placeholder": "Work email or LinkedIn link"}),
            "domain_other": forms.TextInput(attrs={"placeholder": "Tell us your domain"}),
        }
        labels = {
            "whatsapp": "WhatsApp number",
            "email_or_linkedin": "Work email / LinkedIn link",
            "domain": "Which career/domain are you currently pursuing or exploring?",
            "domain_other": "Other domain",
        }

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if len(name) < 2:
            raise forms.ValidationError("Please enter your name.")
        return name

    def clean(self):
        cleaned = super().clean()
        # If they picked a real email in the email_or_linkedin field, mirror it
        # into the proper email field so staff can filter/contact by email.
        val = (cleaned.get("email_or_linkedin") or "").strip()
        if "@" in val and "." in val and " " not in val:
            cleaned["email"] = val
        return cleaned


# --- Quiz choice lists (kept here so the template and validation share them) ---

Q1_CHOICES = [
    "Final-year student", "Recent graduate", "0–2 years of experience",
    "3–7 years of experience", "8+ years of experience", "Considering a career transition",
]
Q2_CHOICES = [
    "Choosing the right career direction", "Selecting a specialization",
    "Understanding industry expectations", "Building the right skills",
    "Career planning", "Job / interview readiness", "Career transition",
    "Leadership development", "Other",
]
Q6_CHOICES = [
    "Yes, I'm actively looking", "Maybe, if I find the right Guru",
    "No, just looking for free guidance",
]
Q7_CHOICES = ["2 hours/week", "3-4 hours/week", "6+ hours/week"]
Q8_CHOICES = [
    "An experienced professional in my target industry", "A senior industry leader",
    "A functional/technical expert", "Someone who has followed a similar career path",
    "Not sure — I would like guidance on this",
]
Q9_CHOICES = [
    "YouTube / Instagram / Random articles", "Asking friends & seniors",
    "Applying randomly on LinkedIn / Naukri", "I have no system",
]
Q10_CHOICES = ["WhatsApp", "Phone call", "Email"]


class QuizForm(forms.ModelForm):
    """Step 2 — the Navi's Career Navigation Audit quiz."""
    class Meta:
        model = Lead
        fields = [
            "q1_stage", "q2_help", "q2_help_other", "q3_challenge", "q4_goal",
            "q6_intent", "q7_time", "q8_mentor_type", "q9_decisions", "q10_contact_pref",
        ]
        widgets = {
            "q1_stage": forms.RadioSelect(choices=[(c, c) for c in Q1_CHOICES]),
            "q2_help": forms.RadioSelect(choices=[(c, c) for c in Q2_CHOICES]),
            "q2_help_other": forms.TextInput(attrs={"placeholder": "Other — tell us"}),
            "q3_challenge": forms.Textarea(attrs={"rows": 3, "placeholder": "Your biggest career question or challenge right now"}),
            "q4_goal": forms.Textarea(attrs={"rows": 3, "placeholder": "What you're hoping to achieve through mentorship"}),
            "q6_intent": forms.RadioSelect(choices=[(c, c) for c in Q6_CHOICES]),
            "q7_time": forms.RadioSelect(choices=[(c, c) for c in Q7_CHOICES]),
            "q8_mentor_type": forms.RadioSelect(choices=[(c, c) for c in Q8_CHOICES]),
            "q9_decisions": forms.RadioSelect(choices=[(c, c) for c in Q9_CHOICES]),
            "q10_contact_pref": forms.RadioSelect(choices=[(c, c) for c in Q10_CHOICES]),
        }
