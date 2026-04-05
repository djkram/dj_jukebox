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

__all__ = [
    'annotate_songs_with_votes',
    'get_annotated_party_songs',
    'get_pending_songs_ordered',
    'get_played_songs_ordered',
]
