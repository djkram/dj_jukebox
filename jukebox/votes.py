from .models import Vote, VotePackage, PartyCoinsGrant
from django.db.models import Sum

def get_user_votes_left(user, party):
    """
    Retorna els vots disponibles per l'usuari a la festa.
    Si es puja max_votes_per_user, l'usuari té més vots automàticament.
    Si es baixa, només redueix els disponibles però NO toca els vots ja fets.
    """
    base_votes = party.max_votes_per_user
    extra_votes = VotePackage.objects.filter(user=user, party=party).aggregate(
        total=Sum('votes_purchased')
    )['total'] or 0
    total_votes_allowed = base_votes + extra_votes

    votes_used = Vote.objects.filter(user=user, party=party).count()
    return max(0, total_votes_allowed - votes_used)


def get_user_party_coins(user, party):
    """
    Retorna els coins gratuïts disponibles de la festa per l'usuari.
    Aquests són independents dels User.credits globals.
    """
    total_granted = PartyCoinsGrant.objects.filter(
        user=user,
        party=party
    ).aggregate(total=Sum('coins_granted'))['total'] or 0

    return max(0, total_granted)


def ensure_user_has_free_coins(user, party):
    """
    S'assegura que l'usuari tingui els coins gratuïts de la festa.
    Comprova si ja se li han donat i ajusta si ha canviat free_coins_per_user.
    """
    current_granted = PartyCoinsGrant.objects.filter(
        user=user,
        party=party,
        reason='free_coins'
    ).aggregate(total=Sum('coins_granted'))['total'] or 0

    expected = party.free_coins_per_user
    difference = expected - current_granted

    if difference != 0:
        # Donar o ajustar coins
        PartyCoinsGrant.objects.create(
            user=user,
            party=party,
            coins_granted=difference,
            reason='free_coins'
        )

    return difference
