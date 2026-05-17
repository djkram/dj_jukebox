"""
Anàlisi d'àudio local per detectar BPM i Key utilitzant librosa.
Utilitzat com a fallback quan les APIs de Spotify/GetSongBPM no tenen dades.
"""
import os
import shutil
import tempfile
import logging
import re
import unicodedata
from django.conf import settings

logger = logging.getLogger(__name__)
_YTDLP_DISABLED_UNTIL = 0.0


def _ytdlp_bot_cooldown_seconds():
    return int(getattr(settings, "YTDLP_BOT_COOLDOWN_SECONDS", 900))


def _is_ytdlp_bot_detection_error(stderr):
    stderr = (stderr or "").lower()
    return "sign in to confirm" in stderr and "not a bot" in stderr


def _normalize_search_text(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[\"'`´‘’“”()\[\]{}]", " ", text)
    text = re.sub(r"[^A-Za-z0-9\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_search_text_soft(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[\"'`´‘’“”]", "", text)
    text = re.sub(r"[^A-Za-z0-9\s,\-!]", " ", text)
    text = re.sub(r"!{2,}", "!", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(" ,-!")


def _simplify_title_for_search(title):
    if not title:
        return ""
    # Treure fragments de versió/remix que embruten la cerca
    simple = re.sub(r"\s*\([^)]*\)", "", title)
    simple = re.sub(r"\s+-\s+.*$", "", simple)
    return _normalize_search_text(simple)


def _first_artist_for_search(artist):
    if not artist:
        return ""
    return _normalize_search_text(artist.split(",")[0].strip())


# Mapa de pitch class a notació musical
PITCH_CLASS_TO_NOTE = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# Mapa de Camelot wheel
CAMELOT_MAP = {
    # Major keys (B side)
    ('C', 'major'): '8B',
    ('G', 'major'): '9B',
    ('D', 'major'): '10B',
    ('A', 'major'): '11B',
    ('E', 'major'): '12B',
    ('B', 'major'): '1B',
    ('F#', 'major'): '2B',
    ('C#', 'major'): '3B',
    ('G#', 'major'): '4B',
    ('D#', 'major'): '5B',
    ('A#', 'major'): '6B',
    ('F', 'major'): '7B',

    # Minor keys (A side)
    ('A', 'minor'): '8A',
    ('E', 'minor'): '9A',
    ('B', 'minor'): '10A',
    ('F#', 'minor'): '11A',
    ('C#', 'minor'): '12A',
    ('G#', 'minor'): '1A',
    ('D#', 'minor'): '2A',
    ('A#', 'minor'): '3A',
    ('F', 'minor'): '4A',
    ('C', 'minor'): '5A',
    ('G', 'minor'): '6A',
    ('D', 'minor'): '7A',
}


def _load_audio_libraries():
    """Load optional audio-analysis dependencies only when the fallback runs."""
    import librosa
    import numpy as np

    return librosa, np


def _get_ytdlp_cookie_args():
    """Returns yt-dlp CLI arguments for YouTube cookie authentication."""
    from django.conf import settings

    cookies_file = getattr(settings, 'YTDLP_COOKIES_FILE', '') or ''
    if cookies_file and os.path.exists(cookies_file):
        logger.info("[YT-DLP] Cookies via fitxer: %s", cookies_file)
        return ['--cookies', cookies_file]
    if cookies_file:
        logger.warning("[YT-DLP] YTDLP_COOKIES_FILE configurat però fitxer NO existeix: %s", cookies_file)

    cookies_browser = getattr(settings, 'YTDLP_COOKIES_FROM_BROWSER', '') or ''
    if cookies_browser:
        logger.info("[YT-DLP] Cookies via browser: %s", cookies_browser)
        return ['--cookies-from-browser', cookies_browser]

    logger.warning("[YT-DLP] Sense cookies configurades")
    return []


def download_temporary_song_audio(title, artist, per_attempt_timeout=None, max_wall_seconds=None):
    """
    Descarrega temporalment l'àudio d'una cançó a partir d'una cerca externa.

    Executa yt-dlp com a subprocess amb timeout dur per garantir que
    mai no excedeix el timeout de gunicorn.
    """
    global _YTDLP_DISABLED_UNTIL

    import sys
    import time as _time
    import subprocess

    now = _time.time()
    if now < _YTDLP_DISABLED_UNTIL:
        remaining = int(_YTDLP_DISABLED_UNTIL - now)
        logger.warning("[YT-DLP] Fallback pausat per bot detection (%ss restants)", remaining)
        raise RuntimeError("yt-dlp bot detection cooldown")

    if per_attempt_timeout is None:
        per_attempt_timeout = int(getattr(settings, "ANALYZE_YTDLP_PER_ATTEMPT_TIMEOUT", 8))
    if max_wall_seconds is None:
        max_wall_seconds = int(getattr(settings, "ANALYZE_YTDLP_MAX_WALL_SECONDS", 18))

    simple_title = _simplify_title_for_search(title)
    clean_title = _normalize_search_text(title)
    first_artist = _first_artist_for_search(artist)
    search_variants = [
        f"{simple_title} {first_artist}",
        f"{simple_title} {first_artist} audio",
        f"{clean_title} {first_artist}",
        f"{simple_title}",
    ]
    # Dedupe i evitar variants buides
    _seen = set()
    search_variants = [q for q in search_variants if q and not (q in _seen or _seen.add(q))]
    logger.info("[YT-DLP] Query variants (%s): %s", len(search_variants), search_variants)

    t_start = _time.time()
    logger.info(f"[YT-DLP] ▶ START '{title}' - '{artist}'")

    cookie_args = _get_ytdlp_cookie_args()
    logger.info(f"[YT-DLP] Cookies: {'configurades' if cookie_args else 'NO configurades'}")

    temp_dir = tempfile.mkdtemp(prefix="song-analysis-")
    output_template = os.path.join(temp_dir, "audio.%(ext)s")

    last_error = None
    for i, query in enumerate(search_variants):
        elapsed = _time.time() - t_start
        remaining = max_wall_seconds - elapsed
        if remaining < 5:
            logger.warning(f"[YT-DLP] ⏱ Wall timeout ({elapsed:.0f}s), abortant")
            break

        attempt_timeout = min(per_attempt_timeout, remaining)

        logger.info(
            f"[YT-DLP] Intent {i+1}/{len(search_variants)}: "
            f"'{query}' (elapsed={elapsed:.1f}s, timeout={attempt_timeout:.0f}s)"
        )

        cmd = [
            sys.executable, '-m', 'yt_dlp',
            '--no-playlist',
            '-o', output_template,
            '--format', 'bestaudio/best',
            '-x', '--audio-format', 'mp3', '--audio-quality', '128',
            '--socket-timeout', '10',
            '--extractor-retries', '1',
            '--fragment-retries', '1',
            '--force-ipv4',
            '--no-part',
            '--force-overwrites',
            '--extractor-args', 'youtube:player_client=android,web',
            *cookie_args,
            f'ytsearch1:{query}',
        ]
        logger.info("[YT-DLP] CMD: %s", ' '.join(cmd))

        t_iter = _time.time()
        try:
            proc = subprocess.run(
                cmd,
                timeout=attempt_timeout,
                capture_output=True,
                text=True,
            )
            dt = _time.time() - t_iter
            if proc.returncode != 0:
                stderr_full = (proc.stderr or '').strip()
                stdout_full = (proc.stdout or '').strip()
                logger.warning(f"[YT-DLP] Intent {i+1}: FAIL exit={proc.returncode} ({dt:.1f}s)")
                if stderr_full:
                    logger.warning(f"[YT-DLP] stderr: {stderr_full}")
                if stdout_full:
                    logger.warning(f"[YT-DLP] stdout: {stdout_full}")
                last_error = RuntimeError(f"yt-dlp exit {proc.returncode}")
                if _is_ytdlp_bot_detection_error(proc.stderr):
                    cooldown = _ytdlp_bot_cooldown_seconds()
                    _YTDLP_DISABLED_UNTIL = _time.time() + cooldown
                    logger.warning("[YT-DLP] Bot detection detectat, pausant fallback %ss", cooldown)
                    break
            else:
                stdout_ok = (proc.stdout or '').strip()
                logger.info(f"[YT-DLP] Intent {i+1}: OK ({dt:.1f}s)")
                if stdout_ok:
                    logger.info(f"[YT-DLP] stdout: {stdout_ok}")

        except subprocess.TimeoutExpired:
            logger.warning(f"[YT-DLP] Intent {i+1}: TIMEOUT ({attempt_timeout:.0f}s)")
            last_error = RuntimeError(f"yt-dlp timeout ({attempt_timeout:.0f}s)")
            for fn in os.listdir(temp_dir):
                try:
                    os.remove(os.path.join(temp_dir, fn))
                except OSError:
                    pass
            continue

        for filename in os.listdir(temp_dir):
            if filename.endswith(".mp3"):
                temp_path = os.path.join(temp_dir, filename)
                fsize = os.path.getsize(temp_path) / 1024
                logger.info(f"[YT-DLP] ✓ MP3 intent {i+1}: {fsize:.0f}KB (total {_time.time() - t_start:.1f}s)")
                return temp_path, temp_dir

        for fn in os.listdir(temp_dir):
            try:
                os.remove(os.path.join(temp_dir, fn))
            except OSError:
                pass

    shutil.rmtree(temp_dir, ignore_errors=True)
    logger.error(f"[YT-DLP] ✗ FAIL tots els intents (total {_time.time() - t_start:.1f}s)")
    raise last_error or RuntimeError("Cap variant de cerca ha funcionat")


def detect_bpm(audio_path):
    """
    Detecta el BPM (tempo) d'un fitxer d'àudio utilitzant librosa.

    Args:
        audio_path: Path al fitxer d'àudio

    Returns:
        BPM detectat (float)
    """
    try:
        librosa, np = _load_audio_libraries()

        analyze_seconds = int(getattr(settings, "ANALYZE_AUDIO_SECONDS", 20))
        sample_rate = int(getattr(settings, "ANALYZE_AUDIO_SAMPLE_RATE", 16000))
        # Carregar àudio parcial per reduir CPU/RAM a Render
        y, sr = librosa.load(audio_path, duration=analyze_seconds, sr=sample_rate)

        # Detectar tempo amb onset strength
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)

        # Convertir a float si és array
        if isinstance(tempo, np.ndarray):
            tempo = float(tempo[0])
        else:
            tempo = float(tempo)

        logger.info(f"[AUDIO_ANALYSIS] BPM detectat: {tempo:.1f}")
        return round(tempo, 1)

    except Exception as e:
        logger.error(f"[AUDIO_ANALYSIS] Error detectant BPM: {e}")
        raise


def detect_key(audio_path):
    """
    Detecta la tonalitat (key) d'un fitxer d'àudio utilitzant chroma features.
    Utilitza l'algorisme de Krumhansl-Schmuckler simplificat.

    Args:
        audio_path: Path al fitxer d'àudio

    Returns:
        Tuple (note, mode) ex: ('C', 'major') o None si falla
    """
    try:
        librosa, np = _load_audio_libraries()

        analyze_seconds = int(getattr(settings, "ANALYZE_AUDIO_SECONDS", 20))
        sample_rate = int(getattr(settings, "ANALYZE_AUDIO_SAMPLE_RATE", 16000))
        # Carregar àudio parcial per reduir CPU/RAM a Render
        y, sr = librosa.load(audio_path, duration=analyze_seconds, sr=sample_rate)

        # Extreure chroma features (12 pitch classes)
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)

        # Calcular la mitjana de cada pitch class
        chroma_mean = np.mean(chroma, axis=1)

        # Normalitzar
        chroma_mean = chroma_mean / np.sum(chroma_mean)

        # Perfils de Krumhansl-Schmuckler (simplificats)
        # Major profile
        major_profile = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
        major_profile = major_profile / np.sum(major_profile)

        # Minor profile
        minor_profile = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
        minor_profile = minor_profile / np.sum(minor_profile)

        # Trobar la millor correlació per cada tonalitat
        best_correlation = -1
        best_key = None
        best_mode = None

        for i in range(12):
            # Rotar el chroma per provar cada tonalitat
            rotated_chroma = np.roll(chroma_mean, i)

            # Correlació amb major
            major_corr = np.corrcoef(rotated_chroma, major_profile)[0, 1]
            if major_corr > best_correlation:
                best_correlation = major_corr
                best_key = PITCH_CLASS_TO_NOTE[i]
                best_mode = 'major'

            # Correlació amb minor
            minor_corr = np.corrcoef(rotated_chroma, minor_profile)[0, 1]
            if minor_corr > best_correlation:
                best_correlation = minor_corr
                best_key = PITCH_CLASS_TO_NOTE[i]
                best_mode = 'minor'

        logger.info(f"[AUDIO_ANALYSIS] Key detectada: {best_key} {best_mode} (conf: {best_correlation:.2f})")
        return (best_key, best_mode)

    except Exception as e:
        logger.error(f"[AUDIO_ANALYSIS] Error detectant key: {e}")
        raise


def key_to_camelot(note, mode):
    """
    Converteix una tonalitat musical a notació Camelot.

    Args:
        note: Nota base ('C', 'C#', 'D', etc.)
        mode: Mode ('major' o 'minor')

    Returns:
        String amb notació Camelot (ex: '8B', '5A') o None
    """
    return CAMELOT_MAP.get((note, mode))


def analyze_audio_file(audio_path):
    """
    Analitza un fitxer d'àudio complet: BPM i Key.

    Args:
        audio_path: Path al fitxer d'àudio

    Returns:
        Dict amb 'bpm' (float) i 'key' (str Camelot) o None
    """
    try:
        # Detectar BPM
        bpm = detect_bpm(audio_path)

        # Detectar Key
        note, mode = detect_key(audio_path)
        camelot_key = key_to_camelot(note, mode)

        return {
            'bpm': bpm,
            'key': camelot_key,
            'key_note': note,
            'key_mode': mode
        }

    except Exception as e:
        logger.error(f"[AUDIO_ANALYSIS] Error en anàlisi complet: {e}")
        raise


def analyze_from_preview_url(preview_url):
    """
    Descarrega un Spotify preview MP3 (30s) i analitza BPM/Key amb librosa.
    Molt més lleuger que yt-dlp: HTTP GET directe, sense autenticació.
    """
    import requests

    if not preview_url:
        return None

    temp_dir = None
    try:
        logger.info(f"[AUDIO_ANALYSIS] Descarregant preview URL: {preview_url[:80]}...")
        resp = requests.get(preview_url, timeout=15)
        resp.raise_for_status()

        temp_dir = tempfile.mkdtemp(prefix="preview-analysis-")
        temp_path = os.path.join(temp_dir, "preview.mp3")
        with open(temp_path, 'wb') as f:
            f.write(resp.content)

        result = analyze_audio_file(temp_path)
        logger.info(f"[AUDIO_ANALYSIS] Preview analitzat: BPM={result['bpm']}, Key={result['key']}")
        return result
    except Exception as e:
        logger.error(f"[AUDIO_ANALYSIS] Error analitzant preview: {e}")
        return None
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


def analyze_song_from_temporary_mp3(title, artist):
    """
    Cerca, descarrega, analitza i esborra un MP3 temporal d'una cançó.
    Utilitza yt-dlp com a subprocess (pot fallar en servidors cloud per bot detection).
    """
    import time as _time

    temp_file = None
    temp_dir = None
    try:
        if not bool(getattr(settings, "ENABLE_YTDLP_FALLBACK", True)):
            logger.warning("[YT-DLP] Fallback desactivat per configuració")
            return None
        temp_file, temp_dir = download_temporary_song_audio(title, artist)
        logger.info("[AUDIO_ANALYSIS] MP3 obtingut, iniciant librosa")
        t0 = _time.time()
        result = analyze_audio_file(temp_file)
        logger.info(
            f"[AUDIO_ANALYSIS] ✓ '{title}' - '{artist}': "
            f"BPM={result['bpm']}, Key={result['key']} (librosa {_time.time() - t0:.1f}s)"
        )
        return result
    except Exception as e:
        logger.error(f"[AUDIO_ANALYSIS] ✗ Error àudio temporal: {e}")
        return None
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
