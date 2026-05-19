"""
Tests per la lògica de negoci:
  - Conversió Coins → Vots (calculate_votes_from_coins, convert_coins_to_votes)
  - Coins gratuïts per festa (ensure_user_has_free_coins)
  - Càlcul de distàncies (haversine)
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from jukebox.models import Party, VotePackage, PartyCoinsGrant
from jukebox.utils.votes_conversion import calculate_votes_from_coins, convert_coins_to_votes
from jukebox.votes import ensure_user_has_free_coins, get_user_party_coins
from jukebox.views import _haversine_km

User = get_user_model()


class CoinsToVotesConversionTests(TestCase):
    """Tests per calculate_votes_from_coins (pura, sense BD)"""

    def test_1_coin_gives_2_votes(self):
        self.assertEqual(calculate_votes_from_coins(1), 2)

    def test_2_coins_gives_4_votes(self):
        self.assertEqual(calculate_votes_from_coins(2), 4)

    def test_3_coins_gives_6_votes(self):
        self.assertEqual(calculate_votes_from_coins(3), 6)

    def test_5_coins_gives_11_votes(self):
        self.assertEqual(calculate_votes_from_coins(5), 11)

    def test_10_coins_gives_25_votes(self):
        self.assertEqual(calculate_votes_from_coins(10), 25)

    def test_20_coins_gives_60_votes(self):
        self.assertEqual(calculate_votes_from_coins(20), 60)

    def test_zero_coins_gives_zero(self):
        self.assertEqual(calculate_votes_from_coins(0), 0)

    def test_large_amount_scales_at_3x(self):
        self.assertEqual(calculate_votes_from_coins(30), 90)

    def test_boundary_5_coins(self):
        self.assertEqual(calculate_votes_from_coins(4), 8)
        self.assertEqual(calculate_votes_from_coins(5), 11)

    def test_boundary_10_coins(self):
        self.assertEqual(calculate_votes_from_coins(9), int(9 * 2.2))
        self.assertEqual(calculate_votes_from_coins(10), 25)

    def test_boundary_20_coins(self):
        self.assertEqual(calculate_votes_from_coins(19), int(19 * 2.5))
        self.assertEqual(calculate_votes_from_coins(20), 60)


class ConvertCoinsToVotesTests(TestCase):
    """Tests per convert_coins_to_votes (amb BD)"""

    def setUp(self):
        self.user = User.objects.create_user(username='user', password='test', credits=20)
        self.party = Party.objects.create(
            name='Test Party',
            date=timezone.now(),
            max_votes_per_user=5,
        )

    def test_successful_conversion_deducts_credits(self):
        success, error, votes = convert_coins_to_votes(self.user, self.party, 5)

        self.assertTrue(success)
        self.assertEqual(error, "")
        self.assertEqual(votes, 11)
        self.user.refresh_from_db()
        self.assertEqual(self.user.credits, 15)

    def test_successful_conversion_creates_vote_package(self):
        convert_coins_to_votes(self.user, self.party, 10)

        package = VotePackage.objects.filter(user=self.user, party=self.party).first()
        self.assertIsNotNone(package)
        self.assertEqual(package.votes_purchased, 25)

    def test_insufficient_credits_fails(self):
        success, error, votes = convert_coins_to_votes(self.user, self.party, 50)

        self.assertFalse(success)
        self.assertNotEqual(error, "")
        self.assertEqual(votes, 0)
        self.user.refresh_from_db()
        self.assertEqual(self.user.credits, 20)

    def test_zero_coins_fails(self):
        success, error, votes = convert_coins_to_votes(self.user, self.party, 0)

        self.assertFalse(success)
        self.assertEqual(votes, 0)

    def test_negative_coins_fails(self):
        success, error, votes = convert_coins_to_votes(self.user, self.party, -5)

        self.assertFalse(success)
        self.assertEqual(votes, 0)

    def test_no_vote_package_on_failure(self):
        convert_coins_to_votes(self.user, self.party, 999)
        self.assertFalse(VotePackage.objects.filter(user=self.user, party=self.party).exists())

    def test_exact_credits_succeeds(self):
        success, _, votes = convert_coins_to_votes(self.user, self.party, 20)
        self.assertTrue(success)
        self.user.refresh_from_db()
        self.assertEqual(self.user.credits, 0)


class EnsureFreeCoinsTests(TestCase):
    """Tests per ensure_user_has_free_coins"""

    def setUp(self):
        self.user = User.objects.create_user(username='user', password='test')
        self.party = Party.objects.create(
            name='Test Party',
            date=timezone.now(),
            free_coins_per_user=5,
        )

    def test_gives_coins_on_first_join(self):
        diff = ensure_user_has_free_coins(self.user, self.party)

        self.assertEqual(diff, 5)
        grant = PartyCoinsGrant.objects.get(user=self.user, party=self.party)
        self.assertEqual(grant.coins_granted, 5)
        self.assertEqual(grant.reason, 'free_coins')

    def test_no_duplicate_grant_on_second_call(self):
        ensure_user_has_free_coins(self.user, self.party)
        diff2 = ensure_user_has_free_coins(self.user, self.party)

        self.assertEqual(diff2, 0)
        self.assertEqual(PartyCoinsGrant.objects.filter(user=self.user, party=self.party).count(), 1)

    def test_adjusts_if_party_increases_free_coins(self):
        ensure_user_has_free_coins(self.user, self.party)

        self.party.free_coins_per_user = 8
        self.party.save()

        diff2 = ensure_user_has_free_coins(self.user, self.party)
        self.assertEqual(diff2, 3)

        total = get_user_party_coins(self.user, self.party)
        self.assertEqual(total, 8)

    def test_zero_free_coins_gives_nothing(self):
        self.party.free_coins_per_user = 0
        self.party.save()

        diff = ensure_user_has_free_coins(self.user, self.party)
        self.assertEqual(diff, 0)
        self.assertFalse(PartyCoinsGrant.objects.filter(user=self.user, party=self.party).exists())


class HaversineTests(TestCase):
    """Tests per _haversine_km (pura, sense BD)"""

    def test_same_point_is_zero(self):
        distance = _haversine_km(41.38, 2.17, 41.38, 2.17)
        self.assertAlmostEqual(distance, 0, places=5)

    def test_barcelona_to_madrid_approx(self):
        # Barcelona: 41.3851, 2.1734 | Madrid: 40.4168, -3.7038
        distance = _haversine_km(41.3851, 2.1734, 40.4168, -3.7038)
        self.assertGreater(distance, 495)
        self.assertLess(distance, 515)

    def test_short_distance(self):
        # ~1 km aproximadament
        distance = _haversine_km(41.3851, 2.1734, 41.3941, 2.1734)
        self.assertGreater(distance, 0.5)
        self.assertLess(distance, 2.0)

    def test_symmetric(self):
        d1 = _haversine_km(41.38, 2.17, 40.41, -3.70)
        d2 = _haversine_km(40.41, -3.70, 41.38, 2.17)
        self.assertAlmostEqual(d1, d2, places=5)
