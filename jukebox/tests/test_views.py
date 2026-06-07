"""
Tests d'integració per les views principals
"""
from unittest.mock import patch

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
import json

from jukebox.models import Party, Playlist, Song, Vote, VotePackage, SongRequest, Notification
from jukebox.views import is_dj_admin

User = get_user_model()


class SelectPartyViewTests(TestCase):
    """Tests per la view de selecció de festa"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='user', password='test')
        self.party = Party.objects.create(
            name='Test Party',
            date=timezone.now()
        )

    def test_select_party_accessible_anonymously(self):
        """Test que select_party és accessible sense login (pàgina pública)"""
        response = self.client.get(reverse('select_party'))
        self.assertEqual(response.status_code, 200)

    def test_select_party_displays_available_parties(self):
        """Test que mostra les festes disponibles"""
        self.client.login(username='user', password='test')
        response = self.client.get(reverse('select_party'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Party')

    def test_set_party_sets_session(self):
        """Test que set_party actualitza la sessió"""
        self.client.login(username='user', password='test')
        response = self.client.get(reverse('set_party', args=[self.party.id]))

        # Verificar redirect cap a main
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
            date=timezone.now(),
            max_votes_per_user=5,
            party_status=Party.STATUS_DJJUKEBOX_ACTIVE,
        )
        self.songs = [
            Song.objects.create(
                party=self.party,
                title=f'Song {i}',
                artist='Artist',
                spotify_id=f'id{i}',
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
        """Test que les cançons s'ordenen per vots (likes reals)"""
        self.client.login(username='user', password='test')
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

        # Crear un usuari addicional per poder votar song[4]
        voter = User.objects.create_user(username='voter', password='test')
        Vote.objects.create(user=voter, song=self.songs[4], party=self.party, vote_type='like')

        response = self.client.get(reverse('song_list'))

        # Song 4 té 1 like real, song 0 en té 0 → Song 4 ha d'aparèixer primer
        content = response.content.decode()
        pos_song4 = content.find('Song 4')
        pos_song0 = content.find('Song 0')
        self.assertGreater(pos_song4, 0, "Song 4 not found in page")
        self.assertGreater(pos_song0, 0, "Song 0 not found in page")
        self.assertLess(pos_song4, pos_song0)

    def test_song_list_can_remove_existing_vote_and_restore_vote_left(self):
        """Test que es pot desfer un vot des de /songs/ i es recupera el vot disponible"""
        self.client.login(username='user', password='test')
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

        song = self.songs[0]
        Vote.objects.create(user=self.user, song=song, party=self.party, vote_type='like')

        response = self.client.post(reverse('song_list'), {'unvote_song_id': song.id})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Vote.objects.filter(user=self.user, song=song, party=self.party).exists())

        response = self.client.get(reverse('song_list'))
        self.assertEqual(response.context['votes_left'], 5)

    def test_song_list_can_remove_dislike_vote(self):
        """Test que es pot desfer un vot negatiu des de /songs/"""
        self.client.login(username='user', password='test')
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

        song = self.songs[1]
        Vote.objects.create(user=self.user, song=song, party=self.party, vote_type='dislike')

        response = self.client.post(reverse('song_list'), {'unvote_song_id': song.id})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Vote.objects.filter(user=self.user, song=song, party=self.party).exists())


class AnalyzeSongAudioViewTests(TestCase):
    """Tests per l'anàlisi manual de BPM/Key."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser(username='admin', password='test')
        self.party = Party.objects.create(
            name='Test Party',
            date=timezone.now(),
        )
        self.song = Song.objects.create(
            party=self.party,
            title='Unknown Song',
            artist='Unknown Artist',
            spotify_id='spotify123',
        )

    @patch('jukebox.views.analyze_song_from_temporary_mp3', return_value=None)
    @patch('jukebox.views.analyze_from_preview_url', return_value=None)
    @patch('jukebox.views._get_acousticbrainz_features', return_value=None)
    @patch('jukebox.views._get_songbpm_features', return_value={'bpm': None, 'key': None, 'source_url': None})
    def test_analyze_song_without_metadata_is_not_server_error(self, mock_songbpm, mock_ab, mock_preview, mock_ytdlp):
        self.client.login(username='admin', password='test')

        response = self.client.post(reverse('analyze_song_audio', args=[self.party.id, self.song.id]))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['reason'], 'no_audio_metadata')


class VoteViewTests(TestCase):
    """Tests per la funcionalitat de votació via POST a song_list"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='user', password='test')
        self.party = Party.objects.create(
            name='Test Party',
            date=timezone.now(),
            max_votes_per_user=5,
            party_status=Party.STATUS_DJJUKEBOX_ACTIVE,
        )
        self.song = Song.objects.create(
            party=self.party,
            title='Test Song',
            artist='Artist',
            spotify_id='id123'
        )

    def test_vote_success(self):
        """Test votar una cançó via POST a song_list"""
        self.client.login(username='user', password='test')
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

        response = self.client.post(
            reverse('song_list'),
            {'vote_song_id': self.song.id, 'vote_type': 'like'}
        )

        self.assertEqual(response.status_code, 302)
        vote_exists = Vote.objects.filter(
            user=self.user,
            song=self.song,
            party=self.party
        ).exists()
        self.assertTrue(vote_exists)

    def test_vote_requires_login(self):
        """Test que cal login per accedir a song_list (i votar)"""
        response = self.client.post(
            reverse('song_list'),
            {'vote_song_id': self.song.id}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_cannot_vote_twice(self):
        """Test que votar dues vegades no crea dos vots"""
        self.client.login(username='user', password='test')
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

        url = reverse('song_list')
        self.client.post(url, {'vote_song_id': self.song.id, 'vote_type': 'like'})
        self.client.post(url, {'vote_song_id': self.song.id, 'vote_type': 'like'})

        vote_count = Vote.objects.filter(
            user=self.user,
            song=self.song,
            party=self.party
        ).count()
        self.assertEqual(vote_count, 1)

    def test_cannot_vote_without_votes_left(self):
        """Test que no es pot votar sense vots disponibles"""
        party_no_votes = Party.objects.create(
            name='No Votes Party',
            date=timezone.now(),
            max_votes_per_user=0,
            party_status=Party.STATUS_DJJUKEBOX_ACTIVE,
        )
        song = Song.objects.create(
            party=party_no_votes,
            title='Song',
            artist='Artist',
            spotify_id='id_no_votes'
        )

        self.client.login(username='user', password='test')
        session = self.client.session
        session['selected_party_id'] = party_no_votes.id
        session.save()

        self.client.post(
            reverse('song_list'),
            {'vote_song_id': song.id, 'vote_type': 'like'}
        )

        vote_exists = Vote.objects.filter(user=self.user, song=song).exists()
        self.assertFalse(vote_exists)

    def test_vote_not_counted_when_voting_disabled(self):
        """Test que no es pot votar si la festa no té voting_enabled"""
        party_hidden = Party.objects.create(
            name='Hidden Party',
            date=timezone.now(),
            max_votes_per_user=5,
            party_status=Party.STATUS_HIDDEN,
        )
        song = Song.objects.create(
            party=party_hidden,
            title='Hidden Song',
            artist='Artist',
            spotify_id='id_hidden'
        )

        self.client.login(username='user', password='test')
        session = self.client.session
        session['selected_party_id'] = party_hidden.id
        session.save()

        self.client.post(
            reverse('song_list'),
            {'vote_song_id': song.id, 'vote_type': 'like'}
        )

        self.assertFalse(Vote.objects.filter(user=self.user, song=song).exists())


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
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()
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


class DJManagementAccessTests(TestCase):
    """Tests d'accés per les rutes de gestió DJ"""

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
            name='Managed Party',
            date=timezone.now()
        )
        self.song = Song.objects.create(
            party=self.party,
            title='Managed Song',
            artist='Artist',
            spotify_id='managed-song'
        )

    def test_party_settings_requires_superuser(self):
        self.client.login(username='user', password='test')

        response = self.client.get(reverse('party_settings', args=[self.party.id]))

        self.assertIn(response.status_code, [302, 403])

    def test_party_settings_accessible_to_superuser(self):
        self.client.login(username='admin', password='admin')
        playlist = Playlist.objects.create(
            spotify_id='playlist-1',
            name='Playlist test',
            owner='admin'
        )
        self.party.playlist = playlist
        self.party.save(update_fields=['playlist'])

        response = self.client.get(reverse('party_settings', args=[self.party.id]))

        self.assertEqual(response.status_code, 200)

    def test_manage_song_requests_requires_superuser(self):
        self.client.login(username='user', password='test')
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

        response = self.client.get(reverse('manage_song_requests'))

        self.assertIn(response.status_code, [302, 403])

    def test_mark_song_played_requires_superuser(self):
        self.client.login(username='user', password='test')

        response = self.client.post(reverse('mark_song_played', args=[self.song.id]))

        self.assertIn(response.status_code, [302, 403])
        self.song.refresh_from_db()
        self.assertFalse(self.song.has_played)

    def test_mark_song_played_allows_superuser(self):
        self.client.login(username='admin', password='admin')
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

        response = self.client.post(reverse('mark_song_played', args=[self.song.id]))

        self.assertEqual(response.status_code, 302)
        self.song.refresh_from_db()
        self.assertTrue(self.song.has_played)
        self.assertIsNotNone(self.song.played_at)


class SetPartyViewTests(TestCase):
    """Tests per la view set_party (codi, ubicació, session)"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='user', password='test')
        self.owner = User.objects.create_user(username='owner', password='test')
        self.party = Party.objects.create(
            name='Test Party',
            date=timezone.now(),
        )

    def test_set_party_no_code_required_sets_session(self):
        """Festa sense codi: set_party estableix la sessió i redirigeix"""
        self.client.login(username='user', password='test')
        response = self.client.get(reverse('set_party', args=[self.party.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get('selected_party_id'), self.party.id)

    def test_set_party_anonymous_can_join(self):
        """Usuaris anònims poden unir-se a festes sense codi"""
        response = self.client.get(reverse('set_party', args=[self.party.id]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get('selected_party_id'), self.party.id)

    def test_set_party_requires_code_when_enabled(self):
        """Festa amb require_join_code: sense codi no es pot entrar"""
        self.party.require_join_code = True
        self.party.save()

        self.client.login(username='user', password='test')
        response = self.client.get(reverse('set_party', args=[self.party.id]))

        self.assertEqual(response.status_code, 302)
        self.assertIn('select-party', response.url)
        self.assertIsNone(self.client.session.get('selected_party_id'))

    def test_set_party_accepts_correct_code(self):
        """Festa amb codi: codi correcte permet entrar"""
        self.party.require_join_code = True
        self.party.save()

        self.client.login(username='user', password='test')
        response = self.client.get(
            reverse('set_party', args=[self.party.id]),
            data={'code': self.party.code}
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get('selected_party_id'), self.party.id)

    def test_set_party_rejects_wrong_code(self):
        """Festa amb codi: codi incorrecte bloqueja l'entrada"""
        self.party.require_join_code = True
        self.party.save()

        self.client.login(username='user', password='test')
        response = self.client.get(
            reverse('set_party', args=[self.party.id]),
            data={'code': 'WRONG99'}
        )

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.client.session.get('selected_party_id'))

    def test_set_party_dj_exempt_from_location_check(self):
        """DJ de la festa pot entrar sense coords quan hi ha restricció de radi"""
        from decimal import Decimal
        self.party.latitude = Decimal('41.3851')
        self.party.longitude = Decimal('2.1734')
        self.party.location_radius_km = 1
        self.party.save()

        dj_user = User.objects.create_user(username='dj', password='test')
        self.party.djs.add(dj_user)

        self.client.login(username='dj', password='test')
        response = self.client.get(reverse('set_party', args=[self.party.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get('selected_party_id'), self.party.id)

    def test_set_party_anonymous_blocked_by_location(self):
        """Usuari anònim sense coords és bloquejat per restricció de radi"""
        from decimal import Decimal
        self.party.latitude = Decimal('41.3851')
        self.party.longitude = Decimal('2.1734')
        self.party.location_radius_km = 1
        self.party.save()

        response = self.client.get(reverse('set_party', args=[self.party.id]))

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.client.session.get('selected_party_id'))


class DJPermissionTests(TestCase):
    """Tests per les permissions de DJ (no superusuari)"""

    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(username='admin', password='admin')
        self.dj_user = User.objects.create_user(username='dj', password='test')
        self.other_user = User.objects.create_user(username='other', password='test')

        self.party = Party.objects.create(
            name='DJ Party',
            date=timezone.now(),
            party_status=Party.STATUS_DJJUKEBOX_ACTIVE,
        )
        self.party.djs.add(self.dj_user)

        self.other_party = Party.objects.create(
            name='Other Party',
            date=timezone.now(),
        )

    def _set_session_party(self, party):
        session = self.client.session
        session['selected_party_id'] = party.id
        session.save()

    def test_dashboard_accessible_to_party_dj(self):
        """DJ de la festa pot accedir al dashboard"""
        self.client.login(username='dj', password='test')
        self._set_session_party(self.party)

        response = self.client.get(reverse('dj_dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_manage_requests_accessible_to_party_dj(self):
        """DJ de la festa pot accedir a gestió de peticions"""
        self.client.login(username='dj', password='test')
        self._set_session_party(self.party)

        response = self.client.get(reverse('manage_song_requests'))
        self.assertEqual(response.status_code, 200)

    def test_party_settings_blocked_to_party_dj(self):
        """DJ de la festa NO pot accedir a la configuració (només superuser)"""
        self.client.login(username='dj', password='test')

        response = self.client.get(reverse('party_settings', args=[self.party.id]))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_blocks_dj_of_other_party(self):
        """DJ d'una altra festa no pot accedir al dashboard d'aquesta"""
        self.other_party.djs.add(self.dj_user)
        self.client.login(username='dj', password='test')
        self._set_session_party(self.party)
        # Treure dj_user de la party principal
        self.party.djs.remove(self.dj_user)

        response = self.client.get(reverse('dj_dashboard'))
        # Hauria de redirigir a song_list
        self.assertEqual(response.status_code, 302)

    def test_regular_user_cannot_access_dashboard(self):
        """Usuari sense DJ role no pot accedir al dashboard"""
        self.client.login(username='other', password='test')
        self._set_session_party(self.party)

        response = self.client.get(reverse('dj_dashboard'))
        self.assertIn(response.status_code, [302, 403])

    def test_party_dj_cannot_access_backoffice(self):
        """DJ de la festa no pot accedir al backoffice (superuser only)"""
        self.client.login(username='dj', password='test')
        response = self.client.get(reverse('dj_backoffice'))
        self.assertIn(response.status_code, [302, 403])


class IsDjAdminTests(TestCase):
    """Tests per la funció is_dj_admin"""

    def setUp(self):
        self.superuser = User.objects.create_superuser(username='admin', password='admin')
        self.dj_user = User.objects.create_user(username='dj', password='test')
        self.regular_user = User.objects.create_user(username='user', password='test')
        self.party = Party.objects.create(
            name='Party',
            date=timezone.now(),
        )
        self.party.djs.add(self.dj_user)

    def test_superuser_is_dj_admin(self):
        self.assertTrue(is_dj_admin(self.superuser))

    def test_dj_of_party_is_dj_admin(self):
        self.assertTrue(is_dj_admin(self.dj_user))

    def test_regular_user_is_not_dj_admin(self):
        self.assertFalse(is_dj_admin(self.regular_user))

    def test_anonymous_is_not_dj_admin(self):
        from django.contrib.auth.models import AnonymousUser
        anon = AnonymousUser()
        self.assertFalse(is_dj_admin(anon))


class UpdatePartyStatusTests(TestCase):
    """Tests per la view update_party_status"""

    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(username='admin', password='admin')
        self.dj_user = User.objects.create_user(username='dj', password='test')
        self.regular_user = User.objects.create_user(username='user', password='test')

        self.party = Party.objects.create(
            name='Status Party',
            date=timezone.now(),
            party_status=Party.STATUS_HIDDEN,
        )
        self.party.djs.add(self.dj_user)

    def _set_session(self, party):
        session = self.client.session
        session['selected_party_id'] = party.id
        session.save()

    def test_superuser_can_update_status(self):
        self.client.login(username='admin', password='admin')
        self._set_session(self.party)

        self.client.post(
            reverse('update_party_status', args=[self.party.id]),
            {'party_status': Party.STATUS_SHOW_PARTY}
        )

        self.party.refresh_from_db()
        self.assertEqual(self.party.party_status, Party.STATUS_SHOW_PARTY)

    def test_party_dj_can_update_status(self):
        self.client.login(username='dj', password='test')
        self._set_session(self.party)

        self.client.post(
            reverse('update_party_status', args=[self.party.id]),
            {'party_status': Party.STATUS_REQUESTS_OPEN}
        )

        self.party.refresh_from_db()
        self.assertEqual(self.party.party_status, Party.STATUS_REQUESTS_OPEN)

    def test_non_dj_cannot_update_status(self):
        self.client.login(username='user', password='test')
        self._set_session(self.party)

        self.client.post(
            reverse('update_party_status', args=[self.party.id]),
            {'party_status': Party.STATUS_SHOW_PARTY}
        )

        self.party.refresh_from_db()
        self.assertEqual(self.party.party_status, Party.STATUS_HIDDEN)

    def test_invalid_status_keeps_current(self):
        self.client.login(username='admin', password='admin')
        self._set_session(self.party)

        self.client.post(
            reverse('update_party_status', args=[self.party.id]),
            {'party_status': 'invalid_status_value'}
        )

        self.party.refresh_from_db()
        self.assertEqual(self.party.party_status, Party.STATUS_HIDDEN)


class ManageSongRequestsTests(TestCase):
    """Tests per la view manage_song_requests (acceptar/rebutjar)"""

    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(username='admin', password='admin')
        self.requester = User.objects.create_user(username='requester', password='test', credits=20)

        self.party = Party.objects.create(
            name='Request Party',
            date=timezone.now(),
            song_request_cost=10,
        )
        self.song_request = SongRequest.objects.create(
            user=self.requester,
            party=self.party,
            spotify_id='req_track_1',
            title='Requested Song',
            artist='Artist',
            status='pending',
            coins_cost=10,
        )

    def _set_session(self):
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

    def test_accept_charges_user_coins(self):
        """Acceptar una petició cobra les coins a l'usuari"""
        self.client.login(username='admin', password='admin')
        self._set_session()

        response = self.client.post(
            reverse('manage_song_requests'),
            {'request_id': self.song_request.id, 'action': 'accept'}
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])

        self.requester.refresh_from_db()
        self.assertEqual(self.requester.credits, 10)

        self.song_request.refresh_from_db()
        self.assertEqual(self.song_request.status, 'accepted')

        self.assertTrue(Song.objects.filter(
            party=self.party,
            spotify_id='req_track_1'
        ).exists())

    def test_reject_does_not_charge(self):
        """Rebutjar una petició no cobra les coins"""
        self.client.login(username='admin', password='admin')
        self._set_session()

        self.client.post(
            reverse('manage_song_requests'),
            {'request_id': self.song_request.id, 'action': 'reject'}
        )

        self.requester.refresh_from_db()
        self.assertEqual(self.requester.credits, 20)

        self.song_request.refresh_from_db()
        self.assertEqual(self.song_request.status, 'rejected')

        self.assertFalse(Song.objects.filter(
            party=self.party,
            spotify_id='req_track_1'
        ).exists())

    def test_accept_without_charge_when_insufficient_credits(self):
        """Acceptar sense cobrar quan l'usuari no té prous coins"""
        self.requester.credits = 0
        self.requester.save()

        self.client.login(username='admin', password='admin')
        self._set_session()

        response = self.client.post(
            reverse('manage_song_requests'),
            {'request_id': self.song_request.id, 'action': 'accept', 'allow_without_charge': '1'}
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])

        self.requester.refresh_from_db()
        self.assertEqual(self.requester.credits, 0)

        self.assertTrue(Song.objects.filter(party=self.party, spotify_id='req_track_1').exists())


class RequestSongViewTests(TestCase):
    """Tests per la view request_song (cerca i peticions)"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='user', password='test', credits=50)
        self.party = Party.objects.create(
            name='Test Party',
            date=timezone.now(),
            song_request_cost=10,
            allow_song_requests=True,
        )

    def _set_session(self):
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

    def test_post_creates_song_request(self):
        """POST crea SongRequest pendent"""
        self.client.login(username='user', password='test')
        self._set_session()

        response = self.client.post(
            reverse('request_song'),
            {
                'spotify_id': 'newtrack123',
                'title': 'New Song',
                'artist': 'Artist',
                'album_image_url': '',
            }
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])

        self.assertTrue(SongRequest.objects.filter(
            user=self.user,
            party=self.party,
            spotify_id='newtrack123',
            status='pending'
        ).exists())

    def test_post_blocked_if_song_already_in_party(self):
        """No es pot demanar una cançó que ja és a la llista"""
        Song.objects.create(
            party=self.party,
            title='Existing',
            artist='Artist',
            spotify_id='existing123'
        )

        self.client.login(username='user', password='test')
        self._set_session()

        response = self.client.post(
            reverse('request_song'),
            {'spotify_id': 'existing123', 'title': 'Existing', 'artist': 'Artist'},
            content_type='application/x-www-form-urlencoded'
        )

        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertEqual(response.status_code, 400)

    def test_post_blocked_if_pending_request_exists(self):
        """No es pot demanar el mateix track dues vegades (pendent)"""
        SongRequest.objects.create(
            user=self.user,
            party=self.party,
            spotify_id='dup123',
            title='Dup',
            artist='Artist',
            status='pending',
            coins_cost=10,
        )

        self.client.login(username='user', password='test')
        self._set_session()

        response = self.client.post(
            reverse('request_song'),
            {'spotify_id': 'dup123', 'title': 'Dup', 'artist': 'Artist'},
            content_type='application/x-www-form-urlencoded'
        )

        data = json.loads(response.content)
        self.assertFalse(data['success'])

    @patch('jukebox.views.search_spotify_tracks_public', return_value=[
        {'id': 'abc', 'title': 'Mocked Song', 'artist': 'Mocked Artist', 'album_image_url': None}
    ])
    def test_search_returns_json(self, mock_search):
        """GET amb ?search retorna JSON de tracks"""
        self.client.login(username='user', password='test')
        self._set_session()

        response = self.client.get(reverse('request_song'), {'search': 'test query'})

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('tracks', data)
        self.assertEqual(len(data['tracks']), 1)
        self.assertEqual(data['tracks'][0]['title'], 'Mocked Song')

    def test_requests_blocked_if_not_allow_song_requests(self):
        """Redirigeix a song_list si les peticions estan desactivades"""
        self.party.allow_song_requests = False
        self.party.save()

        self.client.login(username='user', password='test')
        self._set_session()

        response = self.client.get(reverse('request_song'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('songs', response.url)


class ToggleViewTests(TestCase):
    """Tests per les vistes toggle (allow_requests, auto_sync, auto_analyze)"""

    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(username='admin', password='admin')
        self.party = Party.objects.create(
            name='Toggle Party',
            date=timezone.now(),
            allow_song_requests=True,
            auto_sync_playlist=False,
            auto_analyze_audio=False,
        )

    def test_toggle_allow_requests(self):
        self.client.login(username='admin', password='admin')

        response = self.client.post(reverse('toggle_allow_requests', args=[self.party.id]))

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertFalse(data['allow_song_requests'])
        self.party.refresh_from_db()
        self.assertFalse(self.party.allow_song_requests)

    def test_toggle_allow_requests_twice_restores(self):
        self.client.login(username='admin', password='admin')
        url = reverse('toggle_allow_requests', args=[self.party.id])
        self.client.post(url)
        self.client.post(url)

        self.party.refresh_from_db()
        self.assertTrue(self.party.allow_song_requests)

    def test_toggle_auto_sync(self):
        self.client.login(username='admin', password='admin')

        response = self.client.post(reverse('toggle_auto_sync', args=[self.party.id]))

        self.assertEqual(response.status_code, 200)
        self.party.refresh_from_db()
        self.assertTrue(self.party.auto_sync_playlist)

    def test_toggle_auto_analyze(self):
        self.client.login(username='admin', password='admin')

        response = self.client.post(reverse('toggle_auto_analyze', args=[self.party.id]))

        self.assertEqual(response.status_code, 200)
        self.party.refresh_from_db()
        self.assertTrue(self.party.auto_analyze_audio)

    def test_toggle_auto_analyze_counts_songs_missing_key(self):
        Song.objects.create(
            party=self.party,
            title='Missing Key',
            artist='Artist',
            spotify_id='missing-key',
            bpm=128,
            key=None,
        )
        self.client.login(username='admin', password='admin')

        response = self.client.post(reverse('toggle_auto_analyze', args=[self.party.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['pending_songs'], 1)

    @patch('jukebox.views.get_audio_features_for_songs')
    def test_process_song_features_includes_songs_missing_key(self, mock_features):
        Song.objects.create(
            party=self.party,
            title='Missing Key',
            artist='Artist',
            spotify_id='missing-key',
            bpm=128,
            key=None,
        )
        mock_features.return_value = {'missing-key': {'bpm': 128, 'key': '8A'}}
        self.client.login(username='admin', password='admin')

        response = self.client.post(reverse('process_song_features', args=[self.party.id]), {
            'chunk_size': 10,
            'offset': 0,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['processed'], 1)
        mock_features.assert_called_once()


class SavePartyLocationTests(TestCase):
    """Tests per la view save_party_location"""

    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(username='admin', password='admin')
        self.party = Party.objects.create(
            name='Location Party',
            date=timezone.now(),
        )

    def test_save_location_success(self):
        self.client.login(username='admin', password='admin')

        response = self.client.post(
            reverse('save_party_location', args=[self.party.id]),
            {
                'latitude': '41.3851',
                'longitude': '2.1734',
                'location_name': 'Barcelona',
                'location_radius_km': '5',
            }
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])

        self.party.refresh_from_db()
        self.assertAlmostEqual(float(self.party.latitude), 41.3851, places=3)
        self.assertAlmostEqual(float(self.party.longitude), 2.1734, places=3)
        self.assertEqual(self.party.location_name, 'Barcelona')
        self.assertEqual(self.party.location_radius_km, 5)

    def test_save_location_clears_on_empty(self):
        """Enviar lat/lng buits esborra la localització"""
        from decimal import Decimal
        self.party.latitude = Decimal('41.3851')
        self.party.longitude = Decimal('2.1734')
        self.party.save()

        self.client.login(username='admin', password='admin')

        response = self.client.post(
            reverse('save_party_location', args=[self.party.id]),
            {'latitude': '', 'longitude': '', 'location_name': '', 'location_radius_km': '0'}
        )

        self.assertEqual(response.status_code, 200)
        self.party.refresh_from_db()
        self.assertIsNone(self.party.latitude)
        self.assertIsNone(self.party.longitude)

    def test_save_location_requires_dj_admin(self):
        """Usuaris normals no poden guardar localització"""
        regular = User.objects.create_user(username='user', password='test')
        self.client.login(username='user', password='test')

        response = self.client.post(
            reverse('save_party_location', args=[self.party.id]),
            {'latitude': '41.3851', 'longitude': '2.1734', 'location_name': 'BCN', 'location_radius_km': '5'}
        )

        self.assertIn(response.status_code, [302, 403])


class NotificationViewTests(TestCase):
    """Tests per les vistes de notificació"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='user', password='test')
        self.notif = Notification.objects.create(
            user=self.user,
            type='coins_purchased',
            title='Test Notif',
            message='Test message',
            is_read=False,
        )

    def test_notifications_page_marks_all_read(self):
        """Visitar la pàgina de notificacions marca totes com llegides"""
        self.client.login(username='user', password='test')
        self.client.get(reverse('notifications'))

        self.notif.refresh_from_db()
        self.assertTrue(self.notif.is_read)

    def test_mark_notification_read_api(self):
        """API mark_notification_read retorna JSON i marca com llegida"""
        self.client.login(username='user', password='test')
        response = self.client.post(
            reverse('mark_notification_read', args=[self.notif.id])
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])

        self.notif.refresh_from_db()
        self.assertTrue(self.notif.is_read)

    def test_mark_all_notifications_read(self):
        """mark_all_notifications_read marca totes les no llegides"""
        Notification.objects.create(
            user=self.user, type='song_played', title='T2', message='M2', is_read=False
        )
        self.client.login(username='user', password='test')
        response = self.client.post(reverse('mark_all_notifications_read'))

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['unread_count'], 0)

    def test_mark_notification_other_user_blocked(self):
        """Un usuari no pot marcar notificacions d'un altre"""
        other = User.objects.create_user(username='other', password='test')
        self.client.login(username='other', password='test')
        response = self.client.post(
            reverse('mark_notification_read', args=[self.notif.id])
        )
        self.assertEqual(response.status_code, 404)


class UnmarkSongPlayedTests(TestCase):
    """Tests per unmark_song_played — marcar cançó com a no jugada."""

    def setUp(self):
        self.client = Client()
        self.dj = User.objects.create_user(
            username='dj_unmark', password='test', is_superuser=True, is_staff=True
        )
        self.user = User.objects.create_user(username='user_unmark', password='test')
        self.party = Party.objects.create(
            name='Unmark Party',
            date=timezone.now(),
            party_status=Party.STATUS_DJJUKEBOX_ACTIVE,
        )
        self.song = Song.objects.create(
            party=self.party,
            title='Played Song',
            artist='Artist',
            spotify_id='unmark1',
            has_played=True,
        )

    def test_superuser_can_unmark(self):
        self.client.login(username='dj_unmark', password='test')
        self.song.played_at = timezone.now()
        self.song.save(update_fields=['played_at'])

        response = self.client.post(reverse('unmark_song_played', args=[self.song.id]))
        self.assertIn(response.status_code, (200, 302))
        self.song.refresh_from_db()
        self.assertFalse(self.song.has_played)
        self.assertIsNone(self.song.played_at)

    def test_regular_user_cannot_unmark(self):
        self.client.login(username='user_unmark', password='test')
        response = self.client.post(reverse('unmark_song_played', args=[self.song.id]))
        self.assertEqual(response.status_code, 302)
        self.song.refresh_from_db()
        self.assertTrue(self.song.has_played)

    def test_requires_login(self):
        response = self.client.post(reverse('unmark_song_played', args=[self.song.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('next=', response['Location'])


class PartyStatusApiTests(TestCase):
    """Tests per party_status_api — endpoint JSON de polling."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='apiuser', password='test')
        self.party = Party.objects.create(
            name='API Party',
            date=timezone.now(),
            party_status=Party.STATUS_DJJUKEBOX_ACTIVE,
        )
        self.song = Song.objects.create(
            party=self.party, title='API Song', artist='A', spotify_id='api1'
        )
        self.client.login(username='apiuser', password='test')

    def _set_party(self):
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('party_status_api'))
        self.assertEqual(response.status_code, 302)

    def test_no_party_selected_returns_400(self):
        response = self.client.get(reverse('party_status_api'))
        self.assertEqual(response.status_code, 400)

    def test_returns_json_with_party_status(self):
        self._set_party()
        response = self.client.get(reverse('party_status_api'))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('party_status', data)
        self.assertEqual(data['party_status'], Party.STATUS_DJJUKEBOX_ACTIVE)

    def test_returns_song_counts(self):
        self._set_party()
        response = self.client.get(reverse('party_status_api'))
        data = json.loads(response.content)
        self.assertIn('total_songs', data)
        self.assertIn('songs_played', data)
        self.assertIn('songs_remaining', data)
        self.assertEqual(data['total_songs'], 1)

    def test_returns_votes_left(self):
        self._set_party()
        response = self.client.get(reverse('party_status_api'))
        data = json.loads(response.content)
        self.assertIn('votes_left', data)

    def test_now_playing_reflects_top_voted_song(self):
        self._set_party()
        Vote.objects.create(user=self.user, song=self.song, party=self.party, vote_type='like')
        response = self.client.get(reverse('party_status_api'))
        data = json.loads(response.content)
        self.assertEqual(data['now_playing_title'], 'API Song')

    def test_last_played_reflects_marked_song(self):
        self._set_party()
        self.song.has_played = True
        self.song.played_at = timezone.now()
        self.song.save(update_fields=['has_played', 'played_at'])
        response = self.client.get(reverse('party_status_api'))
        data = json.loads(response.content)
        self.assertEqual(data['last_played_title'], 'API Song')

    def test_last_played_uses_played_at_not_song_id(self):
        self._set_party()
        newer_song = Song.objects.create(
            party=self.party, title='Higher ID Old Load', artist='B', spotify_id='api2'
        )
        older_time = timezone.now() - timezone.timedelta(minutes=5)
        later_time = timezone.now()

        newer_song.has_played = True
        newer_song.played_at = older_time
        newer_song.save(update_fields=['has_played', 'played_at'])

        self.song.has_played = True
        self.song.played_at = later_time
        self.song.save(update_fields=['has_played', 'played_at'])

        response = self.client.get(reverse('party_status_api'))
        data = json.loads(response.content)
        self.assertEqual(data['last_played_title'], 'API Song')


class ManageSongRequestsAllowWithoutChargeTests(TestCase):
    """Tests per l'opció allow_without_charge a manage_song_requests."""

    def setUp(self):
        self.client = Client()
        self.dj = User.objects.create_user(
            username='dj_awc', password='test', is_superuser=True, is_staff=True
        )
        self.user = User.objects.create_user(
            username='user_awc', password='test', credits=0
        )
        self.party = Party.objects.create(
            name='AWC Party',
            date=timezone.now(),
            party_status=Party.STATUS_DJJUKEBOX_ACTIVE,
            allow_song_requests=True,
            song_request_cost=5,
        )
        self.song_request = SongRequest.objects.create(
            user=self.user,
            party=self.party,
            title='Req Song',
            artist='Artist',
            spotify_id='awc1',
            coins_cost=5,
            status='pending',
        )
        self.client.login(username='dj_awc', password='test')
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

    def test_accept_without_charge_when_user_has_no_credits(self):
        response = self.client.post(
            reverse('manage_song_requests'),
            {
                'request_id': self.song_request.id,
                'action': 'accept',
                'allow_without_charge': '1',
            },
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])

    def test_accept_without_charge_does_not_deduct_credits(self):
        self.client.post(
            reverse('manage_song_requests'),
            {
                'request_id': self.song_request.id,
                'action': 'accept',
                'allow_without_charge': '1',
            },
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.credits, 0)

    def test_accept_without_charge_adds_song_to_party(self):
        self.client.post(
            reverse('manage_song_requests'),
            {
                'request_id': self.song_request.id,
                'action': 'accept',
                'allow_without_charge': '1',
            },
        )
        from jukebox.models import Song
        self.assertTrue(
            Song.objects.filter(party=self.party, spotify_id='awc1').exists()
        )

    def test_accept_with_charge_fails_when_no_credits(self):
        response = self.client.post(
            reverse('manage_song_requests'),
            {
                'request_id': self.song_request.id,
                'action': 'accept',
                'allow_without_charge': '0',
            },
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertFalse(data['success'])

    def test_invalid_action_returns_400(self):
        response = self.client.post(
            reverse('manage_song_requests'),
            {
                'request_id': self.song_request.id,
                'action': 'invalid',
            },
        )
        self.assertEqual(response.status_code, 400)


class SongListPartyVisibleTests(TestCase):
    """Tests per l'estat STATUS_PARTY_VISIBLE — mostra pantalla d'espera."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='vis_user', password='test')
        self.party = Party.objects.create(
            name='Visible Party',
            date=timezone.now(),
            party_status=Party.STATUS_PARTY_VISIBLE,
        )
        self.client.login(username='vis_user', password='test')
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

    def test_shows_waiting_screen(self):
        response = self.client.get(reverse('song_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context.get('playlist_not_ready'))

    def test_songs_list_is_empty(self):
        response = self.client.get(reverse('song_list'))
        self.assertEqual(len(response.context.get('songs', [])), 0)


class RegisterViewTests(TestCase):
    """
    Tests per el flux de registre via allauth (account_signup).

    La vista custom register() és codi mort — la URL /register/ redirigeix
    a account_signup gestionat per allauth.
    """

    def setUp(self):
        self.client = Client()
        self.signup_url = reverse('account_signup')
        self.valid_data = {
            'email': 'new@test.com',
            'username': 'newuser',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        }

    def test_register_redirect_points_to_allauth_signup(self):
        response = self.client.get('/ca/register/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('signup', response['Location'])

    def test_signup_get_returns_200(self):
        response = self.client.get(self.signup_url)
        self.assertEqual(response.status_code, 200)

    def test_signup_post_password_mismatch_stays_on_page(self):
        data = {**self.valid_data, 'password2': 'DifferentPass123!'}
        response = self.client.post(self.signup_url, data)
        self.assertEqual(response.status_code, 200)

    def test_signup_post_missing_email_stays_on_page(self):
        data = {**self.valid_data, 'email': ''}
        response = self.client.post(self.signup_url, data)
        self.assertEqual(response.status_code, 200)

    def test_signup_post_duplicate_username_stays_on_page(self):
        User.objects.create_user(username='newuser', password='test', email='existing@test.com')
        response = self.client.post(self.signup_url, self.valid_data)
        self.assertEqual(response.status_code, 200)

    def test_signup_post_valid_creates_user(self):
        from django.core import mail
        self.client.post(self.signup_url, self.valid_data)
        self.assertTrue(User.objects.filter(username='newuser').exists())

    def test_signup_post_valid_creates_email_address_record(self):
        """Allauth crea un EmailAddress pendent de verificació."""
        from allauth.account.models import EmailAddress
        self.client.post(self.signup_url, self.valid_data)
        self.assertTrue(
            EmailAddress.objects.filter(email='new@test.com', verified=False).exists()
        )


class ProfileViewTests(TestCase):
    """
    Tests per la vista de perfil d'usuari.

    Comprova: accés, rol, detecció de comptes socials.
    El template usa {% provider_login_url %} que requereix SocialApp a la BD.
    """

    def setUp(self):
        from allauth.socialaccount.models import SocialApp
        from django.contrib.sites.models import Site
        self.client = Client()
        self.url = reverse('profile')
        site = Site.objects.get_current()
        for provider in ('spotify', 'google'):
            app = SocialApp.objects.create(
                provider=provider,
                name=provider.capitalize(),
                client_id='test_id',
                secret='test_secret',
            )
            app.sites.add(site)

    def test_requires_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('next=', response['Location'])

    def test_regular_user_gets_member_role(self):
        user = User.objects.create_user(username='member', password='test')
        self.client.login(username='member', password='test')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Jukebox Member', response.context['profile_role'])

    def test_dj_user_gets_dj_role(self):
        dj = User.objects.create_user(username='dj', password='test')
        party = Party.objects.create(name='DJ Party', date=timezone.now())
        party.djs.add(dj)
        self.client.login(username='dj', password='test')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('DJ', response.context['profile_role'])

    def test_superuser_gets_admin_role(self):
        admin = User.objects.create_superuser(username='admin', password='test', email='a@a.com')
        self.client.login(username='admin', password='test')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Admin', response.context['profile_role'])

    def test_staff_user_gets_admin_role(self):
        staff = User.objects.create_user(username='staff', password='test', is_staff=True)
        self.client.login(username='staff', password='test')
        response = self.client.get(self.url)
        self.assertIn('Admin', response.context['profile_role'])

    def test_context_has_spotify_false_without_social_account(self):
        user = User.objects.create_user(username='nospot', password='test')
        self.client.login(username='nospot', password='test')
        response = self.client.get(self.url)
        self.assertFalse(response.context['has_spotify'])

    def test_context_has_google_false_without_social_account(self):
        user = User.objects.create_user(username='nogoog', password='test')
        self.client.login(username='nogoog', password='test')
        response = self.client.get(self.url)
        self.assertFalse(response.context['has_google'])

    def test_context_exposes_user(self):
        user = User.objects.create_user(username='ctxuser', password='test')
        self.client.login(username='ctxuser', password='test')
        response = self.client.get(self.url)
        self.assertEqual(response.context['user'], user)


class NotificationsListViewTests(TestCase):
    """
    Tests per la vista de llista de notificacions (notifications GET).

    Cobreix: accés, context, aïllament entre usuaris, límit de 50.
    Els tests de mark-read ja existeixen a NotificationViewTests.
    """

    def setUp(self):
        self.client = Client()
        self.url = reverse('notifications')
        self.user = User.objects.create_user(username='notifuser', password='test')
        self.other = User.objects.create_user(username='othernotif', password='test')

    def _make_notification(self, user, is_read=False, n=1):
        created = []
        for i in range(n):
            created.append(Notification.objects.create(
                user=user,
                type='coins_purchased',
                title=f'Notif {i}',
                message='msg',
                is_read=is_read,
            ))
        return created

    def test_requires_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('next=', response['Location'])

    def test_get_returns_200(self):
        self.client.login(username='notifuser', password='test')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_context_has_notifications_key(self):
        self.client.login(username='notifuser', password='test')
        response = self.client.get(self.url)
        self.assertIn('notifications', response.context)

    def test_shows_own_notifications(self):
        self._make_notification(self.user, n=3)
        self.client.login(username='notifuser', password='test')
        response = self.client.get(self.url)
        self.assertEqual(len(response.context['notifications']), 3)

    def test_does_not_show_other_users_notifications(self):
        self._make_notification(self.other, n=5)
        self.client.login(username='notifuser', password='test')
        response = self.client.get(self.url)
        self.assertEqual(len(response.context['notifications']), 0)

    def test_max_50_notifications_returned(self):
        self._make_notification(self.user, n=60)
        self.client.login(username='notifuser', password='test')
        response = self.client.get(self.url)
        self.assertLessEqual(len(response.context['notifications']), 50)

    def test_unread_notifications_marked_read_on_visit(self):
        notifs = self._make_notification(self.user, is_read=False, n=3)
        self.client.login(username='notifuser', password='test')
        self.client.get(self.url)
        for n in notifs:
            n.refresh_from_db()
            self.assertTrue(n.is_read)

    def test_already_read_notifications_unaffected(self):
        notifs = self._make_notification(self.user, is_read=True, n=2)
        self.client.login(username='notifuser', password='test')
        self.client.get(self.url)
        for n in notifs:
            n.refresh_from_db()
            self.assertTrue(n.is_read)

    def test_empty_state_returns_200(self):
        self.client.login(username='notifuser', password='test')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['notifications']), 0)


class ManageSongRequestsNotificationTests(TestCase):
    """
    Verifica que acceptar/rebutjar una petició crea (o no) notificació.
    """

    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_user(
            username='djsuper', password='test', is_superuser=True, is_staff=True
        )
        self.requester = User.objects.create_user(
            username='requester', password='test', credits=20
        )
        self.party = Party.objects.create(
            name='Notif Party',
            date=timezone.now(),
            party_status=Party.STATUS_DJJUKEBOX_ACTIVE,
            allow_song_requests=True,
            song_request_cost=5,
        )
        self.song_request = SongRequest.objects.create(
            user=self.requester,
            party=self.party,
            title='Test Song',
            artist='Test Artist',
            spotify_id='notiftestid',
            coins_cost=5,
            status='pending',
        )
        self.client.login(username='djsuper', password='test')
        session = self.client.session
        session['selected_party_id'] = self.party.id
        session.save()

    def test_accept_creates_notification_for_requester(self):
        self.client.post(reverse('manage_song_requests'), {
            'request_id': self.song_request.id,
            'action': 'accept',
            'allow_without_charge': '1',
        })
        self.assertTrue(
            Notification.objects.filter(
                user=self.requester,
                type='song_accepted',
            ).exists()
        )

    def test_reject_does_not_create_notification(self):
        self.client.post(reverse('manage_song_requests'), {
            'request_id': self.song_request.id,
            'action': 'reject',
        })
        self.assertFalse(
            Notification.objects.filter(user=self.requester).exists()
        )
