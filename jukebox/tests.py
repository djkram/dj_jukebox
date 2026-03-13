from django.test import SimpleTestCase

from jukebox.spotify_api import _camelot_from_key_string, _pick_getsongbpm_match


class SpotifyApiHelpersTests(SimpleTestCase):
    def test_camelot_from_key_string_supports_major_and_minor(self):
        self.assertEqual(_camelot_from_key_string("C"), "8B")
        self.assertEqual(_camelot_from_key_string("Am"), "8A")
        self.assertEqual(_camelot_from_key_string("F#"), "2B")

    def test_pick_getsongbpm_match_prefers_title_and_artist_match(self):
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
