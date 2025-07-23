# acousticbrainz_api.py

import requests

# URL base d'AcousticBrainz
ACOUSTICBRAINZ_BASE = "https://acousticbrainz.org"

# MusicBrainz WS2 endpoint per cerca per ISRC
MUSICBRAINZ_SEARCH = "https://musicbrainz.org/ws/2/recording/"

# Mapatge (nota, escala) → notació Camelot
CAMELOT_MAP = {
    # Major
    ("C", "major"):   "8B",
    ("C#", "major"):  "3B", ("Db", "major"): "3B",
    ("D", "major"):   "10B",
    ("D#", "major"):  "5B", ("Eb", "major"): "5B",
    ("E", "major"):   "12B",
    ("F", "major"):   "7B",
    ("F#", "major"):  "2B", ("Gb", "major"): "2B",
    ("G", "major"):   "9B",
    ("G#", "major"):  "4B", ("Ab", "major"): "4B",
    ("A", "major"):   "11B",
    ("A#", "major"):  "6B", ("Bb", "major"): "6B",
    ("B", "major"):   "1B",

    # Minor
    ("C", "minor"):   "5A",
    ("C#", "minor"):  "12A", ("Db", "minor"): "12A",
    ("D", "minor"):   "7A",
    ("D#", "minor"):  "2A",  ("Eb", "minor"): "2A",
    ("E", "minor"):   "9A",
    ("F", "minor"):   "4A",
    ("F#", "minor"):  "11A", ("Gb", "minor"): "11A",
    ("G", "minor"):   "6A",
    ("G#", "minor"):  "1A",  ("Ab", "minor"): "1A",
    ("A", "minor"):   "8A",
    ("A#", "minor"):  "3A",  ("Bb", "minor"): "3A",
    ("B", "minor"):   "10A",
}

def get_mbid_from_isrc(isrc):
    """
    Consulta MusicBrainz WS2 per trobar el recording MBID a partir de l'ISRC.
    Torna el primer MBID trobat o None.
    """
    print(f"[acoustic] get_mbid_from_isrc: lookup isrc={isrc}")
    if not isrc:
        print("[acoustic]   → no ISRC proporcionat")
        return None

    params = {
        "query": f"isrc:{isrc}",
        "fmt": "json",
        "limit": 1
    }
    headers = {"User-Agent": "DJJukebox/1.0 (contact@yourdomain.com)"}
    try:
        resp = requests.get(MUSICBRAINZ_SEARCH, params=params, headers=headers, timeout=5)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[acoustic]   → error MusicBrainz lookup: {e}")
        return None

    recordings = resp.json().get("recordings", [])
    print(f"[acoustic]   → MusicBrainz recordings: {recordings}")
    if not recordings:
        print("[acoustic]   → cap recording trobat")
        return None

    mbid = recordings[0].get("id")
    print(f"[acoustic]   → trobat MBID={mbid}")
    return mbid


def get_track_features(mbid):
    """
    Obté BPM i clau Camelot d'una pista donat el seu MusicBrainz ID (mbid),
    usant l'endpoint high-level d'AcousticBrainz.
    Retorna un dict {'bpm': float|None, 'key': str|None}.
    """
    print(f"[acoustic] get_track_features: mbid={mbid}")
    if not mbid:
        print("[acoustic]   → sense MBID, saltem")
        return {"bpm": None, "key": None}

    url = f"{ACOUSTICBRAINZ_BASE}/{mbid}/high-level"
    print(f"[acoustic]   → GET {url}")
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[acoustic]   → error AcousticBrainz: {e}")
        return {"bpm": None, "key": None}

    high = resp.json().get("highlevel", {})
    print(f"[acoustic]   → highlevel keys: {list(high.keys())}")
    print(f"[acoustic]   → highlevel data: {high}")

    # Extreure BPM
    bpm = None
    rhythm = high.get("rhythm", {}).get("bpm", {})
    if isinstance(rhythm, dict):
        bpm = rhythm.get("value")
    print(f"[acoustic]   → BPM={bpm}")

    # Extreure clau i escala
    key = high.get("tonal", {}).get("key_key", {}).get("value")
    scale = high.get("tonal", {}).get("key_scale", {}).get("value")
    print(f"[acoustic]   → key_key={key}, key_scale={scale}")

    # Convertir a notació Camelot
    camelot = None
    if key and scale:
        camelot = CAMELOT_MAP.get((key, scale.lower()))
    print(f"[acoustic]   → Camelot={camelot}")

    return {"bpm": bpm, "key": camelot}
