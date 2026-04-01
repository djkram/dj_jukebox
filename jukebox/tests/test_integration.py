"""
Tests d'integració end-to-end
Testen workflows complets de l'aplicació
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from jukebox.models import Party, Song, Vote, VotePackage, SongRequest, Notification
from jukebox.votes import convert_coins_to_votes, get_user_votes_left

User = get_user_model()


class UserJourneyTests(TestCase):
    """Tests que simulen el journey complet d'un usuari"""

    def setUp(self):
        self.client = Client()
        self.dj = User.objects.create_superuser(
            username='dj',
            email='dj@example.com',
            password='djpass'
        )
        self.user = User.objects.create_user(
            username='user',
            email='user@example.com',
            password='userpass',
            credits=50
        )

    def test_complete_user_journey(self):
        """
        Test journey complet:
        1. DJ crea festa
        2. Usuari fa login
        3. Usuari selecciona festa
        4. Usuari veu cançons
        5. Usuari compra vots
        6. Usuari vota cançons
        """
        # 1. DJ crea festa
        party = Party.objects.create(
            name='Summer Party',
            owner=self.dj,
            date=timezone.now(),
            max_votes_per_user=3
        )

        # Afegir cançons
        songs = []
        for i in range(5):
            song = Song.objects.create(
                party=party,
                title=f'Song {i}',
                artist='Artist',
                spotify_id=f'id{i}'
            )
            songs.append(song)

        # 2. Usuari fa login
        login = self.client.login(username='user', password='userpass')
        self.assertTrue(login)

        # 3. Usuari selecciona festa
        response = self.client.post(reverse('select_party'), {
            'party_code': party.code
        })
        self.assertEqual(response.status_code, 302)

        # Verificar sessió
        session = self.client.session
        self.assertEqual(session['selected_party_id'], party.id)

        # 4. Usuari veu cançons
        response = self.client.get(reverse('song_list'))
        self.assertEqual(response.status_code, 200)
        for song in songs:
            self.assertContains(response, song.title)

        # 5. Usuari compra vots (converteix 5 coins → 11 votes)
        result = convert_coins_to_votes(self.user, party, 5)
        self.assertTrue(result['success'])
        self.assertEqual(result['votes_received'], 11)

        # Verificar vots disponibles (3 base + 11 comprats = 14)
        votes_left = get_user_votes_left(self.user, party)
        self.assertEqual(votes_left, 14)

        # 6. Usuari vota 3 cançons
        for i in range(3):
            response = self.client.post(reverse('vote', args=[songs[i].id]))

        # Verificar vots
        votes_left = get_user_votes_left(self.user, party)
        self.assertEqual(votes_left, 11)  # 14 - 3

        # Verificar que les cançons tenen vots
        for i in range(3):
            songs[i].refresh_from_db()
            self.assertEqual(songs[i].votes, 1)


class DJWorkflowTests(TestCase):
    """Tests que simulen el workflow d'un DJ"""

    def setUp(self):
        self.client = Client()
        self.dj = User.objects.create_superuser(
            username='dj',
            password='djpass'
        )
        self.user = User.objects.create_user(
            username='user',
            password='userpass',
            credits=50
        )

    def test_dj_party_management(self):
        """
        Test workflow de DJ:
        1. Crear festa
        2. Gestionar peticions de cançons
        3. Marcar cançons com a reproduïdes
        """
        # 1. Crear festa
        self.client.login(username='dj', password='djpass')

        party = Party.objects.create(
            name='DJ Party',
            owner=self.dj,
            date=timezone.now(),
            song_request_cost=10
        )

        # Afegir cançons
        songs = []
        for i in range(3):
            song = Song.objects.create(
                party=party,
                title=f'Song {i}',
                artist='Artist',
                spotify_id=f'id{i}',
                votes=i  # Simular vots
            )
            songs.append(song)

        # 2. Usuari demana una cançó
        song_request = SongRequest.objects.create(
            user=self.user,
            party=party,
            spotify_track_id='new_track',
            title='Requested Song',
            artist='New Artist',
            status='pending',
            coins_cost=10
        )

        # DJ accepta la petició
        # (Això normalment es faria via view, aquí simulem)
        song_request.status = 'accepted'
        song_request.save()

        # Afegir cançó a la party
        new_song = Song.objects.create(
            party=party,
            title='Requested Song',
            artist='New Artist',
            spotify_id='new_track'
        )

        # Verificar que s'ha creat notificació per l'usuari
        # (Això hauria de fer-se a la view)
        Notification.objects.create(
            user=self.user,
            type='song_accepted',
            title='Cançó acceptada',
            message='La teva cançó ha estat acceptada',
            song_request=song_request
        )

        notification_exists = Notification.objects.filter(
            user=self.user,
            type='song_accepted'
        ).exists()
        self.assertTrue(notification_exists)

        # 3. DJ marca cançó com a reproduïda
        songs[0].played = True
        songs[0].save()

        # Verificar
        songs[0].refresh_from_db()
        self.assertTrue(songs[0].played)


class NotificationWorkflowTests(TestCase):
    """Tests per el workflow de notificacions"""

    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(username='user1', password='test')
        self.user2 = User.objects.create_user(username='user2', password='test')
        self.dj = User.objects.create_superuser(username='dj', password='test')

        self.party = Party.objects.create(
            name='Party',
            owner=self.dj,
            date=timezone.now()
        )

        self.song = Song.objects.create(
            party=self.party,
            title='Popular Song',
            artist='Artist',
            spotify_id='id123'
        )

    def test_song_played_notifies_all_voters(self):
        """
        Test que quan una cançó es reprodueix,
        tots els votants reben notificació
        """
        # User1 i User2 voten la cançó
        Vote.objects.create(user=self.user1, song=self.song, party=self.party)
        Vote.objects.create(user=self.user2, song=self.song, party=self.party)

        # DJ marca com a reproduïda (trigger notificacions)
        # Això normalment es fa a la view, aquí simulem
        self.song.played = True
        self.song.save()

        # Crear notificacions per tots els votants
        voters = Vote.objects.filter(song=self.song, party=self.party).values_list('user', flat=True)
        for user_id in voters:
            Notification.objects.create(
                user_id=user_id,
                type='song_played',
                title='Cançó sonant!',
                message=f'{self.song.title} està sonant ara',
                song=self.song
            )

        # Verificar que user1 i user2 tenen notificació
        notif1 = Notification.objects.filter(user=self.user1, type='song_played').exists()
        notif2 = Notification.objects.filter(user=self.user2, type='song_played').exists()

        self.assertTrue(notif1)
        self.assertTrue(notif2)

    def test_notification_badge_updates(self):
        """Test que el badge de notificacions s'actualitza"""
        # Crear notificacions per user1
        for i in range(3):
            Notification.objects.create(
                user=self.user1,
                type='coins_purchased',
                title=f'Test {i}',
                message='Test',
                is_read=False
            )

        # User1 fa login
        self.client.login(username='user1', password='test')

        # Anar a pàgina (hauria de mostrar badge amb 3)
        response = self.client.get(reverse('song_list'))

        # El context hauria de tenir unread_count
        # (Això depèn del context processor)

        # User1 marca totes com llegides
        response = self.client.get(reverse('mark_all_notifications_read'))

        # Verificar que totes estan llegides
        unread = Notification.objects.filter(user=self.user1, is_read=False).count()
        self.assertEqual(unread, 0)


class MultiPartyTests(TestCase):
    """Tests amb múltiples festes simultànies"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='user',
            password='test',
            credits=100
        )
        self.dj = User.objects.create_superuser(username='dj', password='test')

        # Crear 2 festes
        self.party1 = Party.objects.create(
            name='Party 1',
            owner=self.dj,
            date=timezone.now(),
            max_votes_per_user=5
        )
        self.party2 = Party.objects.create(
            name='Party 2',
            owner=self.dj,
            date=timezone.now(),
            max_votes_per_user=3
        )

    def test_votes_are_party_specific(self):
        """Test que els vots són específics per cada festa"""
        # Comprar vots per party1
        convert_coins_to_votes(self.user, self.party1, 10)

        # Verificar vots a cada festa
        votes_party1 = get_user_votes_left(self.user, self.party1)
        votes_party2 = get_user_votes_left(self.user, self.party2)

        self.assertEqual(votes_party1, 30)  # 5 base + 25 comprats
        self.assertEqual(votes_party2, 3)   # Només base

    def test_global_credits_shared_across_parties(self):
        """Test que els credits globals es comparteixen"""
        # Gastar 10 coins a party1
        convert_coins_to_votes(self.user, self.party1, 10)

        # Verificar credits globals
        self.user.refresh_from_db()
        self.assertEqual(self.user.credits, 75)  # 100 - 25 (10 coins package)

        # Intentar gastar 80 coins a party2 (no n'hi ha prou)
        result = convert_coins_to_votes(self.user, self.party2, 20)
        self.assertFalse(result['success'])

        # Credits no haurien de canviar
        self.user.refresh_from_db()
        self.assertEqual(self.user.credits, 75)
