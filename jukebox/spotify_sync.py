# spotify_sync.py

from django.utils import timezone
from .models import Party, Song
from .spotify_api import get_playlist_tracks_basic, remove_duplicate_tracks_from_playlist
import logging

logger = logging.getLogger(__name__)


def sync_playlist_with_spotify(party_id):
    """
    Sincronitza la playlist de Spotify amb la BD local.
    Detecta cançons noves (a Spotify però no a BD) i les afegeix.
    Detecta cançons eliminades (a BD però no a Spotify) i les elimina.

    Args:
        party_id: ID de la festa a sincronitzar

    Returns:
        dict amb stats: {
            'success': bool,
            'added': int,
            'removed': int,
            'total': int,
            'synced_at': str (ISO format),
            'skipped': bool (opcional),
            'reason': str (opcional),
            'error': str (opcional)
        }
    """
    try:
        party = Party.objects.select_related('playlist', 'owner').get(id=party_id)

        # Validar que auto-sync estigui activat
        if not party.auto_sync_playlist:
            logger.info(f"[SYNC] Party {party_id} - Auto-sync disabled")
            return {'skipped': True, 'reason': 'Auto-sync disabled'}

        # Rate limiting: no sync si última sync fa menys de 4 minuts
        if party.last_sync_at:
            diff = timezone.now() - party.last_sync_at
            if diff.total_seconds() < 240:  # 4 minuts
                logger.debug(f"[SYNC] Party {party_id} - Too soon (last sync {int(diff.total_seconds())}s ago)")
                return {'skipped': True, 'reason': 'Too soon (rate limit)'}

        # Validar que hi hagi playlist assignada
        playlist = party.playlist
        if not playlist:
            logger.warning(f"[SYNC] Party {party_id} - No playlist assigned")
            return {'error': 'No playlist assigned'}

        # 1. Obtenir tracks de Spotify (només metadata bàsica, usa Client Credentials)
        logger.info(f"[SYNC] Party {party_id} - Fetching tracks from Spotify playlist {playlist.spotify_id}")

        spotify_tracks = get_playlist_tracks_basic(playlist.spotify_id)

        if not spotify_tracks:
            logger.warning(f"[SYNC] Party {party_id} - No tracks found in Spotify playlist")
            return {'error': 'No tracks found in Spotify playlist'}

        # 1b. Eliminar duplicats de la playlist de Spotify (usa token del primer owner)
        owner_user = party.owners.first()
        if owner_user:
            try:
                dupes_removed = remove_duplicate_tracks_from_playlist(
                    owner_user, playlist.spotify_id, spotify_tracks
                )
                if dupes_removed:
                    logger.info(f"[SYNC] Party {party_id} - Eliminades {dupes_removed} ocurrències duplicades de Spotify")
                    spotify_tracks = get_playlist_tracks_basic(playlist.spotify_id)
            except Exception:
                logger.warning(f"[SYNC] Party {party_id} - No s'han pogut eliminar duplicats de Spotify", exc_info=True)

        # 1c. Deduplica la llista en memòria (una entrada per spotify_id)
        seen: set = set()
        unique_tracks = []
        for tr in spotify_tracks:
            if tr['id'] not in seen:
                seen.add(tr['id'])
                unique_tracks.append(tr)
        spotify_ids = seen

        # 2. Obtenir tracks locals actuals
        local_ids = set(party.songs.values_list('spotify_id', flat=True))

        # 2b. Eliminar duplicats de la DB
        from django.db.models import Count
        dupes_qs = (
            party.songs.values('spotify_id')
            .annotate(cnt=Count('id'))
            .filter(cnt__gt=1)
        )
        for row in dupes_qs:
            candidates = list(
                party.songs.filter(spotify_id=row['spotify_id'])
                .extra(select={'completeness': 'CASE WHEN bpm IS NOT NULL AND key IS NOT NULL THEN 2 '
                                              'WHEN bpm IS NOT NULL OR key IS NOT NULL THEN 1 ELSE 0 END'})
                .order_by('-completeness', 'id')
            )
            keep_id = candidates[0].id
            party.songs.filter(spotify_id=row['spotify_id']).exclude(pk=keep_id).delete()

        # 3. Detectar nous tracks (a Spotify però no a BD)
        local_ids = set(party.songs.values_list('spotify_id', flat=True))
        new_ids = spotify_ids - local_ids
        added_count = 0

        for track in unique_tracks:
            if track['id'] in new_ids:
                Song.objects.get_or_create(
                    party=party,
                    spotify_id=track['id'],
                    defaults={
                        'title': track['title'],
                        'artist': track['artist'],
                        'album_image_url': track.get('album_image_url'),
                        'preview_url': track.get('preview_url'),
                        'bpm': None,
                        'key': None,
                    },
                )
                added_count += 1
                logger.debug(f"[SYNC] Party {party_id} - Added: {track['title']} - {track['artist']}")

        # 4. Detectar tracks eliminats (a BD però no a Spotify)
        removed_ids = local_ids - spotify_ids
        if removed_ids:
            removed_count = party.songs.filter(spotify_id__in=removed_ids).delete()[0]
            logger.debug(f"[SYNC] Party {party_id} - Removed {removed_count} songs")
        else:
            removed_count = 0

        # 5. Actualitzar timestamp
        party.last_sync_at = timezone.now()
        party.save(update_fields=['last_sync_at'])

        logger.info(f"[SYNC] Party {party_id} - Completed: +{added_count} -{removed_count} (total: {party.songs.count()})")

        return {
            'success': True,
            'added': added_count,
            'removed': removed_count,
            'total': party.songs.count(),
            'synced_at': party.last_sync_at.isoformat()
        }

    except Party.DoesNotExist:
        logger.error(f"[SYNC] Party {party_id} not found")
        return {'error': f'Party {party_id} not found'}

    except Exception as e:
        logger.error(f"[SYNC] Party {party_id} - Unexpected error: {str(e)}", exc_info=True)
        return {'error': str(e)}


def sync_all_parties():
    """
    Sincronitza totes les festes amb auto_sync_playlist=True.
    Aquesta funció és cridada per el management command o tasca periòdica.

    Returns:
        dict amb resum: {
            'total_parties': int,
            'synced': int,
            'skipped': int,
            'errors': int,
            'results': list[dict]
        }
    """
    parties = Party.objects.filter(auto_sync_playlist=True).select_related('playlist', 'owner')
    total = parties.count()

    if total == 0:
        logger.info("[SYNC_ALL] No parties with auto-sync enabled")
        return {
            'total_parties': 0,
            'synced': 0,
            'skipped': 0,
            'errors': 0,
            'results': []
        }

    logger.info(f"[SYNC_ALL] Starting sync for {total} parties")

    synced = 0
    skipped = 0
    errors = 0
    results = []

    for party in parties:
        result = sync_playlist_with_spotify(party.id)
        result['party_id'] = party.id
        result['party_name'] = party.name
        results.append(result)

        if result.get('success'):
            synced += 1
        elif result.get('skipped'):
            skipped += 1
        else:
            errors += 1

    logger.info(f"[SYNC_ALL] Completed: {synced} synced, {skipped} skipped, {errors} errors")

    return {
        'total_parties': total,
        'synced': synced,
        'skipped': skipped,
        'errors': errors,
        'results': results
    }
