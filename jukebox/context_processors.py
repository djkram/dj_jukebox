from .models import Party, Notification
from allauth.socialaccount.models import SocialAccount


def selected_party(request):
    party_id = request.session.get('selected_party_id')
    party = None
    if party_id:
        try:
            party = Party.objects.get(id=party_id)
        except Party.DoesNotExist:
            party = None
    return {'selected_party': party}


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
