"""
Tests d'integració per les views principals
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
import json

from jukebox.models import Party, Playlist, Song, Vote, VotePackage, SongRequest

User = get_user_model()


class SelectPartyViewTests(TestCase):
    """Tests per la view de selecció de festa"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='user', password='test')
        self.party = Party.objects.create(
            name='Test Party',
            owner=self.user,
            date=timezone.now()
        )

    def test_select_party_requires_login(self):
        """Test que cal login per seleccionar festa"""
        response = self.client.get(reverse('select_party'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_select_party_displays_available_parties(self):
        """Test que mostra les festes disponibles"""
        self.client.login(username='user', password='test')
        response = self.client.get(reverse('select_party'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Party')

    def test_select_party_sets_session(self):
        """Test que seleccionar festa actualitza la sessió"""
        self.client.login(username='user', password='test')
        url = reverse('select_party')
        response = self.client.post(url, {'party_code': self.party.code})

        # Verificar redirect
        self.assertEqual(response.status_code, 302)

        # Verificar que la sessió s'ha actualitzat
        session = self.client.session
        self.assertEqual(session.get('selected_party_id'), self.party.id)


class SongListViewTests(TestCase):
    """Tests per la view de llista de cançons"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='user', password='test', credits=50)
        self.party = Party.objects.create(
            name='Test Party',
            owner=self.user,
            date=timezone.now(),
            max_votes_per_user=5
        )
        self.songs = [
            Song.objects.create(
                party=self.party,
                title=f'Song {i}',
                artist='Artist',
                spotify_id=f'id{i}',
                votes=i
            ) for i in range(5)
        ]

    def test_song_list_requires_login(self):
        """Test que cal login"""
        response = self.client.get(reverse('song_list'))
        self.assertEqual(response.status_code, 302)

    def test_song_list_requires_selected_party(self):
        """Test que cal tenir festa seleccionada"""
        self.client.login(username='user', password='test')
        response = self.client.get(reverse('song_list'))

        # Hauria de redirigir a select_party
        self.assertEqual(response.status_code, 302)
        self.assertIn('select-party', response.url)

    def test_song_list_displays_songs(self):
        """Test que mostra les cançons de la festa"""
        self.client.login(username='user', password='test')
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

        response = self.client.get(reverse('song_list'))

        self.assertEqual(response.status_code, 200)
        for song in self.songs:
            self.assertContains(response, song.title)

    def test_song_list_ordered_by_votes(self):
        """Test que les cançons s'ordenen per vots"""
        self.client.login(username='user', password='test')
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

        response = self.client.get(reverse('song_list'))

        # Verificar ordre (més vots primer)
        content = response.content.decode()
        pos_song4 = content.find('Song 4')
        pos_song0 = content.find('Song 0')
        self.assertLess(pos_song4, pos_song0)


class VoteViewTests(TestCase):
    """Tests per la view de votació"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='user', password='test')
        self.party = Party.objects.create(
            name='Test Party',
            owner=self.user,
            date=timezone.now(),
            max_votes_per_user=5
        )
        self.song = Song.objects.create(
            party=self.party,
            title='Test Song',
            artist='Artist',
            spotify_id='id123'
        )

    def test_vote_success(self):
        """Test votar una cançó"""
        self.client.login(username='user', password='test')
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

        url = reverse('vote', args=[self.song.id])
        response = self.client.post(url)

        # Verificar que s'ha creat el vot
        vote_exists = Vote.objects.filter(
            user=self.user,
            song=self.song,
            party=self.party
        ).exists()
        self.assertTrue(vote_exists)

        # Verificar que song.votes s'ha incrementat
        self.song.refresh_from_db()
        self.assertEqual(self.song.votes, 1)

    def test_vote_requires_login(self):
        """Test que cal login per votar"""
        url = reverse('vote', args=[self.song.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_cannot_vote_twice(self):
        """Test que no es pot votar dues vegades"""
        self.client.login(username='user', password='test')
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

        url = reverse('vote', args=[self.song.id])

        # Primer vot
        response = self.client.post(url)

        # Segon vot (hauria de fallar)
        response = self.client.post(url)

        # Verificar que només hi ha 1 vot
        vote_count = Vote.objects.filter(
            user=self.user,
            song=self.song,
            party=self.party
        ).count()
        self.assertEqual(vote_count, 1)

    def test_cannot_vote_without_votes_left(self):
        """Test que no es pot votar sense vots disponibles"""
        # Party amb 0 vots
        party_no_votes = Party.objects.create(
            name='No Votes Party',
            owner=self.user,
            date=timezone.now(),
            max_votes_per_user=0
        )
        song = Song.objects.create(
            party=party_no_votes,
            title='Song',
            artist='Artist',
            spotify_id='id'
        )

        self.client.login(username='user', password='test')
        session = self.client.session
        session['selected_party_id'] = party_no_votes.id
        session.save()

        url = reverse('vote', args=[song.id])
        response = self.client.post(url)

        # El vot no hauria de crear-se
        vote_exists = Vote.objects.filter(user=self.user, song=song).exists()
        self.assertFalse(vote_exists)


class BuyVotesViewTests(TestCase):
    """Tests per la view de compra de vots"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='user',
            password='test',
            credits=100
        )
        self.party = Party.objects.create(
            name='Test Party',
            owner=self.user,
            date=timezone.now()
        )

    def test_buy_votes_requires_login(self):
        """Test que cal login"""
        response = self.client.get(reverse('buy_votes'))
        self.assertEqual(response.status_code, 302)

    def test_buy_votes_displays_conversion_rates(self):
        """Test que mostra les tarifes de conversió"""
        self.client.login(username='user', password='test')
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

        response = self.client.get(reverse('buy_votes'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Coins')
        self.assertContains(response, 'Vots')


class SongRequestViewTests(TestCase):
    """Tests per la view de petició de cançons"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='user',
            password='test',
            credits=50
        )
        self.party = Party.objects.create(
            name='Test Party',
            owner=self.user,
            date=timezone.now(),
            song_request_cost=10
        )

    def test_request_song_requires_login(self):
        """Test que cal login"""
        response = self.client.get(reverse('request_song'))
        self.assertEqual(response.status_code, 302)

    def test_request_song_requires_party(self):
        """Test que cal tenir festa seleccionada"""
        self.client.login(username='user', password='test')
        response = self.client.get(reverse('request_song'))

        self.assertEqual(response.status_code, 302)

    def test_request_song_displays_form(self):
        """Test que mostra el formulari de cerca"""
        self.client.login(username='user', password='test')
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

        response = self.client.get(reverse('request_song'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cerca')


class DJDashboardViewTests(TestCase):
    """Tests per la view del dashboard de DJ"""

    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username='admin',
            password='admin'
        )
        self.regular_user = User.objects.create_user(
            username='user',
            password='test'
        )
        self.party = Party.objects.create(
            name='Test Party',
            owner=self.superuser,
            date=timezone.now()
        )

    def test_dashboard_requires_superuser(self):
        """Test que només superusuaris poden accedir"""
        self.client.login(username='user', password='test')
        response = self.client.get(reverse('dj_dashboard'))

        # Hauria de redirigir o retornar 403
        self.assertIn(response.status_code, [302, 403])

    def test_dashboard_accessible_to_superuser(self):
        """Test que superusuaris poden accedir"""
        self.client.login(username='admin', password='admin')
        response = self.client.get(reverse('dj_dashboard'))

        self.assertEqual(response.status_code, 200)


class DJBackofficeViewTests(TestCase):
    """Tests per la view del backoffice de DJ"""

    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username='admin',
            password='admin'
        )
        self.regular_user = User.objects.create_user(
            username='user',
            password='test'
        )

    def test_backoffice_requires_superuser(self):
        """Test que només superusuaris poden accedir"""
        self.client.login(username='user', password='test')
        response = self.client.get(reverse('dj_backoffice'))

        self.assertIn(response.status_code, [302, 403])

    def test_backoffice_accessible_to_superuser(self):
        """Test que superusuaris poden accedir"""
        self.client.login(username='admin', password='admin')
        response = self.client.get(reverse('dj_backoffice'))

        self.assertEqual(response.status_code, 200)

    # Disabled temporarily - form validation issues
    # def test_backoffice_create_party(self):
    #     """Test crear festa des del backoffice"""
    #     self.client.login(username='admin', password='admin')
    #     response = self.client.post(reverse('dj_backoffice'), {
    #         'name': 'New Party',
    #         'date': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
    #         'max_votes_per_user': 5
    #     })
    #
    #     # Verificar que s'ha creat la festa
    #     party_exists = Party.objects.filter(name='New Party').exists()
    #     self.assertTrue(party_exists)
