"""
Query helpers for reusable Django ORM annotations and queries.

Provides functions to annotate songs with vote counts and retrieve
commonly used querysets with consistent ordering.
"""
from django.db.models import Count, Q


def annotate_songs_with_votes(queryset):
    """
    Adds num_likes and num_dislikes annotations to a Song queryset.

    Args:
        queryset: QuerySet of Song objects

    Returns:
        QuerySet with annotations:
        - num_likes: Count of 'like' votes
        - num_dislikes: Count of 'dislike' votes

    Example:
        songs = Song.objects.filter(party=party)
        annotated = annotate_songs_with_votes(songs)
        for song in annotated:
            print(f"{song.title}: {song.num_likes} likes")
    """
    return queryset.annotate(
        num_likes=Count('vote', filter=Q(vote__vote_type='like')),
        num_dislikes=Count('vote', filter=Q(vote__vote_type='dislike'))
    )


def get_annotated_party_songs(party, played_filter=None):
    """
    Gets songs from a party with vote annotations.

    Args:
        party: Party instance
        played_filter:
            - None: all songs
            - True: only played songs
            - False: only pending songs

    Returns:
        QuerySet with num_likes and num_dislikes annotations

    Example:
        # Get all pending songs with vote counts
        pending = get_annotated_party_songs(party, played_filter=False)
    """
    qs = party.songs.all()

    if played_filter is not None:
        qs = qs.filter(has_played=played_filter)

    return annotate_songs_with_votes(qs)


def get_pending_songs_ordered(party):
    """
    Gets pending songs ordered by likes (descending) and title.

    Args:
        party: Party instance

    Returns:
        QuerySet of pending songs with annotations, ordered by popularity

    Example:
        songs = get_pending_songs_ordered(party)
        top_song = songs.first()  # Most liked pending song
    """
    return get_annotated_party_songs(
        party,
        played_filter=False
    ).order_by('-num_likes', 'title')


def get_played_songs_ordered(party):
    """
    Gets played songs ordered by ID (most recent first).

    Returns a list (not QuerySet) for compatibility with existing code
    that expects a list for reverse enumeration.

    Args:
        party: Party instance

    Returns:
        List of played Song objects with annotations, ordered by recency

    Example:
        played = get_played_songs_ordered(party)
        for i, song in enumerate(played):
            song.display_order = len(played) - i
    """
    return list(
        get_annotated_party_songs(
            party,
            played_filter=True
        ).order_by('-id')
    )
