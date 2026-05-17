import os
import logging
import time
from datetime import timedelta

from allauth.socialaccount.models import SocialToken
from django.conf import settings
from django.utils import timezone
from spotipy import Spotify
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyClientCredentials
import requests
import musicbrainzngs

logger = logging.getLogger(__name__)

# Configurar MusicBrainz
musicbrainzngs.set_useragent("DJJukebox", "1.0", "https://github.com/yourusername/dj_jukebox")

GETSONGBPM_BASE_URL = "https://api.getsong.co"
GETSONGBPM_TIMEOUT = 5
TUNEBAT_BASE_URL = "https://api.tunebat.com/api/tracks/search"
TUNEBAT_TIMEOUT = 8
TUNEBAT_CACHE_TTL_SECONDS = 3600
_TUNEBAT_CACHE = {}
_TUNEBAT_RATE_LIMIT_UNTIL = 0.0
_TUNEBAT_NEXT_REQUEST_AT = 0.0


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

    app_client_id = None
    app_client_secret = None
    if tok.app and tok.app.client_id and tok.app.secret:
        app_client_id = tok.app.client_id
        app_client_secret = tok.app.secret
    elif settings.SPOTIFY_CLIENT_ID and settings.SPOTIFY_CLIENT_SECRET:
        # Fallback útil quan SocialApp no té creds ben configurades.
        app_client_id = settings.SPOTIFY_CLIENT_ID
        app_client_secret = settings.SPOTIFY_CLIENT_SECRET
        logger.warning("[SPOTIFY] SocialApp sense credencials, fent fallback a settings SPOTIFY_CLIENT_*")
    else:
        raise SpotifyAuthError("Spotify app credentials are missing")

    logger.info("[SPOTIFY] Refrescant access token caducat")
    response = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": app_client_id,
            "client_secret": app_client_secret,
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


def _get_cc_spotify():
    """Returns a Spotify client using app Client Credentials (env vars). No user OAuth needed."""
    return Spotify(auth_manager=SpotifyClientCredentials(
        client_id=settings.SPOTIFY_CLIENT_ID,
        client_secret=settings.SPOTIFY_CLIENT_SECRET,
    ))


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

    normalized = key_string.strip().replace('♯', '#').replace('♭', 'b')
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


def _normalize_search_text(text):
    """Text de cerca robust: sense accents ni puntuació sorollosa."""
    import re
    text = _remove_accents(text or "")
    text = re.sub(r"[\"'`´‘’“”]", "", text)
    text = re.sub(r"[^A-Za-z0-9\s-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_search_text_soft(text):
    """Normalització suau: manté comes i ! per títols on ajuden al match."""
    import re
    text = _remove_accents(text or "")
    text = re.sub(r"[\"'`´‘’“”]", "", text)
    text = re.sub(r"[^A-Za-z0-9\s,\-!]", " ", text)
    text = re.sub(r"!{2,}", "!", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,-!")


def _extract_remix_hint(title):
    """Extreu una pista curta útil per cercar remixes (p. ex. 'Basement Boy')."""
    import re
    if not title:
        return ""
    # Agafem el fragment després del primer guió, on sovint hi ha "Remix/Mix/Edit"
    parts = re.split(r"\s*-\s*", title, maxsplit=1)
    if len(parts) < 2:
        return ""
    tail = _remove_accents(parts[1])
    tail = re.sub(r"[\"'`´‘’“”()]", " ", tail)
    # Treure paraules de format que no ajuden a trobar la cançó
    tail = re.sub(
        r"\b(remix|radio|edit|extended|version|mix|original|official|feat|featuring)\b",
        " ",
        tail,
        flags=re.IGNORECASE,
    )
    tokens = [t for t in re.findall(r"[A-Za-z0-9]+", tail) if len(t) > 2]
    if not tokens:
        return ""
    # Màxim 2 paraules per evitar queries massa llargues
    return " ".join(tokens[:2]).strip()


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


def _get_getsongbpm_features(title, artist, spotify_id=None):
    import re
    import json
    from urllib.parse import quote, urljoin

    global _TUNEBAT_RATE_LIMIT_UNTIL, _TUNEBAT_NEXT_REQUEST_AT

    def _fetch_with_throttle(fetcher, url, timeout=45):
        global _TUNEBAT_NEXT_REQUEST_AT
        now = time.time()
        wait = max(0.0, _TUNEBAT_NEXT_REQUEST_AT - now)
        if wait > 0:
            logger.info("[SCRAPLING] Throttle %.1fs abans de GET %s", wait, url)
            time.sleep(wait)
        logger.info("[SCRAPLING] GET %s (timeout=%s)", url, timeout)
        t0 = time.time()
        res = fetcher.get(url, timeout=timeout)
        status = getattr(res, "status", "?")
        logger.info("[SCRAPLING] GET done status=%s (%.1fs) %s", status, time.time() - t0, url)
        _TUNEBAT_NEXT_REQUEST_AT = time.time() + 1.5
        return res

    def _to_float(value):
        if value is None:
            return None
        m = re.search(r"-?\d+(?:\.\d+)?", str(value))
        return float(m.group(0)) if m else None

    def _to_int(value):
        if value is None:
            return None
        m = re.search(r"-?\d+", str(value))
        return int(m.group(0)) if m else None

    def _track_id(t):
        return (
            t.get("Id") or t.get("id") or
            t.get("SpotifyId") or t.get("spotifyId") or
            t.get("TrackId") or t.get("trackId") or ""
        )

    def _track_name(t):
        return t.get("Name") or t.get("name") or t.get("Title") or t.get("title") or ""

    def _track_artists_str(t):
        artists = (
            t.get("ArtistNames") or t.get("artistNames") or
            t.get("Artists") or t.get("artists") or []
        )
        if isinstance(artists, list):
            parts = []
            for a in artists:
                if isinstance(a, dict):
                    parts.append(a.get("Name") or a.get("name") or "")
                elif isinstance(a, str):
                    parts.append(a)
            return ", ".join(p for p in parts if p)
        return str(artists) if artists else ""

    def _extract_track_fields(t):
        bpm = _to_float(
            t.get("Bpm") or t.get("bpm") or t.get("Tempo") or t.get("tempo")
        )
        camelot = (
            t.get("Camelot") or t.get("camelot") or
            t.get("KeyCamelot") or t.get("keyCamelot")
        )
        key_text = (
            t.get("Key") or t.get("key") or
            t.get("KeyString") or t.get("keyString") or
            t.get("ActualKey") or t.get("actualKey")
        )
        popularity = _to_int(t.get("Popularity") or t.get("popularity"))
        key_camelot = camelot or (_camelot_from_key_string(str(key_text)) if key_text else None)
        return {
            "bpm": bpm,
            "key": key_camelot,
            "camelot": camelot,
            "key_text": str(key_text) if key_text else None,
            "popularity": popularity,
        }

    def _parse_next_data_tracks(html):
        """Extract tracks list from __NEXT_DATA__ JSON embedded in page HTML."""
        m = re.search(
            r'<script[^>]+id=["\'"]__NEXT_DATA__["\'"][^>]*>\s*(\{.*?\})\s*</script>',
            html, re.DOTALL | re.IGNORECASE,
        )
        if not m:
            logger.info("[TUNEBAT] No __NEXT_DATA__ script tag trobat")
            return []
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError as e:
            logger.info("[TUNEBAT] Error parsejant __NEXT_DATA__: %s", e)
            return []

        page_props = data.get("props", {}).get("pageProps", {})

        for key in ("tracks", "searchResults", "results", "items"):
            val = page_props.get(key)
            if isinstance(val, list) and val:
                logger.info("[TUNEBAT] __NEXT_DATA__ tracks via pageProps.%s: %s", key, len(val))
                return val

        data_obj = page_props.get("data")
        if isinstance(data_obj, dict):
            for key in ("tracks", "results", "items"):
                val = data_obj.get(key)
                if isinstance(val, list) and val:
                    logger.info("[TUNEBAT] __NEXT_DATA__ tracks via pageProps.data.%s: %s", key, len(val))
                    return val

        dehydrated = page_props.get("dehydratedState", {})
        for q in (dehydrated.get("queries", []) if isinstance(dehydrated, dict) else []):
            q_data = (q.get("state", {}).get("data", {}) if isinstance(q, dict) else {})
            for key in ("tracks", "results", "items"):
                val = q_data.get(key) if isinstance(q_data, dict) else None
                if isinstance(val, list) and val:
                    logger.info("[TUNEBAT] __NEXT_DATA__ tracks via dehydratedState query.%s: %s", key, len(val))
                    return val

        logger.info("[TUNEBAT] __NEXT_DATA__ present sense llista de tracks. Keys pageProps: %s", list(page_props.keys()))
        return []

    def _match_in_tracks(tracks, expected_spotify_id, t_title, t_artist):
        """Find best matching track, return extracted fields dict or None."""
        norm_title = _normalize_lookup(t_title)
        norm_first_artist = _normalize_lookup((t_artist or "").split(",")[0].strip())

        if expected_spotify_id:
            for t in tracks:
                if _track_id(t) == expected_spotify_id:
                    fields = _extract_track_fields(t)
                    if fields["bpm"] or fields["camelot"]:
                        logger.info(
                            "[TUNEBAT] Match per spotify_id=%s '%s' BPM=%s Key=%s Pop=%s",
                            expected_spotify_id, _track_name(t), fields["bpm"], fields["key"], fields["popularity"],
                        )
                        return fields
                    logger.info("[TUNEBAT] spotify_id=%s trobat però sense BPM/Key", expected_spotify_id)

        best_title = None
        for t in tracks:
            if _normalize_lookup(_track_name(t)) != norm_title:
                continue
            fields = _extract_track_fields(t)
            if not (fields["bpm"] or fields["camelot"]):
                continue
            t_artists = _normalize_lookup(_track_artists_str(t))
            if norm_first_artist and (norm_first_artist in t_artists or t_artists.startswith(norm_first_artist)):
                logger.info(
                    "[TUNEBAT] Match per title+artist '%s' BPM=%s Key=%s Pop=%s",
                    _track_name(t), fields["bpm"], fields["key"], fields["popularity"],
                )
                return fields
            if best_title is None:
                best_title = (t, fields)

        if best_title:
            t, fields = best_title
            logger.info(
                "[TUNEBAT] Match per title (primer) '%s' BPM=%s Key=%s Pop=%s",
                _track_name(t), fields["bpm"], fields["key"], fields["popularity"],
            )
            return fields

        return None

    def _search_and_extract(fetcher, search_query, expected_spotify_id, t_title, t_artist):
        """Fetch Tunebat Search page, parse results, return matched fields or None."""
        global _TUNEBAT_RATE_LIMIT_UNTIL
        search_url = f"https://tunebat.com/Search?q={quote(search_query)}"
        max_attempts = int(getattr(settings, "TUNEBAT_SEARCH_RETRIES", 2))
        retry_pause = float(getattr(settings, "TUNEBAT_SEARCH_RETRY_PAUSE_SECONDS", 2.5))

        for attempt in range(1, max_attempts + 1):
            now = time.time()
            if now < _TUNEBAT_RATE_LIMIT_UNTIL:
                logger.warning(
                    "[TUNEBAT] Cooldown actiu (%.1fs), saltant query '%s'",
                    max(0.0, _TUNEBAT_RATE_LIMIT_UNTIL - now), search_query,
                )
                return None

            logger.info("[TUNEBAT] Search intent %s/%s query='%s'", attempt, max_attempts, search_query)
            try:
                res = _fetch_with_throttle(fetcher, search_url, timeout=45)
                status = getattr(res, "status", None)
                logger.info("[TUNEBAT] Search status=%s query='%s'", status, search_query)

                if status == 429:
                    _TUNEBAT_RATE_LIMIT_UNTIL = time.time() + 30.0
                    logger.warning("[TUNEBAT] 429 a Search, cooldown 30s query='%s'", search_query)
                    if attempt < max_attempts:
                        time.sleep(retry_pause * attempt)
                    continue

                if status and status >= 400:
                    logger.warning("[TUNEBAT] Search status=%s query='%s'", status, search_query)
                    if attempt < max_attempts:
                        time.sleep(retry_pause)
                    continue

                html = res.html_content or ""
            except Exception as e:
                logger.warning("[TUNEBAT] Search exception query='%s' intent=%s: %s", search_query, attempt, e)
                if attempt < max_attempts:
                    time.sleep(retry_pause)
                continue

            info_links = re.findall(
                r'href=["\']([^"\']*?/Info/[^"\']+)["\']',
                html, re.IGNORECASE,
            )
            if not info_links:
                info_links = re.findall(r'(https?://tunebat\.com/Info/[^\s"\'<>]+)', html, re.IGNORECASE)
            if not info_links:
                escaped = re.findall(r'\\u002FInfo\\u002F([^"\\]+)', html, re.IGNORECASE)
                info_links = ["/Info/" + p for p in escaped]

            logger.info("[TUNEBAT] /Info links trobats: %s query='%s'", len(info_links), search_query)

            tracks = _parse_next_data_tracks(html)
            if tracks:
                result = _match_in_tracks(tracks, expected_spotify_id, t_title, t_artist)
                if result:
                    if expected_spotify_id:
                        for lnk in info_links:
                            if lnk.rstrip("/").split("/")[-1] == expected_spotify_id:
                                result["tunebat_url"] = urljoin("https://tunebat.com", lnk)
                                break
                    if not result.get("tunebat_url") and info_links:
                        result["tunebat_url"] = urljoin("https://tunebat.com", info_links[0])
                    return result
                logger.info(
                    "[TUNEBAT] __NEXT_DATA__ tenia %s tracks però cap match per '%s' - '%s'",
                    len(tracks), t_title, t_artist,
                )
            else:
                logger.info("[TUNEBAT] Search HTML (primers 1500 chars): %s", html[:1500])

            if attempt < max_attempts:
                time.sleep(retry_pause)

        return None

    # --- Main ---
    logger.info("[TUNEBAT] Buscant via scraping: '%s' - '%s'", title, artist)

    def _clean(text):
        t = re.sub(r'[\u0022\u0027`\u00b4\u2018\u2019\u201c\u201d]', "", text or "")
        return re.sub(r"\s+", " ", t).strip()

    clean_title = _clean(title)
    clean_artist = _clean(artist)
    cache_key = (spotify_id or "", clean_title.lower(), clean_artist.lower())

    now = time.time()
    cached = _TUNEBAT_CACHE.get(cache_key)
    if cached and (now - cached["ts"] <= TUNEBAT_CACHE_TTL_SECONDS):
        return cached["data"]

    if now < _TUNEBAT_RATE_LIMIT_UNTIL:
        logger.warning(
            "[TUNEBAT] Cooldown actiu (%.1fs), saltant per '%s'",
            max(0.0, _TUNEBAT_RATE_LIMIT_UNTIL - now), title,
        )
        result = {"bpm": None, "key": None, "tunebat_url": None}
        _TUNEBAT_CACHE[cache_key] = {"ts": now, "data": result}
        return result

    try:
        from scrapling import Fetcher
        try:
            Fetcher.configure(huge_tree=True)
        except Exception:
            pass
    except Exception as e:
        logger.error("[TUNEBAT] Scrapling no disponible: %s", e)
        return {"bpm": None, "key": None, "tunebat_url": None}

    fetcher = Fetcher

    q1 = _normalize_search_text(_simplify_title(clean_title))
    q2 = _normalize_search_text(clean_title)
    search_queries = list(dict.fromkeys(q for q in [q1, q2] if q))[:2]
    logger.info("[TUNEBAT] Search queries (title-only): %s", search_queries)

    matched = None
    for query in search_queries:
        try:
            matched = _search_and_extract(fetcher, query, spotify_id, title, artist)
            if matched:
                break
        except Exception as e:
            logger.debug("[TUNEBAT] Error a _search_and_extract query='%s': %s", query, e)

    if not matched:
        logger.warning("[TUNEBAT] ✗ Cap match a Search per '%s' - '%s'", title, artist)
        result = {"bpm": None, "key": None, "tunebat_url": None}
        _TUNEBAT_CACHE[cache_key] = {"ts": now, "data": result}
        return result

    result = {
        "bpm": matched.get("bpm"),
        "key": matched.get("key"),
        "camelot": matched.get("camelot"),
        "key_text": matched.get("key_text"),
        "popularity": matched.get("popularity"),
        "tunebat_url": matched.get("tunebat_url"),
    }
    logger.info(
        "[TUNEBAT] ✓ Resultat '%s': BPM=%s Key=%s Popularity=%s URL=%s",
        title, result.get("bpm"), result.get("key"), result.get("popularity"), result.get("tunebat_url"),
    )
    _TUNEBAT_CACHE[cache_key] = {"ts": now, "data": result}
    return result


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


def get_playlist_tracks_basic(playlist_id):
    """
    Obté només la metadata bàsica de les cançons (títol, artista, ID)
    sense processar BPM ni clau musical. Molt més ràpid.
    Usa Client Credentials — no requereix OAuth d'usuari.
    """
    logger.info(f"[SPOTIFY] Carregant tracks bàsics de la playlist {playlist_id}")

    try:
        sp = _get_cc_spotify()
        all_items = []
        results = sp.playlist_items(
            playlist_id,
            fields="items.track.id,items.track.name,items.track.artists,items.track.album.images,items.track.preview_url,next",
            additional_types=["track"]
        )
        all_items.extend(results["items"])
        while results.get("next"):
            results = sp.next(results)
            all_items.extend(results["items"])
    except Exception as e:
        logger.error(f"[SPOTIFY] Error al carregar tracks bàsics: {e}")
        return []

    logger.info(f"[SPOTIFY] {len(all_items)} tracks trobats a la playlist")

    out = []
    for it in all_items:
        tr = it.get("track") or {}
        sid = tr.get("id")
        if not sid:
            continue

        title = tr.get("name")
        artists = tr.get("artists") or []
        artist_names = [
            a.get("name")
            for a in artists
            if isinstance(a, dict) and a.get("name")
        ]
        if not title or not artist_names:
            logger.warning(
                "[SPOTIFY] Track ignorat per metadata incompleta: id=%s title=%s artists=%s",
                sid, title, artists
            )
            continue

        # Obtenir la imatge de l'àlbum (normalment hi ha 3 mides, agafem la mitjana)
        album_image_url = None
        album = tr.get("album") or {}
        if album.get("images"):
            images = album["images"]
            if images:
                # Agafar la imatge mitjana (normalment 300x300)
                album_image_url = images[1]["url"] if len(images) > 1 else images[0]["url"]

        out.append({
            "id": sid,
            "title": title,
            "artist": ", ".join(artist_names),
            "album_image_url": album_image_url,
            "preview_url": tr.get("preview_url"),
            "bpm": None,
            "key": None,
        })

    return out


def get_playlist_tracks(playlist_id):
    """
    Carrega els tracks d’una playlist amb BPM i key.
    Usa Client Credentials — no requereix OAuth d’usuari.
    Nota: la playlist ha de ser pública o col·laborativa.
    """
    logger.info(f"[SPOTIFY] Carregant tracks de la playlist {playlist_id}")

    try:
        sp = _get_cc_spotify()
        all_items = []
        results = sp.playlist_items(
            playlist_id,
            fields="items.track.id,items.track.name,items.track.artists,items.track.album.images,next",
            additional_types=["track"]
        )
        all_items.extend(results["items"])
        while results.get("next"):
            results = sp.next(results)
            all_items.extend(results["items"])
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
            logger.debug(f"[SPOTIFY] Carregant features chunk {idx+1} ({len(chunk)} tracks)")
            feats = sp.audio_features(tracks=chunk)
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
            feature_data = _get_getsongbpm_features(meta[sid]["title"], meta[sid]["artist"], sid)

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


def get_audio_features_for_songs(song_ids_with_metadata):
    """
    Obté BPM i clau musical per una llista de cançons.
    Usa Client Credentials — no requereix OAuth d'usuari.

    Args:
        song_ids_with_metadata: List[dict] amb 'id', 'title', 'artist'

    Returns:
        dict: {spotify_id: {'bpm': float, 'key': str}}
    """
    if not song_ids_with_metadata:
        return {}

    try:
        sp = _get_cc_spotify()
        ids = [s['id'] for s in song_ids_with_metadata]
        meta = {s['id']: {'title': s['title'], 'artist': s['artist']}
                for s in song_ids_with_metadata}

        features_map = {}

        for idx, chunk in enumerate(_chunked(ids, 50)):
            try:
                logger.debug(f"[SPOTIFY] Carregant features chunk {idx+1} ({len(chunk)} tracks)")
                feats = sp.audio_features(tracks=chunk)
                for f in feats:
                    if not f:
                        continue
                    features_map[f["id"]] = {
                        "bpm": f.get("tempo"),
                        "key": _camelot_from_key_mode(f.get("key"), f.get("mode"))
                    }
            except Exception as e:
                logger.error(f"[SPOTIFY] ERROR al carregar audio features per chunk {idx+1}: {e}")
                for sid in chunk:
                    if sid not in features_map:
                        features_map[sid] = _get_getsongbpm_features(
                            meta[sid]["title"],
                            meta[sid]["artist"],
                            sid,
                        )

        for sid in ids:
            if sid not in features_map or (
                not features_map[sid].get("bpm") and not features_map[sid].get("key")
            ):
                logger.debug(f"[FALLBACK] Spotify no té features, provant Tunebat")
                features_map[sid] = _get_getsongbpm_features(
                    meta[sid]["title"],
                    meta[sid]["artist"],
                    sid,
                )

                if not features_map[sid].get("bpm") and not features_map[sid].get("key"):
                    logger.debug(f"[FALLBACK] Tunebat no té features, provant MusicBrainz")
                    features_map[sid] = _get_musicbrainz_features(
                        meta[sid]["title"],
                        meta[sid]["artist"]
                    )

        return features_map
    except Exception as e:
        logger.error(f"[SPOTIFY] Error al inicialitzar client d'audio features: {e}")
        return {}


def get_spotify_audio_features_only(song_ids_with_metadata):
    """
    Obté només audio features de Spotify (tempo/key) sense cap fallback lent.
    Útil en endpoints HTTP on cal latència baixa i evitar timeouts.
    """
    if not song_ids_with_metadata:
        return {}

    try:
        sp = _get_cc_spotify()
        ids = [s['id'] for s in song_ids_with_metadata if s.get('id')]
        features_map = {}

        for idx, chunk in enumerate(_chunked(ids, 50)):
            try:
                logger.debug(f"[SPOTIFY] (only) Carregant features chunk {idx+1} ({len(chunk)} tracks)")
                feats = sp.audio_features(tracks=chunk)
                for f in feats:
                    if not f:
                        continue
                    features_map[f["id"]] = {
                        "bpm": f.get("tempo"),
                        "key": _camelot_from_key_mode(f.get("key"), f.get("mode"))
                    }
            except Exception as e:
                logger.error(f"[SPOTIFY] (only) ERROR al carregar audio features chunk {idx+1}: {e}")

        return features_map
    except Exception as e:
        logger.error(f"[SPOTIFY] (only) Error al inicialitzar client d'audio features: {e}")
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


def search_spotify_tracks_public(query, limit=20):
    """Search Spotify using app client credentials — no user OAuth required."""
    try:
        sp = Spotify(auth_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET,
        ))
        results = sp.search(q=query, type='track', limit=limit)
        tracks = []
        for item in results['tracks']['items']:
            album_image_url = None
            if item.get('album') and item['album'].get('images'):
                images = item['album']['images']
                album_image_url = images[1]['url'] if len(images) > 1 else images[0]['url']
            tracks.append({
                'id': item['id'],
                'title': item['name'],
                'artist': ', '.join(a['name'] for a in item['artists']),
                'album_image_url': album_image_url,
            })
        logger.info(f"[SPOTIFY] Cerca pública '{query}': {len(tracks)} resultats")
        return tracks
    except Exception as e:
        logger.error(f"[SPOTIFY] Error a cerca pública '{query}': {e}")
        return []


def add_track_to_playlist(request_or_user, playlist_id, track_id):
    """
    Afegeix una cançó a una playlist de Spotify.

    Args:
        request_or_user: Request object o User
        playlist_id: Spotify playlist ID
        track_id: Spotify track ID

    Returns:
        dict: resposta de Spotify amb snapshot_id
    """
    track_uri = track_id if str(track_id).startswith("spotify:track:") else f"spotify:track:{track_id}"

    try:
        result = _run_spotify_call(
            request_or_user,
            "playlist_add_items",
            lambda sp: sp.playlist_add_items(playlist_id, [track_uri]),
        )
        logger.info(f"[SPOTIFY] Cançó {track_id} afegida a la playlist {playlist_id}")
        return result
    except SpotifyAuthError:
        raise
    except Exception as e:
        logger.error(f"[SPOTIFY] Error afegint {track_id} a la playlist {playlist_id}: {e}")
        raise


def remove_track_from_playlist(request_or_user, playlist_id, track_id):
    """
    Elimina una única ocurrència d'una cançó d'una playlist de Spotify.

    Si hi ha duplicats a la playlist, només n'elimina la primera.
    """
    track_uri = track_id if str(track_id).startswith("spotify:track:") else f"spotify:track:{track_id}"

    try:
        def find_first_occurrence(sp):
            position = 0
            results = sp.playlist_items(
                playlist_id,
                fields="items.track.id,next",
                additional_types=["track"],
            )

            while True:
                for item in results.get("items", []):
                    track = item.get("track") or {}
                    if track.get("id") == track_id:
                        return position
                    position += 1

                if not results.get("next"):
                    break
                results = sp.next(results)

            return None

        position = _run_spotify_call(
            request_or_user,
            "playlist_find_track_for_removal",
            find_first_occurrence,
        )

        if position is None:
            logger.warning(f"[SPOTIFY] No s'ha trobat {track_id} a la playlist {playlist_id} per eliminar")
            return None

        result = _run_spotify_call(
            request_or_user,
            "playlist_remove_specific_occurrence",
            lambda sp: sp.playlist_remove_specific_occurrences_of_items(
                playlist_id,
                [{"uri": track_uri, "positions": [position]}],
            ),
        )
        logger.info(f"[SPOTIFY] Cançó {track_id} eliminada de la playlist {playlist_id} a la posició {position}")
        return result
    except SpotifyAuthError:
        raise
    except Exception as e:
        logger.error(f"[SPOTIFY] Error eliminant {track_id} de la playlist {playlist_id}: {e}")
        raise
