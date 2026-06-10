from .models import Vote, VotePackage, PartyCoinsGrant
from django.db import transaction
from django.db.models import Sum, F

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


def get_user_available_coins(user, party):
    """
    Retorna els coins totals disponibles en el context d'una festa:
    coins globals de l'usuari + coins gratuïts/ajustos d'aquesta festa.
    """
    return user.credits + get_user_party_coins(user, party)


def apply_party_coin_adjustment(user, party, amount, reason):
    """
    Aplica un ajust acumulat de coins de festa per usuari/party/reason.
    amount pot ser positiu o negatiu.
    """
    grant, _ = PartyCoinsGrant.objects.select_for_update().get_or_create(
        user=user,
        party=party,
        reason=reason,
        defaults={'coins_granted': 0},
    )
    grant.coins_granted = F('coins_granted') + amount
    grant.save(update_fields=['coins_granted'])


def spend_user_coins_for_party(user, party, amount, reason='coins_spent'):
    """
    Gasta coins en el context d'una festa.
    Consumeix primer els coins gratuïts de festa i després els globals.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    if amount <= 0:
        return True

    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user.pk)
        party_coins = get_user_party_coins(user, party)
        if user.credits + party_coins < amount:
            return False

        party_spend = min(party_coins, amount)
        global_spend = amount - party_spend

        if party_spend:
            apply_party_coin_adjustment(user, party, -party_spend, reason)
        if global_spend:
            User.objects.filter(pk=user.pk).update(credits=F('credits') - global_spend)

    user.refresh_from_db(fields=['credits'])
    return True


def refund_user_coins_for_party(user, party, amount, reason='song_request_refund'):
    """Retorna coins a l'usuari (refund d'una petició rebutjada)."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    if amount <= 0:
        return
    with transaction.atomic():
        User.objects.filter(pk=user.pk).update(credits=F('credits') + amount)
    user.refresh_from_db(fields=['credits'])


def sync_party_free_coins_for_existing_users(party, previous_free_coins=0):
    """
    Quan l'admin puja els coins gratuïts de la festa, actualitza els usuaris
    que ja han interactuat amb aquesta festa. No retira coins si el valor baixa.
    """
    from jukebox.models import SongRequest, SongSwipeSkip

    expected = party.free_coins_per_user
    if expected <= previous_free_coins:
        return 0

    user_ids = set()
    user_ids.update(Vote.objects.filter(party=party).values_list('user_id', flat=True))
    user_ids.update(VotePackage.objects.filter(party=party).values_list('user_id', flat=True))
    user_ids.update(PartyCoinsGrant.objects.filter(party=party).values_list('user_id', flat=True))
    user_ids.update(SongRequest.objects.filter(party=party).values_list('user_id', flat=True))
    user_ids.update(SongSwipeSkip.objects.filter(party=party).values_list('user_id', flat=True))
    user_ids.discard(None)

    updated = 0
    with transaction.atomic():
        existing = PartyCoinsGrant.objects.select_for_update().filter(
            party=party,
            reason='free_coins',
            user_id__in=user_ids,
        )
        updated += existing.filter(coins_granted__lt=expected).update(coins_granted=expected)

        existing_user_ids = set(existing.values_list('user_id', flat=True))
        missing_user_ids = user_ids - existing_user_ids
        grants = [
            PartyCoinsGrant(
                user_id=user_id,
                party=party,
                coins_granted=expected,
                reason='free_coins',
            )
            for user_id in missing_user_ids
        ]
        if grants:
            PartyCoinsGrant.objects.bulk_create(grants, ignore_conflicts=True)
            updated += len(grants)

    return updated


def ensure_user_has_free_coins(user, party):
    """
    S'assegura que l'usuari tingui els coins gratuïts de la festa.
    Comprova si ja se li han donat i ajusta si ha canviat free_coins_per_user.
    Uses a single row per (user, party, reason) updated in place.
    """
    from django.db import IntegrityError

    expected = party.free_coins_per_user
    if expected <= 0:
        return 0

    with transaction.atomic():
        try:
            grant = PartyCoinsGrant.objects.select_for_update().get(
                user=user, party=party, reason='free_coins'
            )
            diff = expected - grant.coins_granted
            if diff > 0:
                grant.coins_granted = expected
                grant.save(update_fields=['coins_granted'])
                return diff
            if diff < 0:
                return 0
            return diff
        except PartyCoinsGrant.DoesNotExist:
            try:
                PartyCoinsGrant.objects.create(
                    user=user,
                    party=party,
                    coins_granted=expected,
                    reason='free_coins'
                )
                return expected
            except IntegrityError:
                return 0
