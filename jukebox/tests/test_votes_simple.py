"""
Tests simples per el sistema de votació (sense funcions no implementades)
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from jukebox.models import Party, Song, Vote, VotePackage
from jukebox.votes import get_user_votes_left

User = get_user_model()


class VotesBasicTests(TestCase):
    """Tests bàsics per el sistema de votació"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='test',
            credits=100
        )
        self.party = Party.objects.create(
            name='Test Party',
            owner=self.user,
            date=timezone.now(),
            max_votes_per_user=5
        )
        self.song = Song.objects.create(
            party=self.party,
            title='Test Song',
            artist='Test Artist',
            spotify_id='id123'
        )

    def test_get_user_votes_left_base_votes(self):
        """Test vots disponibles amb només vots base"""
        votes_left = get_user_votes_left(self.user, self.party)
        self.assertEqual(votes_left, 5)  # max_votes_per_user

    def test_get_user_votes_left_after_voting(self):
        """Test vots disponibles després de votar"""
        Vote.objects.create(user=self.user, song=self.song, party=self.party)

        votes_left = get_user_votes_left(self.user, self.party)
        self.assertEqual(votes_left, 4)  # 5 - 1

    def test_get_user_votes_left_with_purchased_votes(self):
        """Test vots disponibles amb vots comprats"""
        VotePackage.objects.create(
            user=self.user,
            party=self.party,
            votes_purchased=10
        )

        votes_left = get_user_votes_left(self.user, self.party)
        self.assertEqual(votes_left, 15)  # 5 base + 10 comprats

    def test_multiple_votes_deduct_correctly(self):
        """Test que múltiples vots es descompten correctament"""
        # Crear múltiples cançons
        songs = []
        for i in range(3):
            song = Song.objects.create(
                party=self.party,
                title=f'Song {i}',
                artist='Artist',
                spotify_id=f'id{i}'
            )
            songs.append(song)

        # Votar 3 cançons
        for song in songs:
            Vote.objects.create(user=self.user, song=song, party=self.party)

        votes_left = get_user_votes_left(self.user, self.party)
        self.assertEqual(votes_left, 2)  # 5 - 3

    def test_party_votes_are_independent(self):
        """Test que els vots són independents per cada festa"""
        party2 = Party.objects.create(
            name='Party 2',
            owner=self.user,
            date=timezone.now(),
            max_votes_per_user=3
        )

        # Votar a party1
        Vote.objects.create(user=self.user, song=self.song, party=self.party)

        # Verificar vots
        votes_party1 = get_user_votes_left(self.user, self.party)
        votes_party2 = get_user_votes_left(self.user, party2)

        self.assertEqual(votes_party1, 4)  # 5 - 1
        self.assertEqual(votes_party2, 3)  # No afectat
