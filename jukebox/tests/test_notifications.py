"""
Tests per el sistema de notificacions
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
import json

from jukebox.models import Notification, Party, Playlist

User = get_user_model()


class NotificationsTests(TestCase):
    """Tests per la funcionalitat de notificacions"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='testpass123'
        )

    def test_mark_notification_read_success(self):
        """Test marcar una notificació individual com llegida"""
        # Crear notificació
        notification = Notification.objects.create(
            user=self.user,
            type='coins_purchased',
            title='Coins comprats',
            message='Has comprat 10 coins',
            amount=10,
            is_read=False
        )

        # Login i fer request
        self.client.login(username='testuser', password='testpass123')
        url = reverse('mark_notification_read', args=[notification.id])
        response = self.client.post(url)

        # Verificar resposta
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertFalse(data['already_read'])
        self.assertEqual(data['unread_count'], 0)

        # Verificar que s'ha marcat com llegida
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_mark_notification_read_already_read(self):
        """Test marcar una notificació ja llegida"""
        # Crear notificació ja llegida
        notification = Notification.objects.create(
            user=self.user,
            type='coins_purchased',
            title='Coins comprats',
            message='Has comprat 10 coins',
            amount=10,
            is_read=True
        )

        self.client.login(username='testuser', password='testpass123')
        url = reverse('mark_notification_read', args=[notification.id])
        response = self.client.post(url)

        # Verificar resposta
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertTrue(data['already_read'])

    def test_mark_notification_read_wrong_user(self):
        """Test que no es pot marcar notificació d'un altre usuari"""
        # Crear notificació per other_user
        notification = Notification.objects.create(
            user=self.other_user,
            type='coins_purchased',
            title='Coins comprats',
            message='Has comprat 10 coins',
            amount=10,
            is_read=False
        )

        # Login com testuser i intentar marcar notificació d'other_user
        self.client.login(username='testuser', password='testpass123')
        url = reverse('mark_notification_read', args=[notification.id])
        response = self.client.post(url)

        # Hauria de retornar 404
        self.assertEqual(response.status_code, 404)

    def test_mark_notification_read_requires_login(self):
        """Test que cal estar autenticat per marcar notificacions"""
        notification = Notification.objects.create(
            user=self.user,
            type='coins_purchased',
            title='Test',
            message='Test',
            is_read=False
        )

        url = reverse('mark_notification_read', args=[notification.id])
        response = self.client.post(url)

        # Hauria de redirigir a login
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_mark_notification_read_requires_post(self):
        """Test que només accepta POST requests"""
        notification = Notification.objects.create(
            user=self.user,
            type='coins_purchased',
            title='Test',
            message='Test',
            is_read=False
        )

        self.client.login(username='testuser', password='testpass123')
        url = reverse('mark_notification_read', args=[notification.id])
        response = self.client.get(url)

        # Hauria de retornar 405 Method Not Allowed
        self.assertEqual(response.status_code, 405)

    def test_mark_notification_read_updates_unread_count(self):
        """Test que unread_count s'actualitza correctament"""
        # Crear 3 notificacions no llegides
        for i in range(3):
            Notification.objects.create(
                user=self.user,
                type='coins_purchased',
                title=f'Test {i}',
                message=f'Message {i}',
                is_read=False
            )

        # Marcar la primera com llegida
        notification = Notification.objects.filter(user=self.user).first()
        self.client.login(username='testuser', password='testpass123')
        url = reverse('mark_notification_read', args=[notification.id])
        response = self.client.post(url)

        # Verificar que unread_count és 2
        data = json.loads(response.content)
        self.assertEqual(data['unread_count'], 2)

    def test_mark_all_notifications_read(self):
        """Test marcar totes les notificacions com llegides"""
        # Crear múltiples notificacions
        for i in range(5):
            Notification.objects.create(
                user=self.user,
                type='coins_purchased',
                title=f'Test {i}',
                message=f'Message {i}',
                is_read=False
            )

        self.client.login(username='testuser', password='testpass123')
        url = reverse('mark_all_notifications_read')
        response = self.client.get(url)

        # Verificar resposta
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['updated_count'], 5)
        self.assertEqual(data['unread_count'], 0)

        # Verificar que totes s'han marcat com llegides
        unread_count = Notification.objects.filter(user=self.user, is_read=False).count()
        self.assertEqual(unread_count, 0)


class AutoSyncTests(TestCase):
    """Tests per la funcionalitat d'auto-sincronització de playlists"""

    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='adminpass123'
        )
        self.regular_user = User.objects.create_user(
            username='user',
            email='user@example.com',
            password='userpass123'
        )

        self.playlist = Playlist.objects.create(
            spotify_id='test_playlist_123',
            name='Test Playlist',
            owner='test_owner'
        )
        self.party = Party.objects.create(
            name='Test Party',
            owner=self.superuser,
            playlist=self.playlist,
            date=timezone.now(),
            auto_sync_playlist=False
        )

    def test_toggle_auto_sync_success(self):
        """Test activar/desactivar auto-sync"""
        self.client.login(username='admin', password='adminpass123')
        url = reverse('toggle_auto_sync', args=[self.party.id])

        # Activar auto-sync
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertTrue(data['auto_sync_enabled'])

        # Verificar a la BD
        self.party.refresh_from_db()
        self.assertTrue(self.party.auto_sync_playlist)

        # Desactivar auto-sync
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertFalse(data['auto_sync_enabled'])

        # Verificar a la BD
        self.party.refresh_from_db()
        self.assertFalse(self.party.auto_sync_playlist)

    def test_toggle_auto_sync_requires_superuser(self):
        """Test que només superusuaris poden activar auto-sync"""
        self.client.login(username='user', password='userpass123')
        url = reverse('toggle_auto_sync', args=[self.party.id])
        response = self.client.post(url)

        # Hauria de redirigir o retornar 403
        self.assertIn(response.status_code, [302, 403])

    def test_toggle_auto_sync_requires_post(self):
        """Test que només accepta POST"""
        self.client.login(username='admin', password='adminpass123')
        url = reverse('toggle_auto_sync', args=[self.party.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 405)

    def test_toggle_auto_sync_party_not_found(self):
        """Test amb party inexistent"""
        self.client.login(username='admin', password='adminpass123')
        url = reverse('toggle_auto_sync', args=[99999])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 404)
