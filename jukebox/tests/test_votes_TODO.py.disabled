"""
Tests per el sistema de votes i coins
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from jukebox.models import Party, Song, Vote, VotePackage, PartyCoinsGrant
from jukebox.votes import (
    get_user_votes_left,
    get_user_available_coins_for_party,
    convert_coins_to_votes,
    CONVERSION_RATES
)

User = get_user_model()


class VotesSystemTests(TestCase):
    """Tests per el sistema de votació"""

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
            max_votes_per_user=5,
            free_coins_per_user=10
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

    def test_get_user_votes_left_multiple_purchases(self):
        """Test vots amb múltiples compres"""
        VotePackage.objects.create(user=self.user, party=self.party, votes_purchased=5)
        VotePackage.objects.create(user=self.user, party=self.party, votes_purchased=10)

        votes_left = get_user_votes_left(self.user, self.party)
        self.assertEqual(votes_left, 20)  # 5 base + 5 + 10


class CoinsSystemTests(TestCase):
    """Tests per el sistema de coins"""

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
            free_coins_per_user=20
        )

    def test_get_available_coins_only_global(self):
        """Test coins disponibles només globals"""
        available = get_user_available_coins_for_party(self.user, self.party)
        self.assertEqual(available, 100)  # credits globals

    def test_get_available_coins_with_free_coins(self):
        """Test coins disponibles amb free coins de festa"""
        # Crear grant de free coins
        PartyCoinsGrant.objects.create(
            user=self.user,
            party=self.party,
            coins_granted=20,
            reason='free_coins'
        )

        available = get_user_available_coins_for_party(self.user, self.party)
        self.assertEqual(available, 120)  # 100 globals + 20 free

    def test_get_available_coins_with_multiple_grants(self):
        """Test coins amb múltiples grants"""
        PartyCoinsGrant.objects.create(user=self.user, party=self.party, coins_granted=10)
        PartyCoinsGrant.objects.create(user=self.user, party=self.party, coins_granted=15)

        available = get_user_available_coins_for_party(self.user, self.party)
        self.assertEqual(available, 125)  # 100 + 10 + 15

    def test_get_available_coins_with_negative_adjustment(self):
        """Test coins amb ajust negatiu"""
        PartyCoinsGrant.objects.create(user=self.user, party=self.party, coins_granted=20)
        PartyCoinsGrant.objects.create(user=self.user, party=self.party, coins_granted=-10)

        available = get_user_available_coins_for_party(self.user, self.party)
        self.assertEqual(available, 110)  # 100 + 20 - 10


class ConversionRatesTests(TestCase):
    """Tests per les conversions coins → votes"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='test',
            credits=100
        )
        self.party = Party.objects.create(
            name='Test Party',
            owner=self.user,
            date=timezone.now()
        )

    def test_conversion_rates_exist(self):
        """Test que les tarifes de conversió existeixen"""
        self.assertIsNotNone(CONVERSION_RATES)
        self.assertIsInstance(CONVERSION_RATES, dict)
        self.assertIn(1, CONVERSION_RATES)
        self.assertIn(5, CONVERSION_RATES)
        self.assertIn(10, CONVERSION_RATES)

    def test_convert_coins_basic(self):
        """Test conversió bàsica 1 coin → 2 votes"""
        result = convert_coins_to_votes(self.user, self.party, 1)

        self.assertTrue(result['success'])
        self.assertEqual(result['votes_received'], 2)
        self.user.refresh_from_db()
        self.assertEqual(self.user.credits, 99)  # 100 - 1

    def test_convert_coins_with_bonus(self):
        """Test conversió amb bonus (5 coins → 11 votes)"""
        result = convert_coins_to_votes(self.user, self.party, 5)

        self.assertTrue(result['success'])
        self.assertEqual(result['votes_received'], 11)  # 10 base + 1 bonus
        self.user.refresh_from_db()
        self.assertEqual(self.user.credits, 95)

    def test_convert_coins_insufficient_credits(self):
        """Test conversió sense coins suficients"""
        self.user.credits = 2
        self.user.save()

        result = convert_coins_to_votes(self.user, self.party, 5)

        self.assertFalse(result['success'])
        self.assertIn('error', result)
        self.user.refresh_from_db()
        self.assertEqual(self.user.credits, 2)  # No s'han descomptat

    def test_convert_coins_invalid_amount(self):
        """Test conversió amb quantitat invàlida"""
        result = convert_coins_to_votes(self.user, self.party, 7)

        self.assertFalse(result['success'])
        self.assertIn('error', result)

    def test_convert_coins_creates_vote_package(self):
        """Test que la conversió crea VotePackage"""
        convert_coins_to_votes(self.user, self.party, 5)

        package = VotePackage.objects.filter(user=self.user, party=self.party).first()
        self.assertIsNotNone(package)
        self.assertEqual(package.votes_purchased, 11)


class VotesAndCoinsIntegrationTests(TestCase):
    """Tests d'integració entre votes i coins"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='test',
            credits=50
        )
        self.party = Party.objects.create(
            name='Test Party',
            owner=self.user,
            date=timezone.now(),
            max_votes_per_user=3
        )
        self.songs = [
            Song.objects.create(
                party=self.party,
                title=f'Song {i}',
                artist='Artist',
                spotify_id=f'id{i}'
            ) for i in range(5)
        ]

    def test_full_voting_workflow(self):
        """Test workflow complet: comprar coins, convertir i votar"""
        # 1. Usuari té 50 credits
        self.assertEqual(self.user.credits, 50)

        # 2. Convertir 5 coins a 11 votes
        result = convert_coins_to_votes(self.user, self.party, 5)
        self.assertTrue(result['success'])
        self.assertEqual(result['votes_received'], 11)

        # 3. Verificar vots disponibles (3 base + 11 comprats = 14)
        votes_left = get_user_votes_left(self.user, self.party)
        self.assertEqual(votes_left, 14)

        # 4. Votar 4 cançons
        for i in range(4):
            Vote.objects.create(user=self.user, song=self.songs[i], party=self.party)

        # 5. Verificar vots restants (14 - 4 = 10)
        votes_left = get_user_votes_left(self.user, self.party)
        self.assertEqual(votes_left, 10)

        # 6. Verificar credits globals (50 - 5 = 45)
        self.user.refresh_from_db()
        self.assertEqual(self.user.credits, 45)

    def test_cannot_vote_without_votes(self):
        """Test que no es pot votar sense vots disponibles"""
        # Usuari amb 0 vots base
        party_no_votes = Party.objects.create(
            name='No Votes Party',
            owner=self.user,
            date=timezone.now(),
            max_votes_per_user=0
        )

        votes_left = get_user_votes_left(self.user, party_no_votes)
        self.assertEqual(votes_left, 0)

        # Intentar votar hauria de fallar (tested a nivell de view)

    def test_party_specific_votes(self):
        """Test que els vots són específics per festa"""
        party2 = Party.objects.create(
            name='Party 2',
            owner=self.user,
            date=timezone.now(),
            max_votes_per_user=5
        )

        # Comprar vots per party1
        convert_coins_to_votes(self.user, self.party, 5)

        # Verificar vots a cada festa
        votes_party1 = get_user_votes_left(self.user, self.party)
        votes_party2 = get_user_votes_left(self.user, party2)

        self.assertEqual(votes_party1, 14)  # 3 base + 11 comprats
        self.assertEqual(votes_party2, 5)   # Només base

    def test_global_credits_shared(self):
        """Test que els credits globals es comparteixen"""
        party2 = Party.objects.create(
            name='Party 2',
            owner=self.user,
            date=timezone.now()
        )

        # Gastar 10 coins a party1
        convert_coins_to_votes(self.user, self.party, 10)

        # Verificar que credits globals s'han descomptat
        self.user.refresh_from_db()
        self.assertEqual(self.user.credits, 25)  # 50 - 25 coins (10 coins package)

        # Intentar gastar 30 coins a party2 (no hi ha prou)
        result = convert_coins_to_votes(self.user, party2, 20)
        self.assertFalse(result['success'])
