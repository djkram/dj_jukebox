import os
import logging
from allauth.socialaccount.models import SocialToken
from spotipy import Spotify

logger = logging.getLogger(__name__)


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


def get_user_playlists(request_or_user):
    token = _get_user_token(request_or_user)
    if not token:
        return []
    sp = Spotify(auth=token)
    resp = sp.current_user_playlists(limit=50)
    logger.info(f"[SPOTIFY] Llistes de reproducció carregades: {len(resp['items'])}")
    return [
        {"id": p["id"], "name": p["name"], "owner": p["owner"]["display_name"]}
        for p in resp["items"]
    ]


def _chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def get_playlist_tracks(request_or_user, playlist_id):
    logger.info(f"[SPOTIFY] Carregant tracks de la playlist {playlist_id}")

    user_token = _get_user_token(request_or_user)
    if not user_token:
        logger.warning("[SPOTIFY] No s'ha trobat token d'usuari per accedir a la playlist.")
        return []

    sp_user = Spotify(auth=user_token)
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
        out.append({
            "id": sid,
            "title": meta[sid]["title"],
            "artist": meta[sid]["artist"],
            "bpm": features_map.get(sid, {}).get("bpm"),
            "key": features_map.get(sid, {}).get("key"),
        })

    logger.info(f"[SPOTIFY] Resultat final: {len(out)} tracks amb metadades")
    return out
