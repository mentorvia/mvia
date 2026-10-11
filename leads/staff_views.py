"""Staff console: the Leads list (free-consultation funnel)."""

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Lead


def staff_required(view):
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url="login")(view)


@staff_required
def leads_list(request):
    from core.pagination import paginate, querystring_without_page
    from django.db.models import Q

    leads = Lead.objects.all()

    q = request.GET.get("q", "").strip()
    priority = request.GET.get("priority", "").strip()
    if q:
        leads = leads.filter(
            Q(name__icontains=q) | Q(email__icontains=q) |
            Q(email_or_linkedin__icontains=q) | Q(whatsapp__icontains=q))
    if priority:
        leads = leads.filter(priority=priority)
    leads = leads.order_by("-created_at")

    priority_opts = [{"value": v, "label": l, "selected": priority == v}
                     for v, l in Lead.TAG_CHOICES]

    page_obj = paginate(request, leads)
    return render(request, "leads/staff_leads.html", {
        "page_obj": page_obj, "leads": page_obj,
        "qs": querystring_without_page(request),
        "search_value": q, "search_placeholder": "Search name, email, WhatsApp…",
        "filters": [{"name": "priority", "label": "Priority", "options": priority_opts}],
        "has_active": bool(q or priority),
        "active_nav": "leads",
    })


@staff_required
def lead_detail(request, lead_id):
    lead = get_object_or_404(Lead, pk=lead_id)
    return render(request, "leads/staff_lead_detail.html", {
        "lead": lead, "active_nav": "leads",
    })


@staff_required
@require_POST
def toggle_contacted(request, lead_id):
    lead = get_object_or_404(Lead, pk=lead_id)
    lead.is_contacted = not lead.is_contacted
    if lead.is_contacted:
        lead.contacted_at = timezone.now()
        lead.contacted_by = request.user
    else:
        lead.contacted_at = None
        lead.contacted_by = None
    lead.save(update_fields=["is_contacted", "contacted_at", "contacted_by"])
    messages.success(request, "Marked as contacted." if lead.is_contacted else "Marked as not contacted.")
    return redirect("staff:lead_detail", lead_id=lead.id)
