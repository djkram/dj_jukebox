"""
Vote validation and creation with error handling.

Provides unified logic for validating vote availability and creating
votes with consistent error messages across different response types.
"""
from typing import Tuple, Optional
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from .vote_types import VALID_VOTE_TYPES, NEGATIVE_VOTE_TYPES, normalize_vote_type


def validate_and_create_vote(
    user,
    song,
    party,
    vote_type: str = 'like'
) -> Tuple[bool, Optional[str]]:
    """
    Validates and creates a vote atomically with race-condition protection.
    """
    from jukebox.models import Vote
    from jukebox.votes import get_user_votes_left

    vote_type = normalize_vote_type(vote_type)
    if vote_type not in VALID_VOTE_TYPES:
        return False, _("Tipus de vot no vàlid")

    try:
        with transaction.atomic():
            if Vote.objects.filter(user=user, song=song, party=party).exists():
                return False, _("Ja has votat aquesta cançó")

            votes_left = get_user_votes_left(user, party)
            if votes_left <= 0:
                if user.credits > 0:
                    return False, _("No tens vots! Converteix Coins a Vots per continuar.")
                else:
                    return False, _("No tens Coins! Compra Coins i converteix-los a Vots.")

            Vote.objects.create(
                user=user, song=song, party=party, vote_type=vote_type
            )
    except IntegrityError:
        return False, _("Ja has votat aquesta cançó")

    return True, None


def create_vote_response(
    success: bool,
    error_msg: Optional[str],
    user,
    song,
    party,
    response_type: str = 'redirect',
    redirect_url: str = 'song_list'
):
    from jukebox.votes import get_user_votes_left

    if response_type == 'json':
        if success:
            from django.db.models import Count, Q
            from jukebox.utils.badges import BadgeCalculator
            user_likes_count = party.vote_set.filter(user=user, vote_type='like').count()
            num_likes = song.vote.filter(party=party, vote_type='like').count()
            num_dislikes = song.vote.filter(party=party, vote_type__in=NEGATIVE_VOTE_TYPES).count()
            calculator = BadgeCalculator(party.songs)
            badge_label, badge_bg, badge_text = calculator.calculate_badge(num_likes, num_dislikes)
            return JsonResponse({
                'success': True,
                'votes_left': get_user_votes_left(user, party),
                'credits': user.credits,
                'user_likes_count': user_likes_count,
                'badge_label': badge_label,
            })
        else:
            return JsonResponse({
                'success': False,
                'error': error_msg
            }, status=400)

    else:  # redirect
        if success:
            return redirect(redirect_url)
        else:
            # For redirects, error handling is done in the view
            # that calls this function (can't pass error via redirect easily)
            return redirect(redirect_url)


def handle_vote_action(
    user,
    song,
    party,
    vote_type: str,
    response_type: str = 'redirect',
    redirect_url: str = 'song_list'
):
    success, error_msg = validate_and_create_vote(user, song, party, vote_type)
    return create_vote_response(success, error_msg, user, song, party, response_type, redirect_url)
