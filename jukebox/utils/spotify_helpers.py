"""
Spotify integration helpers for error handling and token management.

Provides utilities to handle Spotify authentication errors consistently
across all views and manage user tokens.
"""
from django.http import JsonResponse
from django.urls import reverse
from urllib.parse import urlencode
import logging

from allauth.socialaccount.models import SocialAccount

logger = logging.getLogger(__name__)


def get_spotify_reconnect_url(request) -> str:
    """
    Generates Spotify reconnection URL preserving current page.

    Args:
        request: HttpRequest

    Returns:
        Full reconnection URL with 'next' parameter

    Example:
        url = get_spotify_reconnect_url(request)
        # Returns: /accounts/spotify/login/?process=connect&next=/song-list/
    """
    query = urlencode({
        "process": "connect",
        "next": request.get_full_path(),
    })
    return f"{reverse('spotify_login')}?{query}"


def create_spotify_auth_error_response(request) -> JsonResponse:
    """
    Creates standard JSON response for Spotify authentication errors.

    Args:
        request: HttpRequest

    Returns:
        JsonResponse with error message and reconnect_url (status 401)

    Example:
        except SpotifyAuthError:
            return create_spotify_auth_error_response(request)
    """
    return JsonResponse({
        'error': 'La sessió de Spotify ha caducat. Torna a connectar Spotify per continuar.',
        'reconnect_url': get_spotify_reconnect_url(request),
    }, status=401)


def get_user_spotify_token(user, raise_on_error: bool = False):
    """
    Gets Spotify token for user with error handling.

    Args:
        user: User instance
        raise_on_error: If True, raises exception; if False, returns None

    Returns:
        Spotify token string or None

    Raises:
        SpotifyAuthError: If raise_on_error=True and fails

    Example:
        token = get_user_spotify_token(user)
        if token:
            # Use token for API calls
    """
    from jukebox.spotify_api import SpotifyAuthError, _ensure_valid_user_token

    has_spotify = SocialAccount.objects.filter(
        user=user,
        provider="spotify"
    ).exists()

    if not has_spotify:
        if raise_on_error:
            raise SpotifyAuthError("No Spotify account connected")
        return None

    try:
        token = _ensure_valid_user_token(user)
        return token
    except Exception as e:
        logger.warning(
            f"[SPOTIFY] Error obtenint token per usuari {user.id}: {e}"
        )
        if raise_on_error:
            raise
        return None


def get_spotify_context_for_view(user) -> dict:
    """
    Gets Spotify context for templates (has_spotify + token).

    Checks if user has connected Spotify and obtains valid token.
    If token retrieval fails, sets has_spotify to False.

    Args:
        user: User instance

    Returns:
        Dict with 'has_spotify' (bool) and 'spotify_token' (str or None)

    Example:
        context = get_spotify_context_for_view(user)
        return render(request, 'template.html', {
            'party': party,
            **context,  # Unpacks has_spotify and spotify_token
        })
    """
    has_spotify = SocialAccount.objects.filter(
        user=user,
        provider="spotify"
    ).exists()

    spotify_token = None
    if has_spotify:
        spotify_token = get_user_spotify_token(user, raise_on_error=False)
        if not spotify_token:
            has_spotify = False

    return {
        'has_spotify': has_spotify,
        'spotify_token': spotify_token,
    }
