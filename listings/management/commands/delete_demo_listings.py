"""Remove the demonstration listings used for screenshots and demos."""

from django.core.management.base import BaseCommand

from accounts.models import User
from listings.models import Listing, ListingImage

DEMO_EMAIL = "demo-farmer@example.com"


class Command(BaseCommand):
    """Delete the demo farmer, its listings, and every uploaded photo.

    Deleting the account cascades to listings, images, likes, and the profile,
    and the image signal removes the stored objects from Supabase Storage.
    """

    help = "Delete the demo farmer and every listing it owns, including photos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without changing anything.",
        )

    def handle(self, *args, **options):
        farmers = User.objects.filter(email=DEMO_EMAIL)
        listings = Listing.objects.filter(farmer__email=DEMO_EMAIL)
        photos = ListingImage.objects.filter(listing__in=listings).count()
        listing_count = listings.count()

        if not listing_count and not farmers.exists():
            self.stdout.write("No demo listings found.")
            return

        summary = (
            f"{listing_count} listing(s), {photos} photo(s), "
            f"and {farmers.count()} demo account"
        )
        if options["dry_run"]:
            self.stdout.write(f"Would delete {summary}.")
            return

        farmers.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {summary}."))
