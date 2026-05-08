"""
Anàlisi d'àudio local per detectar BPM i Key utilitzant librosa.
Utilitzat com a fallback quan les APIs de Spotify/GetSongBPM no tenen dades.
"""
import os
import shutil
import tempfile
import logging

logger = logging.getLogger(__name__)


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


def _get_ytdlp_cookie_opts():
    """Returns yt-dlp options for YouTube cookie authentication."""
    from django.conf import settings

    cookies_file = getattr(settings, 'YTDLP_COOKIES_FILE', '') or ''
    if cookies_file and os.path.exists(cookies_file):
        logger.debug(f"[AUDIO_ANALYSIS] Usant cookies file: {cookies_file}")
        return {'cookiefile': cookies_file}

    cookies_browser = getattr(settings, 'YTDLP_COOKIES_FROM_BROWSER', '') or ''
    if cookies_browser:
        logger.debug(f"[AUDIO_ANALYSIS] Usant cookies del navegador: {cookies_browser}")
        return {'cookiesfrombrowser': (cookies_browser,)}

    return {}


def download_temporary_song_audio(title, artist, timeout=60, max_wall_seconds=25):
    """
    Descarrega temporalment l'àudio d'una cançó a partir d'una cerca externa.

    Prova múltiples variants de cerca amb un límit de temps total
    (max_wall_seconds) per evitar worker timeouts a gunicorn.
    """
    import time as _time
    import resource

    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    search_variants = [
        f"{title} {artist} audio",
        f"{title} {artist}",
        f"{title} audio",
    ]

    def _mem_mb():
        try:
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        except Exception:
            return 0

    t_start = _time.time()
    logger.info(f"[YT-DLP] ▶ START '{title}' - '{artist}' (mem={_mem_mb():.0f}MB)")

    cookie_opts = _get_ytdlp_cookie_opts()
    logger.info(f"[YT-DLP] Cookies: {'configurades' if cookie_opts else 'NO configurades'}")

    last_error = None
    for i, query in enumerate(search_variants):
        elapsed = _time.time() - t_start
        if elapsed > max_wall_seconds:
            logger.warning(f"[YT-DLP] ⏱ Wall timeout ({elapsed:.0f}s > {max_wall_seconds}s), abortant")
            break

        t_iter = _time.time()
        search_query = f"ytsearch1:{query}"
        temp_dir = tempfile.mkdtemp(prefix="song-analysis-")
        output_template = os.path.join(temp_dir, "audio.%(ext)s")

        logger.info(f"[YT-DLP] Intent {i+1}/{len(search_variants)}: '{query}' (elapsed={elapsed:.1f}s, mem={_mem_mb():.0f}MB)")

        ydl_opts = {
            "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "outtmpl": output_template,
            "default_search": "ytsearch1",
            "socket_timeout": min(timeout, 15),
            "nopart": True,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }],
            **cookie_opts,
        }

        try:
            with YoutubeDL(ydl_opts) as ydl:
                logger.info(f"[YT-DLP] Intent {i+1}: extract_info start (mem={_mem_mb():.0f}MB)")
                ydl.extract_info(search_query, download=True)
                logger.info(f"[YT-DLP] Intent {i+1}: extract_info OK ({_time.time() - t_iter:.1f}s, mem={_mem_mb():.0f}MB)")

            for filename in os.listdir(temp_dir):
                if filename.endswith(".mp3"):
                    temp_path = os.path.join(temp_dir, filename)
                    fsize = os.path.getsize(temp_path) / 1024
                    logger.info(f"[YT-DLP] ✓ MP3 descarregat intent {i+1}: {fsize:.0f}KB (total {_time.time() - t_start:.1f}s, mem={_mem_mb():.0f}MB)")
                    return temp_path, temp_dir

            shutil.rmtree(temp_dir, ignore_errors=True)
            last_error = RuntimeError("No s'ha generat cap MP3 temporal")
            logger.warning(f"[YT-DLP] Intent {i+1}: extract OK però sense MP3 ({_time.time() - t_iter:.1f}s)")

        except DownloadError as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.warning(f"[YT-DLP] Intent {i+1} DownloadError ({_time.time() - t_iter:.1f}s, mem={_mem_mb():.0f}MB): {e}")
            last_error = e
            continue
        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.error(f"[YT-DLP] Intent {i+1} EXCEPTION ({_time.time() - t_iter:.1f}s, mem={_mem_mb():.0f}MB): {type(e).__name__}: {e}")
            raise

    logger.error(f"[YT-DLP] ✗ FAIL tots els intents (total {_time.time() - t_start:.1f}s, mem={_mem_mb():.0f}MB)")
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

        # Carregar àudio (només els primers 45s per estalviar memòria)
        y, sr = librosa.load(audio_path, duration=45, sr=22050)

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

        # Carregar àudio
        y, sr = librosa.load(audio_path, duration=45, sr=22050)

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
    Utilitza yt-dlp (pot fallar en servidors cloud per bot detection).
    """
    import time as _time
    import resource

    def _mem_mb():
        try:
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        except Exception:
            return 0

    temp_file = None
    temp_dir = None
    try:
        temp_file, temp_dir = download_temporary_song_audio(title, artist)
        logger.info(f"[AUDIO_ANALYSIS] MP3 obtingut, iniciant librosa (mem={_mem_mb():.0f}MB)")
        t0 = _time.time()
        result = analyze_audio_file(temp_file)
        logger.info(
            f"[AUDIO_ANALYSIS] ✓ Anàlisi completat per '{title}' - '{artist}': "
            f"BPM={result['bpm']}, Key={result['key']} (librosa {_time.time() - t0:.1f}s, mem={_mem_mb():.0f}MB)"
        )
        return result
    except Exception as e:
        logger.error(f"[AUDIO_ANALYSIS] ✗ Error àudio temporal (mem={_mem_mb():.0f}MB): {e}")
        return None
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
