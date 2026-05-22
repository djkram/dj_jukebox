"""
Tests unitaris per les funcions de creació de notificacions (notifications.py).

Cobreix:
- create_song_accepted_notification
- create_song_played_notification (notifica tots els votants)
- create_coins_purchased_notification
- create_coins_received_notification
"""
from django.test import TestCase
from django.utils import timezone

from jukebox.models import Party, Song, Vote, SongRequest, Notification
from jukebox.notifications import (
    create_song_accepted_notification,
    create_song_played_notification,
    create_coins_purchased_notification,
    create_coins_received_notification,
)
from django.contrib.auth import get_user_model

User = get_user_model()


class CreateSongAcceptedNotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='nfacc', password='test')
        self.party = Party.objects.create(name='Notif Party', date=timezone.now())
        self.song_request = SongRequest.objects.create(
            user=self.user,
            party=self.party,
            title='Accepted Song',
            artist='Artist A',
            spotify_id='nf_acc1',
            coins_cost=5,
        )

    def test_creates_notification_for_user(self):
        create_song_accepted_notification(self.song_request)
        self.assertTrue(
            Notification.objects.filter(user=self.user, type='song_accepted').exists()
        )

    def test_notification_links_song_request(self):
        create_song_accepted_notification(self.song_request)
        notif = Notification.objects.get(user=self.user, type='song_accepted')
        self.assertEqual(notif.song_request, self.song_request)

    def test_notification_amount_when_charged(self):
        create_song_accepted_notification(self.song_request, charged_amount=5)
        notif = Notification.objects.get(user=self.user, type='song_accepted')
        self.assertEqual(notif.amount, 5)

    def test_notification_amount_none_when_not_charged(self):
        create_song_accepted_notification(self.song_request, charged_amount=None)
        notif = Notification.objects.get(user=self.user, type='song_accepted')
        self.assertIsNone(notif.amount)

    def test_notification_title_not_empty(self):
        create_song_accepted_notification(self.song_request)
        notif = Notification.objects.get(user=self.user, type='song_accepted')
        self.assertTrue(notif.title)

    def test_notification_message_contains_song_title(self):
        create_song_accepted_notification(self.song_request)
        notif = Notification.objects.get(user=self.user, type='song_accepted')
        self.assertIn('Accepted Song', notif.message)


class CreateSongPlayedNotificationTests(TestCase):
    def setUp(self):
        self.party = Party.objects.create(name='Played Party', date=timezone.now())
        self.song = Song.objects.create(
            party=self.party, title='Played Song', artist='Artist P', spotify_id='nf_play1'
        )
        self.voters = [
            User.objects.create_user(username=f'voter_nf{i}', password='test')
            for i in range(3)
        ]
        for voter in self.voters:
            Vote.objects.create(user=voter, song=self.song, party=self.party, vote_type='like')

    def test_creates_notification_for_each_voter(self):
        create_song_played_notification(self.song)
        count = Notification.objects.filter(type='song_played').count()
        self.assertEqual(count, 3)

    def test_each_voter_receives_notification(self):
        create_song_played_notification(self.song)
        for voter in self.voters:
            self.assertTrue(
                Notification.objects.filter(user=voter, type='song_played').exists(),
                f"Voter {voter.username} has no notification"
            )

    def test_notification_links_song(self):
        create_song_played_notification(self.song)
        notif = Notification.objects.filter(type='song_played').first()
        self.assertEqual(notif.song, self.song)

    def test_no_notification_when_no_voters(self):
        song_no_votes = Song.objects.create(
            party=self.party, title='Empty Song', artist='A', spotify_id='nf_empty'
        )
        create_song_played_notification(song_no_votes)
        self.assertFalse(Notification.objects.filter(type='song_played').exists())

    def test_dislikers_also_notified(self):
        disliked_song = Song.objects.create(
            party=self.party, title='Disliked', artist='A', spotify_id='nf_dis'
        )
        extra_user = User.objects.create_user(username='disliker_nf', password='test')
        Vote.objects.create(
            user=extra_user, song=disliked_song, party=self.party, vote_type='dislike'
        )
        create_song_played_notification(disliked_song)
        self.assertTrue(
            Notification.objects.filter(user=extra_user, type='song_played').exists()
        )

    def test_notification_message_contains_song_title(self):
        create_song_played_notification(self.song)
        notif = Notification.objects.filter(type='song_played').first()
        self.assertIn('Played Song', notif.message)


class CreateCoinsPurchasedNotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='nfpurch', password='test')

    def test_creates_notification(self):
        create_coins_purchased_notification(self.user, 25)
        self.assertTrue(
            Notification.objects.filter(user=self.user, type='coins_purchased').exists()
        )

    def test_notification_amount(self):
        create_coins_purchased_notification(self.user, 25)
        notif = Notification.objects.get(user=self.user, type='coins_purchased')
        self.assertEqual(notif.amount, 25)

    def test_notification_message_contains_amount(self):
        create_coins_purchased_notification(self.user, 60)
        notif = Notification.objects.get(user=self.user, type='coins_purchased')
        self.assertIn('60', notif.message)


class CreateCoinsReceivedNotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='nfrecv', password='test')

    def test_creates_notification(self):
        create_coins_received_notification(self.user, 10)
        self.assertTrue(
            Notification.objects.filter(user=self.user, type='coins_received').exists()
        )

    def test_notification_amount(self):
        create_coins_received_notification(self.user, 10)
        notif = Notification.objects.get(user=self.user, type='coins_received')
        self.assertEqual(notif.amount, 10)

    def test_notification_with_reason(self):
        create_coins_received_notification(self.user, 5, reason='Prova benvinguda')
        notif = Notification.objects.get(user=self.user, type='coins_received')
        self.assertIn('Prova benvinguda', notif.message)

    def test_notification_without_reason(self):
        create_coins_received_notification(self.user, 5)
        notif = Notification.objects.get(user=self.user, type='coins_received')
        self.assertIn('5', notif.message)
