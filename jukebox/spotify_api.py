# jukebox/spotify_api.py

from allauth.socialaccount.models import SocialToken
import requests
import math

def _get_token(request_or_user):
    """
    Retorna el SocialToken de Spotify per l'usuari.
    """
    user = getattr(request_or_user, 'user', request_or_user)
    token = SocialToken.objects.filter(
        account__user=user,
        account__provider='spotify'
    ).first()
    print(f"[spotify_api] _get_token: trobat token? {'sí' if token else 'no'}")
    return token

def _chunks(lst, n):
    """
    Generador de llistes de mida màxima n (per batches de l'API).
    """
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def _camelot_from_key_mode(key, mode):
    """
    Converteix key (0–11) i mode (0 minor, 1 major) a notació Camelot.
    """
    mapping = {
        # major
        (0,1): "8B", (7,1): "9B", (2,1): "10B", (9,1): "11B",
        (4,1): "12B", (11,1): "1B", (6,1): "2B", (1,1): "3B",
        (8,1): "4B", (3,1): "5B", (10,1): "6B", (5,1): "7B",
        # minor
        (9,0): "8A", (4,0): "9A", (11,0): "10A", (6,0): "11A",
        (1,0): "12A", (8,0): "1A", (3,0): "2A", (10,0): "3A",
        (5,0): "4A", (0,0): "5A", (7,0): "6A", (2,0): "7A",
    }
    camelot = mapping.get((key, mode))
    print(f"[spotify_api] _camelot_from_key_mode: key={key}, mode={mode} → {camelot}")
    return camelot or None

def get_user_playlists(request_or_user):
    """
    Retorna la llista de playlists de l'usuari (id, nom, owner).
    """
    token = _get_token(request_or_user)
    if not token:
        return []

    headers = {"Authorization": f"Bearer {token.token}"}
    print("[spotify_api] get_user_playlists: fent GET a /v1/me/playlists")
    try:
        resp = requests.get(
            "https://api.spotify.com/v1/me/playlists",
            headers=headers,
            timeout=5
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[spotify_api] get_user_playlists: error → {e}")
        return []

    items = resp.json().get("items", [])
    print(f"[spotify_api] get_user_playlists: obtinguts {len(items)} playlists")
    return [
        {"id": pl["id"], "name": pl["name"], "owner": pl["owner"]["display_name"]}
        for pl in items
    ]

def get_playlist_tracks(request_or_user, playlist_id):
    """
    Retorna els tracks d'una playlist de Spotify amb:
      - id        (spotify track id)
      - title
      - artist
      - bpm       (via Spotify Audio Features)
      - key       (Camelot)
    """
    token = _get_token(request_or_user)
    if not token:
        return []

    headers = {"Authorization": f"Bearer {token.token}"}

    # 1) Paginació per obtenir tots els tracks
    print(f"[spotify_api] get_playlist_tracks: obtenint tracks de playlist {playlist_id}")
    all_items = []
    url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
    while url:
        print(f"[spotify_api]   GET {url}")
        try:
            resp = requests.get(url, headers=headers, timeout=5)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[spotify_api]   error al GET tracks: {e}")
            break
        data = resp.json()
        batch = data.get("items", [])
        print(f"[spotify_api]   obtinguts {len(batch)} tracks en aquesta pàgina")
        all_items.extend(batch)
        url = data.get("next")  # seguir paginant si cal

    # 2) Extracció d'ids i metadades bàsiques
    track_ids = []
    meta = {}
    for item in all_items:
        tr = item.get("track") or {}
        sid = tr.get("id")
        if not sid:
            continue
        track_ids.append(sid)
        meta[sid] = {
            "title": tr.get("name"),
            "artist": ", ".join(a["name"] for a in tr.get("artists", []))
        }
    print(f"[spotify_api] Total de tracks vàlids: {len(track_ids)}")

    # 3) Cridar Audio Features en batches de 100
    features_map = {}
    for chunk in _chunks(track_ids, 100):
        ids_param = ",".join(chunk)
        url_af = f"https://api.spotify.com/v1/audio-features?ids={ids_param}"
        print(f"[spotify_api]   GET Audio Features per {len(chunk)} ids")
        try:
            resp = requests.get(url_af, headers=headers, timeout=5)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[spotify_api]   error Audio Features: {e}")
            continue
        for feat in resp.json().get("audio_features", []):
            if not feat:
                continue
            sid = feat["id"]
            tempo = feat.get("tempo")
            key = feat.get("key")
            mode = feat.get("mode")
            camelot = _camelot_from_key_mode(key, mode)
            features_map[sid] = {"bpm": tempo, "key": camelot}

    # 4) Compondre llista final
    tracks = []
    for sid in track_ids:
        bpm = features_map.get(sid, {}).get("bpm")
        key = features_map.get(sid, {}).get("key")
        info = {
            "id": sid,
            "title": meta[sid]["title"],
            "artist": meta[sid]["artist"],
            "bpm": bpm,
            "key": key,
        }
        print(f"[spotify_api] → {info}")
        tracks.append(info)

    print(f"[spotify_api] get_playlist_tracks: retornant {len(tracks)} tracks amb BPM+key")
    return tracks
