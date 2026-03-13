import os
import logging
from allauth.socialaccount.models import SocialToken
from spotipy import Spotify
import requests

logger = logging.getLogger(__name__)

GETSONGBPM_BASE_URL = "https://api.getsong.co"
GETSONGBPM_TIMEOUT = 5


def _get_user_token(request_or_user):
    user = getattr(request_or_user, 'user', request_or_user)
    tok = SocialToken.objects.filter(
        account__user=user,
        account__provider='spotify'
    ).first()
    if tok:
        logger.debug(f"[SPOTIFY] Token trobat per l'usuari {user}")
    else:
        logger.warning(f"[SPOTIFY] No s'ha trobat cap token per l'usuari {user}")
    return tok.token if tok else None


def _camelot_from_key_mode(key, mode):
    mapping = {
        (0, 1): "8B", (7, 1): "9B", (2, 1): "10B", (9, 1): "11B",
        (4, 1): "12B", (11, 1): "1B", (6, 1): "2B", (1, 1): "3B",
        (8, 1): "4B", (3, 1): "5B", (10, 1): "6B", (5, 1): "7B",
        (9, 0): "8A", (4, 0): "9A", (11, 0): "10A", (6, 0): "11A",
        (1, 0): "12A", (8, 0): "1A", (3, 0): "2A", (10, 0): "3A",
        (5, 0): "4A", (0, 0): "5A", (7, 0): "6A", (2, 0): "7A",
    }
    return mapping.get((key, mode))


def _camelot_from_key_string(key_string):
    if not key_string:
        return None

    normalized = key_string.strip()
    mode = 0 if normalized.endswith("m") else 1
    note = normalized[:-1] if mode == 0 else normalized
    note_map = {
        "C": 0,
        "C#": 1,
        "Db": 1,
        "D": 2,
        "D#": 3,
        "Eb": 3,
        "E": 4,
        "F": 5,
        "F#": 6,
        "Gb": 6,
        "G": 7,
        "G#": 8,
        "Ab": 8,
        "A": 9,
        "A#": 10,
        "Bb": 10,
        "B": 11,
    }
    key_value = note_map.get(note)
    if key_value is None:
        return None
    return _camelot_from_key_mode(key_value, mode)


def _normalize_lookup(value):
    return " ".join((value or "").strip().lower().split())


def _pick_getsongbpm_match(results, title, artist):
    normalized_title = _normalize_lookup(title)
    normalized_artist = _normalize_lookup(artist)

    exact_match = None
    title_match = None
    fallback = None

    for result in results:
        result_title = _normalize_lookup(result.get("title"))
        result_artist = _normalize_lookup(result.get("artist", {}).get("name"))
        if fallback is None:
            fallback = result
        if result_title == normalized_title:
            if title_match is None:
                title_match = result
            if normalized_artist and (
                normalized_artist in result_artist or result_artist in normalized_artist
            ):
                exact_match = result
                break

    return exact_match or title_match or fallback


def _get_getsongbpm_features(title, artist):
    api_key = os.environ.get("GETSONGBPM_API_KEY")
    if not api_key:
        return {"bpm": None, "key": None}

    params = {
        "api_key": api_key,
        "type": "both",
        "lookup": f"song:{title} artist:{artist}",
        "limit": 10,
    }

    try:
        response = requests.get(
            f"{GETSONGBPM_BASE_URL}/search/",
            params=params,
            timeout=GETSONGBPM_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("[GETSONGBPM] Search failed for %s - %s: %s", artist, title, exc)
        return {"bpm": None, "key": None}

    payload = response.json()
    match = _pick_getsongbpm_match(payload.get("search", []), title, artist)
    if not match:
        logger.info("[GETSONGBPM] No match for %s - %s", artist, title)
        return {"bpm": None, "key": None}

    bpm = match.get("tempo")
    try:
        bpm = float(bpm) if bpm is not None else None
    except (TypeError, ValueError):
        bpm = None

    return {
        "bpm": bpm,
        "key": _camelot_from_key_string(match.get("key_of")),
    }


def get_user_playlists(request_or_user):
    token = _get_user_token(request_or_user)
    if not token:
        return []

    try:
        sp = Spotify(auth=token)
        resp = sp.current_user_playlists(limit=50)
        logger.info(f"[SPOTIFY] Llistes de reproducció carregades: {len(resp['items'])}")
        return [
            {"id": p["id"], "name": p["name"], "owner": p["owner"]["display_name"]}
            for p in resp["items"]
        ]
    except Exception as e:
        logger.error(f"[SPOTIFY] Error al carregar playlists: {e}")
        return []


def _chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def get_playlist_tracks(request_or_user, playlist_id):
    logger.info(f"[SPOTIFY] Carregant tracks de la playlist {playlist_id}")

    user_token = _get_user_token(request_or_user)
    if not user_token:
        logger.warning("[SPOTIFY] No s'ha trobat token d'usuari per accedir a la playlist.")
        return []

    try:
        sp_user = Spotify(auth=user_token)
    except Exception as e:
        logger.error(f"[SPOTIFY] Error al inicialitzar client: {e}")
        return []
    all_items = []
    results = sp_user.playlist_items(
        playlist_id,
        fields="items.track.id,items.track.name,items.track.artists,next",
        additional_types=["track"]
    )
    all_items.extend(results["items"])
    while results.get("next"):
        results = sp_user.next(results)
        all_items.extend(results["items"])
    logger.info(f"[SPOTIFY] Tracks trobats a la playlist: {len(all_items)}")

    ids, meta = [], {}
    for it in all_items:
        tr = it["track"]
        sid = tr["id"]
        if not sid:
            continue
        ids.append(sid)
        meta[sid] = {
            "title": tr["name"],
            "artist": ", ".join(a["name"] for a in tr["artists"])
        }

    logger.debug(f"[SPOTIFY] Track IDs extrets: {len(ids)}")

    features_map = {}
    for idx, chunk in enumerate(_chunked(ids, 50)):
        try:
            logger.debug(f"[SPOTIFY] Carregant features chunk {idx+1} ({len(chunk)} tracks) amb token d’usuari")
            feats = sp_user.audio_features(tracks=chunk)
            for f in feats:
                if not f:
                    continue
                features_map[f["id"]] = {
                    "bpm": f.get("tempo"),
                    "key": _camelot_from_key_mode(f.get("key"), f.get("mode"))
                }
        except Exception as e:
            logger.error(f"[SPOTIFY] ERROR al carregar audio features per chunk {idx+1}: {e}")
            logger.debug(f"[SPOTIFY] IDs del chunk amb error: {chunk}")

    out = []
    for sid in ids:
        feature_data = features_map.get(sid, {})
        if not feature_data.get("bpm") and not feature_data.get("key"):
            feature_data = _get_getsongbpm_features(meta[sid]["title"], meta[sid]["artist"])

        out.append({
            "id": sid,
            "title": meta[sid]["title"],
            "artist": meta[sid]["artist"],
            "bpm": feature_data.get("bpm"),
            "key": feature_data.get("key"),
        })

    logger.info(f"[SPOTIFY] Resultat final: {len(out)} tracks amb metadades")
    return out
