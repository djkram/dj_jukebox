import os
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand

from allauth.socialaccount.models import SocialApp


class Command(BaseCommand):
    help = "Configura automàticament superuser i SocialApp de Spotify per producció"

    def handle(self, *args, **options):
        User = get_user_model()

        # 1. Crear superuser si no existeix
        if not User.objects.filter(is_superuser=True).exists():
            admin_username = os.environ.get("ADMIN_USERNAME", "admin")
            admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com")
            admin_password = os.environ.get("ADMIN_PASSWORD")

            if admin_password:
                user = User.objects.create_superuser(
                    username=admin_username,
                    email=admin_email,
                    password=admin_password,
                )
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Superuser creat: {user.username}")
                )
            else:
                self.stdout.write(
                    self.style.WARNING("⚠ ADMIN_PASSWORD no configurat, superuser no creat")
                )
        else:
            self.stdout.write(self.style.SUCCESS("✓ Superuser ja existeix"))

        # 2. Crear SocialApp de Spotify si no existeix
        spotify_client_id = os.environ.get("SPOTIFY_CLIENT_ID")
        spotify_client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")

        if spotify_client_id and spotify_client_secret:
            app, created = SocialApp.objects.get_or_create(
                provider="spotify",
                defaults={
                    "name": "Spotify",
                    "client_id": spotify_client_id,
                    "secret": spotify_client_secret,
                },
            )

            # Actualitzar si ja existia però amb credencials diferents
            if not created:
                app.client_id = spotify_client_id
                app.secret = spotify_client_secret
                app.save()

            # Associar amb el site actual
            site = Site.objects.get(id=settings.SITE_ID)
            if site not in app.sites.all():
                app.sites.add(site)

            status = "creat" if created else "actualitzat"
            self.stdout.write(
                self.style.SUCCESS(f"✓ SocialApp Spotify {status} i associat al site {site.domain}")
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "⚠ SPOTIFY_CLIENT_ID o SPOTIFY_CLIENT_SECRET no configurats, "
                    "SocialApp no creat"
                )
            )

        self.stdout.write(self.style.SUCCESS("\n✓ Setup de producció completat!"))
