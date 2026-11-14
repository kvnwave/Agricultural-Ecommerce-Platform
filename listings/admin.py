from django.contrib import admin
from django.db.models import Count

from .models import Category, Listing, ListingImage, ListingLike


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


class ListingImageInline(admin.TabularInline):
    model = ListingImage
    extra = 0
    fields = ("image", "position", "alt_text")


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "farmer",
        "price",
        "unit",
        "stock_quantity",
        "is_free",
        "status",
        "likes_total",
        "created_at",
    )
    list_filter = ("status", "is_free", "condition", "category", "bulk_order")
    search_fields = (
        "title",
        "description",
        "farmer__username",
        "farmer__email",
        "category__name",
    )
    list_select_related = ("farmer", "category")
    readonly_fields = (
        "public_id",
        "sold_out_at",
        "created_at",
        "updated_at",
        "likes_total",
    )
    inlines = [ListingImageInline]
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(likes_total=Count("likes"))

    @admin.display(description="Likes", ordering="likes_total")
    def likes_total(self, obj):
        return obj.likes_total


@admin.register(ListingImage)
class ListingImageAdmin(admin.ModelAdmin):
    list_display = ("listing", "position", "alt_text")
    list_select_related = ("listing",)
    search_fields = ("listing__title",)


@admin.register(ListingLike)
class ListingLikeAdmin(admin.ModelAdmin):
    list_display = ("user", "listing", "created_at")
    list_select_related = ("user", "listing")
    search_fields = ("user__email", "listing__title")
    readonly_fields = ("user", "listing", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
