"""
Tests per Spotify API helpers
"""
from django.test import SimpleTestCase

from jukebox.spotify_api import (
    _camelot_from_key_string,
    _pick_songbpm_match,
    _normalize_match_text,
    _songbpm_key_to_camelot,
    _songdata_slug,
    _song_title_search_queries,
)


class SpotifyApiHelpersTests(SimpleTestCase):
    """Tests per funcions helper de Spotify API"""

    def test_camelot_from_key_string_supports_major_and_minor(self):
        """Test conversió de keys a notació Camelot"""
        self.assertEqual(_camelot_from_key_string("C"), "8B")
        self.assertEqual(_camelot_from_key_string("Am"), "8A")
        self.assertEqual(_camelot_from_key_string("F#"), "2B")
        self.assertEqual(_camelot_from_key_string("Dm"), "7A")
        self.assertEqual(_camelot_from_key_string("G"), "9B")

    def test_camelot_from_key_string_with_flat(self):
        """Test conversió amb bemolls"""
        self.assertEqual(_camelot_from_key_string("Bb"), "6B")
        self.assertEqual(_camelot_from_key_string("Ebm"), "2A")  # Eb menor = 2A

    def test_pick_songbpm_match_prefers_title_and_artist_match(self):
        """Test que tria el millor match de SongBPM"""
        results = [
            {
                "title": "Five More Hours - Remix",
                "artist": {"name": "Deorro"},
            },
            {
                "title": "Five More Hours",
                "artist": {"name": "Deorro, Chris Brown"},
            },
        ]

        match = _pick_songbpm_match(results, "Five More Hours", "Deorro, Chris Brown")

        self.assertEqual(match, results[1])

    def test_pick_songbpm_match_returns_first_if_no_exact(self):
        """Test que retorna el primer si no hi ha match exacte"""
        results = [
            {
                "title": "Song A",
                "artist": {"name": "Artist A"},
            },
            {
                "title": "Song B",
                "artist": {"name": "Artist B"},
            },
        ]

        match = _pick_songbpm_match(results, "Different Song", "Different Artist")

        # Hauria de retornar el primer per defecte
        self.assertEqual(match, results[0])

    def test_pick_songbpm_match_empty_results(self):
        """Test amb llista buida"""
        match = _pick_songbpm_match([], "Song", "Artist")

        self.assertIsNone(match)

    def test_songbpm_key_to_camelot_uses_mode(self):
        self.assertEqual(_songbpm_key_to_camelot("F♯/G♭", "major"), "2B")
        self.assertEqual(_songbpm_key_to_camelot("F♯/G♭", "minor"), "11A")
        self.assertIsNone(_songbpm_key_to_camelot("F♯/G♭"))

    def test_songdata_slug_uses_title_and_first_artist(self):
        self.assertEqual(
            _songdata_slug("Y.M.C.A.", "Village People, Other"),
            "Y-M-C-A-by-Village-People",
        )

    def test_song_title_search_queries_use_only_title_variants(self):
        self.assertEqual(
            _song_title_search_queries("Barbra Streisand - Radio Edit"),
            ["Barbra Streisand - Radio Edit", "Barbra Streisand"],
        )

    def test_normalize_match_text_ignores_accents_and_punctuation(self):
        self.assertEqual(
            _normalize_match_text("Barbra Streisand - Radio Edit"),
            "barbra streisand radio edit",
        )
        self.assertEqual(_normalize_match_text("D♭ Major"), "d major")
