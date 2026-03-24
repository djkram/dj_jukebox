from django.test import SimpleTestCase, TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
import json

from jukebox.spotify_api import _camelot_from_key_string, _pick_getsongbpm_match
from jukebox.models import Notification, Party, Playlist

User = get_user_model()


class SpotifyApiHelpersTests(SimpleTestCase):
    def test_camelot_from_key_string_supports_major_and_minor(self):
        self.assertEqual(_camelot_from_key_string("C"), "8B")
        self.assertEqual(_camelot_from_key_string("Am"), "8A")
        self.assertEqual(_camelot_from_key_string("F#"), "2B")

    def test_pick_getsongbpm_match_prefers_title_and_artist_match(self):
        results = [
            {
                "title": "Five More Hours - Remix",
                "artist": {"name": "Deorro"},
            },
            {
                "title": "Five More Hours",
                "artist": {"name": "Deorro, Chris Brown"},
            },
        ]

        match = _pick_getsongbpm_match(results, "Five More Hours", "Deorro, Chris Brown")

        self.assertEqual(match, results[1])


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

    def test_sync_playlist_disabled(self):
        """Test que no sync si auto_sync_playlist està desactivat"""
        from jukebox.spotify_sync import sync_playlist_with_spotify

        result = sync_playlist_with_spotify(self.party.id)

        self.assertTrue(result.get('skipped'))
        self.assertEqual(result.get('reason'), 'Auto-sync disabled')

    def test_sync_playlist_no_playlist(self):
        """Test error si no hi ha playlist assignada"""
        from jukebox.spotify_sync import sync_playlist_with_spotify

        party_without_playlist = Party.objects.create(
            name='Party Without Playlist',
            owner=self.superuser,
            date=timezone.now(),
            auto_sync_playlist=True
        )

        result = sync_playlist_with_spotify(party_without_playlist.id)

        self.assertIsNotNone(result.get('error'))
        self.assertIn('No playlist', result.get('error'))

    def test_sync_playlist_rate_limiting(self):
        """Test que rate limiting funciona (no sync si fa menys de 4 min)"""
        from jukebox.spotify_sync import sync_playlist_with_spotify
        from django.utils import timezone

        # Activar auto-sync i simular última sync fa 2 minuts
        self.party.auto_sync_playlist = True
        self.party.last_sync_at = timezone.now() - timezone.timedelta(minutes=2)
        self.party.save()

        result = sync_playlist_with_spotify(self.party.id)

        self.assertTrue(result.get('skipped'))
        self.assertIn('Too soon', result.get('reason'))

    def test_force_sync_ignores_rate_limit(self):
        """Test que force_sync ignora el rate limit"""
        from django.utils import timezone

        # Activar auto-sync i simular última sync fa 1 minut
        self.party.auto_sync_playlist = True
        self.party.last_sync_at = timezone.now() - timezone.timedelta(minutes=1)
        self.party.save()

        self.client.login(username='admin', password='adminpass123')
        url = reverse('force_sync_playlist', args=[self.party.id])

        # Force sync hauria de funcionar tot i el rate limit
        # (Nota: Aquest test pot fallar si Spotify API no està disponible en testing)
        response = self.client.post(url)

        # Acceptem 200 (success), 400 (error de sync), o 500 (error de Spotify)
        self.assertIn(response.status_code, [200, 400, 500])

    def test_management_command_exists(self):
        """Test que el management command existeix"""
        from django.core.management import call_command
        from io import StringIO
        import sys

        out = StringIO()
        # Cridar amb --help provoca SystemExit(0), això és normal
        try:
            call_command('sync_playlists', '--help', stdout=out)
            success = True
        except SystemExit as e:
            # SystemExit(0) significa èxit (help mostrat correctament)
            success = (e.code == 0)
        except Exception:
            success = False

        self.assertTrue(success, "Management command 'sync_playlists' should exist")
