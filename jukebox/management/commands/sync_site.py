from django.conf import settings
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Sync django.contrib.sites with SITE_DOMAIN and SITE_NAME."

    def handle(self, *args, **options):
        domain = getattr(settings, "SITE_DOMAIN", None)
        name = getattr(settings, "SITE_NAME", None) or domain

        if not domain:
            self.stdout.write("SITE_DOMAIN not set; skipping Site sync.")
            return

        site, _ = Site.objects.update_or_create(
            id=settings.SITE_ID,
            defaults={"domain": domain, "name": name},
        )
        self.stdout.write(
            self.style.SUCCESS(f"Synced Site #{site.id} to {site.domain} ({site.name})")
        )
