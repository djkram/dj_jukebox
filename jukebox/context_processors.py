from django.conf import settings

from .models import Party, Notification
from .spotify_permissions import is_spotify_auth_for_all_enabled, user_can_connect_spotify
from allauth.socialaccount.models import SocialAccount, SocialApp


def selected_party(request):
    party_id = request.session.get('selected_party_id')
    party = None
    is_party_dj = False
    if party_id:
        try:
            party = Party.objects.get(id=party_id)
            if request.user.is_authenticated and not request.user.is_superuser:
                is_party_dj = party.djs.filter(pk=request.user.pk).exists()
        except Party.DoesNotExist:
            party = None
    return {'selected_party': party, 'is_party_dj': is_party_dj}


def user_avatar(request):
    user = getattr(request, "user", None)
    avatar_url = None
    avatar_initial = None
    display_name = None

    if user and user.is_authenticated:
        spotify_account = SocialAccount.objects.filter(
            user=user,
            provider="spotify",
        ).first()
        if spotify_account:
            images = spotify_account.extra_data.get("images") or []
            if images:
                avatar_url = images[0].get("url")
            display_name = spotify_account.extra_data.get("display_name")

        display_name = (display_name or user.get_full_name().strip() or user.username or user.email or "U").strip()
        display_name = display_name[:1].upper() + display_name[1:]
        avatar_initial = display_name[0].upper()

    return {
        "user_avatar_url": avatar_url,
        "user_avatar_initial": avatar_initial,
        "user_display_name": display_name,
    }


def unread_notifications_count(request):
    """Retorna el nombre de notificacions no llegides"""
    count = 0
    if request.user.is_authenticated:
        count = Notification.objects.filter(user=request.user, is_read=False).count()
    return {'unread_notifications_count': count}


def social_login_providers(request):
    # Providers configurats via base de dades (SocialApp)
    configured_providers = set(
        SocialApp.objects.filter(sites__id=settings.SITE_ID).values_list("provider", flat=True)
    )
    # Providers configurats via settings (APPS dins SOCIALACCOUNT_PROVIDERS)
    for provider_id, config in getattr(settings, "SOCIALACCOUNT_PROVIDERS", {}).items():
        if any(a.get("client_id") for a in config.get("APPS", [])):
            configured_providers.add(provider_id)
    spotify_configured = "spotify" in configured_providers
    return {
        "spotify_social_login_enabled": spotify_configured and is_spotify_auth_for_all_enabled(),
        "spotify_connect_enabled": spotify_configured and user_can_connect_spotify(request.user),
        "google_social_login_enabled": "google" in configured_providers,
    }
