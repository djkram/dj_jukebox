import logging

from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _

from allauth.socialaccount.adapter import get_adapter
from allauth.socialaccount.providers.base import ProviderException
from allauth.socialaccount.providers.oauth2.views import OAuth2CallbackView
from allauth.socialaccount.providers.spotify.views import (
    SpotifyOAuth2Adapter as AllauthSpotifyOAuth2Adapter,
    oauth_login as allauth_spotify_oauth_login,
)

from .spotify_permissions import (
    is_spotify_auth_for_all_enabled,
    user_can_connect_spotify,
)


logger = logging.getLogger(__name__)


class SpotifyOAuth2Adapter(AllauthSpotifyOAuth2Adapter):
    basic_auth = True

    def complete_login(self, request: HttpRequest, app, token, **kwargs):
        with get_adapter().get_requests_session() as sess:
            resp = sess.get(
                self.profile_url,
                headers={"Authorization": f"Bearer {token.token}"},
            )

        try:
            extra_data = resp.json()
        except ValueError as exc:
            logger.warning(
                "Spotify profile response was not JSON: status=%s body=%r",
                resp.status_code,
                resp.text[:500],
            )
            raise ProviderException(
                f"Spotify profile response was not JSON (HTTP {resp.status_code})."
            ) from exc

        if resp.status_code >= 400:
            logger.warning(
                "Spotify profile request failed: status=%s body=%s",
                resp.status_code,
                extra_data,
            )
            raise ProviderException(
                f"Spotify profile request failed (HTTP {resp.status_code}): {extra_data}"
            )

        return self.get_provider().sociallogin_from_response(request, extra_data)


def spotify_oauth_login(request: HttpRequest, *args, **kwargs):
    process = request.GET.get("process") or request.POST.get("process")

    if is_spotify_auth_for_all_enabled():
        return allauth_spotify_oauth_login(request, *args, **kwargs)

    if process == "connect" and user_can_connect_spotify(request.user):
        return allauth_spotify_oauth_login(request, *args, **kwargs)

    messages.warning(
        request,
        _("La connexió amb Spotify està limitada temporalment als DJs i administradors."),
    )
    if request.user.is_authenticated:
        return redirect("profile")
    return redirect("account_login")


spotify_oauth_callback = OAuth2CallbackView.adapter_view(SpotifyOAuth2Adapter)
