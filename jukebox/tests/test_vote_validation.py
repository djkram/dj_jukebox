"""
Tests per validate_and_create_vote i el flux AJAX de vot/desvot a song_list.

Cobreix:
- validate_and_create_vote: èxit, duplicat, sense vots, sense credits
- AJAX POST vote_song_id → JSON amb badge i votes_left
- AJAX POST unvote_song_id → JSON actualitzat
- Conversió de Coins a Vots des de song_list
"""
import json

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from jukebox.models import Party, Song, Vote, VotePackage
from jukebox.utils.vote_validation import validate_and_create_vote
from django.contrib.auth import get_user_model

User = get_user_model()

AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}


class ValidateAndCreateVoteTests(TestCase):
    """Tests unitaris per validate_and_create_vote."""

    def setUp(self):
        self.user = User.objects.create_user(username='voter', password='test', credits=10)
        self.party = Party.objects.create(
            name='Vote Party',
            date=timezone.now(),
            max_votes_per_user=5,
            party_status=Party.STATUS_DJJUKEBOX_ACTIVE,
        )
        self.song = Song.objects.create(
            party=self.party, title='Song', artist='Artist', spotify_id='vvv1'
        )

    def test_successful_vote_returns_true(self):
        success, error = validate_and_create_vote(self.user, self.song, self.party)
        self.assertTrue(success)
        self.assertIsNone(error)

    def test_successful_vote_creates_vote_object(self):
        validate_and_create_vote(self.user, self.song, self.party)
        self.assertTrue(
            Vote.objects.filter(user=self.user, song=self.song, party=self.party).exists()
        )

    def test_duplicate_vote_returns_false(self):
        Vote.objects.create(user=self.user, song=self.song, party=self.party, vote_type='like')
        success, error = validate_and_create_vote(self.user, self.song, self.party)
        self.assertFalse(success)
        self.assertIsNotNone(error)

    def test_duplicate_vote_no_extra_vote_created(self):
        Vote.objects.create(user=self.user, song=self.song, party=self.party, vote_type='like')
        validate_and_create_vote(self.user, self.song, self.party)
        self.assertEqual(Vote.objects.filter(user=self.user, song=self.song, party=self.party).count(), 1)

    def test_no_votes_left_with_credits_returns_convert_message(self):
        # Exhaurir tots els vots base
        for i in range(5):
            s = Song.objects.create(
                party=self.party, title=f'S{i}', artist='A', spotify_id=f'ex{i}'
            )
            Vote.objects.create(user=self.user, song=s, party=self.party, vote_type='like')
        success, error = validate_and_create_vote(self.user, self.song, self.party)
        self.assertFalse(success)
        self.assertIn('Coins', error)

    def test_no_votes_left_no_credits_returns_buy_message(self):
        self.user.credits = 0
        self.user.save()
        for i in range(5):
            s = Song.objects.create(
                party=self.party, title=f'SC{i}', artist='A', spotify_id=f'sc{i}'
            )
            Vote.objects.create(user=self.user, song=s, party=self.party, vote_type='like')
        success, error = validate_and_create_vote(self.user, self.song, self.party)
        self.assertFalse(success)
        self.assertIsNotNone(error)

    def test_dislike_vote_type_saved(self):
        validate_and_create_vote(self.user, self.song, self.party, vote_type='dislike')
        vote = Vote.objects.get(user=self.user, song=self.song, party=self.party)
        self.assertEqual(vote.vote_type, 'dislike')

    def test_extra_votes_from_package_count(self):
        # Exhaurir vots base però tenir un paquet comprat
        VotePackage.objects.create(user=self.user, party=self.party, votes_purchased=3)
        for i in range(5):
            s = Song.objects.create(
                party=self.party, title=f'SP{i}', artist='A', spotify_id=f'sp{i}'
            )
            Vote.objects.create(user=self.user, song=s, party=self.party, vote_type='like')
        success, _ = validate_and_create_vote(self.user, self.song, self.party)
        self.assertTrue(success)


class SongListAjaxVoteTests(TestCase):
    """Tests per la resposta JSON del vot via AJAX a song_list."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='ajaxvoter', password='test', credits=10)
        self.party = Party.objects.create(
            name='AJAX Party',
            date=timezone.now(),
            max_votes_per_user=5,
            party_status=Party.STATUS_DJJUKEBOX_ACTIVE,
        )
        self.song = Song.objects.create(
            party=self.party, title='AJAX Song', artist='Artist', spotify_id='ajax1'
        )
        self.client.login(username='ajaxvoter', password='test')
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

    def test_ajax_vote_success_returns_json(self):
        response = self.client.post(
            reverse('song_list'),
            {'vote_song_id': self.song.id, 'vote_type': 'like'},
            **AJAX,
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['song_id'], self.song.id)
        self.assertEqual(data['user_vote'], 'like')
        self.assertIn('badge_label', data)
        self.assertIn('votes_left', data)

    def test_ajax_vote_duplicate_returns_400(self):
        Vote.objects.create(user=self.user, song=self.song, party=self.party, vote_type='like')
        response = self.client.post(
            reverse('song_list'),
            {'vote_song_id': self.song.id, 'vote_type': 'like'},
            **AJAX,
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('error', data)

    def test_ajax_vote_updates_votes_left_count(self):
        response = self.client.post(
            reverse('song_list'),
            {'vote_song_id': self.song.id, 'vote_type': 'like'},
            **AJAX,
        )
        data = json.loads(response.content)
        self.assertEqual(data['votes_left'], 4)  # 5 base - 1 usat

    def test_ajax_vote_returns_num_likes(self):
        response = self.client.post(
            reverse('song_list'),
            {'vote_song_id': self.song.id, 'vote_type': 'like'},
            **AJAX,
        )
        data = json.loads(response.content)
        self.assertEqual(data['num_likes'], 1)

    def test_ajax_vote_disabled_when_status_not_active(self):
        self.party.party_status = Party.STATUS_SHOW_PARTY
        self.party.save()
        response = self.client.post(
            reverse('song_list'),
            {'vote_song_id': self.song.id, 'vote_type': 'like'},
            **AJAX,
        )
        # Quan voting_enabled=False, no processa el vot → redirecció o no JSON
        self.assertFalse(Vote.objects.filter(user=self.user, song=self.song).exists())


class SongListAjaxUnvoteTests(TestCase):
    """Tests per la resposta JSON del desvot via AJAX."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='unvoter', password='test', credits=0)
        self.party = Party.objects.create(
            name='Unvote Party',
            date=timezone.now(),
            max_votes_per_user=5,
            party_status=Party.STATUS_DJJUKEBOX_ACTIVE,
        )
        self.song = Song.objects.create(
            party=self.party, title='Unvote Song', artist='Artist', spotify_id='unv1'
        )
        Vote.objects.create(user=self.user, song=self.song, party=self.party, vote_type='like')
        self.client.login(username='unvoter', password='test')
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

    def test_ajax_unvote_returns_json(self):
        response = self.client.post(
            reverse('song_list'),
            {'unvote_song_id': self.song.id},
            **AJAX,
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertIsNone(data['user_vote'])

    def test_ajax_unvote_removes_vote(self):
        self.client.post(
            reverse('song_list'),
            {'unvote_song_id': self.song.id},
            **AJAX,
        )
        self.assertFalse(
            Vote.objects.filter(user=self.user, song=self.song, party=self.party).exists()
        )

    def test_ajax_unvote_restores_votes_left(self):
        response = self.client.post(
            reverse('song_list'),
            {'unvote_song_id': self.song.id},
            **AJAX,
        )
        data = json.loads(response.content)
        self.assertEqual(data['votes_left'], 5)  # vot eliminat, recuperem 1

    def test_ajax_unvote_returns_badge(self):
        response = self.client.post(
            reverse('song_list'),
            {'unvote_song_id': self.song.id},
            **AJAX,
        )
        data = json.loads(response.content)
        self.assertIn('badge_label', data)


class SongListConvertCoinsTests(TestCase):
    """Tests per la conversió de Coins a Vots des de song_list (POST action=convert_coins)."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='converter', password='test', credits=20)
        self.party = Party.objects.create(
            name='Convert Party',
            date=timezone.now(),
            max_votes_per_user=5,
            party_status=Party.STATUS_DJJUKEBOX_ACTIVE,
        )
        self.client.login(username='converter', password='test')
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

    def test_convert_5_coins_creates_vote_package(self):
        self.client.post(
            reverse('song_list'),
            {'action': 'convert_coins', 'coins_to_convert': '5'},
        )
        self.assertTrue(VotePackage.objects.filter(user=self.user, party=self.party).exists())

    def test_convert_5_coins_deducts_credits(self):
        self.client.post(
            reverse('song_list'),
            {'action': 'convert_coins', 'coins_to_convert': '5'},
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.credits, 15)

    def test_convert_redirects_on_success(self):
        response = self.client.post(
            reverse('song_list'),
            {'action': 'convert_coins', 'coins_to_convert': '5'},
        )
        self.assertEqual(response.status_code, 302)

    def test_convert_below_minimum_does_not_deduct(self):
        self.client.post(
            reverse('song_list'),
            {'action': 'convert_coins', 'coins_to_convert': '3'},
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.credits, 20)

    def test_convert_zero_coins_does_not_deduct(self):
        self.client.post(
            reverse('song_list'),
            {'action': 'convert_coins', 'coins_to_convert': '0'},
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.credits, 20)
