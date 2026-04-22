"""
Tests unitaris per models
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from jukebox.models import Party, Playlist, Song, Vote, VotePackage, PartyCoinsGrant, SongRequest, Notification

User = get_user_model()


class UserModelTests(TestCase):
    """Tests per el model User"""

    def test_user_creation(self):
        """Test crear usuari amb credits per defecte"""
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.assertEqual(user.credits, 0)
        self.assertTrue(user.is_active)

    def test_user_credits_update(self):
        """Test actualitzar credits d'un usuari"""
        user = User.objects.create_user(username='testuser', password='test')
        user.credits = 100
        user.save()

        user.refresh_from_db()
        self.assertEqual(user.credits, 100)


class PartyModelTests(TestCase):
    """Tests per el model Party"""

    def setUp(self):
        self.owner = User.objects.create_user(username='dj', password='test')
        self.playlist = Playlist.objects.create(
            spotify_id='test123',
            name='Test Playlist',
            owner='test_owner'
        )

    def test_party_creation_generates_code(self):
        """Test que Party genera codi automàticament"""
        party = Party.objects.create(
            name='Test Party',
            owner=self.owner,
            date=timezone.now()
        )
        self.assertIsNotNone(party.code)
        self.assertGreaterEqual(len(party.code), 4)
        self.assertLessEqual(len(party.code), 12)
        self.assertTrue(party.code.isalnum())

    def test_party_code_is_unique(self):
        """Test que cada party té un codi únic"""
        party1 = Party.objects.create(name='Party 1', owner=self.owner, date=timezone.now())
        party2 = Party.objects.create(name='Party 2', owner=self.owner, date=timezone.now())
        self.assertNotEqual(party1.code, party2.code)

    def test_party_default_values(self):
        """Test valors per defecte de Party"""
        party = Party.objects.create(
            name='Test Party',
            owner=self.owner,
            date=timezone.now()
        )
        self.assertEqual(party.max_votes_per_user, 5)
        self.assertEqual(party.free_coins_per_user, 0)
        self.assertEqual(party.song_request_cost, 10)
        self.assertFalse(party.auto_sync_playlist)
        self.assertFalse(party.auto_analyze_audio)

    def test_party_with_playlist(self):
        """Test party amb playlist assignada"""
        party = Party.objects.create(
            name='Test Party',
            owner=self.owner,
            playlist=self.playlist,
            date=timezone.now()
        )
        self.assertEqual(party.playlist.spotify_id, 'test123')

    def test_party_str(self):
        """Test __str__ de Party"""
        party = Party.objects.create(name='My Party', owner=self.owner, date=timezone.now())
        self.assertEqual(str(party), 'My Party')


class PlaylistModelTests(TestCase):
    """Tests per el model Playlist"""

    def test_playlist_creation(self):
        """Test crear playlist"""
        playlist = Playlist.objects.create(
            spotify_id='spotify123',
            name='Summer Hits',
            owner='dj_owner'
        )
        self.assertEqual(playlist.spotify_id, 'spotify123')
        self.assertEqual(playlist.name, 'Summer Hits')

    def test_playlist_spotify_id_unique(self):
        """Test que spotify_id és únic"""
        Playlist.objects.create(spotify_id='unique123', name='Playlist 1', owner='owner1')

        with self.assertRaises(Exception):
            Playlist.objects.create(spotify_id='unique123', name='Playlist 2', owner='owner2')

    def test_playlist_str(self):
        """Test __str__ de Playlist"""
        playlist = Playlist.objects.create(spotify_id='id', name='My Playlist', owner='me')
        self.assertEqual(str(playlist), 'My Playlist')


class SongModelTests(TestCase):
    """Tests per el model Song"""

    def setUp(self):
        self.user = User.objects.create_user(username='user', password='test')
        self.party = Party.objects.create(name='Party', owner=self.user, date=timezone.now())

    def test_song_creation(self):
        """Test crear cançó"""
        song = Song.objects.create(
            party=self.party,
            title='Test Song',
            artist='Test Artist',
            spotify_id='spotify123'
        )
        self.assertEqual(song.title, 'Test Song')
        self.assertEqual(song.votes, 0)
        self.assertFalse(song.played)
        self.assertFalse(song.has_played)

    def test_song_with_metadata(self):
        """Test cançó amb BPM i key"""
        song = Song.objects.create(
            party=self.party,
            title='EDM Track',
            artist='DJ Test',
            spotify_id='id123',
            bpm=128.5,
            key='8B'
        )
        self.assertEqual(song.bpm, 128.5)
        self.assertEqual(song.key, '8B')

    def test_song_str(self):
        """Test __str__ de Song"""
        song = Song.objects.create(
            party=self.party,
            title='My Song',
            artist='My Artist',
            spotify_id='id'
        )
        self.assertEqual(str(song), 'My Song - My Artist')


class VoteModelTests(TestCase):
    """Tests per el model Vote"""

    def setUp(self):
        self.user = User.objects.create_user(username='user', password='test')
        self.party = Party.objects.create(name='Party', owner=self.user, date=timezone.now())
        self.song = Song.objects.create(
            party=self.party,
            title='Song',
            artist='Artist',
            spotify_id='id123'
        )

    def test_vote_creation(self):
        """Test crear vot"""
        vote = Vote.objects.create(
            user=self.user,
            song=self.song,
            party=self.party,
            vote_type='like'
        )
        self.assertEqual(vote.vote_type, 'like')
        self.assertIsNotNone(vote.created_at)

    def test_vote_unique_constraint(self):
        """Test que un usuari no pot votar dues vegades la mateixa cançó"""
        Vote.objects.create(user=self.user, song=self.song, party=self.party)

        with self.assertRaises(Exception):
            Vote.objects.create(user=self.user, song=self.song, party=self.party)

    def test_vote_types(self):
        """Test diferents tipus de vot"""
        for vote_type in ['like', 'dislike', 'skip']:
            vote = Vote.objects.create(
                user=self.user,
                song=Song.objects.create(
                    party=self.party,
                    title=f'Song {vote_type}',
                    artist='Artist',
                    spotify_id=f'id_{vote_type}'
                ),
                party=self.party,
                vote_type=vote_type
            )
            self.assertEqual(vote.vote_type, vote_type)


class VotePackageModelTests(TestCase):
    """Tests per el model VotePackage"""

    def setUp(self):
        self.user = User.objects.create_user(username='user', password='test')
        self.party = Party.objects.create(name='Party', owner=self.user, date=timezone.now())

    def test_vote_package_creation(self):
        """Test crear paquet de vots"""
        package = VotePackage.objects.create(
            user=self.user,
            party=self.party,
            votes_purchased=10,
            payment_id='stripe_123'
        )
        self.assertEqual(package.votes_purchased, 10)
        self.assertEqual(package.payment_id, 'stripe_123')
        self.assertIsNotNone(package.created_at)


class PartyCoinsGrantModelTests(TestCase):
    """Tests per el model PartyCoinsGrant"""

    def setUp(self):
        self.user = User.objects.create_user(username='user', password='test')
        self.party = Party.objects.create(name='Party', owner=self.user, date=timezone.now())

    def test_coins_grant_creation(self):
        """Test crear grant de coins"""
        grant = PartyCoinsGrant.objects.create(
            user=self.user,
            party=self.party,
            coins_granted=50,
            reason='free_coins'
        )
        self.assertEqual(grant.coins_granted, 50)
        self.assertEqual(grant.reason, 'free_coins')

    def test_coins_grant_negative(self):
        """Test retirar coins amb valor negatiu"""
        grant = PartyCoinsGrant.objects.create(
            user=self.user,
            party=self.party,
            coins_granted=-20,
            reason='adjustment'
        )
        self.assertEqual(grant.coins_granted, -20)

    def test_coins_grant_ordering(self):
        """Test que grants s'ordenen per created_at descendent"""
        grant1 = PartyCoinsGrant.objects.create(
            user=self.user,
            party=self.party,
            coins_granted=10
        )
        grant2 = PartyCoinsGrant.objects.create(
            user=self.user,
            party=self.party,
            coins_granted=20
        )

        grants = PartyCoinsGrant.objects.all()
        self.assertEqual(grants[0].id, grant2.id)  # Més recent primer


class SongRequestModelTests(TestCase):
    """Tests per el model SongRequest"""

    def setUp(self):
        self.user = User.objects.create_user(username='user', password='test')
        self.party = Party.objects.create(name='Party', owner=self.user, date=timezone.now())

    def test_song_request_creation(self):
        """Test crear petició de cançó"""
        request = SongRequest.objects.create(
            user=self.user,
            party=self.party,
            spotify_id='track123',
            title='Requested Song',
            artist='Artist',
            status='pending',
            coins_cost=10
        )
        self.assertEqual(request.status, 'pending')
        self.assertEqual(request.coins_cost, 10)
        self.assertIsNotNone(request.created_at)

    def test_song_request_status_transitions(self):
        """Test canvis d'estat de peticions"""
        request = SongRequest.objects.create(
            user=self.user,
            party=self.party,
            spotify_id='track123',
            title='Song',
            artist='Artist',
            status='pending',
            coins_cost=10
        )

        # Acceptar
        request.status = 'accepted'
        request.save()
        request.refresh_from_db()
        self.assertEqual(request.status, 'accepted')

        # Rebutjar
        request.status = 'rejected'
        request.save()
        request.refresh_from_db()
        self.assertEqual(request.status, 'rejected')


class NotificationModelTests(TestCase):
    """Tests per el model Notification"""

    def setUp(self):
        self.user = User.objects.create_user(username='user', password='test')

    def test_notification_creation(self):
        """Test crear notificació"""
        notification = Notification.objects.create(
            user=self.user,
            type='coins_purchased',
            title='Coins comprats',
            message='Has comprat 10 coins',
            amount=10
        )
        self.assertFalse(notification.is_read)
        self.assertEqual(notification.amount, 10)
        self.assertIsNotNone(notification.created_at)

    def test_notification_types(self):
        """Test diferents tipus de notificacions"""
        types = ['song_accepted', 'song_played', 'coins_purchased', 'coins_received']

        for notif_type in types:
            notification = Notification.objects.create(
                user=self.user,
                type=notif_type,
                title=f'Test {notif_type}',
                message='Test message'
            )
            self.assertEqual(notification.type, notif_type)

    def test_notification_mark_read(self):
        """Test marcar notificació com llegida"""
        notification = Notification.objects.create(
            user=self.user,
            type='coins_purchased',
            title='Test',
            message='Test'
        )

        notification.is_read = True
        notification.save()
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
