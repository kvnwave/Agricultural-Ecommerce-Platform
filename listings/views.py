from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.models import Profile, User

from .forms import ListingForm
from .models import Category, Listing, ListingLike

PUBLIC_LISTING_STATUSES = (Listing.Status.ACTIVE, Listing.Status.SOLD_OUT)
LISTINGS_PER_PAGE = 24
SEARCH_QUERY_MAX_LENGTH = 100


def with_likes_total(queryset):
    """Annotate ``likes_total`` without joining the likes table.

    ``Count("likes")`` adds a ``LEFT OUTER JOIN`` and ``GROUP BY``, which also
    slows ``Paginator.count``. A correlated subquery keeps the count query on
    the listings table alone.
    """

    return queryset.annotate(
        likes_total=Coalesce(
            Subquery(
                ListingLike.objects.filter(listing=OuterRef("pk"))
                .values("listing")
                .annotate(total=Count("pk"))
                .values("total"),
                output_field=IntegerField(),
            ),
            0,
        )
    )


def listing_limit_message(user):
    """Return why ``user`` cannot create another listing, or ``None``.

    Archived listings are excluded from the open cap but still count toward
    the rolling daily creation limit.
    """

    open_count = user.listings.exclude(status=Listing.Status.ARCHIVED).count()
    if open_count >= Listing.MAX_OPEN_LISTINGS:
        return (
            f"You can keep at most {Listing.MAX_OPEN_LISTINGS} open listings. "
            "Archive or delete one before creating another."
        )

    created_today = user.listings.filter(
        created_at__gte=timezone.now() - timedelta(days=1)
    ).count()
    if created_today >= Listing.MAX_LISTINGS_PER_DAY:
        return (
            f"You can create at most {Listing.MAX_LISTINGS_PER_DAY} listings "
            "in 24 hours. Try again later."
        )
    return None


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
    """Public marketplace with portable ORM search and basic filters."""

    listings = (
        Listing.objects.filter(status__in=PUBLIC_LISTING_STATUSES)
        .select_related("category", "farmer")
        .prefetch_related("images")
        .order_by("-created_at")
    )
    listings = with_likes_total(listings)

    query = (request.GET.get("q") or "").strip()[:SEARCH_QUERY_MAX_LENGTH]
    if query:
        listings = listings.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(category__name__icontains=query)
            | Q(farmer__first_name__icontains=query)
            | Q(farmer__last_name__icontains=query)
            | Q(farmer__username__icontains=query)
        )

    category_slug = (request.GET.get("category") or "").strip()
    if category_slug:
        listings = listings.filter(category__slug=category_slug)

    condition = (request.GET.get("condition") or "").strip()
    if condition in Listing.Condition.values:
        listings = listings.filter(condition=condition)

    pricing = (request.GET.get("pricing") or "").strip()
    if pricing == "free":
        listings = listings.filter(is_free=True)
    elif pricing == "paid":
        listings = listings.filter(is_free=False)

    page_obj = Paginator(listings, LISTINGS_PER_PAGE).get_page(
        request.GET.get("page")
    )

    return render(
        request,
        "listings/listings.html",
        {
            "page_obj": page_obj,
            "listings": page_obj.object_list,
            "categories": Category.objects.all(),
            "conditions": Listing.Condition.choices,
            "pricing_options": (("free", "Free"), ("paid", "Paid")),
            "query": query,
            "selected_category": category_slug,
            "selected_condition": condition,
            "selected_pricing": pricing,
        },
    )


def listing_detail(request, public_id):
    listing = get_object_or_404(
        with_likes_total(
            Listing.objects.select_related("category", "farmer").prefetch_related(
                "images"
            )
        ),
        public_id=public_id,
    )

    is_owner = (
        request.user.is_authenticated and listing.farmer_id == request.user.id
    )
    if listing.status not in PUBLIC_LISTING_STATUSES and not is_owner:
        raise Http404("Listing is not available.")

    is_liked = (
        request.user.is_authenticated
        and ListingLike.objects.filter(
            user=request.user,
            listing=listing,
        ).exists()
    )

    return render(
        request,
        "listings/listing_detail.html",
        {
            "listing": listing,
            "is_owner": is_owner,
            "can_like": listing.status in PUBLIC_LISTING_STATUSES,
            "is_liked": is_liked,
        },
    )


@login_required
@require_POST
def listing_like_toggle(request, public_id):
    """Save or remove a listing for the signed-in user."""

    listing = get_object_or_404(
        Listing,
        public_id=public_id,
        status__in=PUBLIC_LISTING_STATUSES,
    )
    like, created = ListingLike.objects.get_or_create(
        user=request.user,
        listing=listing,
    )
    if not created:
        like.delete()

    listing.likes_total = listing.likes.count()

    if request.headers.get("HX-Request") == "true":
        return render(
            request,
            "listings/_like_button.html",
            {"listing": listing, "is_liked": created},
        )

    return redirect("listing_detail", public_id=listing.public_id)


@login_required
def liked_listings(request):
    """Listings the signed-in user saved, including sold-out ones."""

    listings = (
        Listing.objects.filter(
            likes__user=request.user,
            status__in=PUBLIC_LISTING_STATUSES,
        )
        .select_related("category", "farmer")
        .prefetch_related("images")
        .order_by("-likes__created_at")
    )
    listings = with_likes_total(listings)
    page_obj = Paginator(listings, LISTINGS_PER_PAGE).get_page(
        request.GET.get("page")
    )

    return render(
        request,
        "listings/liked_listings.html",
        {
            "page_obj": page_obj,
            "listings": page_obj.object_list,
        },
    )



@farmer_required
def listing_create(request):
    if request.method == "POST":
        with transaction.atomic():
            # Serialize creations per farmer so two concurrent requests cannot
            # both pass the cap check and save.
            User.objects.select_for_update().get(pk=request.user.pk)
            limit_message = listing_limit_message(request.user)
            if limit_message:
                messages.error(request, limit_message)
                return redirect("my_listings")

            form = ListingForm(request.POST, request.FILES)
            if form.is_valid():
                form.instance.farmer = request.user
                form.save()
                messages.success(request, "Your listing has been created.")
                return redirect("my_listings")
    else:
        limit_message = listing_limit_message(request.user)
        if limit_message:
            messages.error(request, limit_message)
            return redirect("my_listings")
        form = ListingForm()

    return render(
        request,
        "listings/listing_form.html",
        {"form": form, "is_edit": False},
    )


@login_required
def listing_update(request, public_id):
    if request.method == "POST":
        with transaction.atomic():
            # Lock the row before validating so two concurrent edits cannot
            # each remove a different photo and both pass the minimum check.
            listing = get_object_or_404(
                Listing.objects.select_for_update(),
                public_id=public_id,
                farmer=request.user,
            )
            form = ListingForm(request.POST, request.FILES, instance=listing)
            saved = form.is_valid()
            if saved:
                form.save()

        if saved:
            messages.success(request, "Your listing has been updated.")
            return redirect("my_listings")
    else:
        listing = get_object_or_404(
            Listing,
            public_id=public_id,
            farmer=request.user,
        )
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
        request.user.listings.select_related("category").order_by("-created_at")
    )
    listings = with_likes_total(listings)
    page_obj = Paginator(listings, LISTINGS_PER_PAGE).get_page(
        request.GET.get("page")
    )

    return render(
        request,
        "listings/my_listings.html",
        {
            "page_obj": page_obj,
            "listings": page_obj.object_list,
        },
    )
