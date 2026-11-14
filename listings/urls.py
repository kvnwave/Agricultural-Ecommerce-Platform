from django.urls import path

from . import views

urlpatterns = [
    path("", views.listings_view, name="listings"),
    path("mine/", views.my_listings, name="my_listings"),
    path("liked/", views.liked_listings, name="liked_listings"),
    path("new/", views.listing_create, name="listing_create"),
    path(
        "<uuid:public_id>/",
        views.listing_detail,
        name="listing_detail",
    ),
    path(
        "<uuid:public_id>/like/",
        views.listing_like_toggle,
        name="listing_like_toggle",
    ),
    path(
        "<uuid:public_id>/edit/",
        views.listing_update,
        name="listing_update",
    ),
    path(
        "<uuid:public_id>/delete/",
        views.listing_delete,
        name="listing_delete",
    ),
]
