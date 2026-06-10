"""
Utilitats per crear notificacions als usuaris
"""
import random
from django.utils.translation import gettext as _
from .models import Notification, Song, SongRequest, User

_REJECTION_MSGS = [
    _("Aquesta vegada no, però la festa just comença! Torna a proposar-ne una altra 🎶"),
    _("El DJ guarda el teu gust per un altre moment màgic. Vine a ballar! 🕺"),
    _("No és el teu moment... però la nit és llarga! Proposa'n una altra 🔥"),
    _("Vibe incompatible ara mateix, però tu segur que tens la propera cançó guanyadora! 🎵"),
    _("La pista de ball és gran i les opcions infinites. Torna a intentar-ho! 💃"),
    _("El DJ ha dit que no, però el DJ també s'equivoca de vegades 😄 Prova una altra!"),
]


def create_song_accepted_notification(song_request, charged_amount=None):
    """Notifica quan una cançó és posada a la sessió (via accept directe)"""
    Notification.objects.create(
        user=song_request.user,
        type='song_accepted',
        title=_('Posada a la sessió! 🎉'),
        message=_('"%(title)s" de %(artist)s ha estat posada a la sessió pel DJ!') % {
            'title': song_request.title,
            'artist': song_request.artist
        },
        song_request=song_request,
        amount=charged_amount
    )


def create_song_played_notification(song):
    """Notifica a tots els que van votar la cançó que s'ha reproduït"""
    voters = User.objects.filter(
        vote__song=song,
        vote__party=song.party
    ).distinct()

    title = _('Match! La teva cançó ha sonat 🎵')
    message = _('\"%(title)s\" de %(artist)s s\'ha reproduït! Has fet match!') % {
        'title': song.title,
        'artist': song.artist
    }

    notifications = [
        Notification(user=voter, type='song_played', title=title, message=message, song=song)
        for voter in voters
    ]
    if notifications:
        Notification.objects.bulk_create(notifications)


def create_coins_purchased_notification(user, amount):
    """Notifica quan compres Coins"""
    Notification.objects.create(
        user=user,
        type='coins_purchased',
        title=_('Coins comprats! 💰'),
        message=_('Has comprat %(amount)s Coins. Ja pots convertir-los a Vots!') % {'amount': amount},
        amount=amount
    )


def create_song_rejected_notification(song_request):
    """Notificació amable quan rebutgen una petició (devolució de coins inclosa)."""
    msg = random.choice(_REJECTION_MSGS)
    Notification.objects.create(
        user=song_request.user,
        type='song_rejected',
        title=_('Petició no acceptada 🎵'),
        message=f'"{song_request.title}" — {msg}',
        song_request=song_request,
        amount=song_request.coins_cost if song_request.coins_charged else None,
    )


def create_song_queued_notification(song_request):
    """Notificació quan la cançó entra a la maleta (sense cobrar)."""
    Notification.objects.create(
        user=song_request.user,
        type='song_queued',
        title=_('A la maleta! 🎒'),
        message=_('\"%(title)s\" de %(artist)s ja és a la maleta. Espera el teu moment a la pista!') % {
            'title': song_request.title,
            'artist': song_request.artist,
        },
        song_request=song_request,
    )


def create_song_loaded_notification(song_request):
    """Notificació quan el DJ fa LOAD: cançó posada a la sessió."""
    Notification.objects.create(
        user=song_request.user,
        type='song_loaded',
        title=_('LOAD! Posada a la sessió 🚀'),
        message=_('"%(title)s" de %(artist)s ha estat posada a la sessió. Prepara\'t per ballar!') % {
            'title': song_request.title,
            'artist': song_request.artist,
        },
        song_request=song_request,
        amount=song_request.coins_cost,
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
