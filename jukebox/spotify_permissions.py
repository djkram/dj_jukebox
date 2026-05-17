from django.conf import settings

from .models import Party


def is_spotify_auth_for_all_enabled() -> bool:
    return bool(getattr(settings, "SPOTIFY_AUTH_FOR_ALL", False))


def user_can_connect_spotify(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if is_spotify_auth_for_all_enabled():
        return True
    if user.is_staff or user.is_superuser:
        return True
    return Party.objects.filter(djs=user).exists()
