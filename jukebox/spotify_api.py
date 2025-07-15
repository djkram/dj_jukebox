# jukebox/spotify_api.py

from allauth.socialaccount.models import SocialToken
import requests

def get_user_playlists(request_or_user):
    """
    Retorna la llista de playlists de l'usuari (via request o User).
    """
    user = request_or_user.user if hasattr(request_or_user, 'user') else request_or_user

    token = SocialToken.objects.filter(
        account__user=user,
        account__provider='spotify'
    ).first()
    if not token:
        return []

    headers = {"Authorization": f"Bearer {token.token}"}
    try:
        resp = requests.get("https://api.spotify.com/v1/me/playlists", headers=headers)
        resp.raise_for_status()
    except requests.RequestException:
        return []

    data = resp.json()
    return [
        {'id': pl['id'], 'name': pl['name'], 'owner': pl['owner']['display_name']}
        for pl in data.get('items', [])
    ]


def get_playlist_tracks(request_or_user, playlist_id):
    """
    Retorna els tracks d'una playlist concreta (via request o User).
    """
    user = request_or_user.user if hasattr(request_or_user, 'user') else request_or_user

    token = SocialToken.objects.filter(
        account__user=user,
        account__provider='spotify'
    ).first()
    if not token:
        return []

    headers = {"Authorization": f"Bearer {token.token}"}
    url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
    except requests.RequestException:
        return []

    data = resp.json()
    tracks = []
    for item in data.get('items', []):
        track = item.get('track')
        if not track:
            continue
        tracks.append({
            'id': track.get('id'),
            'title': track.get('name'),
            'artist': ', '.join(a.get('name') for a in track.get('artists', [])),
        })
    return tracks
