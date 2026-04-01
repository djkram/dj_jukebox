"""
Tests per Spotify API helpers
"""
from django.test import SimpleTestCase

from jukebox.spotify_api import _camelot_from_key_string, _pick_getsongbpm_match


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
        self.assertEqual(_camelot_from_key_string("Ebm"), "12A")

    def test_pick_getsongbpm_match_prefers_title_and_artist_match(self):
        """Test que tria el millor match de GetSongBPM"""
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

        match = _pick_getsongbpm_match(results, "Five More Hours", "Deorro, Chris Brown")

        self.assertEqual(match, results[1])

    def test_pick_getsongbpm_match_returns_first_if_no_exact(self):
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

        match = _pick_getsongbpm_match(results, "Different Song", "Different Artist")

        # Hauria de retornar el primer per defecte
        self.assertEqual(match, results[0])

    def test_pick_getsongbpm_match_empty_results(self):
        """Test amb llista buida"""
        match = _pick_getsongbpm_match([], "Song", "Artist")

        self.assertIsNone(match)
