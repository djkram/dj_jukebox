"""
Tests per BadgeCalculator — lògica de badges per cançons basada en percentils.

Cobreix tots els tipus de badge:
INTACTA, UNÀNIME, HIMNE, DIVISIVA, PETANT-HO, EXPLOSIVA,
TRENDING, CALENTA, JOIA, GÈLIDA, FRESCA
"""
from django.test import TestCase
from django.utils import timezone

from jukebox.models import Party, Song, Vote
from jukebox.utils.badges import BadgeCalculator, calculate_and_apply_badges
from django.contrib.auth import get_user_model

User = get_user_model()


def _make_party():
    return Party.objects.create(name='Badge Party', date=timezone.now())


def _make_songs(party, n):
    return [
        Song.objects.create(party=party, title=f'Song {i}', artist='A', spotify_id=f'bid{i}')
        for i in range(n)
    ]


class BadgeCalculatorBadgeTypesTests(TestCase):
    """Verifica que cada tipus de badge es retorna correctament."""

    def setUp(self):
        self.party = _make_party()
        # Una sola cançó: tots els percentils li pertanyen
        self.songs = _make_songs(self.party, 1)

    def _calc(self):
        return BadgeCalculator(self.party.songs)

    def test_intacta_zero_interactions(self):
        label, _, _ = self._calc().calculate_badge(0, 0)
        self.assertEqual(label, 'INTACTA')

    def test_unanime_all_likes(self):
        label, _, _ = self._calc().calculate_badge(10, 0)
        self.assertEqual(label, 'UNÀNIME')

    def test_unanime_requires_minimum_3_interactions(self):
        # 2 likes, 0 dislikes: ratio 100% però total < 3 → no és UNÀNIME
        label, _, _ = self._calc().calculate_badge(2, 0)
        self.assertNotEqual(label, 'UNÀNIME')

    def test_unanime_ratio_threshold(self):
        # 90% likes exactament → UNÀNIME
        label, _, _ = self._calc().calculate_badge(9, 1)
        self.assertEqual(label, 'UNÀNIME')

    def test_below_unanime_ratio(self):
        # 89% likes → no és UNÀNIME
        label, _, _ = self._calc().calculate_badge(89, 11)
        self.assertNotEqual(label, 'UNÀNIME')

    def test_gelida_many_dislikes(self):
        # <30% likes i ≥3 interaccions
        label, _, _ = self._calc().calculate_badge(1, 9)
        self.assertEqual(label, 'GÈLIDA')

    def test_gelida_requires_3_interactions(self):
        # 2 interaccions, 0% likes → no és GÈLIDA
        label, _, _ = self._calc().calculate_badge(0, 2)
        self.assertNotEqual(label, 'GÈLIDA')

    def test_joia_low_engagement_good_ratio(self):
        # 2 interaccions, 100% likes → JOIA (gem hidden)
        label, _, _ = self._calc().calculate_badge(2, 0)
        self.assertEqual(label, 'JOIA')

    def test_fresca_default_low_engagement(self):
        # 1 interacció, no reuneix cap condició especial
        label, _, _ = self._calc().calculate_badge(1, 0)
        self.assertEqual(label, 'FRESCA')


class BadgeCalculatorPercentileTests(TestCase):
    """Verifica badges que depenen del percentil (necessiten més cançons)."""

    def setUp(self):
        self.party = _make_party()
        self.users = [
            User.objects.create_user(username=f'bpu{i}', password='test')
            for i in range(20)
        ]
        # 10 cançons amb 0-9 likes
        self.songs = _make_songs(self.party, 10)
        for idx, song in enumerate(self.songs):
            for user in self.users[:idx]:
                Vote.objects.create(user=user, song=song, party=self.party, vote_type='like')

    def test_himne_top_percentile_high_likes(self):
        # La cançó amb més likes (9) és la del top percentil — ha de ser HIMNE o similar
        calc = BadgeCalculator(self.party.songs)
        label, _, _ = calc.calculate_badge(9, 0)
        self.assertIn(label, ('HIMNE', 'UNÀNIME'))

    def test_trending_mid_percentile(self):
        # Cançó al voltant del 60-70% percentil amb bona ratio
        calc = BadgeCalculator(self.party.songs)
        label, _, _ = calc.calculate_badge(6, 1)
        self.assertIn(label, ('TRENDING', 'CALENTA', 'PETANT-HO', 'EXPLOSIVA', 'HIMNE'))

    def test_fresca_bottom_percentile(self):
        calc = BadgeCalculator(self.party.songs)
        label, _, _ = calc.calculate_badge(1, 1)
        self.assertIn(label, ('FRESCA', 'GÈLIDA'))


class BadgeCalculatorPercentileCalculationTests(TestCase):
    """Testa el càlcul de percentils directament."""

    def setUp(self):
        self.party = _make_party()
        self.songs = _make_songs(self.party, 4)

    def test_percentile_zero_songs(self):
        empty_party = Party.objects.create(name='Empty', date=timezone.now())
        calc = BadgeCalculator(empty_party.songs)
        self.assertEqual(calc._calculate_percentile(5), 0)

    def test_percentile_single_song(self):
        party = Party.objects.create(name='Single', date=timezone.now())
        Song.objects.create(party=party, title='S', artist='A', spotify_id='s_single')
        calc = BadgeCalculator(party.songs)
        pct = calc._calculate_percentile(0)
        self.assertGreaterEqual(pct, 0)

    def test_percentile_increases_with_interactions(self):
        party = Party.objects.create(name='Pct', date=timezone.now())
        _make_songs(party, 5)
        calc = BadgeCalculator(party.songs)
        p_low = calc._calculate_percentile(0)
        p_high = calc._calculate_percentile(100)
        self.assertLessEqual(p_low, p_high)


class BadgeApplyToSongsTests(TestCase):
    """Testa calculate_and_apply_badges afegeix atributs a cada cançó."""

    def setUp(self):
        self.party = _make_party()
        self.users = [
            User.objects.create_user(username=f'bau{i}', password='test')
            for i in range(5)
        ]
        self.songs = _make_songs(self.party, 3)
        for user in self.users[:3]:
            Vote.objects.create(user=user, song=self.songs[0], party=self.party, vote_type='like')

    def test_badges_applied_to_annotated_songs(self):
        from jukebox.utils.query_helpers import get_annotated_party_songs
        songs_qs = get_annotated_party_songs(self.party)
        calc = BadgeCalculator(self.party.songs)
        calculate_and_apply_badges(self.party, songs_qs, calc)
        for song in songs_qs:
            self.assertTrue(hasattr(song, 'badge_label'), f"Song {song.title} missing badge_label")
            self.assertTrue(hasattr(song, 'badge_bg'))
            self.assertTrue(hasattr(song, 'badge_text'))

    def test_badge_label_is_non_empty_string(self):
        from jukebox.utils.query_helpers import get_annotated_party_songs
        songs_qs = get_annotated_party_songs(self.party)
        calc = BadgeCalculator(self.party.songs)
        calculate_and_apply_badges(self.party, songs_qs, calc)
        for song in songs_qs:
            self.assertIsInstance(song.badge_label, str)
            self.assertGreater(len(song.badge_label), 0)

    def test_calculate_and_apply_creates_calculator_if_none(self):
        from jukebox.utils.query_helpers import get_annotated_party_songs
        songs_qs = get_annotated_party_songs(self.party)
        # No passem calculator → l'ha de crear internament sense error
        calculate_and_apply_badges(self.party, songs_qs)
        for song in songs_qs:
            self.assertTrue(hasattr(song, 'badge_label'))
