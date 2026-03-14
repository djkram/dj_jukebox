"""
Utilitats per crear notificacions als usuaris
"""
from .models import Notification, Song, SongRequest, User


def create_song_accepted_notification(song_request):
    """Notifica quan accepten una cançó demanada"""
    Notification.objects.create(
        user=song_request.user,
        type='song_accepted',
        title='Cançó acceptada! 🎉',
        message=f'La teva petició "{song_request.title}" de {song_request.artist} ha estat acceptada pel DJ!',
        song_request=song_request,
        amount=song_request.coins_cost
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
            title='Match! La teva cançó ha sonat 🎵',
            message=f'"{song.title}" de {song.artist} s\'ha reproduït! Has fet match!',
            song=song
        )


def create_coins_purchased_notification(user, amount):
    """Notifica quan compres Coins"""
    Notification.objects.create(
        user=user,
        type='coins_purchased',
        title='Coins comprats! 💰',
        message=f'Has comprat {amount} Coins. Ja pots convertir-los a Vots!',
        amount=amount
    )


def create_coins_received_notification(user, amount, reason=''):
    """Notifica quan reps Coins (regal, promoció, etc)"""
    message = f'Has rebut {amount} Coins'
    if reason:
        message += f': {reason}'

    Notification.objects.create(
        user=user,
        type='coins_received',
        title='Has rebut Coins! 🎁',
        message=message,
        amount=amount
    )
