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
]
