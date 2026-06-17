"""Staff console: read all reviews including admin-only text and private notes."""

from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render
from django.db.models import Q

from .models import Review


def staff_required(view):
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url="login")(view)


@staff_required
def reviews_list(request):
    from core.pagination import paginate, querystring_without_page

    reviews = Review.objects.select_related("mentor", "mentee", "booking").all()
    q = request.GET.get("q", "").strip()
    rating = request.GET.get("rating", "").strip()
    flagged = request.GET.get("flagged", "").strip()
    if q:
        reviews = reviews.filter(
            Q(mentor__full_name__icontains=q) | Q(mentee__full_name__icontains=q) |
            Q(review_text__icontains=q) | Q(private_note__icontains=q))
    if rating:
        reviews = reviews.filter(rating=rating)
    if flagged == "yes":
        reviews = reviews.exclude(private_note="")

    rating_opts = [{"value": str(n), "label": f"{n} star", "selected": rating == str(n)} for n in range(5, 0, -1)]
    page_obj = paginate(request, reviews)
    return render(request, "reviews/staff_reviews.html", {
        "reviews": page_obj, "page_obj": page_obj,
        "qs": querystring_without_page(request),
        "search_value": q, "search_placeholder": "Search mentor, mentee, or text…",
        "filters": [
            {"name": "rating", "label": "Rating", "options": rating_opts},
            {"name": "flagged", "label": "Private notes", "options": [
                {"value": "yes", "label": "Has private note", "selected": flagged == "yes"}]},
        ],
        "has_active": bool(q or rating or flagged),
        "active_nav": "reviews",
    })
