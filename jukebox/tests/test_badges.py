"""
Tests per BadgeCalculator — lògica de badges per cançons basada en percentils.

Cobreix tots els tipus de badge:
INTACTA, UNÀNIME, HIMNE, DIVISIVA, PETANT-HO, EXPLOSIVA,
TRENDING, CALENTA, JOIA, GÈLIDA, FRESCA

Estratègia:
- _classify_badge testa la lògica pura de classificació (sense BD)
- calculate_badge i apply testen la integració amb DB
"""
from django.test import TestCase, SimpleTestCase
from django.utils import timezone

from jukebox.models import Party, Song, Vote
from jukebox.utils.badges import BadgeCalculator, calculate_and_apply_badges
from django.contrib.auth import get_user_model

User = get_user_model()


def _make_party(name='Badge Party'):
    return Party.objects.create(name=name, date=timezone.now())


def _make_songs(party, n, prefix='bid'):
    return [
        Song.objects.create(party=party, title=f'Song {i}', artist='A', spotify_id=f'{prefix}{i}')
        for i in range(n)
    ]


class BadgeClassifyDirectTests(SimpleTestCase):
    """
    Tests directes sobre _classify_badge sense cap dependència de BD.
    Controla percentil i like_ratio manualment.
    """

    def _calc_empty(self):
        """Retorna un BadgeCalculator sense dades reals (usem _classify_badge directament)."""
        calc = BadgeCalculator.__new__(BadgeCalculator)
        calc.vote_counts = []
        calc.sorted_counts = []
        calc.total_ranked_songs = 0
        return calc

    def test_intacta_zero_interactions(self):
        calc = self._calc_empty()
        label, _, _ = calc._classify_badge(0, 50, 50)
        # 0 total → retorna INTACTA via calculate_badge (no _classify_badge)
        # Testem via calculate_badge
        label, _, _ = calc.calculate_badge(0, 0)
        self.assertEqual(label, 'INTACTA')

    def test_unanime_high_likes(self):
        calc = self._calc_empty()
        label, _, _ = calc._classify_badge(10, 90, 95)
        self.assertEqual(label, 'UNÀNIME')

    def test_unanime_exactly_90_percent(self):
        calc = self._calc_empty()
        label, _, _ = calc._classify_badge(10, 90.0, 50)
        self.assertEqual(label, 'UNÀNIME')

    def test_himne_top_percentile_good_ratio(self):
        calc = self._calc_empty()
        # 87% likes: suficient per HIMNE (>=85%) però per sota el llindar UNÀNIME (90%)
        label, _, _ = calc._classify_badge(15, 87, 92)
        self.assertEqual(label, 'HIMNE')

    def test_divisiva_high_engagement_controversial(self):
        calc = self._calc_empty()
        # top 30% (percentile >= 70), 50% likes
        label, _, _ = calc._classify_badge(20, 50, 75)
        self.assertEqual(label, 'DIVISIVA')

    def test_petant_ho_high_engagement_good_ratio(self):
        calc = self._calc_empty()
        # top 30%, 80% likes
        label, _, _ = calc._classify_badge(20, 80, 80)
        self.assertEqual(label, 'PETANT-HO')

    def test_explosiva_high_engagement_other_ratio(self):
        calc = self._calc_empty()
        # top 30%, 65% likes (no divisiva ni petant-ho)
        label, _, _ = calc._classify_badge(20, 65, 75)
        self.assertEqual(label, 'EXPLOSIVA')

    def test_trending_mid_percentile_decent_ratio(self):
        calc = self._calc_empty()
        # percentile 60-70%, 70% likes
        label, _, _ = calc._classify_badge(10, 70, 65)
        self.assertEqual(label, 'TRENDING')

    def test_calenta_mid_percentile(self):
        calc = self._calc_empty()
        # percentile 40-60%, 55% likes
        label, _, _ = calc._classify_badge(5, 55, 50)
        self.assertEqual(label, 'CALENTA')

    def test_joia_low_engagement_good_ratio(self):
        calc = self._calc_empty()
        # percentile < 40, 2+ interactions, 85% likes
        label, _, _ = calc._classify_badge(4, 85, 20)
        self.assertEqual(label, 'JOIA')

    def test_joia_requires_2_interactions(self):
        calc = self._calc_empty()
        # 1 interacció no pot ser JOIA
        label, _, _ = calc._classify_badge(1, 100, 10)
        self.assertNotEqual(label, 'JOIA')

    def test_gelida_many_dislikes(self):
        calc = self._calc_empty()
        # percentile < 70, 3+ interactions, <30% likes
        label, _, _ = calc._classify_badge(10, 10, 50)
        self.assertEqual(label, 'GÈLIDA')

    def test_gelida_requires_3_interactions(self):
        calc = self._calc_empty()
        # 2 interaccions, no GÈLIDA
        label, _, _ = calc._classify_badge(2, 0, 5)
        self.assertNotEqual(label, 'GÈLIDA')

    def test_fresca_low_engagement_default(self):
        calc = self._calc_empty()
        # percentile < 40, 1 interacció
        label, _, _ = calc._classify_badge(1, 50, 10)
        self.assertEqual(label, 'FRESCA')

    def test_unanime_takes_priority_over_himne(self):
        calc = self._calc_empty()
        # 95% likes, top percentile → UNÀNIME, no HIMNE
        label, _, _ = calc._classify_badge(10, 95, 95)
        self.assertEqual(label, 'UNÀNIME')


class BadgeCalculatorIntegrationTests(TestCase):
    """Tests d'integració amb BD: percentil calculat a partir de vots reals."""

    def setUp(self):
        self.party = _make_party()
        self.bg_users = [
            User.objects.create_user(username=f'bgbadge{i}', password='test')
            for i in range(30)
        ]

    def _add_votes(self, song, n_likes=0, n_dislikes=0):
        users = iter(self.bg_users)
        for _ in range(n_likes):
            u = next(users)
            Vote.objects.create(user=u, song=song, party=self.party, vote_type='like')
        for _ in range(n_dislikes):
            u = next(users)
            Vote.objects.create(user=u, song=song, party=self.party, vote_type='dislike')

    def test_calculate_badge_intacta_no_votes(self):
        song = Song.objects.create(party=self.party, title='Intacta', artist='A', spotify_id='bi1')
        calc = BadgeCalculator(self.party.songs)
        label, _, _ = calc.calculate_badge(0, 0)
        self.assertEqual(label, 'INTACTA')

    def test_calculate_badge_unanime_all_likes(self):
        songs = _make_songs(self.party, 10, prefix='biu')
        # cançó 0 té 20 likes → top percentil, 100% likes
        self._add_votes(songs[0], n_likes=20)
        calc = BadgeCalculator(self.party.songs)
        label, _, _ = calc.calculate_badge(20, 0)
        self.assertEqual(label, 'UNÀNIME')

    def test_badge_colors_are_strings(self):
        calc = BadgeCalculator(self.party.songs)
        label, bg, text = calc.calculate_badge(0, 0)
        self.assertIsInstance(bg, str)
        self.assertIsInstance(text, str)
        self.assertTrue(bg.startswith('#'))
        self.assertTrue(text.startswith('#'))


class BadgeApplyToSongsTests(TestCase):
    """Testa que calculate_and_apply_badges afegeix atributs a cada cançó."""

    def setUp(self):
        self.party = _make_party('Apply Party')
        self.users = [
            User.objects.create_user(username=f'bau{i}', password='test')
            for i in range(5)
        ]
        self.songs = _make_songs(self.party, 3, prefix='bap')
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

    def test_skip_votes_count_as_negative_votes(self):
        from jukebox.utils.query_helpers import get_annotated_party_songs
        Vote.objects.create(
            user=self.users[3],
            song=self.songs[1],
            party=self.party,
            vote_type='skip',
        )

        song = get_annotated_party_songs(self.party).get(pk=self.songs[1].pk)

        self.assertEqual(song.num_dislikes, 1)

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
        calculate_and_apply_badges(self.party, songs_qs)
        for song in songs_qs:
            self.assertTrue(hasattr(song, 'badge_label'))

    def test_apply_badges_to_songs_method(self):
        from jukebox.utils.query_helpers import get_annotated_party_songs
        songs_qs = get_annotated_party_songs(self.party)
        calc = BadgeCalculator(self.party.songs)
        calc.apply_badges_to_songs(songs_qs)
        for song in songs_qs:
            self.assertTrue(hasattr(song, 'badge_label'))
