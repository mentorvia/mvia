"""Staff-console views for managing the interest taxonomy."""

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count
from django.shortcuts import render, redirect, get_object_or_404

from .models import Interest
from .forms import InterestForm


def staff_required(view):
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url="login")(view)


def _tree():
    """Return categories with their nested descendants, for display."""
    # Pull everything once, then build the tree in Python (few rows, simple & fast).
    all_interests = list(Interest.objects.all().order_by("name"))
    by_parent = {}
    for i in all_interests:
        by_parent.setdefault(i.parent_id, []).append(i)

    def build(node_id):
        out = []
        for node in by_parent.get(node_id, []):
            out.append({"node": node, "children": build(node.id)})
        return out

    return build(None)


@staff_required
def interests_list(request):
    q = request.GET.get("q", "").strip()
    pending_custom = Interest.objects.filter(is_custom=True, is_approved=False).count()
    total = Interest.objects.count()

    search_results = None
    tree = None
    if q:
        # Flat, filtered results with their parent shown for context.
        search_results = Interest.objects.filter(
            name__icontains=q).select_related("parent").order_by("name")
    else:
        tree = _tree()

    return render(request, "interests/staff_list.html", {
        "tree": tree, "search_results": search_results, "search_value": q,
        "pending_custom": pending_custom, "total": total,
        "has_active": bool(q),
        "active_nav": "interests",
    })


@staff_required
def interest_add(request):
    if request.method == "POST":
        form = InterestForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.is_custom = False
            obj.save()
            messages.success(request, f"Added “{obj.breadcrumb()}”.")
            return redirect("staff:interests")
    else:
        form = InterestForm()
    return render(request, "interests/staff_form.html", {
        "form": form, "title": "Add interest", "active_nav": "interests",
    })


@staff_required
def interest_edit(request, interest_id):
    obj = get_object_or_404(Interest, pk=interest_id)
    if request.method == "POST":
        form = InterestForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated “{obj.breadcrumb()}”.")
            return redirect("staff:interests")
    else:
        form = InterestForm(instance=obj)
    return render(request, "interests/staff_form.html", {
        "form": form, "title": "Edit interest", "obj": obj, "active_nav": "interests",
    })


@staff_required
def interest_delete(request, interest_id):
    obj = get_object_or_404(Interest, pk=interest_id)
    if request.method == "POST":
        name = obj.breadcrumb()
        child_count = obj.children.count()
        obj.delete()  # cascades to children
        msg = f"Deleted “{name}”."
        if child_count:
            msg += f" ({child_count} sub-item(s) removed too.)"
        messages.success(request, msg)
        return redirect("staff:interests")
    return render(request, "interests/staff_delete.html", {
        "obj": obj, "child_count": obj.children.count(), "active_nav": "interests",
    })


@staff_required
def custom_review(request):
    """Review user-submitted custom interests and approve (promote) or reject them."""
    if request.method == "POST":
        action = request.POST.get("action")
        cid = request.POST.get("interest_id")
        obj = get_object_or_404(Interest, pk=cid, is_custom=True)
        if action == "approve":
            new_parent_id = request.POST.get("parent") or None
            if new_parent_id:
                obj.parent_id = int(new_parent_id)
            obj.is_approved = True
            obj.is_custom = False  # promoted into the managed list
            obj.save()
            messages.success(request, f"Promoted “{obj.name}” into the managed list.")
        elif action == "reject":
            name = obj.name
            obj.delete()
            messages.success(request, f"Rejected and removed “{name}”.")
        return redirect("staff:custom_review")

    pending = Interest.objects.filter(is_custom=True, is_approved=False).order_by("created_at")
    categories = Interest.objects.filter(parent__isnull=True).order_by("name")
    all_for_parent = Interest.objects.filter(is_approved=True).order_by("name")
    return render(request, "interests/staff_custom_review.html", {
        "pending": pending, "categories": categories, "all_for_parent": all_for_parent,
        "active_nav": "interests",
    })
