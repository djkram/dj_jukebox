"""
Tests per Spotify API helpers
"""
import time
from unittest.mock import patch

from django.test import SimpleTestCase

from jukebox import spotify_api
from jukebox.spotify_api import _camelot_from_key_string, _get_getsongbpm_features, _pick_getsongbpm_match


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

    def test_tunebat_cooldown_returns_without_sleeping(self):
        """El cooldown de Tunebat no ha de bloquejar una request HTTP."""
        previous_until = spotify_api._TUNEBAT_RATE_LIMIT_UNTIL
        spotify_api._TUNEBAT_RATE_LIMIT_UNTIL = time.time() + 60
        try:
            with patch("jukebox.spotify_api.time.sleep") as mock_sleep:
                result = _get_getsongbpm_features("Cooldown Test Song", "Cooldown Artist", "cooldown-spotify-id")
        finally:
            spotify_api._TUNEBAT_RATE_LIMIT_UNTIL = previous_until

        self.assertEqual(result, {"bpm": None, "key": None, "tunebat_url": None})
        mock_sleep.assert_not_called()
