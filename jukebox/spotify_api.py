import os
import logging
from datetime import timedelta

from allauth.socialaccount.models import SocialToken
from django.utils import timezone
from spotipy import Spotify
from spotipy.exceptions import SpotifyException
import requests
import musicbrainzngs

logger = logging.getLogger(__name__)

# Configurar MusicBrainz
musicbrainzngs.set_useragent("DJJukebox", "1.0", "https://github.com/yourusername/dj_jukebox")

GETSONGBPM_BASE_URL = "https://api.getsong.co"
GETSONGBPM_TIMEOUT = 5


class SpotifyAuthError(Exception):
    """No hi ha un token usable de Spotify i no s'ha pogut refrescar."""


def _get_social_token_obj(request_or_user):
    user = getattr(request_or_user, 'user', request_or_user)
    tok = SocialToken.objects.filter(
        account__user=user,
        account__provider='spotify'
    ).select_related("app").first()
    if tok:
        logger.debug(f"[SPOTIFY] Token trobat per l'usuari {user}")
    else:
        logger.warning(f"[SPOTIFY] No s'ha trobat cap token per l'usuari {user}")
    return tok


def _get_user_token(request_or_user):
    tok = _get_social_token_obj(request_or_user)
    return tok.token if tok else None


def _refresh_social_token(tok):
    refresh_token = tok.token_secret
    if not refresh_token:
        raise SpotifyAuthError("No refresh token available for Spotify")

    if not tok.app or not tok.app.client_id or not tok.app.secret:
        raise SpotifyAuthError("Spotify app credentials are missing")

    logger.info("[SPOTIFY] Refrescant access token caducat")
    response = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": tok.app.client_id,
            "client_secret": tok.app.secret,
        },
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()

    new_access_token = payload.get("access_token")
    if not new_access_token:
        raise SpotifyAuthError("Spotify token refresh did not return an access token")

    tok.token = new_access_token
    if payload.get("refresh_token"):
        tok.token_secret = payload["refresh_token"]
    expires_in = payload.get("expires_in")
    if expires_in:
        tok.expires_at = timezone.now() + timedelta(seconds=int(expires_in))
    tok.save(update_fields=["token", "token_secret", "expires_at"])
    logger.info("[SPOTIFY] Access token refrescat correctament")
    return tok.token


def _ensure_valid_user_token(request_or_user, force_refresh=False):
    tok = _get_social_token_obj(request_or_user)
    if not tok:
        raise SpotifyAuthError("Spotify account not connected")

    now = timezone.now()
    expires_soon = bool(tok.expires_at and tok.expires_at <= now + timedelta(seconds=60))

    if force_refresh or expires_soon:
        try:
            return _refresh_social_token(tok)
        except requests.RequestException as exc:
            logger.error(f"[SPOTIFY] Error refrescant token: {exc}")
            raise SpotifyAuthError("Unable to refresh Spotify token") from exc

    return tok.token


def _run_spotify_call(request_or_user, operation_name, callback):
    token = _ensure_valid_user_token(request_or_user)
    sp = Spotify(auth=token)
    try:
        return callback(sp)
    except SpotifyException as exc:
        if exc.http_status == 401:
            logger.warning(f"[SPOTIFY] {operation_name}: token invàlid o caducat, reintentant amb refresh")
            token = _ensure_valid_user_token(request_or_user, force_refresh=True)
            sp = Spotify(auth=token)
            return callback(sp)
        raise


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

    logger.debug(f"[GETSONGBPM] Comparant amb {len(results)} resultats")

    exact_match = None
    title_match = None
    fallback = None

    for result in results:
        # Skip non-dictionary results
        if not isinstance(result, dict):
            logger.debug(f"[GETSONGBPM]   - Resultat invàlid (no és diccionari): {type(result)} = {result}")
            continue

        result_title = _normalize_lookup(result.get("title"))
        result_artist_obj = result.get("artist", {})
        if isinstance(result_artist_obj, dict):
            result_artist = _normalize_lookup(result_artist_obj.get("name"))
        else:
            result_artist = _normalize_lookup(str(result_artist_obj)) if result_artist_obj else ""

        logger.debug(f"[GETSONGBPM]   - '{result.get('title')}' by {result_artist_obj.get('name') if isinstance(result_artist_obj, dict) else result_artist_obj}")

        if fallback is None:
            fallback = result
        if result_title == normalized_title:
            if title_match is None:
                title_match = result
                logger.debug(f"[GETSONGBPM]     → Title match!")
            if normalized_artist and (
                normalized_artist in result_artist or result_artist in normalized_artist
            ):
                exact_match = result
                logger.debug(f"[GETSONGBPM]     → Exact match!")
                break

    selected = exact_match or title_match or fallback
    if selected:
        logger.debug(f"[GETSONGBPM] Seleccionat: '{selected.get('title')}' - Match type: {'exact' if exact_match else 'title' if title_match else 'fallback'}")
    return selected


def _remove_accents(text):
    """Elimina accents i diacrítics d'un text."""
    import unicodedata
    if not text:
        return text
    # Normalitzar a NFD (forma descomposta) i eliminar marques diacritiques
    nfd = unicodedata.normalize('NFD', text)
    return ''.join(char for char in nfd if unicodedata.category(char) != 'Mn')


def _simplify_title(title):
    """Simplifica un títol eliminant text entre parèntesis, guions, etc."""
    import re
    # Eliminar text entre parèntesis
    simplified = re.sub(r'\s*\([^)]*\)', '', title)
    # Eliminar text després de guió (com "- Radio Edit")
    simplified = re.sub(r'\s*-\s*.*$', '', simplified)
    return simplified.strip()


def _ultra_simplify_title(title):
    """Simplificació ultra-agressiva: sense accents, parèntesis, guions, només paraules principals."""
    import re
    # Primer simplificar normalment
    simplified = _simplify_title(title)
    # Eliminar accents
    simplified = _remove_accents(simplified)
    # Eliminar feat., ft., with, etc.
    simplified = re.sub(r'\s+(feat\.|ft\.|featuring|with|con)\s+.*$', '', simplified, flags=re.IGNORECASE)
    return simplified.strip()


def _simplify_artist(artist):
    """Simplifica l'artista agafant només el primer si n'hi ha múltiples."""
    # Si hi ha múltiples artistes separats per comes, agafar només el primer
    return artist.split(',')[0].strip()


def _search_getsongbpm(title, artist, api_key):
    """Realitza una cerca a GetSongBPM amb els paràmetres donats."""
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
        payload = response.json()

        if not isinstance(payload, dict):
            logger.debug(f"[GETSONGBPM] Payload no és diccionari: {type(payload)}")
            return None

        results = payload.get("search", [])
        if not results:
            logger.debug(f"[GETSONGBPM] No hi ha resultats a la cerca")
            return None

        logger.debug(f"[GETSONGBPM] API retorna {len(results)} resultats")
        match = _pick_getsongbpm_match(results, title, artist)
        if match and isinstance(match, dict):
            return match

    except (requests.RequestException, ValueError, KeyError):
        pass

    return None


def _get_getsongbpm_features(title, artist):
    api_key = os.environ.get("GETSONGBPM_API_KEY")
    if not api_key:
        return {"bpm": None, "key": None}

    logger.info(f"[GETSONGBPM] Buscant: '{title}' - '{artist}'")

    # Estratègia 1: Cerca amb títol i artista complets
    logger.debug(f"[GETSONGBPM] Estratègia 1: Títol i artista complets")
    match = _search_getsongbpm(title, artist, api_key)
    if match:
        logger.info(f"[GETSONGBPM] ✓ Match trobat amb estratègia 1")

    # Estratègia 2: Si no funciona, simplificar el títol
    if not match:
        simplified_title = _simplify_title(title)
        if simplified_title != title:
            logger.debug(f"[GETSONGBPM] Estratègia 2: Títol simplificat '{simplified_title}'")
            match = _search_getsongbpm(simplified_title, artist, api_key)
            if match:
                logger.info(f"[GETSONGBPM] ✓ Match trobat amb estratègia 2")

    # Estratègia 3: Si no funciona, usar només el primer artista
    if not match and ',' in artist:
        simplified_artist = _simplify_artist(artist)
        logger.debug(f"[GETSONGBPM] Estratègia 3: Primer artista '{simplified_artist}'")
        match = _search_getsongbpm(title, simplified_artist, api_key)
        if match:
            logger.info(f"[GETSONGBPM] ✓ Match trobat amb estratègia 3")

    # Estratègia 4: Títol simplificat + primer artista
    if not match and (',' in artist or '(' in title):
        simplified_title = _simplify_title(title)
        simplified_artist = _simplify_artist(artist)
        logger.debug(f"[GETSONGBPM] Estratègia 4: Ambdós simplificats '{simplified_title}' - '{simplified_artist}'")
        match = _search_getsongbpm(simplified_title, simplified_artist, api_key)
        if match:
            logger.info(f"[GETSONGBPM] ✓ Match trobat amb estratègia 4")

    # Estratègia 5: Només títol (sense artista)
    if not match:
        simplified_title = _simplify_title(title)
        logger.debug(f"[GETSONGBPM] Estratègia 5: Només títol '{simplified_title}'")
        params = {
            "api_key": api_key,
            "type": "song",
            "lookup": f"song:{simplified_title}",
            "limit": 10,
        }
        try:
            response = requests.get(
                f"{GETSONGBPM_BASE_URL}/search/",
                params=params,
                timeout=GETSONGBPM_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                results = payload.get("search", [])
                if results:
                    match = _pick_getsongbpm_match(results, simplified_title, "")
                    if match:
                        logger.info(f"[GETSONGBPM] ✓ Match trobat amb estratègia 5")
        except (requests.RequestException, ValueError, KeyError):
            pass

    # Estratègia 6: Ultra-simplificat (sense accents, feat., etc.)
    if not match:
        ultra_title = _ultra_simplify_title(title)
        ultra_artist = _simplify_artist(artist)
        if ultra_title != _simplify_title(title) or artist != ultra_artist:
            logger.debug(f"[GETSONGBPM] Estratègia 6: Ultra-simplificat '{ultra_title}' - '{ultra_artist}'")
            match = _search_getsongbpm(ultra_title, ultra_artist, api_key)
            if match:
                logger.info(f"[GETSONGBPM] ✓ Match trobat amb estratègia 6")

    # Estratègia 7: Ultra-simplificat només títol
    if not match:
        ultra_title = _ultra_simplify_title(title)
        if ultra_title != _simplify_title(title):
            logger.debug(f"[GETSONGBPM] Estratègia 7: Ultra-simplificat només títol '{ultra_title}'")
            params = {
                "api_key": api_key,
                "type": "song",
                "lookup": f"song:{ultra_title}",
                "limit": 10,
            }
            try:
                response = requests.get(
                    f"{GETSONGBPM_BASE_URL}/search/",
                    params=params,
                    timeout=GETSONGBPM_TIMEOUT,
                )
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict):
                    results = payload.get("search", [])
                    if results:
                        match = _pick_getsongbpm_match(results, ultra_title, "")
                        if match:
                            logger.info(f"[GETSONGBPM] ✓ Match trobat amb estratègia 7")
            except (requests.RequestException, ValueError, KeyError):
                pass

    # Estratègia 8: Buscar text dins dels parèntesis (noms alternatius)
    if not match and '(' in title:
        import re
        parenthesis_content = re.findall(r'\(([^)]+)\)', title)
        if parenthesis_content:
            # Agafar el contingut més llarg dels parèntesis
            alt_name = max(parenthesis_content, key=len)
            # Netejar "feat.", "with", etc.
            alt_name = re.sub(r'^(feat\.|ft\.|featuring|with|con)\s+', '', alt_name, flags=re.IGNORECASE).strip()
            # Si encara té contingut significatiu (més de 3 paraules), buscar-lo
            if len(alt_name.split()) >= 3:
                logger.debug(f"[GETSONGBPM] Estratègia 8: Nom alternatiu dels parèntesis '{alt_name}'")
                simplified_artist = _simplify_artist(artist)
                match = _search_getsongbpm(alt_name, simplified_artist, api_key)
                if match:
                    logger.info(f"[GETSONGBPM] ✓ Match trobat amb estratègia 8 (nom alternatiu)")

    if not match:
        logger.warning(f"[GETSONGBPM] ✗ Cap match després de totes les estratègies: '{title}' - '{artist}'")
        return {"bpm": None, "key": None}

    bpm = match.get("tempo")
    try:
        bpm = float(bpm) if bpm is not None else None
    except (TypeError, ValueError):
        bpm = None

    key_str = match.get('key_of')
    camelot_key = _camelot_from_key_string(key_str)
    logger.info(f"[GETSONGBPM] ✓ Resultat final '{title}': BPM={bpm}, Key={key_str} ({camelot_key})")

    return {
        "bpm": bpm,
        "key": camelot_key,
    }


def _get_musicbrainz_features(title, artist):
    """
    Busca BPM i key a MusicBrainz com a últim recurs.
    MusicBrainz no té BPM directament, però podem buscar
    tags d'usuaris o metadades alternatives.
    """
    logger.info(f"[MUSICBRAINZ] Buscant: '{title}' - '{artist}'")

    try:
        # Buscar recordings que coincideixin
        result = musicbrainzngs.search_recordings(
            artist=artist,
            recording=title,
            limit=5,
            strict=False
        )

        if not result or 'recording-list' not in result:
            logger.warning(f"[MUSICBRAINZ] No s'han trobat resultats per '{title}' - '{artist}'")
            return {"bpm": None, "key": None}

        recordings = result['recording-list']
        if not recordings:
            logger.warning(f"[MUSICBRAINZ] Llista de recordings buida")
            return {"bpm": None, "key": None}

        # Agafar el primer resultat (més rellevant)
        recording = recordings[0]
        recording_id = recording['id']
        recording_title = recording.get('title', 'Unknown')

        logger.debug(f"[MUSICBRAINZ] Recording trobat: '{recording_title}' (ID: {recording_id})")

        # Intentar obtenir detalls del recording incloent tags
        try:
            detailed = musicbrainzngs.get_recording_by_id(
                recording_id,
                includes=['tags', 'artist-credits']
            )

            recording_data = detailed.get('recording', {})
            tags = recording_data.get('tag-list', [])

            # Buscar BPM als tags
            bpm = None
            for tag in tags:
                tag_name = tag.get('name', '').lower()
                # Alguns usuaris etiqueten amb "bpm: 120" o "120 bpm"
                if 'bpm' in tag_name:
                    import re
                    # Extreure número del tag
                    match = re.search(r'(\d+)', tag_name)
                    if match:
                        try:
                            bpm = float(match.group(1))
                            logger.info(f"[MUSICBRAINZ] BPM trobat als tags: {bpm}")
                            break
                        except ValueError:
                            pass

            # Buscar key als tags (alguns usuaris ho etiqueten)
            key = None
            for tag in tags:
                tag_name = tag.get('name', '').strip()
                # Buscar tags que semblin claus musicals (C, D#, Em, etc.)
                if len(tag_name) <= 3 and tag_name[0].isupper():
                    # Podria ser una clau musical
                    camelot = _camelot_from_key_string(tag_name)
                    if camelot:
                        key = camelot
                        logger.info(f"[MUSICBRAINZ] Key trobada als tags: {tag_name} ({camelot})")
                        break

            if bpm or key:
                logger.info(f"[MUSICBRAINZ] Resultat: BPM={bpm}, Key={key}")
                return {"bpm": bpm, "key": key}
            else:
                logger.warning(f"[MUSICBRAINZ] Recording trobat però sense BPM/key als tags")
                return {"bpm": None, "key": None}

        except Exception as e:
            logger.warning(f"[MUSICBRAINZ] Error obtenint detalls del recording: {e}")
            return {"bpm": None, "key": None}

    except musicbrainzngs.WebServiceError as e:
        logger.warning(f"[MUSICBRAINZ] Error de servei web: {e}")
        return {"bpm": None, "key": None}
    except Exception as e:
        logger.error(f"[MUSICBRAINZ] Error inesperat: {e}")
        return {"bpm": None, "key": None}


def get_user_playlists(request_or_user, only_owned=False):
    """
    Obté les playlists de Spotify de l'usuari.

    Args:
        request_or_user: Request object o User
        only_owned: Si True, només retorna playlists propietat de l'usuari.
                   Si False, retorna totes les playlists (incloses les que segueix).

    Returns:
        List[dict]: Llista de playlists amb id, name i owner
    """
    try:
        # Obtenir TOTES les playlists amb paginació
        def fetch_all_playlists(sp):
            all_items = []
            results = sp.current_user_playlists(limit=50)
            all_items.extend(results["items"])

            # Paginar fins a obtenir-les totes
            while results.get("next"):
                results = sp.next(results)
                all_items.extend(results["items"])

            logger.info(f"[SPOTIFY] Total playlists obtingudes: {len(all_items)}")
            return all_items

        all_items = _run_spotify_call(
            request_or_user,
            "current_user_playlists",
            fetch_all_playlists,
        )

        # Log de debug per veure totes les playlists
        for p in all_items:
            logger.debug(f"[SPOTIFY] Playlist: '{p['name']}' (Owner: {p['owner']['id']}, Type: {p.get('type', 'N/A')}, Collaborative: {p.get('collaborative', False)})")

        if only_owned:
            # Obtenir informació de l'usuari actual per filtrar
            current_user = _run_spotify_call(
                request_or_user,
                "current_user",
                lambda sp: sp.current_user(),
            )
            current_user_id = current_user.get('id')
            logger.info(f"[SPOTIFY] Usuari actual: {current_user_id}")

            # Filtrar només les playlists que són propietat de l'usuari actual
            filtered_playlists = [
                {"id": p["id"], "name": p["name"], "owner": p["owner"]["display_name"]}
                for p in all_items
                if p["owner"]["id"] == current_user_id
            ]

            logger.info(f"[SPOTIFY] Playlists totals: {len(all_items)}, propietat de l'usuari: {len(filtered_playlists)}")
            return filtered_playlists
        else:
            # Retornar totes les playlists
            all_playlists = [
                {"id": p["id"], "name": p["name"], "owner": p["owner"]["display_name"]}
                for p in all_items
            ]
            logger.info(f"[SPOTIFY] Playlists totals: {len(all_playlists)}")
            return all_playlists

    except SpotifyAuthError:
        raise
    except Exception as e:
        logger.error(f"[SPOTIFY] Error al carregar playlists: {e}")
        return []


def _chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def get_playlist_tracks_basic(request_or_user, playlist_id):
    """
    Obté només la metadata bàsica de les cançons (títol, artista, ID)
    sense processar BPM ni clau musical. Molt més ràpid.
    """
    logger.info(f"[SPOTIFY] Carregant tracks bàsics de la playlist {playlist_id}")

    try:
        def fetch_tracks(sp_user):
            all_items = []
            results = sp_user.playlist_items(
                playlist_id,
                fields="items.track.id,items.track.name,items.track.artists,items.track.album.images,next",
                additional_types=["track"]
            )
            all_items.extend(results["items"])
            while results.get("next"):
                results = sp_user.next(results)
                all_items.extend(results["items"])
            return all_items

        all_items = _run_spotify_call(request_or_user, "playlist_items_basic", fetch_tracks)
    except SpotifyAuthError:
        raise
    except Exception as e:
        logger.error(f"[SPOTIFY] Error al carregar tracks bàsics: {e}")
        return []

    logger.info(f"[SPOTIFY] {len(all_items)} tracks trobats a la playlist")

    out = []
    for it in all_items:
        tr = it["track"]
        sid = tr["id"]
        if not sid:
            continue

        # Obtenir la imatge de l'àlbum (normalment hi ha 3 mides, agafem la mitjana)
        album_image_url = None
        if tr.get("album") and tr["album"].get("images"):
            images = tr["album"]["images"]
            if images:
                # Agafar la imatge mitjana (normalment 300x300)
                album_image_url = images[1]["url"] if len(images) > 1 else images[0]["url"]

        out.append({
            "id": sid,
            "title": tr["name"],
            "artist": ", ".join(a["name"] for a in tr["artists"]),
            "album_image_url": album_image_url,
            "bpm": None,
            "key": None,
        })

    return out


def get_playlist_tracks(request_or_user, playlist_id):
    logger.info(f"[SPOTIFY] Carregant tracks de la playlist {playlist_id}")

    try:
        def fetch_tracks(sp_user):
            all_items = []
            results = sp_user.playlist_items(
                playlist_id,
                fields="items.track.id,items.track.name,items.track.artists,items.track.album.images,next",
                additional_types=["track"]
            )
            all_items.extend(results["items"])
            while results.get("next"):
                results = sp_user.next(results)
                all_items.extend(results["items"])
            return all_items

        all_items = _run_spotify_call(request_or_user, "playlist_items", fetch_tracks)
    except SpotifyAuthError:
        raise
    except Exception as e:
        logger.error(f"[SPOTIFY] Error al carregar tracks de playlist: {e}")
        return []
    logger.info(f"[SPOTIFY] Tracks trobats a la playlist: {len(all_items)}")

    ids, meta = [], {}
    for it in all_items:
        tr = it["track"]
        sid = tr["id"]
        if not sid:
            continue
        ids.append(sid)

        # Obtenir la imatge de l'àlbum
        album_image_url = None
        if tr.get("album") and tr["album"].get("images"):
            images = tr["album"]["images"]
            if images:
                album_image_url = images[1]["url"] if len(images) > 1 else images[0]["url"]

        meta[sid] = {
            "title": tr["name"],
            "artist": ", ".join(a["name"] for a in tr["artists"]),
            "album_image_url": album_image_url
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

        # Fallback 1: GetSongBPM
        if not feature_data.get("bpm") and not feature_data.get("key"):
            logger.debug(f"[FALLBACK] Spotify no té features per '{meta[sid]['title']}', provant GetSongBPM")
            feature_data = _get_getsongbpm_features(meta[sid]["title"], meta[sid]["artist"])

        # Fallback 2: MusicBrainz
        if not feature_data.get("bpm") and not feature_data.get("key"):
            logger.debug(f"[FALLBACK] GetSongBPM no té features per '{meta[sid]['title']}', provant MusicBrainz")
            feature_data = _get_musicbrainz_features(meta[sid]["title"], meta[sid]["artist"])

        out.append({
            "id": sid,
            "title": meta[sid]["title"],
            "artist": meta[sid]["artist"],
            "album_image_url": meta[sid].get("album_image_url"),
            "bpm": feature_data.get("bpm"),
            "key": feature_data.get("key"),
        })

    logger.info(f"[SPOTIFY] Resultat final: {len(out)} tracks amb metadades")
    return out


def get_audio_features_for_songs(request_or_user, song_ids_with_metadata):
    """
    Obté BPM i clau musical per una llista de cançons.

    Args:
        song_ids_with_metadata: List[dict] amb 'id', 'title', 'artist'

    Returns:
        dict: {spotify_id: {'bpm': float, 'key': str}}
    """
    if not song_ids_with_metadata:
        return {}

    try:
        def fetch_audio_features(sp_user, chunk):
            return sp_user.audio_features(tracks=chunk)

        ids = [s['id'] for s in song_ids_with_metadata]
        meta = {s['id']: {'title': s['title'], 'artist': s['artist']}
                for s in song_ids_with_metadata}

        features_map = {}

        # Intentar obtenir features de Spotify en chunks de 50
        for idx, chunk in enumerate(_chunked(ids, 50)):
            try:
                logger.debug(f"[SPOTIFY] Carregant features chunk {idx+1} ({len(chunk)} tracks)")
                feats = _run_spotify_call(
                    request_or_user,
                    f"audio_features chunk {idx+1}",
                    lambda sp_user, c=chunk: fetch_audio_features(sp_user, c),
                )
                for f in feats:
                    if not f:
                        continue
                    features_map[f["id"]] = {
                        "bpm": f.get("tempo"),
                        "key": _camelot_from_key_mode(f.get("key"), f.get("mode"))
                    }
            except SpotifyAuthError:
                raise
            except Exception as e:
                logger.error(f"[SPOTIFY] ERROR al carregar audio features per chunk {idx+1}: {e}")
                # Si falla Spotify, utilitzar GetSongBPM per aquest chunk
                for sid in chunk:
                    if sid not in features_map:
                        features_map[sid] = _get_getsongbpm_features(
                            meta[sid]["title"],
                            meta[sid]["artist"]
                        )

        # Per les cançons sense features, intentar GetSongBPM i després MusicBrainz
        for sid in ids:
            if sid not in features_map or (
                not features_map[sid].get("bpm") and not features_map[sid].get("key")
            ):
                # Fallback 1: GetSongBPM
                logger.debug(f"[FALLBACK] Spotify no té features, provant GetSongBPM")
                features_map[sid] = _get_getsongbpm_features(
                    meta[sid]["title"],
                    meta[sid]["artist"]
                )

                # Fallback 2: MusicBrainz si GetSongBPM tampoc ho té
                if not features_map[sid].get("bpm") and not features_map[sid].get("key"):
                    logger.debug(f"[FALLBACK] GetSongBPM no té features, provant MusicBrainz")
                    features_map[sid] = _get_musicbrainz_features(
                        meta[sid]["title"],
                        meta[sid]["artist"]
                    )

        return features_map
    except SpotifyAuthError:
        raise
    except Exception as e:
        logger.error(f"[SPOTIFY] Error al inicialitzar client d'audio features: {e}")
        return {}


def search_spotify_tracks(request_or_user, query, limit=10):
    """
    Cerca cançons a Spotify.

    Args:
        request_or_user: Request object o User
        query: Text de cerca
        limit: Màxim de resultats

    Returns:
        List[dict]: Llista de cançons amb id, title, artist, album_image_url
    """
    try:
        results = _run_spotify_call(
            request_or_user,
            "track_search",
            lambda sp: sp.search(q=query, type='track', limit=limit),
        )

        tracks = []
        for item in results['tracks']['items']:
            album_image_url = None
            if item.get('album') and item['album'].get('images'):
                images = item['album']['images']
                if images:
                    album_image_url = images[1]['url'] if len(images) > 1 else images[0]['url']

            tracks.append({
                'id': item['id'],
                'title': item['name'],
                'artist': ', '.join(a['name'] for a in item['artists']),
                'album_image_url': album_image_url,
            })

        logger.info(f"[SPOTIFY] Cerca '{query}': {len(tracks)} resultats")
        return tracks

    except SpotifyAuthError:
        raise
    except Exception as e:
        logger.error(f"[SPOTIFY] Error al cercar '{query}': {e}")
        return []
