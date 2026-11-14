from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.models import Profile

from .forms import ListingForm
from .models import Listing


def farmer_required(view_func):
    """Allow only authenticated accounts that registered as farmers."""

    @login_required
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if request.user.profile.role != Profile.Role.FARMER:
            raise PermissionDenied("Only farmer accounts can sell produce.")
        return view_func(request, *args, **kwargs)

    return wrapped


def listings_view(request):
    return render(request, "listings/listings.html")


@farmer_required
def listing_create(request):
    if request.method == "POST":
        form = ListingForm(request.POST, request.FILES)
        if form.is_valid():
            form.instance.farmer = request.user
            form.save()
            messages.success(request, "Your listing has been created.")
            return redirect("my_listings")
    else:
        form = ListingForm()

    return render(
        request,
        "listings/listing_form.html",
        {"form": form, "is_edit": False},
    )


@login_required
def listing_update(request, public_id):
    listing = get_object_or_404(
        Listing,
        public_id=public_id,
        farmer=request.user,
    )

    if request.method == "POST":
        form = ListingForm(request.POST, request.FILES, instance=listing)
        if form.is_valid():
            form.save()
            messages.success(request, "Your listing has been updated.")
            return redirect("my_listings")
    else:
        form = ListingForm(instance=listing)

    return render(
        request,
        "listings/listing_form.html",
        {"form": form, "listing": listing, "is_edit": True},
    )


@login_required
@require_http_methods(["GET", "POST"])
def listing_delete(request, public_id):
    listing = get_object_or_404(
        Listing,
        public_id=public_id,
        farmer=request.user,
    )

    if request.method == "POST":
        listing.delete()
        messages.success(request, "Your listing has been deleted.")
        return redirect("my_listings")

    return render(
        request,
        "listings/listing_confirm_delete.html",
        {"listing": listing},
    )


@farmer_required
def my_listings(request):
    listings = (
        request.user.listings.prefetch_related("images")
        .annotate(likes_total=Count("likes"))
        .order_by("-created_at")
    )

    return render(
        request,
        "listings/my_listings.html",
        {"listings": listings},
    )
