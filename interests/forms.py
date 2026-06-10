"""Forms for managing interests in the staff console."""

from django import forms
from .models import Interest


class InterestForm(forms.ModelForm):
    class Meta:
        model = Interest
        fields = ["name", "parent", "is_approved"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Machine Learning"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Parent dropdown shows the full breadcrumb path for clarity, and a
        # blank option meaning "top-level category". Exclude self to prevent loops.
        qs = Interest.objects.all()
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        self.fields["parent"].queryset = qs
        self.fields["parent"].required = False
        self.fields["parent"].empty_label = "— Top-level category —"
        self.fields["parent"].label_from_instance = lambda obj: obj.breadcrumb()

    def clean_parent(self):
        parent = self.cleaned_data.get("parent")
        # Guard against making something its own ancestor (would create a cycle).
        if parent and self.instance and self.instance.pk:
            node = parent
            while node is not None:
                if node.pk == self.instance.pk:
                    raise forms.ValidationError("An interest can't be placed under itself.")
                node = node.parent
        return parent
