"""
Tests per la vista song_swipe (Busca Match).

Cobreix:
- Accés requereix login i party seleccionada
- Redirect si voting no actiu
- GET mostra cançons no votades (exclou les ja votades)
- POST like/dislike/skip → resposta JSON
- POST acció invàlida → JSON error
"""
import json

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from jukebox.models import Party, Song, Vote
from django.contrib.auth import get_user_model

User = get_user_model()

AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}


class SongSwipeAccessTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='swiper', password='test', credits=0)
        self.party = Party.objects.create(
            name='Swipe Party',
            date=timezone.now(),
            max_votes_per_user=10,
            party_status=Party.STATUS_DJJUKEBOX_ACTIVE,
        )

    def _set_party(self):
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

    def test_requires_login(self):
        response = self.client.get(reverse('song_swipe'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/', response['Location'])

    def test_requires_selected_party(self):
        self.client.login(username='swiper', password='test')
        response = self.client.get(reverse('song_swipe'))
        self.assertRedirects(response, reverse('select_party'))

    def test_redirects_if_voting_not_active(self):
        self.client.login(username='swiper', password='test')
        self._set_party()
        self.party.party_status = Party.STATUS_SHOW_PARTY
        self.party.save()
        response = self.client.get(reverse('song_swipe'))
        self.assertRedirects(response, reverse('song_list'))

    def test_get_accessible_when_active(self):
        self.client.login(username='swiper', password='test')
        self._set_party()
        response = self.client.get(reverse('song_swipe'))
        self.assertEqual(response.status_code, 200)

    def test_get_accessible_when_requests_open(self):
        self.client.login(username='swiper', password='test')
        self._set_party()
        self.party.party_status = Party.STATUS_REQUESTS_OPEN
        self.party.save()
        response = self.client.get(reverse('song_swipe'))
        self.assertEqual(response.status_code, 200)


class SongSwipeGetTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='swipget', password='test', credits=0)
        self.party = Party.objects.create(
            name='Swipe Get Party',
            date=timezone.now(),
            max_votes_per_user=10,
            party_status=Party.STATUS_DJJUKEBOX_ACTIVE,
        )
        self.songs = [
            Song.objects.create(
                party=self.party, title=f'SwSong {i}', artist='A', spotify_id=f'sw{i}'
            )
            for i in range(5)
        ]
        self.client.login(username='swipget', password='test')
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

    def test_get_shows_unvoted_songs(self):
        response = self.client.get(reverse('song_swipe'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('songs', response.context)
        self.assertEqual(len(response.context['songs']), 5)

    def test_voted_songs_excluded(self):
        Vote.objects.create(
            user=self.user, song=self.songs[0], party=self.party, vote_type='like'
        )
        response = self.client.get(reverse('song_swipe'))
        # Una cançó votada → 4 sense votar
        self.assertEqual(len(response.context['songs']), 4)

    def test_context_has_votes_left(self):
        response = self.client.get(reverse('song_swipe'))
        self.assertIn('votes_left', response.context)
        self.assertEqual(response.context['votes_left'], 10)

    def test_context_has_total_songs(self):
        response = self.client.get(reverse('song_swipe'))
        self.assertEqual(response.context['total_songs'], 5)

    def test_songs_have_badge_attributes(self):
        response = self.client.get(reverse('song_swipe'))
        for song in response.context['songs']:
            self.assertTrue(hasattr(song, 'badge_label'))


class SongSwipePostTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='swippost', password='test', credits=0)
        self.party = Party.objects.create(
            name='Swipe Post Party',
            date=timezone.now(),
            max_votes_per_user=10,
            party_status=Party.STATUS_DJJUKEBOX_ACTIVE,
        )
        self.song = Song.objects.create(
            party=self.party, title='Swipe Song', artist='A', spotify_id='swp1'
        )
        self.client.login(username='swippost', password='test')
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

    def test_post_like_creates_vote(self):
        self.client.post(
            reverse('song_swipe'),
            {'action': 'like', 'song_id': self.song.id},
        )
        self.assertTrue(
            Vote.objects.filter(user=self.user, song=self.song, party=self.party).exists()
        )

    def test_post_like_returns_json_success(self):
        response = self.client.post(
            reverse('song_swipe'),
            {'action': 'like', 'song_id': self.song.id},
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])

    def test_post_dislike_creates_vote(self):
        self.client.post(
            reverse('song_swipe'),
            {'action': 'dislike', 'song_id': self.song.id},
        )
        self.assertTrue(
            Vote.objects.filter(
                user=self.user, song=self.song, party=self.party, vote_type='dislike'
            ).exists()
        )

    def test_post_skip_does_not_create_vote(self):
        self.client.post(
            reverse('song_swipe'),
            {'action': 'skip', 'song_id': self.song.id},
        )
        self.assertFalse(
            Vote.objects.filter(user=self.user, song=self.song, party=self.party).exists()
        )

    def test_post_skip_returns_json(self):
        response = self.client.post(
            reverse('song_swipe'),
            {'action': 'skip', 'song_id': self.song.id},
        )
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_post_invalid_action_returns_400(self):
        response = self.client.post(
            reverse('song_swipe'),
            {'action': 'invalid', 'song_id': self.song.id},
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertFalse(data['success'])

    def test_post_no_votes_left_returns_error(self):
        self.party.max_votes_per_user = 0
        self.party.save()
        response = self.client.post(
            reverse('song_swipe'),
            {'action': 'like', 'song_id': self.song.id},
        )
        data = json.loads(response.content)
        self.assertFalse(data['success'])
