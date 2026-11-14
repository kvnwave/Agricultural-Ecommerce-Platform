from django.urls import path

from . import views

urlpatterns = [
    path("", views.listings_view, name="listings"),
    path("mine/", views.my_listings, name="my_listings"),
    path("new/", views.listing_create, name="listing_create"),
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
