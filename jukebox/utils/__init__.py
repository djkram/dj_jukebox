"""
Utilities package for DJ Jukebox.

Provides reusable helper functions and classes for:
- Badge calculation
- Votes conversion (Coins → Votes)
- Vote validation
- Spotify error handling
- Query helpers
"""

from .query_helpers import (
    annotate_songs_with_votes,
    get_annotated_party_songs,
    get_pending_songs_ordered,
    get_played_songs_ordered,
)
from .votes_conversion import (
    calculate_votes_from_coins,
    convert_coins_to_votes,
    get_conversion_preview,
)
from .spotify_helpers import (
    get_spotify_reconnect_url,
    create_spotify_auth_error_response,
    get_user_spotify_token,
    get_spotify_context_for_view,
)
from .vote_validation import (
    validate_and_create_vote,
    create_vote_response,
    handle_vote_action,
)

__all__ = [
    # Query helpers
    'annotate_songs_with_votes',
    'get_annotated_party_songs',
    'get_pending_songs_ordered',
    'get_played_songs_ordered',
    # Votes conversion
    'calculate_votes_from_coins',
    'convert_coins_to_votes',
    'get_conversion_preview',
    # Spotify helpers
    'get_spotify_reconnect_url',
    'create_spotify_auth_error_response',
    'get_user_spotify_token',
    'get_spotify_context_for_view',
    # Vote validation
    'validate_and_create_vote',
    'create_vote_response',
    'handle_vote_action',
]
