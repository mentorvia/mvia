from django import forms
from .models import Review


class ReviewForm(forms.ModelForm):
    rating = forms.TypedChoiceField(
        choices=[(5, "★★★★★ Excellent"), (4, "★★★★ Good"), (3, "★★★ Okay"),
                 (2, "★★ Poor"), (1, "★ Very poor")],
        coerce=int, widget=forms.RadioSelect, label="Your rating")

    class Meta:
        model = Review
        fields = ["rating", "review_text", "private_note"]
        widgets = {
            "review_text": forms.Textarea(attrs={"rows": 4, "placeholder": "What was helpful? (optional)"}),
            "private_note": forms.Textarea(attrs={"rows": 3, "placeholder": "Anything you'd like to flag privately to the mVia team? (optional, never shown publicly)"}),
        }
        labels = {
            "review_text": "Written review (optional)",
            "private_note": "Private note to mVia (optional)",
        }
