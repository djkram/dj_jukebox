"""
Utilitats per crear notificacions als usuaris
"""
from django.utils.translation import gettext as _
from .models import Notification, Song, SongRequest, User


def create_song_accepted_notification(song_request, charged_amount=None):
    """Notifica quan accepten una cançó demanada"""
    Notification.objects.create(
        user=song_request.user,
        type='song_accepted',
        title=_('Cançó acceptada! 🎉'),
        message=_('La teva petició "%(title)s" de %(artist)s ha estat acceptada pel DJ!') % {
            'title': song_request.title,
            'artist': song_request.artist
        },
        song_request=song_request,
        amount=charged_amount
    )


def create_song_played_notification(song):
    """Notifica a tots els que van votar la cançó que s'ha reproduït"""
    from .models import Vote

    # Obtenir tots els usuaris que van votar aquesta cançó
    voters = User.objects.filter(
        vote__song=song,
        vote__party=song.party
    ).distinct()

    for voter in voters:
        Notification.objects.create(
            user=voter,
            type='song_played',
            title=_('Match! La teva cançó ha sonat 🎵'),
            message=_('\"%(title)s\" de %(artist)s s\'ha reproduït! Has fet match!') % {
                'title': song.title,
                'artist': song.artist
            },
            song=song
        )


def create_coins_purchased_notification(user, amount):
    """Notifica quan compres Coins"""
    Notification.objects.create(
        user=user,
        type='coins_purchased',
        title=_('Coins comprats! 💰'),
        message=_('Has comprat %(amount)s Coins. Ja pots convertir-los a Vots!') % {'amount': amount},
        amount=amount
    )


def create_coins_received_notification(user, amount, reason=''):
    """Notifica quan reps Coins (regal, promoció, etc)"""
    if reason:
        message = _('Has rebut %(amount)s Coins: %(reason)s') % {'amount': amount, 'reason': reason}
    else:
        message = _('Has rebut %(amount)s Coins') % {'amount': amount}

    Notification.objects.create(
        user=user,
        type='coins_received',
        title=_('Has rebut Coins! 🎁'),
        message=message,
        amount=amount
    )
