"""
Sistema de recomanació de cançons per a DJs
Té en compte harmonia (Camelot key), BPM i vots
"""
from django.db.models import Count
from .models import Song


def get_compatible_camelot_keys(key):
    """
    Retorna les claus Camelot compatibles per a mescles harmòniques.

    Regles de mescla harmònica:
    - Mateix número (canvi major/menor): 8A ↔ 8B
    - ±1 en el mateix mode: 8A → 7A o 9A
    - ±7 en el mateix mode (canvi de quinta): 8A → 1A o 3A (8-7=1, 8+7=15→3)
    """
    if not key:
        return []

    # Extraure número i mode
    try:
        num = int(key[:-1])
        mode = key[-1]
    except (ValueError, IndexError):
        return []

    compatible = [key]  # La mateixa clau sempre és compatible

    # Regla 1: Canvi major/menor (mateix número)
    other_mode = 'B' if mode == 'A' else 'A'
    compatible.append(f"{num}{other_mode}")

    # Regla 2: ±1 en el mateix mode
    prev_num = num - 1 if num > 1 else 12
    next_num = num + 1 if num < 12 else 1
    compatible.append(f"{prev_num}{mode}")
    compatible.append(f"{next_num}{mode}")

    # Regla 3: ±7 (quinta) en el mateix mode
    fifth_up = num + 7 if num <= 5 else num + 7 - 12
    fifth_down = num - 7 if num >= 8 else num - 7 + 12
    compatible.append(f"{fifth_up}{mode}")
    compatible.append(f"{fifth_down}{mode}")

    return list(set(compatible))


def get_recommended_songs(party, limit=5, reference_song=None):
    """
    Genera una llista de cançons recomanades per al DJ.

    Té en compte:
    - Harmonia (Camelot key compatible amb la última cançó)
    - BPM similar per beat matching
    - Vots (popularitat)
    - Cançons no reproduïdes

    Args:
        party: Party object
        limit: Número màxim de recomanacions
        reference_song: Cançó de referència (si None, usa l'última reproduïda)

    Returns:
        QuerySet de Song amb score calculat
    """
    # Obtenir totes les cançons no reproduïdes de la festa
    unplayed_songs = party.songs.filter(has_played=False).annotate(
        num_votes=Count('vote')
    )

    if not unplayed_songs.exists():
        return unplayed_songs[:limit]

    # Si no hi ha cançó de referència, buscar l'última reproduïda
    if not reference_song:
        last_played = party.songs.filter(has_played=True).order_by('-id').first()
        reference_song = last_played

    # Si encara no hi ha referència, usar la més votada
    if not reference_song:
        reference_song = unplayed_songs.order_by('-num_votes').first()

    # Si no tenim referència (festa buida), retornar per vots
    if not reference_song:
        return unplayed_songs.order_by('-num_votes')[:limit]

    # Calcular scores per cada cançó
    scored_songs = []

    for song in unplayed_songs:
        score = 0
        reasons = []

        # 1. Vots (40% del score, màxim 40 punts)
        vote_score = min(song.num_votes * 4, 40)
        score += vote_score
        if song.num_votes > 0:
            reasons.append(f"{song.num_votes} vots")

        # 2. Compatibilitat de Key (30% del score)
        if reference_song.key and song.key:
            compatible_keys = get_compatible_camelot_keys(reference_song.key)
            if song.key in compatible_keys:
                key_score = 30
                if song.key == reference_song.key:
                    reasons.append(f"Mateixa clau ({song.key})")
                else:
                    reasons.append(f"Clau compatible ({song.key})")
            else:
                key_score = 0
            score += key_score

        # 3. Compatibilitat de BPM (30% del score)
        if reference_song.bpm and song.bpm:
            bpm_diff = abs(float(song.bpm) - float(reference_song.bpm))
            if bpm_diff <= 5:
                bpm_score = 30
                reasons.append(f"BPM molt similar ({song.bpm})")
            elif bpm_diff <= 10:
                bpm_score = 20
                reasons.append(f"BPM similar ({song.bpm})")
            elif bpm_diff <= 15:
                bpm_score = 10
                reasons.append(f"BPM proper ({song.bpm})")
            else:
                bpm_score = 0
            score += bpm_score

        # Guardar score i raons
        song.recommendation_score = score
        song.recommendation_reasons = reasons
        scored_songs.append(song)

    # Ordenar per score i retornar top
    scored_songs.sort(key=lambda x: x.recommendation_score, reverse=True)

    return scored_songs[:limit]
