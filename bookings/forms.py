"""Forms for mentor availability."""

from django import forms
from django.utils import timezone

from .models import AvailabilitySlot


class SlotForm(forms.Form):
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    start_time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))
    duration_minutes = forms.ChoiceField(
        choices=[(30, "30 minutes"), (45, "45 minutes"), (60, "60 minutes"), (90, "90 minutes")],
        initial=60)

    def clean(self):
        cleaned = super().clean()
        date = cleaned.get("date")
        start_time = cleaned.get("start_time")
        dur = cleaned.get("duration_minutes")
        if date and start_time and dur:
            from datetime import datetime, timedelta
            tz = timezone.get_current_timezone()
            start = timezone.make_aware(datetime.combine(date, start_time), tz)
            if start <= timezone.now():
                raise forms.ValidationError("Pick a time in the future.")
            cleaned["start_dt"] = start
            cleaned["end_dt"] = start + timedelta(minutes=int(dur))
        return cleaned
