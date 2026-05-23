"""
Tests per PartySettingsForm i PartyForm.

Cobreix:
- clean_max_votes_per_user: valor vàlid, zero, negatiu
- clean_song_request_cost: valor vàlid, zero, negatiu
- clean_code: codi vàlid, massa curt, duplicat, auto-exclusió instància pròpia
- save() sense playlist: desa els camps del Party
- save() amb playlist (mock Spotify): crea Playlist i Songs
- save() amb load_songs=False: no crea Songs tot i tenir playlist
- PartyForm: smoke test de camps i widget de data
"""
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from jukebox.forms import PartyForm, PartySettingsForm
from jukebox.models import Party, Playlist, Song
from django.contrib.auth import get_user_model

User = get_user_model()

FAKE_PLAYLISTS = [
    {'id': 'pl_abc123', 'name': 'Test Playlist', 'owner': 'testuser'},
]
FAKE_TRACKS = [
    {'id': 'tr1', 'title': 'Song A', 'artist': 'Artist A', 'album_image_url': None, 'bpm': 128, 'key': '8B'},
    {'id': 'tr2', 'title': 'Song B', 'artist': 'Artist B', 'album_image_url': None, 'bpm': None, 'key': None},
]


def _base_party_data(**overrides):
    data = {
        'name': 'Test Party',
        'date': '2026-06-01T21:00',
        'code': 'TEST',
        'max_votes_per_user': 10,
        'song_request_cost': 5,
        'free_coins_per_user': 0,
        'is_public': True,
        'require_join_code': False,
        'allow_song_requests': True,
        'djs': [],
    }
    data.update(overrides)
    return data


class CleanMaxVotesTests(TestCase):
    """Tests per clean_max_votes_per_user."""

    def _form(self, value, instance=None):
        data = _base_party_data(max_votes_per_user=value)
        return PartySettingsForm(data, instance=instance)

    def test_valid_value_passes(self):
        form = self._form(5)
        self.assertTrue(form.is_valid(), form.errors)

    def test_one_is_minimum_valid(self):
        form = self._form(1)
        self.assertTrue(form.is_valid(), form.errors)

    def test_zero_raises_error(self):
        form = self._form(0)
        self.assertFalse(form.is_valid())
        self.assertIn('max_votes_per_user', form.errors)

    def test_negative_raises_error(self):
        form = self._form(-3)
        self.assertFalse(form.is_valid())
        self.assertIn('max_votes_per_user', form.errors)

    def test_error_message_is_descriptive(self):
        form = self._form(0)
        form.is_valid()
        self.assertIn('1', form.errors['max_votes_per_user'][0])


class CleanSongRequestCostTests(TestCase):
    """Tests per clean_song_request_cost."""

    def _form(self, value):
        data = _base_party_data(song_request_cost=value)
        return PartySettingsForm(data)

    def test_valid_value_passes(self):
        form = self._form(5)
        self.assertTrue(form.is_valid(), form.errors)

    def test_one_is_minimum_valid(self):
        form = self._form(1)
        self.assertTrue(form.is_valid(), form.errors)

    def test_zero_raises_error(self):
        form = self._form(0)
        self.assertFalse(form.is_valid())
        self.assertIn('song_request_cost', form.errors)

    def test_negative_raises_error(self):
        form = self._form(-1)
        self.assertFalse(form.is_valid())
        self.assertIn('song_request_cost', form.errors)


class CleanCodeTests(TestCase):
    """Tests per clean_code."""

    def _form(self, code, instance=None):
        data = _base_party_data(code=code)
        return PartySettingsForm(data, instance=instance)

    def test_valid_4char_code_passes(self):
        form = self._form('ABCD')
        self.assertTrue(form.is_valid(), form.errors)

    def test_code_normalised_to_uppercase(self):
        form = self._form('abcd')
        form.is_valid()
        self.assertEqual(form.cleaned_data['code'], 'ABCD')

    def test_too_short_code_raises_error(self):
        form = self._form('AB')
        self.assertFalse(form.is_valid())
        self.assertIn('code', form.errors)

    def test_empty_code_raises_error(self):
        form = self._form('')
        self.assertFalse(form.is_valid())
        self.assertIn('code', form.errors)

    def test_duplicate_code_raises_error(self):
        Party.objects.create(name='Existing', date=timezone.now(), code='DUPL')
        form = self._form('DUPL')
        self.assertFalse(form.is_valid())
        self.assertIn('code', form.errors)

    def test_same_instance_code_does_not_raise(self):
        """Una festa pot guardar el seu propi codi sense error de duplicat."""
        party = Party.objects.create(name='Own Party', date=timezone.now(), code='MINE')
        form = self._form('MINE', instance=party)
        self.assertTrue(form.is_valid(), form.errors)

    def test_different_code_from_existing_passes(self):
        Party.objects.create(name='Other', date=timezone.now(), code='AAAA')
        form = self._form('BBBB')
        self.assertTrue(form.is_valid(), form.errors)


class PartySettingsFormSaveTests(TestCase):
    """Tests per PartySettingsForm.save()."""

    def setUp(self):
        self.party = Party.objects.create(
            name='Old Name',
            date=timezone.now(),
            code='ORIG',
            max_votes_per_user=5,
            song_request_cost=3,
        )

    def test_save_without_playlist_updates_party_fields(self):
        data = _base_party_data(name='New Name', code='ORIG', max_votes_per_user=15)
        form = PartySettingsForm(data, instance=self.party)
        self.assertTrue(form.is_valid(), form.errors)
        party = form.save(load_songs=False)
        self.assertEqual(party.name, 'New Name')
        self.assertEqual(party.max_votes_per_user, 15)

    @patch('jukebox.forms.get_playlist_tracks', return_value=FAKE_TRACKS)
    @patch('jukebox.forms.get_user_playlists', return_value=FAKE_PLAYLISTS)
    def test_save_with_playlist_creates_playlist_object(self, mock_playlists, mock_tracks):
        data = _base_party_data(code='ORIG', spotify_playlist='pl_abc123')
        form = PartySettingsForm(data, instance=self.party, request=object())
        self.assertTrue(form.is_valid(), form.errors)
        form.save(load_songs=True)
        self.assertTrue(Playlist.objects.filter(spotify_id='pl_abc123').exists())

    @patch('jukebox.forms.get_playlist_tracks', return_value=FAKE_TRACKS)
    @patch('jukebox.forms.get_user_playlists', return_value=FAKE_PLAYLISTS)
    def test_save_with_playlist_creates_songs(self, mock_playlists, mock_tracks):
        data = _base_party_data(code='ORIG', spotify_playlist='pl_abc123')
        form = PartySettingsForm(data, instance=self.party, request=object())
        self.assertTrue(form.is_valid(), form.errors)
        form.save(load_songs=True)
        self.assertEqual(Song.objects.filter(party=self.party).count(), len(FAKE_TRACKS))

    @patch('jukebox.forms.get_playlist_tracks', return_value=FAKE_TRACKS)
    @patch('jukebox.forms.get_user_playlists', return_value=FAKE_PLAYLISTS)
    def test_save_load_songs_false_does_not_create_songs(self, mock_playlists, mock_tracks):
        data = _base_party_data(code='ORIG', spotify_playlist='pl_abc123')
        form = PartySettingsForm(data, instance=self.party, request=object())
        self.assertTrue(form.is_valid(), form.errors)
        form.save(load_songs=False)
        self.assertEqual(Song.objects.filter(party=self.party).count(), 0)

    @patch('jukebox.forms.get_playlist_tracks', return_value=FAKE_TRACKS)
    @patch('jukebox.forms.get_user_playlists', return_value=FAKE_PLAYLISTS)
    def test_save_with_playlist_links_playlist_to_party(self, mock_playlists, mock_tracks):
        data = _base_party_data(code='ORIG', spotify_playlist='pl_abc123')
        form = PartySettingsForm(data, instance=self.party, request=object())
        self.assertTrue(form.is_valid(), form.errors)
        party = form.save(load_songs=False)
        party.refresh_from_db()
        self.assertIsNotNone(party.playlist)
        self.assertEqual(party.playlist.spotify_id, 'pl_abc123')

    @patch('jukebox.forms.get_playlist_tracks', return_value=FAKE_TRACKS)
    @patch('jukebox.forms.get_user_playlists', return_value=FAKE_PLAYLISTS)
    def test_save_with_playlist_clears_previous_songs(self, mock_playlists, mock_tracks):
        Song.objects.create(party=self.party, spotify_id='old1', title='Old', artist='Old')
        data = _base_party_data(code='ORIG', spotify_playlist='pl_abc123')
        form = PartySettingsForm(data, instance=self.party, request=object())
        self.assertTrue(form.is_valid(), form.errors)
        form.save(load_songs=True)
        self.assertFalse(Song.objects.filter(party=self.party, spotify_id='old1').exists())

    @patch('jukebox.forms.get_playlist_tracks', return_value=FAKE_TRACKS)
    @patch('jukebox.forms.get_user_playlists', return_value=FAKE_PLAYLISTS)
    def test_save_songs_with_bpm_and_key(self, mock_playlists, mock_tracks):
        data = _base_party_data(code='ORIG', spotify_playlist='pl_abc123')
        form = PartySettingsForm(data, instance=self.party, request=object())
        self.assertTrue(form.is_valid(), form.errors)
        form.save(load_songs=True)
        song = Song.objects.get(party=self.party, spotify_id='tr1')
        self.assertEqual(song.bpm, 128)
        self.assertEqual(song.key, '8B')


class PartyFormTests(TestCase):
    """Smoke tests per PartyForm (creació bàsica)."""

    def test_valid_form_passes(self):
        form = PartyForm(data={'name': 'My Party', 'date': '2026-07-01T20:00'})
        self.assertTrue(form.is_valid(), form.errors)

    def test_missing_name_fails(self):
        form = PartyForm(data={'name': '', 'date': '2026-07-01T20:00'})
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)

    def test_missing_date_fails(self):
        form = PartyForm(data={'name': 'My Party', 'date': ''})
        self.assertFalse(form.is_valid())
        self.assertIn('date', form.errors)

    def test_date_widget_is_datetimeinput(self):
        from django.forms import DateTimeInput
        form = PartyForm()
        self.assertIsInstance(form.fields['date'].widget, DateTimeInput)
