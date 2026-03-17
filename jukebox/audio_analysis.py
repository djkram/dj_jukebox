"""
Anàlisi d'àudio local per detectar BPM i Key utilitzant librosa.
Utilitzat com a fallback quan les APIs de Spotify/GetSongBPM no tenen dades.
"""
import os
import tempfile
import logging
import requests
import librosa
import numpy as np

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


def download_audio_preview(preview_url, timeout=30):
    """
    Descarrega el preview d'àudio de Spotify a un fitxer temporal.

    Args:
        preview_url: URL del preview MP3 (30 segons)
        timeout: Temps màxim d'espera en segons

    Returns:
        Path al fitxer temporal descarregat
    """
    try:
        response = requests.get(preview_url, timeout=timeout, stream=True)
        response.raise_for_status()

        # Crear fitxer temporal
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')

        # Descarregar en chunks
        for chunk in response.iter_content(chunk_size=8192):
            temp_file.write(chunk)

        temp_file.close()
        logger.info(f"[AUDIO_ANALYSIS] Preview descarregat: {temp_file.name}")
        return temp_file.name

    except Exception as e:
        logger.error(f"[AUDIO_ANALYSIS] Error descarregant preview: {e}")
        raise


def detect_bpm(audio_path):
    """
    Detecta el BPM (tempo) d'un fitxer d'àudio utilitzant librosa.

    Args:
        audio_path: Path al fitxer d'àudio

    Returns:
        BPM detectat (float)
    """
    try:
        # Carregar àudio (només els primers 30s per estalviar memòria)
        y, sr = librosa.load(audio_path, duration=30, sr=22050)

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
        # Carregar àudio
        y, sr = librosa.load(audio_path, duration=30, sr=22050)

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


def analyze_spotify_preview(preview_url):
    """
    Analitza un preview de Spotify: descarrega, analitza i neteja.

    Args:
        preview_url: URL del preview MP3 de Spotify

    Returns:
        Dict amb 'bpm' i 'key' o None si falla
    """
    temp_file = None
    try:
        # Descarregar preview
        temp_file = download_audio_preview(preview_url)

        # Analitzar
        result = analyze_audio_file(temp_file)

        logger.info(f"[AUDIO_ANALYSIS] Anàlisi completat: BPM={result['bpm']}, Key={result['key']}")
        return result

    except Exception as e:
        logger.error(f"[AUDIO_ANALYSIS] Error analitzant preview: {e}")
        return None

    finally:
        # Netejar fitxer temporal
        if temp_file and os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
                logger.debug(f"[AUDIO_ANALYSIS] Fitxer temporal eliminat: {temp_file}")
            except Exception as e:
                logger.warning(f"[AUDIO_ANALYSIS] No s'ha pogut eliminar temporal: {e}")
