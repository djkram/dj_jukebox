from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from allauth.socialaccount.models import SocialToken
from allauth.socialaccount.providers.base import ProviderException

from jukebox.models import Party
from jukebox.socialaccount_adapters import SpotifyOAuth2Adapter
from jukebox.socialaccount_adapters import spotify_oauth_login
from jukebox.spotify_permissions import user_can_connect_spotify


class SpotifyOAuth2AdapterTests(TestCase):
    def test_get_client_uses_http_basic_auth_for_token_exchange(self):
        request = RequestFactory().get("/")
        adapter = SpotifyOAuth2Adapter(request)

        client = adapter.get_client(
            request,
            SimpleNamespace(client_id="client-id", secret="client-secret"),
        )

        self.assertTrue(client.basic_auth)

    def test_complete_login_uses_bearer_authorization_header(self):
        request = RequestFactory().get("/")
        adapter = SpotifyOAuth2Adapter(request)
        token = SocialToken(token="spotify-token")

        response = Mock(status_code=200)
        response.json.return_value = {"id": "spotify-user", "display_name": "Spotify User"}

        session = Mock()
        session.get.return_value = response
        session_context = Mock()
        session_context.__enter__ = Mock(return_value=session)
        session_context.__exit__ = Mock(return_value=False)

        allauth_adapter = Mock()
        allauth_adapter.get_requests_session.return_value = session_context

        provider = Mock()
        provider.sociallogin_from_response.return_value = "social-login"

        with (
            patch("jukebox.socialaccount_adapters.get_adapter", return_value=allauth_adapter),
            patch.object(adapter, "get_provider", return_value=provider),
        ):
            result = adapter.complete_login(request, SimpleNamespace(), token)

        self.assertEqual(result, "social-login")
        session.get.assert_called_once_with(
            adapter.profile_url,
            headers={"Authorization": "Bearer spotify-token"},
        )

    def test_complete_login_raises_provider_exception_for_non_json_response(self):
        request = RequestFactory().get("/")
        adapter = SpotifyOAuth2Adapter(request)
        token = SocialToken(token="spotify-token")

        response = Mock(status_code=401)
        response.text = "not json"
        response.json.side_effect = ValueError("not json")

        session = Mock()
        session.get.return_value = response
        session_context = Mock()
        session_context.__enter__ = Mock(return_value=session)
        session_context.__exit__ = Mock(return_value=False)

        allauth_adapter = Mock()
        allauth_adapter.get_requests_session.return_value = session_context

        with patch("jukebox.socialaccount_adapters.get_adapter", return_value=allauth_adapter):
            with self.assertRaises(ProviderException):
                adapter.complete_login(request, SimpleNamespace(), token)

    @override_settings(SPOTIFY_AUTH_FOR_ALL=False)
    def test_spotify_login_is_blocked_for_public_auth_when_flag_is_off(self):
        request = RequestFactory().get("/accounts/spotify/login/")
        request.user = AnonymousUser()

        with patch("jukebox.socialaccount_adapters.messages.warning"):
            response = spotify_oauth_login(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/accounts/login/")

    @override_settings(SPOTIFY_AUTH_FOR_ALL=True)
    def test_spotify_login_is_allowed_when_public_auth_flag_is_on(self):
        request = RequestFactory().get("/accounts/spotify/login/")
        request.user = AnonymousUser()

        with patch(
            "jukebox.socialaccount_adapters.allauth_spotify_oauth_login",
            return_value=HttpResponse("ok"),
        ) as oauth_login:
            response = spotify_oauth_login(request)

        self.assertEqual(response.status_code, 200)
        oauth_login.assert_called_once()

    @override_settings(SPOTIFY_AUTH_FOR_ALL=False)
    def test_spotify_connect_is_allowed_for_staff_when_flag_is_off(self):
        request = RequestFactory().get("/accounts/spotify/login/?process=connect")
        request.user = SimpleNamespace(
            is_authenticated=True,
            is_staff=True,
            is_superuser=False,
        )

        with patch(
            "jukebox.socialaccount_adapters.allauth_spotify_oauth_login",
            return_value=HttpResponse("ok"),
        ) as oauth_login:
            response = spotify_oauth_login(request)

        self.assertEqual(response.status_code, 200)
        oauth_login.assert_called_once()

    @override_settings(SPOTIFY_AUTH_FOR_ALL=False)
    def test_spotify_connect_is_allowed_for_party_dj_when_flag_is_off(self):
        user = get_user_model().objects.create_user(username="dj", password="test")
        party = Party.objects.create(name="Festa", date=timezone.now())
        party.djs.add(user)

        self.assertTrue(user_can_connect_spotify(user))
