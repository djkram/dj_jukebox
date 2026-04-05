"""
Vote validation and creation with error handling.

Provides unified logic for validating vote availability and creating
votes with consistent error messages across different response types.
"""
from typing import Tuple, Optional
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.translation import gettext as _


def validate_and_create_vote(
    user,
    song,
    party,
    vote_type: str = 'like'
) -> Tuple[bool, Optional[str]]:
    """
    Validates and creates a vote with error handling.

    Checks:
    1. User hasn't already voted this song
    2. User has votes available (via get_user_votes_left)
    3. User has coins to convert if no votes left

    Args:
        user: User instance
        song: Song instance
        party: Party instance
        vote_type: Vote type ('like', 'dislike', 'skip')

    Returns:
        Tuple[success: bool, error_msg: Optional[str]]
        - success: True if vote created successfully
        - error_msg: Error message if failed, None if successful

    Example:
        success, error = validate_and_create_vote(user, song, party, 'like')
        if not success:
            return JsonResponse({'error': error}, status=400)
    """
    from jukebox.models import Vote
    from jukebox.votes import get_user_votes_left

    # Check if already voted
    existing_vote = Vote.objects.filter(
        user=user,
        song=song,
        party=party
    ).first()

    if existing_vote:
        return False, _("Ja has votat aquesta cançó")

    # Check votes available
    votes_left = get_user_votes_left(user, party)

    if votes_left <= 0:
        if user.credits > 0:
            return False, _("No tens vots! Converteix Coins a Vots per continuar.")
        else:
            return False, _("No tens Coins! Compra Coins i converteix-los a Vots.")

    # Create vote
    Vote.objects.create(
        user=user,
        song=song,
        party=party,
        vote_type=vote_type
    )

    return True, None


def create_vote_response(
    success: bool,
    error_msg: Optional[str],
    user,
    party,
    response_type: str = 'redirect',
    redirect_url: str = 'song_list'
):
    """
    Creates HTTP response based on validation result.

    Args:
        success: If validation was successful
        error_msg: Error message (if success=False)
        user: User instance
        party: Party instance
        response_type: 'redirect' or 'json'
        redirect_url: URL to redirect (if response_type='redirect')

    Returns:
        HttpResponse (redirect or JsonResponse)

    Example:
        return create_vote_response(
            success, error, user, party,
            response_type='json'
        )
    """
    from jukebox.votes import get_user_votes_left

    if response_type == 'json':
        if success:
            return JsonResponse({
                'success': True,
                'votes_left': get_user_votes_left(user, party),
                'credits': user.credits
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
    """
    Complete handler for vote action (validation + response).

    Convenience function that combines validation and response creation.

    Args:
        user: User instance
        song: Song instance
        party: Party instance
        vote_type: Vote type
        response_type: 'redirect' or 'json'
        redirect_url: URL to redirect

    Returns:
        HttpResponse

    Example:
        # In song_swipe view (AJAX):
        return handle_vote_action(
            user, song, party, 'like',
            response_type='json'
        )

        # In song_list view (form POST):
        return handle_vote_action(
            user, song, party, vote_type,
            response_type='redirect',
            redirect_url='song_list'
        )
    """
    success, error_msg = validate_and_create_vote(
        user, song, party, vote_type
    )

    return create_vote_response(
        success, error_msg, user, party, response_type, redirect_url
    )
