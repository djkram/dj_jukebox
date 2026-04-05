"""
Badge calculation for songs based on engagement percentiles.

Provides dynamic badge labels, colors and classification based on:
- Total interactions (likes + dislikes)
- Like ratio (likes / total interactions)
- Percentile within party (ranked by total interactions)
"""
from typing import Tuple
from django.db.models import Count, Q


class BadgeCalculator:
    """
    Calculator for song badges based on engagement metrics.

    Calculates percentile-based badges considering all songs in a party
    to provide context-aware classifications.

    Example:
        calculator = BadgeCalculator(party.songs)
        label, bg, text = calculator.calculate_badge(10, 2)
        # Returns: ("TRENDING", "#06ffa5", "#000000")
    """

    def __init__(self, party_songs_queryset):
        """
        Initializes calculator with party context.

        Args:
            party_songs_queryset: QuerySet of Song objects from a party
        """
        self.vote_counts = self._extract_vote_counts(party_songs_queryset)
        self.sorted_counts = sorted(self.vote_counts)
        self.total_ranked_songs = len(self.sorted_counts)

    def _extract_vote_counts(self, queryset) -> list:
        """
        Extracts list of total interactions for each song.

        Args:
            queryset: QuerySet of Song objects

        Returns:
            List of integers (total_interactions per song)
        """
        return list(
            queryset.annotate(
                total_interactions=(
                    Count('vote', filter=Q(vote__vote_type='like')) +
                    Count('vote', filter=Q(vote__vote_type='dislike'))
                )
            ).values_list('total_interactions', flat=True)
        )

    def calculate_badge(self, likes: int, dislikes: int) -> Tuple[str, str, str]:
        """
        Calculates badge based on likes, dislikes and percentile.

        Badge logic:
        - INTACTA: No interactions
        - UNÀNIME: ≥3 interactions, ≥90% likes
        - HIMNE: Top 10% percentile, ≥85% likes
        - DIVISIVA: Top 30% percentile, 40-60% likes (polarizing)
        - PETANT-HO: Top 30% percentile, ≥75% likes
        - EXPLOSIVA: Top 30% percentile, other ratios
        - TRENDING: Top 40% percentile, ≥65% likes
        - CALENTA: Top 60% percentile, ≥50% likes
        - JOIA: ≥2 interactions, ≥80% likes (hidden gem)
        - GÈLIDA: ≥3 interactions, <30% likes (cold)
        - FRESCA: Default (low engagement)

        Args:
            likes: Number of like votes
            dislikes: Number of dislike votes

        Returns:
            Tuple[label: str, bg_color: str, text_color: str]

        Example:
            >>> calculator = BadgeCalculator(party.songs)
            >>> calculator.calculate_badge(0, 0)
            ('INTACTA', '#cbd5e1', '#475569')
            >>> calculator.calculate_badge(10, 0)
            ('UNÀNIME', '#e63946', '#ffffff')
        """
        total_interactions = likes + dislikes

        # Special case: No interactions
        if total_interactions == 0:
            return ("INTACTA", "#cbd5e1", "#475569")

        # Calculate like ratio
        like_ratio = (likes / total_interactions * 100)

        # Calculate percentile
        percentile = self._calculate_percentile(total_interactions)

        # Classify badge
        return self._classify_badge(total_interactions, like_ratio, percentile)

    def _calculate_percentile(self, total_interactions: int) -> float:
        """
        Calculates percentile of interactions within party.

        Args:
            total_interactions: Total interactions for a song

        Returns:
            Percentile (0-100)
        """
        if self.total_ranked_songs == 0:
            return 0
        songs_below = sum(
            1 for count in self.sorted_counts
            if count <= total_interactions
        )
        return (songs_below / self.total_ranked_songs) * 100

    def _classify_badge(
        self,
        total: int,
        like_ratio: float,
        percentile: float
    ) -> Tuple[str, str, str]:
        """
        Classifies badge based on metrics.

        Args:
            total: Total interactions
            like_ratio: Percentage of likes (0-100)
            percentile: Percentile within party (0-100)

        Returns:
            Tuple[label, bg_color, text_color]
        """
        # Special case: Unanimous (almost all likes)
        if total >= 3 and like_ratio >= 90:
            return ("UNÀNIME", "#e63946", "#ffffff")

        # Top tier with good ratio
        if percentile >= 90 and like_ratio >= 85:
            return ("HIMNE", "#ff006e", "#ffffff")

        # High engagement (controversial or trending)
        if percentile >= 70:
            if 40 <= like_ratio <= 60:
                return ("DIVISIVA", "#f77f00", "#000000")
            elif like_ratio >= 75:
                return ("PETANT-HO", "#fcbf49", "#000000")
            else:
                return ("EXPLOSIVA", "#ef476f", "#ffffff")

        # Trending with good ratio
        if percentile >= 60 and like_ratio >= 65:
            return ("TRENDING", "#06ffa5", "#000000")

        # Medium with decent ratio
        if percentile >= 40 and like_ratio >= 50:
            return ("CALENTA", "#ff9e00", "#000000")

        # Low engagement but good ratio (hidden gem)
        if total >= 2 and like_ratio >= 80:
            return ("JOIA", "#4cc9f0", "#000000")

        # Many dislikes
        if total >= 3 and like_ratio < 30:
            return ("GÈLIDA", "#8338ec", "#ffffff")

        # Low engagement (default)
        return ("FRESCA", "#90e0ef", "#000000")

    def apply_badges_to_songs(self, songs_queryset):
        """
        Applies badge attributes to each song in queryset.

        Modifies songs in-place by adding:
        - badge_label
        - badge_bg
        - badge_text

        Args:
            songs_queryset: QuerySet or iterable with songs
                           (must have num_likes and num_dislikes)

        Example:
            songs = party.songs.annotate(num_likes=..., num_dislikes=...)
            calculator.apply_badges_to_songs(songs)
            for song in songs:
                print(f"{song.title}: {song.badge_label}")
        """
        for song in songs_queryset:
            label, bg, text = self.calculate_badge(
                song.num_likes,
                song.num_dislikes
            )
            song.badge_label = label
            song.badge_bg = bg
            song.badge_text = text


def calculate_and_apply_badges(party, songs_queryset):
    """
    Helper function to calculate and apply badges to a queryset.

    Convenience function that creates BadgeCalculator and applies badges.

    Args:
        party: Party instance
        songs_queryset: QuerySet with num_likes and num_dislikes annotations

    Returns:
        QuerySet with badges applied (modifies in-place)

    Example:
        from jukebox.utils import get_pending_songs_ordered
        from jukebox.utils import calculate_and_apply_badges

        pending = get_pending_songs_ordered(party)
        calculate_and_apply_badges(party, pending)

        for song in pending:
            print(f"{song.badge_label}: {song.title}")
    """
    calculator = BadgeCalculator(party.songs)
    calculator.apply_badges_to_songs(songs_queryset)
    return songs_queryset
