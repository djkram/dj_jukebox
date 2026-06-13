# views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.core.cache import cache
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.translation import gettext as _
from allauth.socialaccount.models import SocialToken, SocialAccount
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.urls import reverse
from urllib.parse import urlencode

from .models import Song, Party, Playlist, Vote, VotePackage, SongRequest, Notification, SongSwipeSkip
from django.db.models import Sum, Count, Q, F, Avg
from django.db import transaction, connection
import threading
from .forms import PartyForm, PartySettingsForm
from .notifications import (
    create_song_accepted_notification,
    create_song_queued_notification,
    create_song_loaded_notification,
    create_song_rejected_notification,
    create_song_played_notification,
    create_coins_purchased_notification,
    create_coins_received_notification,
)
from .spotify_api import (
    SpotifyAuthError,
    _ensure_valid_user_token,
    _get_songbpm_features,
    _get_acousticbrainz_features,
    add_track_to_playlist,
    remove_track_from_playlist,
    remove_duplicate_tracks_from_playlist,
    get_user_playlists,

    get_playlist_tracks_basic,
    get_audio_features_for_songs,

    search_spotify_tracks_public,
)
from .utils.spotify_helpers import get_spotify_reconnect_url
from .spotify_permissions import user_can_connect_spotify
from .votes import (
    get_user_votes_left,
    get_user_party_coins,
    get_user_available_coins,
    ensure_user_has_free_coins,
    spend_user_coins_for_party,
    refund_user_coins_for_party,
    sync_party_free_coins_for_existing_users,
)
from django.utils import timezone
from datetime import datetime
from .audio_analysis import analyze_song_from_temporary_mp3, analyze_from_preview_url

# Import utils for refactoring
from .utils import (
    get_annotated_party_songs,
    get_pending_songs_ordered,
    get_played_songs_ordered,
    convert_coins_to_votes,
    get_spotify_context_for_view,
    calculate_and_apply_badges,
    create_spotify_auth_error_response,
    NEGATIVE_VOTE_TYPES,
    negative_vote_q,
)
from .utils.badges import BadgeCalculator

from django.contrib.auth import get_user_model
User = get_user_model()

import stripe
import logging

logger = logging.getLogger(__name__)


def _party_dj_check(request, party):
    """Returns 403 JsonResponse if user is not a DJ/owner of this party, else None."""
    if request.user.is_superuser or party.djs.filter(pk=request.user.pk).exists():
        return None
    return JsonResponse({'error': 'Forbidden'}, status=403)


# Create your views here.


def is_dj_admin(user):
    return user.is_authenticated and (user.is_superuser or user.dj_parties.exists())


# def song_list(request):
#     songs = Song.objects.filter(played=False).order_by('-votes')
#     return render(request, 'jukebox/song_list.html', {'songs': songs})
#
# def main(request):
#     return render(request, 'jukebox/admin_base.html')

def main(request):
    party_id = request.session.get('selected_party_id')
    if not party_id:
        return redirect('select_party')
    return redirect('song_list')


def _add_song_to_party(song_request):
    """Afegeix la cançó de la petició a la llista de la festa si no hi és. Returns the Song."""
    spotify_id = (song_request.spotify_id or "").strip()
    if spotify_id:
        song, _ = Song.objects.get_or_create(
            party=song_request.party,
            spotify_id=spotify_id,
            defaults={
                'title': song_request.title,
                'artist': song_request.artist,
                'album_image_url': song_request.album_image_url,
            },
        )
    else:
        song, _ = Song.objects.get_or_create(
            party=song_request.party,
            title=song_request.title,
            artist=song_request.artist,
            defaults={
                'spotify_id': f"request-{song_request.id}",
                'album_image_url': song_request.album_image_url,
            },
        )
    return song


def _analyze_and_add_to_spotify(song_id, party_playlist_id, dj_user):
    """Background thread: BPM/Key analysis + add to Spotify playlist."""
    import time as _t
    try:
        song = Song.objects.get(pk=song_id)

        # BPM/Key — skip if already complete
        if not (song.bpm and song.key):
            t0 = _t.time()
            result = _get_songbpm_features(song.title, song.artist, song.spotify_id)
            bpm = result.get('bpm') if result else None
            key = result.get('key') if result else None
            logger.info("[QUEUE_BG] SongBPM song_id=%s bpm=%s key=%s (%.1fs)", song_id, bpm, key, _t.time() - t0)

            if not bpm and not key:
                ab = _get_acousticbrainz_features(song.title, song.artist)
                bpm = ab.get('bpm') if ab else None
                key = ab.get('key') if ab else None
                logger.info("[QUEUE_BG] AcousticBrainz song_id=%s bpm=%s key=%s", song_id, bpm, key)

            if not bpm and not key and getattr(song, 'preview_url', None):
                pr = analyze_from_preview_url(song.preview_url)
                if pr:
                    bpm = pr.get('bpm')
                    key = pr.get('key')

            update_fields = []
            if bpm and not song.bpm:
                song.bpm = bpm
                update_fields.append('bpm')
            if key and not song.key:
                song.key = key
                update_fields.append('key')
            if result:
                for field in ('key_text', 'duration', 'popularity', 'energy', 'danceability',
                              'happiness', 'acousticness', 'instrumentalness', 'liveness',
                              'speechiness', 'loudness'):
                    val = result.get(field)
                    if val is not None and not getattr(song, field, None):
                        setattr(song, field, val)
                        update_fields.append(field)
            if update_fields:
                song.save(update_fields=update_fields)
                logger.info("[QUEUE_BG] ✓ Saved song_id=%s fields=%s", song_id, update_fields)

        # Add to Spotify playlist
        if party_playlist_id and not (song.spotify_id or '').startswith('request-'):
            try:
                add_track_to_playlist(dj_user, party_playlist_id, song.spotify_id)
                logger.info("[QUEUE_BG] ✓ Added song_id=%s to Spotify playlist %s", song_id, party_playlist_id)
            except Exception:
                logger.exception("[QUEUE_BG] Spotify playlist add failed song_id=%s", song_id)

    except Exception:
        logger.exception("[QUEUE_BG] Unexpected error for song_id=%s", song_id)
    finally:
        connection.close()



def _queue_song_request(song_request, processed_by):
    """Posa la cançó a la maleta: afegeix a la llista, analitza BPM/Key i a la playlist Spotify."""
    with transaction.atomic():
        song = _add_song_to_party(song_request)
        song_request.status = 'queued'
        song_request.processed_at = timezone.now()
        song_request.processed_by = processed_by
        song_request.save(update_fields=['status', 'processed_at', 'processed_by'])
    create_song_queued_notification(song_request)

    party = song_request.party
    playlist_id = party.playlist.spotify_id if party.playlist else None
    threading.Thread(
        target=_analyze_and_add_to_spotify,
        args=(song.id, playlist_id, processed_by),
        daemon=True,
    ).start()


def _load_song_request(song_request, processed_by):
    """LOAD: confirma la cançó al jukebox actiu. Cobra si no s'ha cobrat. Envia notificació."""
    with transaction.atomic():
        if not song_request.coins_charged:
            spent = spend_user_coins_for_party(
                song_request.user,
                song_request.party,
                song_request.coins_cost,
                reason='song_request_cost',
            )
            if not spent:
                raise ValueError("Insufficient credits")
            song_request.coins_charged = True

        song = _add_song_to_party(song_request)
        song.has_played = True
        song.played_at = timezone.now()
        song.save(update_fields=['has_played', 'played_at'])
        song_request.status = 'accepted'
        song_request.processed_at = timezone.now()
        song_request.processed_by = processed_by
        song_request.save(update_fields=['status', 'processed_at', 'processed_by', 'coins_charged'])
    create_song_loaded_notification(song_request)


def _reject_song_request(song_request, processed_by):
    """Rebutja la petició. Si els coins havien estat retinguts, els retorna."""
    with transaction.atomic():
        if song_request.coins_charged:
            refund_user_coins_for_party(
                song_request.user,
                song_request.party,
                song_request.coins_cost,
            )
        song_request.status = 'rejected'
        song_request.processed_at = timezone.now()
        song_request.processed_by = processed_by
        song_request.save(update_fields=['status', 'processed_at', 'processed_by'])
    create_song_rejected_notification(song_request)


@login_required
def profile(request):
    user = request.user
    spotify_account = SocialAccount.objects.filter(user=user, provider="spotify").first()
    has_spotify = spotify_account is not None
    has_google = SocialAccount.objects.filter(user=user, provider="google").exists()
    is_dj = Party.objects.filter(djs=user).exists()

    if has_spotify:
        _refresh_spotify_profile(user, spotify_account, request)

    if user.is_staff or user.is_superuser:
        profile_role = _("Admin")
        profile_role_icon = "admin_panel_settings"
    elif is_dj:
        profile_role = _("DJ")
        profile_role_icon = "graphic_eq"
    else:
        profile_role = _("Jukebox Member")
        profile_role_icon = "person"
    return render(request, "jukebox/profile.html", {
        "user": user,
        "has_spotify": has_spotify,
        "has_google": has_google,
        "spotify_connect_enabled": user_can_connect_spotify(user),
        "profile_role": profile_role,
        "profile_role_icon": profile_role_icon,
    })


def _refresh_spotify_profile(user, spotify_account, request):
    """Refresh Spotify extra_data (images, display_name) to avoid expired CDN URLs."""
    import requests as http_requests
    try:
        token = _ensure_valid_user_token(user)
        resp = http_requests.get(
            "https://api.spotify.com/v1/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        if resp.status_code != 200:
            return
        data = resp.json()
        changed = False
        for field in ("images", "display_name"):
            if field in data and spotify_account.extra_data.get(field) != data[field]:
                spotify_account.extra_data[field] = data[field]
                changed = True
        if changed:
            spotify_account.save(update_fields=["extra_data"])
            request.session.pop('_avatar_cache_v2', None)
    except Exception:
        pass

@login_required
@require_POST
def update_profile_name(request):
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()

    if not first_name:
        return JsonResponse({'success': False, 'errors': {'first_name': _('El nom és obligatori.')}}, status=400)

    full_name = f"{first_name} {last_name}".strip()
    User = get_user_model()
    if User.objects.exclude(pk=request.user.pk).filter(username=full_name).exists():
        return JsonResponse({'success': False, 'errors': {'full_name': _('Aquest nom ja està en ús.')}}, status=400)

    request.user.first_name = first_name
    request.user.last_name = last_name
    request.user.username = full_name
    request.user.save(update_fields=['first_name', 'last_name', 'username'])
    return JsonResponse({'success': True, 'display_name': full_name})


def select_party(request):
    # Només mostrem festes públiques que no han acabat
    parties = Party.objects.filter(is_public=True).exclude(party_status=Party.STATUS_FINISHED).order_by('-date')

    # Processar entrada de codi
    code_error = None
    if request.method == 'POST':
        code = request.POST.get('party_code', '').strip().upper()
        if code:
            try:
                party = Party.objects.get(code=code)
                # Redirigir a set_party amb el codi
                return redirect(f"{reverse('set_party', args=[party.id])}?code={code}")
            except Party.DoesNotExist:
                code_error = _("Codi invàlid. Comprova que l'has escrit correctament.")

    return render(request, "jukebox/select_party.html", {
        "parties": parties,
        "code_error": code_error,
    })

def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    import math
    d_lat = math.radians(float(lat2) - float(lat1))
    d_lon = math.radians(float(lon2) - float(lon1))
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(float(lat1))) * math.cos(math.radians(float(lat2))) * math.sin(d_lon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def set_party(request, party_id):
    party = get_object_or_404(Party, pk=party_id)

    # Si la festa requereix codi, validar-lo
    if party.require_join_code:
        provided_code = request.GET.get('code', '').strip().upper()
        if provided_code != party.code:
            messages.error(request, _("Codi incorrecte. Aquesta festa requereix un codi d'entrada."))
            return redirect('select_party')

    # Si la festa té restricció de radi, validar ubicació (admins i DJs de la festa estan exempts)
    is_exempt = request.user.is_authenticated and (
        request.user.is_superuser or party.djs.filter(pk=request.user.pk).exists()
    )
    if not is_exempt and party.location_radius_km and party.location_radius_km > 0 and party.latitude and party.longitude:
        user_lat = request.GET.get('ulat', '').strip()
        user_lng = request.GET.get('ulng', '').strip()
        if not user_lat or not user_lng:
            messages.warning(request, _("Aquesta festa requereix verificar la teva ubicació per unir-te."))
            return redirect(f"{reverse('select_party')}?verify_location={party_id}&code={request.GET.get('code', '')}")
        try:
            distance = _haversine_km(party.latitude, party.longitude, float(user_lat), float(user_lng))
            if distance > party.location_radius_km:
                messages.error(request, _("Per entrar a aquesta festa has de ser-hi físicament present."))
                return redirect('select_party')
        except (ValueError, TypeError):
            messages.error(request, _("No s'ha pogut verificar la teva ubicació."))
            return redirect('select_party')

    request.session['selected_party_id'] = party.id
    messages.success(request, _("T'has unit a la festa: %(name)s") % {'name': party.name})
    return redirect("main")

def unset_party(request):
    try:
        del request.session['selected_party_id']
    except KeyError:
        pass
    return redirect('select_party')

def past_parties(request):
    parties = Party.objects.filter(is_public=True, party_status=Party.STATUS_FINISHED).order_by('-date')
    return render(request, "jukebox/past_parties.html", {"parties": parties})

@login_required
@user_passes_test(lambda u: u.is_superuser)
def create_party(request):
    if request.method == 'POST':
        form = PartyForm(request.POST)
        if form.is_valid():
            party = form.save()
            return redirect('party_settings', party_id=party.id)
    else:
        form = PartyForm()
    return render(request, 'jukebox/create_party.html', {'form': form})


@login_required
@require_POST
def update_party_code(request, party_id):
    party = get_object_or_404(Party, pk=party_id)
    if not (request.user.is_superuser or party.djs.filter(pk=request.user.pk).exists()):
        return JsonResponse({'ok': False, 'error': 'forbidden'}, status=403)

    new_code = Party.normalize_code(request.POST.get('code', ''))
    if not new_code:
        return JsonResponse({'ok': False, 'error': 'El codi no pot estar buit.'})
    if len(new_code) > 12:
        return JsonResponse({'ok': False, 'error': 'El codi no pot tenir més de 12 caràcters.'})
    if Party.objects.exclude(pk=party_id).filter(code=new_code).exists():
        return JsonResponse({'ok': False, 'error': 'Aquest codi ja l\'utilitza una altra festa.'})

    party.code = new_code
    party.save(update_fields=['code'])
    return JsonResponse({'ok': True, 'code': party.code})


@login_required
@user_passes_test(lambda u: u.is_superuser)
def party_settings(request, party_id):
    party = get_object_or_404(Party, pk=party_id)

    has_spotify = SocialAccount.objects.filter(user=request.user, provider="spotify").exists()

    # Processament del formulari
    if request.method == 'POST':
        # Path ràpid: actualitzar només els DJs
        if 'save_djs' in request.POST:
            if request.user.is_superuser:
                dj_ids = request.POST.getlist('djs')
                party.djs.set(dj_ids)
                messages.success(request, _("DJs actualitzats correctament."))
            return redirect('party_settings', party_id=party.id)

        # Path ràpid: actualitzar els owners de la festa
        if 'save_owner' in request.POST:
            if request.user.is_superuser:
                owner_ids = request.POST.getlist('owners')
                party.owners.set(owner_ids)
                messages.success(request, _("Owners de la festa actualitzats."))
            return redirect('party_settings', party_id=party.id)

        form = PartySettingsForm(request.POST, request.FILES, instance=party, request=request)
        if form.is_valid():
            previous_free_coins = party.free_coins_per_user
            # Si es crida via AJAX i hi ha playlist, no carregar cançons
            # (es carregaran després via process_playlist_songs)
            has_playlist = bool(form.cleaned_data.get('spotify_playlist'))
            is_ajax = (
                request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
                request.POST.get('ajax_request') == '1'
            )
            load_songs = not (has_playlist and is_ajax)

            try:
                party = form.save(load_songs=load_songs)
                sync_party_free_coins_for_existing_users(
                    party,
                    previous_free_coins=previous_free_coins,
                )
            except Exception:
                logger.exception("[PARTY_SETTINGS] Error guardant party_id=%s user_id=%s FILES=%s",
                                 party_id, request.user.id, list(request.FILES.keys()))
                raise

            if is_ajax:
                return JsonResponse({'success': True})
            messages.success(request, _("Configuració guardada correctament."))
            return redirect('party_settings', party_id=party.id)
    else:
        form = PartySettingsForm(instance=party, request=request)

    # Annotem els vots totals reals per cançó
    songs = party.songs.annotate(
        num_likes=Count('vote', filter=Q(vote__vote_type='like')),
        num_dislikes=Count('vote', filter=negative_vote_q())
    ).order_by('-num_likes', 'title')
    pending_analysis_count = songs.filter(
        Q(bpm__isnull=True) | Q(key__isnull=True)
    ).count()

    # Només carreguem playlists de Spotify si NO n'hi ha i hem pitjat el botó
    playlists = None
    only_owned = request.GET.get('only_owned') == '1'
    if has_spotify and not party.playlist and request.GET.get('load_spotify') == '1':
        try:
            playlists = get_user_playlists(request, only_owned=only_owned)
        except SpotifyAuthError:
            return redirect(get_spotify_reconnect_url(request))

    all_users = User.objects.order_by('username') if request.user.is_superuser else []
    owner_pks = set(party.owners.values_list('pk', flat=True)) if request.user.is_superuser else set()

    return render(request, 'jukebox/party_settings.html', {
        'party':     party,
        'form':      form,
        'songs':     songs,
        'pending_analysis_count': pending_analysis_count,
        'playlists': playlists,
        'has_spotify': has_spotify,
        'only_owned': only_owned,
        'all_users': all_users,
        'owner_pks': owner_pks,
    })


@login_required
@user_passes_test(is_dj_admin)
def party_qr_code(request, party_id):
    """Genera un codi QR per compartir la festa."""
    import qrcode
    from io import BytesIO
    from django.http import HttpResponse

    party = get_object_or_404(Party, pk=party_id)
    if err := _party_dj_check(request, party):
        return HttpResponse(status=403)

    # URL completa de la festa amb el codi
    party_path = reverse('set_party', args=[party.id])
    party_url = request.build_absolute_uri(f'{party_path}?code={party.code}')

    # Generar QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(party_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # Retornar com a imatge PNG
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    return HttpResponse(buffer, content_type='image/png')


@login_required
@user_passes_test(is_dj_admin)
@require_POST
def delete_party(request, party_id):
    party = get_object_or_404(Party, pk=party_id)
    if err := _party_dj_check(request, party):
        return err
    # Clear selected party from session if it's the one being deleted
    if request.session.get('selected_party_id') == party.id:
        del request.session['selected_party_id']
    party.delete()
    messages.success(request, _("Festa eliminada correctament."))
    return redirect('dj_backoffice')


@login_required
@user_passes_test(is_dj_admin)
@require_POST
def remove_playlist(request, party_id):
    party = get_object_or_404(Party, pk=party_id)
    if err := _party_dj_check(request, party):
        return err
    # només serveix si la festa ja té playlist
    if party.playlist:
        party.playlist = None
        party.songs.all().delete()   # opcional: neteja també les cançons
        party.save()
    return redirect('party_settings', party_id=party.id)


@login_required
@user_passes_test(is_dj_admin)
@require_POST
def assign_party_playlist(request, party_id):
    party = get_object_or_404(Party, pk=party_id)
    if err := _party_dj_check(request, party):
        return err
    spotify_playlist_id = request.POST.get('spotify_playlist_id', '').strip()

    if not spotify_playlist_id:
        return JsonResponse({'error': _('No s\'ha seleccionat cap playlist.')}, status=400)

    try:
        playlists = get_user_playlists(request)
    except SpotifyAuthError:
        return create_spotify_auth_error_response(request)

    playlist_data = next((pl for pl in playlists if pl['id'] == spotify_playlist_id), None)
    if not playlist_data:
        return JsonResponse({'error': _('No s\'ha trobat aquesta playlist a Spotify.')}, status=404)

    playlist_obj, _ = Playlist.objects.get_or_create(
        spotify_id=spotify_playlist_id,
        defaults={
            'name': playlist_data['name'],
            'owner': playlist_data['owner'],
        }
    )
    playlist_obj.name = playlist_data['name']
    playlist_obj.owner = playlist_data['owner']
    playlist_obj.save(update_fields=['name', 'owner'])

    party.playlist = playlist_obj
    party.save(update_fields=['playlist'])

    return JsonResponse({
        'success': True,
        'playlist': {
            'id': playlist_obj.spotify_id,
            'name': playlist_obj.name,
            'owner': playlist_obj.owner,
        }
    })


def _dedup_party_songs(party):
    """
    Elimina cançons duplicades de la festa (mateix spotify_id).
    Manté la que té dades més completes (bpm+key > bpm > key > cap), i en cas
    d'empat la de pk menor. Retorna el nombre de registres eliminats.
    """
    from django.db.models import Min, Count
    dupes = (
        party.songs
        .values('spotify_id')
        .annotate(cnt=Count('id'))
        .filter(cnt__gt=1)
    )
    removed = 0
    for row in dupes:
        songs_qs = party.songs.filter(spotify_id=row['spotify_id']).order_by(
            # Prioritza: té bpm I key → té bpm → té key → res
            # False<True en ordre ascendent, volem True primer → descendent
        )
        candidates = list(
            party.songs.filter(spotify_id=row['spotify_id'])
            .extra(select={'completeness': 'CASE WHEN bpm IS NOT NULL AND key IS NOT NULL THEN 2 '
                                          'WHEN bpm IS NOT NULL OR key IS NOT NULL THEN 1 '
                                          'ELSE 0 END'})
            .order_by('-completeness', 'id')
        )
        keep_id = candidates[0].id
        n, _ = party.songs.filter(spotify_id=row['spotify_id']).exclude(pk=keep_id).delete()
        removed += n
    return removed


@login_required
@user_passes_test(is_dj_admin)
@require_POST
def process_playlist_songs(request, party_id):
    """
    Sincronitza les cançons d'una playlist de Spotify amb la DB.
    Afegeix noves cançons i elimina les que ja no estan a la playlist.
    NO processa BPM ni clau musical automàticament.
    """
    from .models import Playlist

    party = get_object_or_404(Party, pk=party_id)
    if err := _party_dj_check(request, party):
        return err
    spotify_playlist_id = request.POST.get('spotify_playlist_id')

    if not spotify_playlist_id:
        return JsonResponse({'error': _('No playlist ID provided')}, status=400)

    try:
        # Obtenir les cançons de Spotify (ràpid, només metadata + posició)
        tracks = get_playlist_tracks_basic(spotify_playlist_id)

        # ── 1. Eliminar duplicats de la playlist de Spotify ──────────────
        spotify_removed_dupes = 0
        playlist_id = party.playlist.spotify_id if party.playlist else spotify_playlist_id
        try:
            spotify_removed_dupes = remove_duplicate_tracks_from_playlist(
                request, playlist_id, tracks
            )
            if spotify_removed_dupes:
                logger.info("[PROCESS_SONGS] Eliminades %d ocurrències duplicades de Spotify (party_id=%s)",
                            spotify_removed_dupes, party_id)
                # Re-fetch tracks ja sense duplicats
                tracks = get_playlist_tracks_basic(spotify_playlist_id)
        except Exception:
            logger.warning("[PROCESS_SONGS] No s'han pogut eliminar duplicats de Spotify (party_id=%s)", party_id, exc_info=True)

        # ── 2. Deduplica DB: si hi ha cançons duplicades (mateix spotify_id), en queda una ──
        db_removed_dupes = _dedup_party_songs(party)
        if db_removed_dupes:
            logger.info("[PROCESS_SONGS] Eliminades %d cançons duplicades de la DB (party_id=%s)",
                        db_removed_dupes, party_id)

        # ── 3. Construir llista deduplicada de Spotify (una entrada per spotify_id) ──
        seen_ids: set = set()
        unique_tracks = []
        for tr in tracks:
            if tr['id'] not in seen_ids:
                seen_ids.add(tr['id'])
                unique_tracks.append(tr)

        spotify_ids_in_playlist = seen_ids

        # Obtenir les cançons existents a la DB
        existing_spotify_ids = set(party.songs.values_list('spotify_id', flat=True))

        # Identificar cançons a afegir (noves a la playlist) i a eliminar
        new_spotify_ids = spotify_ids_in_playlist - existing_spotify_ids
        removed_spotify_ids = existing_spotify_ids - spotify_ids_in_playlist

        # Eliminar cançons que ja no estan a la playlist
        if removed_spotify_ids:
            party.songs.filter(spotify_id__in=removed_spotify_ids).delete()

        # Afegir noves cançons
        new_songs_count = 0
        for tr in unique_tracks:
            if tr['id'] in new_spotify_ids:
                _, created = Song.objects.get_or_create(
                    party=party,
                    spotify_id=tr['id'],
                    defaults={
                        'title': tr['title'],
                        'artist': tr['artist'],
                        'album_image_url': tr.get('album_image_url'),
                        'preview_url': tr.get('preview_url'),
                    },
                )
                if created:
                    new_songs_count += 1

        # Preparar missatge informatiu
        message_parts = []
        if spotify_removed_dupes:
            message_parts.append(f'{spotify_removed_dupes} duplicats eliminats de Spotify')
        if db_removed_dupes:
            message_parts.append(f'{db_removed_dupes} duplicats eliminats de la DB')
        if new_songs_count > 0:
            message_parts.append(f'{new_songs_count} cançons noves afegides')
        if removed_spotify_ids:
            message_parts.append(f'{len(removed_spotify_ids)} cançons eliminades')
        if not message_parts:
            message_parts.append('Playlist sincronitzada (sense canvis)')

        message = '. '.join(message_parts) + '.'

        return JsonResponse({
            'success': True,
            'total': len(unique_tracks),
            'new_songs': new_songs_count,
            'removed_songs': len(removed_spotify_ids),
            'spotify_dupes_removed': spotify_removed_dupes,
            'db_dupes_removed': db_removed_dupes,
            'message': message
        })
    except SpotifyAuthError:
        return create_spotify_auth_error_response(request)

    except Exception as e:
        logger.exception("[PROCESS_SONGS] Error for party_id=%s", party_id)
        return JsonResponse({
            'error': _('Error intern processant les cançons.')
        }, status=500)


@login_required
@user_passes_test(is_dj_admin)
@require_POST
def toggle_allow_requests(request, party_id):
    party = get_object_or_404(Party, pk=party_id)
    if err := _party_dj_check(request, party):
        return err
    party.allow_song_requests = not party.allow_song_requests
    party.save(update_fields=['allow_song_requests'])
    return JsonResponse({'allow_song_requests': party.allow_song_requests})


@login_required
@user_passes_test(is_dj_admin)
@require_POST
def save_party_location(request, party_id):
    import math
    party = get_object_or_404(Party, pk=party_id)
    if err := _party_dj_check(request, party):
        return err
    try:
        lat = request.POST.get('latitude', '').strip()
        lng = request.POST.get('longitude', '').strip()
        location_name = request.POST.get('location_name', '').strip()
        radius_km = int(request.POST.get('location_radius_km', 0) or 0)

        party.location_name = location_name
        party.latitude = float(lat) if lat else None
        party.longitude = float(lng) if lng else None
        party.location_radius_km = max(0, min(radius_km, 500))
        party.save(update_fields=['location_name', 'latitude', 'longitude', 'location_radius_km'])

        return JsonResponse({'success': True, 'location_name': party.location_name})
    except Exception as e:
        logger.exception("[SAVE_LOCATION] Error for party_id=%s", party_id)
        return JsonResponse({'error': _('Error guardant la ubicació.')}, status=400)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def party_settings_search_tracks(request, party_id):
    party = get_object_or_404(Party, pk=party_id)
    if err := _party_dj_check(request, party):
        return err
    query = request.GET.get('search', '').strip()

    if not query:
        return JsonResponse({'tracks': []})

    tracks = search_spotify_tracks_public(query, limit=12)
    existing_ids = set(party.songs.values_list('spotify_id', flat=True))
    serialized_tracks = []
    for track in tracks:
        serialized_tracks.append({
            **track,
            'already_in_party': track['id'] in existing_ids,
        })

    return JsonResponse({'tracks': serialized_tracks})


@login_required
@user_passes_test(is_dj_admin)
@require_POST
def add_track_to_party_playlist(request, party_id):
    party = get_object_or_404(Party, pk=party_id)
    if err := _party_dj_check(request, party):
        return err

    if not party.playlist:
        return JsonResponse({'error': _('La festa encara no té una playlist assignada.')}, status=400)

    spotify_id = request.POST.get('spotify_id', '').strip()
    title = request.POST.get('title', '').strip()
    artist = request.POST.get('artist', '').strip()
    album_image_url = request.POST.get('album_image_url', '').strip()

    if not spotify_id or not title or not artist:
        return JsonResponse({'error': _('Falten dades de la cançó.')}, status=400)

    if party.songs.filter(spotify_id=spotify_id).exists():
        return JsonResponse({'error': _('Aquesta cançó ja és a la playlist de la festa.')}, status=400)

    try:
        add_track_to_playlist(request, party.playlist.spotify_id, spotify_id)

        features = get_audio_features_for_songs([{
            'id': spotify_id,
            'title': title,
            'artist': artist,
        }]).get(spotify_id, {})

        song, created = Song.objects.get_or_create(
            party=party,
            spotify_id=spotify_id,
            defaults={
                'title': title,
                'artist': artist,
                'album_image_url': album_image_url or None,
                'bpm': features.get('bpm'),
                'key': features.get('key'),
            },
        )
        if not created:
            return JsonResponse({'error': _('Aquesta cançó ja és a la playlist de la festa.')}, status=400)

        pending_analysis_count = party.songs.filter(
            Q(bpm__isnull=True) | Q(key__isnull=True)
        ).count()

        return JsonResponse({
            'success': True,
            'song': {
                'id': song.id,
                'title': song.title,
                'artist': song.artist,
                'spotify_id': song.spotify_id,
                'album_image_url': song.album_image_url,
                'bpm': round(song.bpm) if song.bpm else None,
                'key': song.key,
                'num_votes': 0,
                'needs_analysis': not song.bpm or not song.key,
            },
            'pending_analysis_count': pending_analysis_count,
            'message': 'Cançó afegida a la playlist de Spotify i a la llista de la festa.',
        })
    except SpotifyAuthError:
        return create_spotify_auth_error_response(request)
    except Exception:
        logger.exception("[PLAYLIST_ADD] Error afegint cançó a party_id=%s", party_id)
        return JsonResponse({'error': _('No s\'ha pogut afegir la cançó ara mateix.')}, status=500)


@login_required
@user_passes_test(is_dj_admin)
@require_POST
def delete_song_from_party_playlist(request, party_id, song_id):
    party = get_object_or_404(Party, pk=party_id)
    if err := _party_dj_check(request, party):
        return err
    song = get_object_or_404(Song, pk=song_id, party=party)

    try:
        if party.playlist and song.spotify_id:
            remove_track_from_playlist(request, party.playlist.spotify_id, song.spotify_id)

        song.delete()

        pending_analysis_count = party.songs.filter(
            Q(bpm__isnull=True) | Q(key__isnull=True)
        ).count()

        return JsonResponse({
            'success': True,
            'pending_analysis_count': pending_analysis_count,
            'message': 'Cançó eliminada de la playlist i de la festa.',
        })
    except SpotifyAuthError:
        return create_spotify_auth_error_response(request)
    except Exception:
        logger.exception(
            "[PLAYLIST_DELETE] Error eliminant song_id=%s de party_id=%s",
            song_id,
            party_id,
        )
        return JsonResponse({'error': _('No s\'ha pogut eliminar la cançó ara mateix.')}, status=500)


@login_required
@user_passes_test(is_dj_admin)
@require_POST
def process_song_features(request, party_id):
    """
    Processa BPM i clau musical per un chunk de cançons.
    """
    party = get_object_or_404(Party, pk=party_id)
    if err := _party_dj_check(request, party):
        return err
    try:
        chunk_size = int(request.POST.get('chunk_size', 10))
        offset = int(request.POST.get('offset', 0))
    except (ValueError, TypeError):
        chunk_size, offset = 10, 0

    try:
        pending_features_filter = Q(bpm__isnull=True) | Q(key__isnull=True)

        # Obtenir cançons amb metadata incompleta
        songs_to_process = party.songs.filter(pending_features_filter)[offset:offset+chunk_size]
        total_pending = party.songs.filter(pending_features_filter).count()

        if not songs_to_process:
            return JsonResponse({
                'success': True,
                'completed': True,
                'processed': 0,
                'total_pending': 0,
                'message': 'Totes les cançons processades correctament'
            })

        # Preparar metadata per obtenir features
        songs_metadata = [
            {'id': song.spotify_id, 'title': song.title, 'artist': song.artist}
            for song in songs_to_process
        ]

        # Obtenir features
        features_map = get_audio_features_for_songs(songs_metadata)

        # Actualitzar cançons
        processed = 0
        for song in songs_to_process:
            features = features_map.get(song.spotify_id, {})
            if features.get('bpm') or features.get('key'):
                song.bpm = features.get('bpm')
                song.key = features.get('key')
                song.save()
                processed += 1

        # Recalcular total pending després de processar
        total_pending_after = party.songs.filter(pending_features_filter).count()

        return JsonResponse({
            'success': True,
            'completed': total_pending_after == 0,
            'processed': processed,
            'total_pending': total_pending_after,
            'total_songs': party.songs.count(),
            'message': f'Processat chunk: {processed}/{len(songs_to_process)} cançons amb features'
        })

    except SpotifyAuthError:
        return create_spotify_auth_error_response(request)

    except Exception:
        logger.exception("[FEATURES] Error processant metadades per party_id=%s", party_id)
        return JsonResponse({
            'error': _('No s\'han pogut processar les metadades de les cançons.')
        }, status=500)


@login_required
@user_passes_test(is_dj_admin)
@require_POST
def update_song_metadata(request, party_id, song_id):
    party = get_object_or_404(Party, pk=party_id)
    if err := _party_dj_check(request, party):
        return err
    song = get_object_or_404(Song, pk=song_id, party=party)

    bpm_raw = request.POST.get('bpm', '').strip()
    key_raw = request.POST.get('key', '').strip().upper()

    if bpm_raw:
        try:
            bpm = float(bpm_raw)
            if not (20 <= bpm <= 300):
                return JsonResponse({'success': False, 'error': 'BPM ha d\'estar entre 20 i 300'}, status=400)
            song.bpm = bpm
        except ValueError:
            return JsonResponse({'success': False, 'error': 'BPM invàlid'}, status=400)
    else:
        song.bpm = None

    valid_keys = [f"{n}{l}" for n in range(1, 13) for l in ('A', 'B')]
    if key_raw:
        if key_raw not in valid_keys:
            return JsonResponse({'success': False, 'error': 'Clau Camelot invàlida'}, status=400)
        song.key = key_raw
    else:
        song.key = None

    song.save(update_fields=['bpm', 'key'])
    return JsonResponse({
        'success': True,
        'bpm': round(song.bpm) if song.bpm else None,
        'key': song.key,
    })


@login_required
@user_passes_test(is_dj_admin)
@require_POST
def analyze_song_audio(request, party_id, song_id):
    """
    Intenta obtenir BPM i Key per aquest ordre:
    1) SongBPM
    2) AcousticBrainz
    3) Preview URL (si existeix)
    4) MP3 temporal (yt-dlp + librosa)
    """
    party = get_object_or_404(Party, pk=party_id)
    if err := _party_dj_check(request, party):
        return err
    song = get_object_or_404(Song, pk=song_id, party=party)

    try:
        import time as _time
        t0 = _time.time()
        logger.info("[ANALYZE_AUDIO] ▶ START song_id=%s '%s' - '%s'", song.id, song.title, song.artist)

        source = "songbpm"
        result = _get_songbpm_features(song.title, song.artist, song.spotify_id)
        t1 = _time.time()

        bpm = result.get('bpm') if result else None
        key = result.get('key') if result else None
        source_url = result.get('source_url') if result else None
        logger.info("[ANALYZE_AUDIO] SongBPM song_id=%s → BPM=%s Key=%s URL=%s (%.1fs)", song.id, bpm, key, source_url, t1 - t0)

        if not bpm and not key:
            logger.info("[ANALYZE_AUDIO] Fallback AcousticBrainz per song_id=%s", song.id)
            ab_result = _get_acousticbrainz_features(song.title, song.artist)
            t_ab = _time.time()
            bpm = ab_result.get('bpm') if ab_result else None
            key = ab_result.get('key') if ab_result else None
            source_url = ab_result.get('source_url') if ab_result else None
            logger.info("[ANALYZE_AUDIO] AcousticBrainz song_id=%s → BPM=%s Key=%s (%.1fs)", song.id, bpm, key, t_ab - t1)
            if bpm or key:
                source = "acousticbrainz"

        if not bpm and not key and song.preview_url:
            logger.info("[ANALYZE_AUDIO] Fallback preview_url per song_id=%s", song.id)
            preview_result = analyze_from_preview_url(song.preview_url)
            if preview_result:
                bpm = bpm or preview_result.get('bpm')
                key = key or preview_result.get('key')
                source = "preview_mp3"

        if not bpm and not key:
            logger.info("[ANALYZE_AUDIO] Fallback yt-dlp per song_id=%s (preview_url=%s)", song.id, bool(song.preview_url))
            temp_result = analyze_song_from_temporary_mp3(song.title, song.artist)
            t2 = _time.time()
            logger.info("[ANALYZE_AUDIO] yt-dlp song_id=%s → %s (%.1fs)", song.id, temp_result, t2 - t1)
            if temp_result:
                bpm = bpm or temp_result.get('bpm')
                key = key or temp_result.get('key')
                source = "temporary_mp3"

        if not bpm and not key:
            logger.warning("[ANALYZE_AUDIO] ✗ FAIL song_id=%s sense dades (total %.1fs)", song.id, _time.time() - t0)
            return JsonResponse({
                'success': False,
                'error': 'No s\'ha pogut obtenir BPM i Key per aquesta cançó.',
                'reason': 'no_audio_metadata',
            }, status=200)

        if bpm:
            song.bpm = bpm
        if key:
            song.key = key

        # Mètriques extra de proveïdors externs quan estan disponibles.
        if result:
            song.key_text = result.get('key_text') or song.key_text
            song.duration = result.get('duration') or song.duration
            song.popularity = result.get('popularity') if result.get('popularity') is not None else song.popularity
            song.energy = result.get('energy') if result.get('energy') is not None else song.energy
            song.danceability = result.get('danceability') if result.get('danceability') is not None else song.danceability
            song.happiness = result.get('happiness') if result.get('happiness') is not None else song.happiness
            song.acousticness = result.get('acousticness') if result.get('acousticness') is not None else song.acousticness
            song.instrumentalness = result.get('instrumentalness') if result.get('instrumentalness') is not None else song.instrumentalness
            song.liveness = result.get('liveness') if result.get('liveness') is not None else song.liveness
            song.speechiness = result.get('speechiness') if result.get('speechiness') is not None else song.speechiness
            song.loudness = result.get('loudness') if result.get('loudness') is not None else song.loudness

        song.save()

        logger.info("[ANALYZE_AUDIO] ✓ OK song_id=%s via %s BPM=%s Key=%s SourceURL=%s (total %.1fs)", song.id, source, bpm, key, source_url, _time.time() - t0)

        return JsonResponse({
            'success': True,
            'bpm': bpm,
            'key': key,
            'source': source,
            'source_url': source_url,
            'partial': not bpm or not key,
            'duration': song.duration,
            'popularity': song.popularity,
            'energy': song.energy,
            'danceability': song.danceability,
            'happiness': song.happiness,
            'acousticness': song.acousticness,
            'instrumentalness': song.instrumentalness,
            'liveness': song.liveness,
            'speechiness': song.speechiness,
            'loudness': song.loudness,
        })

    except Exception:
        logger.exception("[ANALYZE_AUDIO] ✗ EXCEPTION song_id=%s (total %.1fs)", song_id, _time.time() - t0)

        return JsonResponse({
            'success': False,
            'error': _('Error analitzant l\'àudio de la cançó.')
        }, status=500)


@login_required
def song_list(request):
    party_id = request.session.get('selected_party_id')
    if not party_id:
        return redirect('select_party')
    party = get_object_or_404(Party, pk=party_id)
    request._party_cache = party
    user = request.user

    # Si la festa és visible però la llista no s'ha carregat encara, mostrar espera
    if party.party_status == Party.STATUS_PARTY_VISIBLE:
        return render(request, 'jukebox/song_list.html', {
            'party': party,
            'songs': [],
            'playlist_not_ready': True,
        })

    # Assegurar que l'usuari tingui els coins gratuïts de festa (si han canviat)
    ensure_user_has_free_coins(user, party)

    # Comprovar vots restants segons límit de la festa
    votes_left = get_user_votes_left(user, party)
    credits = get_user_available_coins(user, party)
    party_coins = get_user_party_coins(user, party)  # Coins gratuïts de festa

    # Obtenir cançons amb annotations de vots
    annotated_songs = get_annotated_party_songs(party)

    voting_enabled = party.party_status in (
        Party.STATUS_REQUESTS_OPEN,
        Party.STATUS_DJJUKEBOX_ACTIVE,
    )

    if request.method == 'POST':
        # Conversió de Coins a Vots amb bonificació per volum
        if 'action' in request.POST and request.POST['action'] == 'convert_coins':
            try:
                coins_to_convert = max(0, min(int(request.POST.get('coins_to_convert', 0)), 10000))
            except (ValueError, TypeError):
                return redirect('song_list')
            success, error_msg, votes_added = convert_coins_to_votes(
                user, party, coins_to_convert
            )
            if success:
                return redirect('song_list')
            # Si falla, continua per mostrar error (es gestiona més avall)

        # Desfer vot d'una cançó
        elif 'unvote_song_id' in request.POST and voting_enabled:
            song = get_object_or_404(Song, pk=request.POST['unvote_song_id'], party=party)
            Vote.objects.filter(user=user, song=song, party=party).delete()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                num_likes = song.vote.filter(party=party, vote_type='like').count()
                num_dislikes = song.vote.filter(party=party, vote_type__in=NEGATIVE_VOTE_TYPES).count()
                calc = BadgeCalculator(party.songs)
                badge_label, badge_bg, badge_text = calc.calculate_badge(num_likes, num_dislikes)
                return JsonResponse({
                    'success': True, 'song_id': song.id, 'user_vote': None,
                    'num_likes': num_likes, 'badge_label': badge_label,
                    'badge_bg': badge_bg, 'badge_text': badge_text,
                    'votes_left': get_user_votes_left(user, party), 'credits': get_user_available_coins(user, party),
                })
            return redirect('song_list')

        # Votar una cançó
        elif 'vote_song_id' in request.POST and voting_enabled:
            song = get_object_or_404(Song, pk=request.POST['vote_song_id'], party=party)
            vote_type = request.POST.get('vote_type', 'like')

            from jukebox.utils.vote_validation import validate_and_create_vote
            success, error_msg = validate_and_create_vote(user, song, party, vote_type)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                if success:
                    num_likes = song.vote.filter(party=party, vote_type='like').count()
                    num_dislikes = song.vote.filter(party=party, vote_type__in=NEGATIVE_VOTE_TYPES).count()
                    calc = BadgeCalculator(party.songs)
                    badge_label, badge_bg, badge_text = calc.calculate_badge(num_likes, num_dislikes)
                    return JsonResponse({
                        'success': True, 'song_id': song.id, 'user_vote': vote_type,
                        'num_likes': num_likes, 'badge_label': badge_label,
                        'badge_bg': badge_bg, 'badge_text': badge_text,
                        'votes_left': get_user_votes_left(user, party), 'credits': get_user_available_coins(user, party),
                    })
                else:
                    return JsonResponse({'success': False, 'error': error_msg}, status=400)
            if not success and error_msg:
                messages.warning(request, error_msg)
            return redirect('song_list')

    SONGS_PAGE_SIZE = 15

    # Played songs (avaluat completament — normalment petit)
    played_songs = list(annotated_songs.filter(has_played=True).order_by('-played_at', '-id'))

    # Pending: primer page per al render inicial
    pending_songs_qs = annotated_songs.filter(has_played=False).order_by('-num_likes', 'title')
    pending_songs = list(pending_songs_qs[:SONGS_PAGE_SIZE])

    # Compte total ràpid (sense annotations) per als stats i infinite scroll
    pending_total = party.songs.filter(has_played=False).count()
    has_more_pending = pending_total > SONGS_PAGE_SIZE

    # Obtenir els vots de l'usuari per mostrar els cors/creus marcats
    user_votes = Vote.objects.filter(user=user, party=party).select_related('song')
    user_votes_dict = {v.song_id: v.vote_type for v in user_votes}

    songs_played = len(played_songs)
    songs_remaining = pending_total
    total_songs = pending_total + songs_played
    songs_with_votes = 0
    songs_with_votes_percentage = 0

    # Cançó que està sonant (primera en la cua per vots)
    now_playing = pending_songs[0] if pending_songs else None

    # songs queryset per al desktop view (no avaluat si no s'usa)
    songs = pending_songs_qs

    # KPIs amb aggregate combinat (1 query per Vote, 1 per SongRequest)
    thirty_min_ago = timezone.now() - timezone.timedelta(minutes=30)
    vote_stats = Vote.objects.filter(party=party).aggregate(
        total_votes=Count('id', filter=Q(vote_type='like')),
        user_votes_count=Count('id', filter=Q(user=user, vote_type='like')),
        recent_votes=Count('id', filter=Q(created_at__gte=thirty_min_ago)),
        my_played_votes=Count('id', filter=Q(user=user, vote_type='like', song__has_played=True)),
    )
    total_votes = vote_stats['total_votes'] or 0
    user_votes_count = vote_stats['user_votes_count'] or 0
    recent_votes = vote_stats['recent_votes'] or 0
    my_played_votes = vote_stats['my_played_votes'] or 0

    request_stats = SongRequest.objects.filter(party=party).aggregate(
        active_count=Count('id', filter=Q(status__in=['pending', 'queued'])),
        total_coins=Sum('coins_cost', filter=Q(status='accepted')),
    )
    pending_requests_count = request_stats['active_count'] or 0
    total_coins_spent = request_stats['total_coins'] or 0

    # KPI actius — cached 30s per evitar la OR cross-table en cada request
    _active_users_key = f'active_users_{party.pk}'
    active_users = cache.get(_active_users_key)
    if active_users is None:
        active_users = User.objects.filter(
            Q(vote__party=party) | Q(songrequest__party=party)
        ).distinct().count()
        cache.set(_active_users_key, active_users, 30)

    # Aplicar badges dinàmics (pending_songs i played_songs ja són llistes)
    badge_calc = BadgeCalculator(party.songs)
    calculate_and_apply_badges(party, pending_songs, badge_calc)
    calculate_and_apply_badges(party, played_songs, badge_calc)

    # Afegir display_order per cançons jugades
    for index, song in enumerate(played_songs):
        song.display_order = songs_played - index

    # Recomanacions intel·ligents (harmonia + BPM + vots)
    from .recommendation import get_recommended_songs
    recommended_songs = get_recommended_songs(party, limit=6) if party.party_status == Party.STATUS_DJJUKEBOX_ACTIVE else []
    if recommended_songs:
        calculate_and_apply_badges(party, recommended_songs, badge_calc)

    # Obtenir context Spotify (token i has_spotify)
    spotify_context = get_spotify_context_for_view(user)

    return render(request, "jukebox/song_list.html", {
        "party": party,
        "songs": songs,
        "pending_songs": pending_songs,
        "played_songs": played_songs,
        "votes_left": votes_left,
        "credits": credits,
        "party_coins": party_coins,
        "songs_played": songs_played,
        "songs_remaining": songs_remaining,
        "user_votes_count": user_votes_count,
        "total_songs": total_songs,
        "total_votes": total_votes,
        "now_playing": now_playing,
        "user_votes_dict": user_votes_dict,
        **spotify_context,  # Desempaqueta has_spotify i spotify_token
        "active_users": active_users,
        "recent_votes": recent_votes,
        "pending_requests_count": pending_requests_count,
        "songs_with_votes": songs_with_votes,
        "songs_with_votes_percentage": songs_with_votes_percentage,
        "total_coins_spent": total_coins_spent,
        "voting_enabled": voting_enabled,
        "my_played_votes": my_played_votes,
        "recommended_songs": recommended_songs,
        "has_more_pending": has_more_pending,
        "pending_page_size": SONGS_PAGE_SIZE,
    })


@login_required
def song_list_more(request):
    """Infinite scroll endpoint: returns next batch of mobile pending song cards as HTML."""
    party_id = request.session.get('selected_party_id')
    if not party_id:
        return JsonResponse({'error': 'no party'}, status=400)

    party = get_object_or_404(Party, pk=party_id)
    user = request.user

    SONGS_PAGE_SIZE = 15
    try:
        offset = max(0, int(request.GET.get('offset', 0)))
    except (ValueError, TypeError):
        offset = 0

    from .utils.query_helpers import get_annotated_party_songs
    pending_qs = get_annotated_party_songs(party, played_filter=False).order_by('-num_likes', 'title')
    songs = list(pending_qs[offset:offset + SONGS_PAGE_SIZE])
    pending_total = party.songs.filter(has_played=False).count()
    has_more = (offset + SONGS_PAGE_SIZE) < pending_total

    badge_calc = BadgeCalculator(party.songs)
    calculate_and_apply_badges(party, songs, badge_calc)

    song_ids = [s.id for s in songs]
    user_votes_dict = {
        v.song_id: v.vote_type
        for v in Vote.objects.filter(user=user, party=party, song_id__in=song_ids)
    }

    votes_left = get_user_votes_left(user, party)
    credits = get_user_available_coins(user, party)
    voting_enabled = party.party_status in (Party.STATUS_REQUESTS_OPEN, Party.STATUS_DJJUKEBOX_ACTIVE)
    spotify_context = get_spotify_context_for_view(user)

    from django.template.loader import render_to_string
    html = render_to_string('jukebox/_song_card_mobile_pending.html', {
        'songs': songs,
        'user_votes_dict': user_votes_dict,
        'voting_enabled': voting_enabled,
        'votes_left': votes_left,
        'credits': credits,
        'has_spotify': spotify_context.get('has_spotify', False),
    }, request=request)

    return JsonResponse({
        'html': html,
        'has_more': has_more,
        'next_offset': offset + SONGS_PAGE_SIZE,
    })


@login_required
def party_status_api(request):
    """Lightweight JSON endpoint for polling party status from song_list."""
    party_id = request.session.get('selected_party_id')
    if not party_id:
        return JsonResponse({'error': 'No party selected'}, status=400)
    party = get_object_or_404(Party, pk=party_id)
    user = request.user

    last_played = party.songs.filter(has_played=True).order_by('-played_at', '-id').first()
    now_playing_song = party.songs.filter(has_played=False).annotate(
        num_likes=Count('vote', filter=Q(vote__vote_type='like'))
    ).order_by('-num_likes').first()

    total_songs = party.songs.count()
    total_votes = Vote.objects.filter(party=party, vote_type='like').count()
    songs_played = party.songs.filter(has_played=True).count()
    user_votes_count = Vote.objects.filter(user=user, party=party, vote_type='like').count()
    songs_remaining = total_songs - songs_played
    my_played_votes = Vote.objects.filter(
        user=user, party=party, vote_type='like', song__has_played=True
    ).count()
    pending_requests_count = SongRequest.objects.filter(party=party, status__in=['pending', 'queued']).count()
    User = get_user_model()
    active_users = User.objects.filter(
        Q(vote__party=party) | Q(songrequest__party=party)
    ).distinct().count()

    return JsonResponse({
        'party_status': party.party_status,
        'total_songs': total_songs,
        'total_votes': total_votes,
        'songs_played': songs_played,
        'songs_remaining': songs_remaining,
        'user_votes_count': user_votes_count,
        'last_played_title': last_played.title if last_played else None,
        'last_played_artist': last_played.artist if last_played else None,
        'now_playing_title': now_playing_song.title if now_playing_song else None,
        'now_playing_artist': now_playing_song.artist if now_playing_song else None,
        'party_date': party.date.strftime('%d/%m %H:%M') if party.date else None,
        'votes_left': get_user_votes_left(user, party),
        'credits': get_user_available_coins(user, party),
        'my_played_votes': my_played_votes,
        'pending_requests_count': pending_requests_count,
        'active_users': active_users,
    })


@user_passes_test(lambda u: u.is_superuser)
def dj_backoffice(request):
    songs = Song.objects.annotate(num_likes=Count('vote', filter=Q(vote__vote_type='like'))).order_by('-num_likes')
    parties = Party.objects.order_by('-date')
    return render(request, 'jukebox/dj_backoffice.html', {
        'songs': songs,
        'parties': parties,
    })

@user_passes_test(lambda u: u.is_superuser)
def dj_monitoring(request):
    import sys as _sys
    import os as _os
    import django as _django

    # ── App KPIs ──────────────────────────────────────────────────────────────
    user_stats = User.objects.aggregate(
        total=Count('id'),
        avg_credits=Avg('credits'),
        total_credits=Sum('credits'),
    )
    party_stats = Party.objects.aggregate(
        total=Count('id'),
        active=Count('id', filter=~Q(party_status=Party.STATUS_FINISHED) & ~Q(party_status=Party.STATUS_HIDDEN)),
        finished=Count('id', filter=Q(party_status=Party.STATUS_FINISHED)),
    )
    vote_stats = Vote.objects.aggregate(
        total_votes=Count('id'),
        total_likes=Count('id', filter=Q(vote_type='like')),
    )
    request_stats = SongRequest.objects.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='pending')),
        queued=Count('id', filter=Q(status='queued')),
        accepted=Count('id', filter=Q(status='accepted')),
        rejected=Count('id', filter=Q(status='rejected')),
    )
    total_songs = Song.objects.count()
    songs_played = Song.objects.filter(has_played=True).count()
    paid_purchases = VotePackage.objects.filter(payment_id__isnull=False).count()
    total_coins_charged = SongRequest.objects.filter(
        coins_charged=True
    ).aggregate(total=Sum('coins_cost'))['total'] or 0

    # ── Server health ─────────────────────────────────────────────────────────
    try:
        connection.ensure_connection()
        db_ok = True
    except Exception:
        db_ok = False

    try:
        cache.set('_mon_health', 1, 10)
        cache_ok = cache.get('_mon_health') == 1
    except Exception:
        cache_ok = False

    db_engine = settings.DATABASES['default']['ENGINE'].split('.')[-1]
    db_name = settings.DATABASES['default'].get('NAME', '')
    db_size_mb = None
    if db_engine == 'sqlite3' and db_name:
        try:
            db_size_mb = round(_os.path.getsize(db_name) / 1024 / 1024, 1)
        except OSError:
            pass

    python_version = f"{_sys.version_info.major}.{_sys.version_info.minor}.{_sys.version_info.micro}"
    django_version = f"{_django.VERSION[0]}.{_django.VERSION[1]}.{_django.VERSION[2]}"

    # ── CPU / RAM ─────────────────────────────────────────────────────────────
    cpu_pct = None
    ram_pct = None
    ram_used_mb = None
    try:
        import psutil as _psutil
        cpu_pct = _psutil.cpu_percent(interval=0.1)
        _vm = _psutil.virtual_memory()
        ram_pct = round(_vm.percent, 1)
        ram_used_mb = _vm.used // (1024 * 1024)
    except Exception:
        pass

    # ── Response time stats (from ResponseTimingMiddleware) ───────────────────
    resp_avg_ms = None
    resp_p95_ms = None
    resp_samples = 0
    try:
        _samples = cache.get('_mon_resp_times') or []
        resp_samples = len(_samples)
        if _samples:
            _sorted = sorted(_samples)
            resp_avg_ms = round(sum(_sorted) / len(_sorted))
            p95_idx = max(0, int(len(_sorted) * 0.95) - 1)
            resp_p95_ms = round(_sorted[p95_idx])
    except Exception:
        pass

    # ── Recent server errors (last 200 log lines) ─────────────────────────────
    recent_errors = []
    log_path = _os.path.join(settings.BASE_DIR, 'server.log')
    try:
        with open(log_path, 'rb') as f:
            f.seek(0, 2)
            size = f.tell()
            chunk = min(size, 32768)
            f.seek(-chunk, 2)
            tail = f.read().decode('utf-8', errors='replace')
        for line in tail.splitlines():
            if 'Internal Server Error' in line or ('ERROR' in line and 'dj_jukebox' in line):
                recent_errors.append(line.strip())
        recent_errors = recent_errors[-10:]
    except (OSError, IOError):
        pass

    all_parties = Party.objects.order_by('-date')

    users = User.objects.prefetch_related('dj_parties').annotate(
        vote_count=Count('vote', distinct=True),
        request_count=Count('songrequest', distinct=True),
        paid_packages_count=Count(
            'votepackage',
            filter=Q(votepackage__payment_id__isnull=False),
            distinct=True,
        ),
    ).order_by('username')

    party_table = Party.objects.annotate(
        like_count=Count('vote', filter=Q(vote__vote_type='like'), distinct=True),
        user_count=Count('vote__user', distinct=True),
        played_count=Count('songs', filter=Q(songs__has_played=True), distinct=True),
    ).order_by('-date')

    return render(request, 'jukebox/monitoring.html', {
        # App KPIs
        'total_users': user_stats['total'] or 0,
        'avg_credits': round(user_stats['avg_credits'] or 0, 1),
        'total_credits': user_stats['total_credits'] or 0,
        'total_parties': party_stats['total'] or 0,
        'active_parties': party_stats['active'] or 0,
        'finished_parties': party_stats['finished'] or 0,
        'total_votes': vote_stats['total_votes'] or 0,
        'total_likes': vote_stats['total_likes'] or 0,
        'total_songs': total_songs,
        'songs_played': songs_played,
        'total_requests': request_stats['total'] or 0,
        'pending_requests': request_stats['pending'] or 0,
        'queued_requests': request_stats['queued'] or 0,
        'requests_accepted': request_stats['accepted'] or 0,
        'requests_rejected': request_stats['rejected'] or 0,
        'paid_purchases': paid_purchases,
        'total_coins_charged': total_coins_charged,
        # Server health
        'db_ok': db_ok,
        'cache_ok': cache_ok,
        'db_engine': db_engine,
        'db_size_mb': db_size_mb,
        'python_version': python_version,
        'django_version': django_version,
        'debug_mode': settings.DEBUG,
        'recent_errors': recent_errors,
        # CPU / RAM / Response time
        'cpu_pct': cpu_pct,
        'ram_pct': ram_pct,
        'ram_used_mb': ram_used_mb,
        'resp_avg_ms': resp_avg_ms,
        'resp_p95_ms': resp_p95_ms,
        'resp_samples': resp_samples,
        # Tables
        'users': users,
        'party_table': party_table,
        'all_parties': all_parties,
    })


@user_passes_test(lambda u: u.is_superuser)
@require_POST
def update_user(request):
    import json as _json
    target = get_object_or_404(User, pk=request.POST.get('user_id'))
    update_fields = []
    errors = {}

    if 'credits' in request.POST:
        try:
            val = int(request.POST['credits'])
            if val < 0:
                raise ValueError
            target.credits = val
            update_fields.append('credits')
        except (ValueError, TypeError):
            errors['credits'] = 'Valor invàlid'

    if 'is_active' in request.POST:
        target.is_active = request.POST['is_active'] in ('1', 'true')
        update_fields.append('is_active')

    if 'username' in request.POST:
        new_username = request.POST['username'].strip()
        if not new_username:
            errors['username'] = 'El nom no pot estar buit'
        elif User.objects.exclude(pk=target.pk).filter(username=new_username).exists():
            errors['username'] = 'Aquest nom ja existeix'
        else:
            target.username = new_username
            update_fields.append('username')

    if errors:
        return JsonResponse({'success': False, 'errors': errors}, status=400)
    if update_fields:
        target.save(update_fields=update_fields)

    if 'dj_party_ids' in request.POST:
        try:
            new_ids = set(int(x) for x in _json.loads(request.POST['dj_party_ids']))
        except (ValueError, _json.JSONDecodeError):
            new_ids = set()
        current_ids = set(Party.objects.filter(djs=target).values_list('id', flat=True))
        for party in Party.objects.filter(pk__in=current_ids - new_ids):
            party.djs.remove(target)
        for party in Party.objects.filter(pk__in=new_ids - current_ids):
            party.djs.add(target)

    dj_party_ids = list(Party.objects.filter(djs=target).values_list('id', flat=True))
    return JsonResponse({
        'success': True,
        'user_id': target.id,
        'credits': target.credits,
        'is_active': target.is_active,
        'username': target.username,
        'dj_party_ids': dj_party_ids,
        'is_dj': bool(dj_party_ids),
    })


@login_required
@user_passes_test(is_dj_admin)
def dj_dashboard(request):
    from .recommendation import get_recommended_songs

    party_id = request.session.get('selected_party_id')
    if not party_id:
        return redirect('select_party')

    party = get_object_or_404(Party, pk=party_id)
    request._party_cache = party

    if not (request.user.is_superuser or party.djs.filter(pk=request.user.pk).exists()):
        return redirect('song_list')

    # Separar cançons pendents i ja posades amb annotations
    pending_songs = get_pending_songs_ordered(party)
    played_songs_list = get_played_songs_ordered(party)

    total_songs = party.songs.count()
    total_votes = Vote.objects.filter(party=party).count()
    played_songs_count = len(played_songs_list)
    for index, song in enumerate(played_songs_list):
        song.display_order = played_songs_count - index

    is_djjukebox_active = party.party_status == Party.STATUS_DJJUKEBOX_ACTIVE
    party_status_step_map = {
        Party.STATUS_HIDDEN: 0,
        Party.STATUS_PARTY_VISIBLE: 1,
        Party.STATUS_SHOW_PARTY: 2,
        Party.STATUS_REQUESTS_OPEN: 3,
        Party.STATUS_DJJUKEBOX_ACTIVE: 4,
    }
    is_party_finished = party.party_status == Party.STATUS_FINISHED
    party_status_step = party_status_step_map.get(party.party_status, 0)

    if party.party_status == Party.STATUS_HIDDEN:
        party_status_label = 'Festa Pausada'
        party_status_help = "La festa està pausada i encara no és visible pels usuaris."
    elif party.party_status == Party.STATUS_PARTY_VISIBLE:
        party_status_label = 'Festa Visible'
        party_status_help = "La festa és visible però la llista de cançons no s'ha carregat."
    elif party.party_status == Party.STATUS_SHOW_PARTY:
        party_status_label = 'Llista Carregada'
        party_status_help = "La llista de cançons és visible. Ja es pot votar."
    elif party.party_status == Party.STATUS_REQUESTS_OPEN:
        party_status_label = 'Obrir peticions'
        party_status_help = "Ja es pot votar i demanar cançons, però el DJ encara no les està puntant."
    elif party.party_status == Party.STATUS_DJJUKEBOX_ACTIVE:
        party_status_label = 'Iniciar Jukebox'
        party_status_help = "El DJ ja està marcant les cançons que van sonant."
    else:
        party_status_label = 'Acabar festa'
        party_status_help = "La festa queda tancada i ja no s'accepten més accions."

    # ==========================================
    # Nous KPIs per Dashboard Compacte
    # ==========================================

    # 1. Usuaris actius (han votat o demanat cançons)
    users_voted = Vote.objects.filter(party=party).values('user').distinct().count()
    users_requested = SongRequest.objects.filter(party=party).values('user').distinct().count()
    active_users = User.objects.filter(
        Q(vote__party=party) | Q(songrequest__party=party)
    ).distinct().count()

    # 2. Vots últims 30 minuts
    thirty_min_ago = timezone.now() - timezone.timedelta(minutes=30)
    recent_votes = Vote.objects.filter(party=party, created_at__gte=thirty_min_ago).count()

    # 3. Peticions


    # 4. Temes amb vots
    songs_with_votes = party.songs.annotate(vote_count=Count('vote')).filter(vote_count__gt=0).count()
    songs_with_votes_percentage = round((songs_with_votes / total_songs * 100) if total_songs > 0 else 0, 1)

    # 5. Coins gastats (peticions acceptades)
    total_coins_spent = SongRequest.objects.filter(
        party=party, status='accepted'
    ).aggregate(total=Sum('coins_cost'))['total'] or 0

    # Alternativa: comptar VotePackages creats per aquesta party (conversions coins->vots)
    vote_conversions_count = VotePackage.objects.filter(party=party).count()

    # Mapa posició a la maleta: song.id → número d'ordre (1-based)
    pending_song_positions = {song.id: i + 1 for i, song in enumerate(pending_songs)}

    # Obtenir recomanacions intel·ligents
    recommended_songs = get_recommended_songs(party, limit=6)
    pending_requests = list(SongRequest.objects.filter(party=party, status='pending').select_related('user').order_by('created_at'))
    queued_requests  = list(SongRequest.objects.filter(party=party, status='queued').select_related('user').order_by('created_at'))
    pending_requests_count = len(pending_requests) + len(queued_requests)

    unplayed_songs_by_spotify = {
        song.spotify_id: song.id
        for song in party.songs.filter(has_played=False)
    }
    accepted_unplayed_requests = list(
        SongRequest.objects.filter(
            party=party,
            status='accepted',
            spotify_id__in=list(unplayed_songs_by_spotify),
        ).select_related('user').order_by('-processed_at')
    )
    for req in accepted_unplayed_requests:
        req.linked_song_id = unplayed_songs_by_spotify.get(req.spotify_id)

    # ── Monitoring data (superuser only — no overhead for regular DJs) ──────────
    mon = {}
    if request.user.is_superuser:
        import sys as _sys, os as _os, django as _django
        # CPU / RAM
        try:
            import psutil as _psutil
            mon['cpu_pct'] = _psutil.cpu_percent(interval=0.1)
            _vm = _psutil.virtual_memory()
            mon['ram_pct'] = round(_vm.percent, 1)
            mon['ram_used_mb'] = _vm.used // (1024 * 1024)
        except Exception:
            pass
        # Response times
        try:
            _samples = cache.get('_mon_resp_times') or []
            if _samples:
                _s = sorted(_samples)
                mon['resp_avg_ms'] = round(sum(_s) / len(_s))
                mon['resp_p95_ms'] = round(_s[max(0, int(len(_s) * 0.95) - 1)])
        except Exception:
            pass
        # DB / cache status
        try:
            connection.ensure_connection()
            mon['db_ok'] = True
        except Exception:
            mon['db_ok'] = False
        try:
            cache.set('_mon_h2', 1, 10)
            mon['cache_ok'] = cache.get('_mon_h2') == 1
        except Exception:
            mon['cache_ok'] = False
        # Global app KPIs
        _ustats = User.objects.aggregate(total=Count('id'), avg_credits=Avg('credits'))
        mon['g_users'] = _ustats['total'] or 0
        mon['g_avg_credits'] = round(_ustats['avg_credits'] or 0, 1)
        mon['g_active_parties'] = Party.objects.filter(
            ~Q(party_status=Party.STATUS_FINISHED) & ~Q(party_status=Party.STATUS_HIDDEN)
        ).count()
        mon['g_total_parties'] = Party.objects.count()
        mon['g_total_votes'] = Vote.objects.count()
        mon['g_songs_played'] = Song.objects.filter(has_played=True).count()
        mon['g_pending_requests'] = SongRequest.objects.filter(status__in=['pending', 'queued']).count()
        # Recent errors
        _recent_errors = 0
        try:
            _log = _os.path.join(settings.BASE_DIR, 'server.log')
            with open(_log, 'rb') as _f:
                _f.seek(0, 2); _sz = _f.tell()
                _f.seek(-min(_sz, 32768), 2)
                for _line in _f.read().decode('utf-8', errors='replace').splitlines():
                    if 'Internal Server Error' in _line or ('ERROR' in _line and 'dj_jukebox' in _line):
                        _recent_errors += 1
            _recent_errors = min(_recent_errors, 99)
        except Exception:
            pass
        mon['recent_errors'] = _recent_errors
        # User list
        mon['users'] = User.objects.annotate(
            vote_count=Count('vote', distinct=True),
        ).order_by('username').values('id', 'username', 'credits', 'is_active', 'is_superuser', 'vote_count')

    context = {
        'party': party,
        'pending_songs': pending_songs,
        'played_songs_list': played_songs_list,
        'total_songs': total_songs,
        'total_votes': total_votes,
        'played_songs': played_songs_count,
        'recommended_songs': recommended_songs,
        'pending_song_positions': pending_song_positions,
        'pending_requests': pending_requests,
        'queued_requests': queued_requests,
        'accepted_unplayed_requests': accepted_unplayed_requests,
        # Nous KPIs
        'active_users': active_users,
        'recent_votes': recent_votes,
        'pending_requests_count': pending_requests_count,
        'songs_with_votes': songs_with_votes,
        'songs_with_votes_percentage': songs_with_votes_percentage,
        'total_coins_spent': total_coins_spent,
        'is_djjukebox_active': is_djjukebox_active,
        'is_party_finished': is_party_finished,
        'party_status_label': party_status_label,
        'party_status_help': party_status_help,
        'party_status_step': party_status_step,
        # Monitoring (superuser only)
        'mon': mon,
    }
    return render(request, 'jukebox/dj_dashboard.html', context)


@login_required
@require_POST
def update_party_status(request, party_id):
    """Actualitza l'estat operatiu de la festa i l'hora prevista del DJJukebox."""
    party = get_object_or_404(Party, id=party_id)
    if not (request.user.is_superuser or party.djs.filter(pk=request.user.pk).exists()):
        return redirect('song_list')
    requested_status = request.POST.get('party_status', party.party_status)
    allowed_statuses = {
        Party.STATUS_HIDDEN,
        Party.STATUS_PARTY_VISIBLE,
        Party.STATUS_SHOW_PARTY,
        Party.STATUS_REQUESTS_OPEN,
        Party.STATUS_DJJUKEBOX_ACTIVE,
        Party.STATUS_FINISHED,
    }

    if requested_status not in allowed_statuses:
        requested_status = party.party_status

    starts_at_raw = (request.POST.get('jukebox_starts_at') or '').strip()
    jukebox_starts_at = None
    if starts_at_raw:
        try:
            jukebox_starts_at = datetime.strptime(starts_at_raw, '%H:%M').time()
        except ValueError:
            jukebox_starts_at = party.jukebox_starts_at

    party.party_status = requested_status
    party.jukebox_starts_at = jukebox_starts_at
    party.save(update_fields=['party_status', 'jukebox_starts_at', 'is_jukebox_active'])

    logger.info("[PARTY_STATUS] party_id=%s status=%s", party_id, party.party_status)
    return redirect('dj_dashboard')


@login_required
@user_passes_test(is_dj_admin)
@require_POST
def mark_song_played(request, song_id):
    song = get_object_or_404(Song, pk=song_id)
    if not (request.user.is_superuser or (song.party and song.party.djs.filter(pk=request.user.pk).exists())):
        return HttpResponse(status=403)
    song.has_played = True
    song.played_at = timezone.now()
    song.save(update_fields=['has_played', 'played_at'])

    create_song_played_notification(song)

    if song.party_id:
        from .recommendation import invalidate_recommendations_cache
        invalidate_recommendations_cache(song.party_id)

    return redirect('dj_dashboard')

@login_required
@user_passes_test(is_dj_admin)
@require_POST
def unmark_song_played(request, song_id):
    song = get_object_or_404(Song, pk=song_id)
    if not (request.user.is_superuser or (song.party and song.party.djs.filter(pk=request.user.pk).exists())):
        return HttpResponse(status=403)
    song.has_played = False
    song.played_at = None
    song.save(update_fields=['has_played', 'played_at'])
    return redirect('dj_dashboard')

@login_required
def buy_votes(request):
    import logging
    logger = logging.getLogger(__name__)

    party_id = request.session.get('selected_party_id')
    if not party_id:
        return redirect('select_party')
    party = get_object_or_404(Party, id=party_id)
    user = request.user
    ensure_user_has_free_coins(user, party)

    stripe.api_key = settings.STRIPE_SECRET_KEY  # ← AQUI SEMPRE!

    votes_left = get_user_votes_left(user, party)

    if request.method == 'POST':
        # Conversió de Coins a Vots
        if 'action' in request.POST and request.POST['action'] == 'convert_coins':
            try:
                coins_to_convert = max(0, min(int(request.POST.get('coins_to_convert', 0)), 10000))
            except (ValueError, TypeError):
                return HttpResponse(status=400)
            success, error_msg, votes_added = convert_coins_to_votes(
                user, party, coins_to_convert
            )
            if success:
                return redirect('buy_votes')
            # Si falla, continua amb render (gestiona error més avall)

        # Compra de Coins amb Stripe
        else:
            try:
                coins_to_buy = int(request.POST.get('votes', 10))  # 'votes' param name per compatibilitat
            except (ValueError, TypeError):
                return HttpResponse(status=400)
            package_prices = {
                5: 1,
                30: 5,
                60: 10,
            }
            price_eur = package_prices.get(coins_to_buy)

            if price_eur is None:
                return render(request, "jukebox/buy_votes.html", {
                    "party": party,
                    "credits": get_user_available_coins(user, party),
                    "votes_left": votes_left,
                    "error": "Paquet de Coins no disponible."
                })

            try:
                session = stripe.checkout.Session.create(
                    payment_method_types=['card'],
                    line_items=[{
                        'price_data': {
                            'currency': 'eur',
                            'product_data': {
                                'name': f'Paquet de {coins_to_buy} Coins - DJ Jukebox',
                                'description': f'Moneda virtual per votar a les festes',
                            },
                            'unit_amount': int(price_eur * 100),
                        },
                        'quantity': 1,
                    }],
                    mode='payment',
                    success_url=request.build_absolute_uri('/buy-coins/success/') + '?session_id={CHECKOUT_SESSION_ID}',
                    cancel_url=request.build_absolute_uri('/buy-coins/'),
                    metadata={
                        'user_id': request.user.id,
                        'party_id': party.id,
                        'votes_purchased': coins_to_buy,  # ara són Coins
                    }
                )
                return redirect(session.url, code=303)
            except stripe.error.AuthenticationError:
                logger.exception("[STRIPE] Error d'autenticació creant checkout per user_id=%s", user.id)
                return render(request, "jukebox/buy_votes.html", {
                    "party": party,
                    "credits": get_user_available_coins(user, party),
                    "votes_left": votes_left,
                    "error": "Error de configuració de pagament. Contacta amb l'administrador."
                })
            except stripe.error.StripeError:
                logger.exception("[STRIPE] Error de Stripe creant checkout per user_id=%s", user.id)
                return render(request, "jukebox/buy_votes.html", {
                    "party": party,
                    "credits": get_user_available_coins(user, party),
                    "votes_left": votes_left,
                    "error": "Error processant el pagament. Si us plau, torna-ho a provar més tard."
                })

    return render(request, "jukebox/buy_votes.html", {
        "party": party,
        "credits": get_user_available_coins(user, party),
        "votes_left": votes_left,
    })

@login_required
def buy_votes_success(request):
    # En desenvolupament, simular el webhook si no s'ha rebut
    if settings.DEBUG:
        import logging
        logger = logging.getLogger(__name__)

        # Comprovar si hi ha session_id a la URL
        session_id = request.GET.get('session_id')
        if session_id:
            try:
                stripe.api_key = settings.STRIPE_SECRET_KEY
                session = stripe.checkout.Session.retrieve(session_id)

                # Comprovar si ja s'ha processat aquest pagament
                already_processed = VotePackage.objects.filter(payment_id=session_id).exists()

                if session.payment_status == 'paid' and not already_processed:
                    user_id = int(session.metadata['user_id'])
                    coins = int(session.metadata['votes_purchased'])
                    party_id = int(session.metadata['party_id'])

                    if user_id == request.user.id:
                        user = request.user
                        party = Party.objects.get(id=party_id)
                        logger.info("[DEV_WEBHOOK] Simulant webhook en debug per session_id=%s", session_id)
                        with transaction.atomic():
                            pkg, created = VotePackage.objects.get_or_create(
                                payment_id=session_id,
                                defaults={'user': user, 'party': party, 'votes_purchased': 0}
                            )
                            if created:
                                User.objects.filter(pk=user.pk).update(credits=F('credits') + coins)
                                user.refresh_from_db(fields=['credits'])
                                create_coins_purchased_notification(user, coins)
                                logger.info("[DEV_WEBHOOK] Pagament aplicat a user_id=%s", user.id)
                elif already_processed:
                    logger.info("[DEV_WEBHOOK] Pagament duplicat ignorat per session_id=%s", session_id)
            except Exception:
                logger.exception("[DEV_WEBHOOK] Error processant session_id=%s", session_id)

    return render(request, "jukebox/buy_votes_success.html")


@csrf_exempt
def stripe_webhook(request):
    import logging
    logger = logging.getLogger(__name__)

    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    event = None

    logger.info("[STRIPE_WEBHOOK] Webhook rebut")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
        logger.info("[STRIPE_WEBHOOK] Event verificat type=%s", event.type)
    except (ValueError, AttributeError, stripe.error.SignatureVerificationError):
        logger.warning("[STRIPE_WEBHOOK] Error de verificació de signatura")
        return HttpResponse(status=400)

    if event.type == 'checkout.session.completed':
        session = event.data.object
        session_id = session.id
        user_id = session.metadata['user_id']
        coins = int(session.metadata['votes_purchased'])  # Comprem Coins!
        party_id = session.metadata['party_id']

        logger.info("[STRIPE_WEBHOOK] Processant checkout.session.completed session_id=%s", session_id)

        try:
            user = User.objects.get(id=user_id)
            party = Party.objects.get(id=party_id)

            with transaction.atomic():
                package, created = VotePackage.objects.get_or_create(
                    payment_id=session_id,
                    defaults={
                        'user': user,
                        'party': party,
                        'votes_purchased': 0,
                    }
                )
                if not created:
                    logger.warning("[STRIPE_WEBHOOK] Pagament duplicat ignorat per session_id=%s", session_id)
                    return HttpResponse(status=200)

                # Afegir Coins atòmicament
                User.objects.filter(pk=user.pk).update(credits=F('credits') + coins)

            # Crear notificació (fora de la transacció atòmica per evitar bloquejos llargs)
            user.refresh_from_db(fields=['credits'])
            create_coins_purchased_notification(user, coins)

            logger.info("[STRIPE_WEBHOOK] Pagament aplicat a user_id=%s", user.id)
        except User.DoesNotExist:
            logger.error("[STRIPE_WEBHOOK] Usuari inexistent per session_id=%s", session_id)
        except Party.DoesNotExist:
            logger.error("[STRIPE_WEBHOOK] Party inexistent per session_id=%s", session_id)

    return HttpResponse(status=200)

@login_required
@user_passes_test(is_dj_admin)
def get_spotify_playlists(request):
    """
    Retorna JSON amb la llista de playlists de l'usuari logat a Spotify.
    Si no està enllaçat o no hi ha playlists, retorna error 400.
    """
    try:
        playlists = get_user_playlists(request)
    except SpotifyAuthError:
        return JsonResponse(
            {
                'error': 'La sessió de Spotify ha caducat.',
                'reconnect_url': get_spotify_reconnect_url(request),
            },
            status=401
        )
    if not playlists:
        return JsonResponse(
            {'error': 'No Spotify account linked or no playlists found.'},
            status=400
        )
    return JsonResponse({'playlists': playlists})


@login_required
def api_spotify_token(request):
    """Returns the current user's Spotify token for the Web Playback SDK."""
    from .utils.spotify_helpers import get_user_spotify_token
    token = get_user_spotify_token(request.user, raise_on_error=False)
    if not token:
        return JsonResponse({'error': 'No Spotify token available'}, status=401)
    return JsonResponse({'token': token})


def buttons(request):
    return render(request, 'jukebox/buttons.html')

def cards(request):
    return render(request, 'jukebox/cards.html')

def charts(request):
    return render(request, 'jukebox/charts.html')

def tables(request):
    return render(request, 'jukebox/tables.html')

# def login(request):
#     return render(request, 'jukebox/login.html')
#
# def register(request):
#     return render(request, 'jukebox/register.html')

def forgot_password(request):
    return render(request, 'jukebox/forgot-password.html')

def blank(request):
    return render(request, 'jukebox/blank.html')

def about(request):
    """Pàgina pública amb informació del projecte."""
    return render(request, 'jukebox/about.html')

def page_404(request):
    return render(request, 'jukebox/404.html')

def utilities_color(request):
    return render(request, 'jukebox/utilities-color.html')

def utilities_border(request):
    return render(request, 'jukebox/utilities-border.html')

def utilities_animation(request):
    return render(request, 'jukebox/utilities-animation.html')

def utilities_other(request):
    return render(request, 'jukebox/utilities-other.html')


@login_required
def notifications(request):
    """Vista per veure totes les notificacions de l'usuari"""
    user_notifications = request.user.notifications.all()[:50]  # Últimes 50

    # Marcar totes com a llegides quan visites la pàgina
    request.user.notifications.filter(is_read=False).update(is_read=True)

    return render(request, 'jukebox/notifications.html', {
        'notifications': user_notifications,
    })


@login_required
@require_POST
def mark_notification_read(request, notification_id):
    """
    API endpoint per marcar una notificació individual com a llegida.
    Retorna JSON amb l'estat actualitzat del comptador de notificacions.
    """
    notification = get_object_or_404(Notification, pk=notification_id, user=request.user)

    if notification.is_read:
        # Ja estava llegida, no cal actualitzar
        unread_count = request.user.notifications.filter(is_read=False).count()
        return JsonResponse({
            'success': True,
            'already_read': True,
            'unread_count': unread_count,
        })

    notification.is_read = True
    notification.save(update_fields=['is_read'])

    # Obtenir el nou comptador de notificacions no llegides
    unread_count = request.user.notifications.filter(is_read=False).count()

    return JsonResponse({
        'success': True,
        'already_read': False,
        'unread_count': unread_count,
    })


@login_required
@require_POST
def mark_all_notifications_read(request):
    """
    Marca totes les notificacions de l'usuari com a llegides.
    Retorna el nombre de notificacions actualitzades.
    """
    updated_count = request.user.notifications.filter(is_read=False).update(is_read=True)
    return JsonResponse({
        'success': True,
        'updated_count': updated_count,
        'unread_count': 0,
    })


@login_required
def song_swipe(request):
    """Vista Busca Match per votar cançons amb like/next"""
    party_id = request.session.get('selected_party_id')
    if not party_id:
        return redirect('select_party')

    party = get_object_or_404(Party, pk=party_id)
    request._party_cache = party
    user = request.user

    if party.party_status not in (Party.STATUS_REQUESTS_OPEN, Party.STATUS_DJJUKEBOX_ACTIVE):
        messages.warning(request, _("Els vots encara no estan disponibles per a aquesta festa."))
        return redirect('song_list')

    # Assegurar que l'usuari tingui els coins gratuïts de festa
    ensure_user_has_free_coins(user, party)

    votes_left = get_user_votes_left(user, party)
    credits = get_user_available_coins(user, party)
    party_coins = get_user_party_coins(user, party)
    user_likes_count = Vote.objects.filter(user=user, party=party, vote_type='like').count()
    total_songs = party.songs.count()

    if request.method == 'POST':
        action = request.POST.get('action')
        song_id = request.POST.get('song_id')

        # Gestió unificada de vots
        if action in ['like', 'dislike'] and song_id:
            from .utils import handle_vote_action
            try:
                song = get_object_or_404(Song, pk=song_id, party=party)
                return handle_vote_action(
                    user, song, party, action,
                    response_type='json'
                )
            except Exception as exc:
                import logging
                logging.getLogger(__name__).exception('Error al votar song_id=%s', song_id)
                return JsonResponse({'success': False, 'error': str(exc) or _('Error inesperat al votar')}, status=500)

        if action == 'next' and song_id:
            song = get_object_or_404(Song, pk=song_id, party=party)
            if Vote.objects.filter(user=user, song=song, party=party).exists():
                return JsonResponse({'success': False, 'error': _('Ja has votat aquesta cançó')}, status=400)
            SongSwipeSkip.objects.get_or_create(user=user, song=song, party=party)
            return JsonResponse({
                'success': True,
                'votes_left': get_user_votes_left(user, party),
                'credits': get_user_available_coins(user, party),
                'user_likes_count': Vote.objects.filter(user=user, party=party, vote_type='like').count(),
            })

        if action == 'undo' and song_id:
            song = get_object_or_404(Song, pk=song_id, party=party)
            Vote.objects.filter(user=user, song=song, party=party).delete()
            SongSwipeSkip.objects.filter(user=user, song=song, party=party).delete()
            return JsonResponse({
                'success': True,
                'votes_left': get_user_votes_left(user, party),
                'credits': get_user_available_coins(user, party),
                'user_likes_count': Vote.objects.filter(user=user, party=party, vote_type='like').count(),
            })

        # Qualsevol POST no reconegut retorna JSON (evita HTML fall-through)
        return JsonResponse({'success': False, 'error': _('Acció no vàlida')}, status=400)

    # Obtenir cançons que l'usuari encara no ha votat amb annotations
    import random as _random
    voted_song_ids = Vote.objects.filter(user=user, party=party).values_list('song_id', flat=True)
    skipped_song_ids = SongSwipeSkip.objects.filter(user=user, party=party).values_list('song_id', flat=True)
    songs = list(
        get_annotated_party_songs(party)
        .exclude(id__in=voted_song_ids)
        .exclude(id__in=skipped_song_ids)
    )
    _random.shuffle(songs)
    swiped_count = total_songs - len(songs)

    # Aplicar badges dinàmics
    calculate_and_apply_badges(party, songs)

    # Obtenir context Spotify
    spotify_context = get_spotify_context_for_view(user)

    return render(request, 'jukebox/song_swipe.html', {
        'party': party,
        'songs': songs,
        'votes_left': votes_left,
        'user_likes_count': user_likes_count,
        'total_songs': total_songs,
        'swiped_count': swiped_count,
        'credits': credits,
        'party_coins': party_coins,
        **spotify_context,  # Desempaqueta has_spotify i spotify_token
    })


@login_required
def request_song(request):
    """Vista per demanar cançons noves"""
    party_id = request.session.get('selected_party_id')
    if not party_id:
        return redirect('select_party')

    party = get_object_or_404(Party, pk=party_id)

    if not party.allow_song_requests:
        messages.error(request, _("Les peticions de cançons no estan activades per a aquesta festa."))
        return redirect('song_list')

    user = request.user
    ensure_user_has_free_coins(user, party)

    # Cerca de cançons — usa client credentials, no cal que l'usuari tingui Spotify connectat
    if request.method == 'GET' and 'search' in request.GET:
        query = request.GET.get('search', '').strip()
        if query:
            tracks = search_spotify_tracks_public(query, limit=20)
            if tracks:
                track_ids = [t['id'] for t in tracks]
                # Songs already in the party list
                in_list = set(
                    Song.objects.filter(party=party, spotify_id__in=track_ids)
                    .values_list('spotify_id', flat=True)
                )
                # Active song requests (pending/queued)
                requested = dict(
                    SongRequest.objects.filter(
                        party=party,
                        spotify_id__in=track_ids,
                        status__in=['pending', 'queued'],
                    ).values_list('spotify_id', 'status')
                )
                for track in tracks:
                    tid = track['id']
                    if tid in in_list:
                        track['maleta_status'] = 'in_list'
                    elif tid in requested:
                        track['maleta_status'] = requested[tid]
            return JsonResponse({'tracks': tracks})
        return JsonResponse({'tracks': []})

    # Enviar o cancel·lar petició
    if request.method == 'POST':
        # Cancel·lar petició pròpia (pending only — queued ja ha estat acceptada pel DJ)
        if request.POST.get('action') == 'cancel':
            request_id = request.POST.get('request_id')
            if not request_id:
                return JsonResponse({'success': False, 'error': _('Petició no especificada.')}, status=400)
            try:
                with transaction.atomic():
                    song_request = SongRequest.objects.select_for_update().get(
                        pk=request_id, party=party, user=user, status='pending',
                    )
                    refunded = 0
                    if song_request.coins_charged:
                        refund_user_coins_for_party(user, party, song_request.coins_cost)
                        refunded = song_request.coins_cost
                    Notification.objects.filter(song_request=song_request).delete()
                    title_saved = song_request.title
                    song_request.delete()
                if refunded:
                    create_coins_received_notification(
                        user, refunded,
                        reason=_('Petició cancel·lada: "%(title)s"') % {'title': title_saved},
                    )
                return JsonResponse({'success': True, 'message': _('Petició cancel·lada. %(coins)s Coins retornats.') % {'coins': refunded}})
            except SongRequest.DoesNotExist:
                return JsonResponse({'success': False, 'error': _('Petició no trobada o ja processada.')}, status=404)
            except Exception:
                logger.exception("[REQUESTS] Error cancel·lant petició request_id=%s", request_id)
                return JsonResponse({'success': False, 'error': _('Error intern cancel·lant la petició.')}, status=500)

        spotify_id = request.POST.get('spotify_id')
        title = request.POST.get('title')
        artist = request.POST.get('artist')
        album_image_url = request.POST.get('album_image_url', '')

        if not spotify_id or not title or not artist:
            return JsonResponse({'success': False, 'error': _('Dades incompletes')}, status=400)

        cost = party.song_request_cost
        available = get_user_available_coins(user, party)
        if available < cost:
            return JsonResponse({
                'success': False,
                'error': _('No tens prou Coins per fer la petició (tens %(available)s, calen %(cost)s).') % {
                    'available': available, 'cost': cost,
                },
            }, status=400)

        # Retenir coins i crear petició — comprovacions dins la transacció per evitar race conditions
        with transaction.atomic():
            if party.songs.filter(spotify_id=spotify_id).exists():
                return JsonResponse({'success': False, 'error': _('Aquesta cançó ja està a la llista!')}, status=400)
            if SongRequest.objects.filter(party=party, spotify_id=spotify_id, status__in=['pending', 'queued']).exists():
                return JsonResponse({'success': False, 'error': _('Aquesta cançó ja ha estat demanada i està pendent')}, status=400)
            spent = spend_user_coins_for_party(user, party, cost, reason='song_request_hold')
            if not spent:
                return JsonResponse({'success': False, 'error': _('No tens prou Coins.')}, status=400)
            SongRequest.objects.create(
                user=user,
                party=party,
                title=title,
                artist=artist,
                spotify_id=spotify_id,
                album_image_url=album_image_url,
                coins_cost=cost,
                coins_charged=True,
                status='pending',
            )

        return JsonResponse({'success': True, 'message': _('Petició enviada! S\'han retingut %(cost)s Coins fins que el DJ decideixi.') % {'cost': cost}})

    # Llistar peticions de l'usuari per aquesta festa
    user_requests = SongRequest.objects.filter(user=user, party=party).order_by('-created_at')

    return render(request, 'jukebox/request_song.html', {
        'party': party,
        'user_requests': user_requests,
        'request_cost': party.song_request_cost,
        'user_credits': get_user_available_coins(user, party),
    })


@login_required
@user_passes_test(is_dj_admin)
@require_POST
def toggle_auto_sync(request, party_id):
    """
    Activa/desactiva la sincronització automàtica de playlist amb Spotify.
    Només accessible per superusuaris.
    """
    party = get_object_or_404(Party, id=party_id)
    if err := _party_dj_check(request, party):
        return err
    party.auto_sync_playlist = not party.auto_sync_playlist
    party.save(update_fields=['auto_sync_playlist'])

    logger.info(
        "[AUTO_SYNC] party_id=%s enabled=%s",
        party_id,
        party.auto_sync_playlist,
    )

    return JsonResponse({
        'success': True,
        'auto_sync_enabled': party.auto_sync_playlist,
        'last_sync_at': party.last_sync_at.isoformat() if party.last_sync_at else None,
    })


@login_required
@user_passes_test(is_dj_admin)
@require_POST
def toggle_auto_analyze(request, party_id):
    """
    Activa/desactiva l'anàlisi automàtica d'àudio de cançons pendents.
    Només accessible per superusuaris.
    """
    party = get_object_or_404(Party, id=party_id)
    if err := _party_dj_check(request, party):
        return err
    party.auto_analyze_audio = not party.auto_analyze_audio
    party.save(update_fields=['auto_analyze_audio'])

    # Comptar cançons pendents d'anàlisi
    pending_count = Song.objects.filter(party=party).filter(Q(bpm__isnull=True) | Q(key__isnull=True)).count()

    logger.info(
        "[AUTO_ANALYZE] party_id=%s enabled=%s pending=%s",
        party_id,
        party.auto_analyze_audio,
        pending_count,
    )

    return JsonResponse({
        'success': True,
        'auto_analyze_enabled': party.auto_analyze_audio,
        'pending_songs': pending_count,
        'last_analyze_at': party.last_analyze_at.isoformat() if party.last_analyze_at else None,
    })


@login_required
@user_passes_test(is_dj_admin)
@require_POST
def force_sync_playlist(request, party_id):
    """
    Força una sincronització manual de la playlist amb Spotify.
    Ignora el rate limit de 4 minuts.
    Només accessible per superusuaris.
    """
    from .spotify_sync import sync_playlist_with_spotify

    party = get_object_or_404(Party, id=party_id)
    if err := _party_dj_check(request, party):
        return err

    # Temporalment habilitar auto_sync per permetre la sincronització
    original_auto_sync = party.auto_sync_playlist
    if not original_auto_sync:
        party.auto_sync_playlist = True
        party.save(update_fields=['auto_sync_playlist'])

    # Temporalment esborrar last_sync_at per evitar rate limiting
    original_last_sync = party.last_sync_at
    party.last_sync_at = None
    party.save(update_fields=['last_sync_at'])

    try:
        result = sync_playlist_with_spotify(party_id)

        # Restaurar auto_sync si estava desactivat
        if not original_auto_sync:
            party.auto_sync_playlist = False
            party.save(update_fields=['auto_sync_playlist'])

        if result.get('success'):
            return JsonResponse(result)
        else:
            # Si hi ha error, restaurar last_sync_at original
            if not result.get('success') and original_last_sync:
                party.last_sync_at = original_last_sync
                party.save(update_fields=['last_sync_at'])

            return JsonResponse(result, status=400 if result.get('error') else 200)

    except Exception as e:
        logger.exception("[FORCE_SYNC] Error for party_id=%s", party_id)
        # Restaurar valors originals en cas d'error
        party.auto_sync_playlist = original_auto_sync
        party.last_sync_at = original_last_sync
        party.save(update_fields=['auto_sync_playlist', 'last_sync_at'])

        return JsonResponse({'error': _('Error intern sincronitzant la playlist.')}, status=500)


@login_required
@user_passes_test(is_dj_admin)
def manage_song_requests(request):
    """Vista per DJs per gestionar peticions de cançons"""
    party_id = request.session.get('selected_party_id')
    if request.method == 'POST' and not party_id:
        party_id = request.POST.get('party_id')
    if not party_id:
        return redirect('select_party')

    party = get_object_or_404(Party, pk=party_id)

    if not (request.user.is_superuser or party.djs.filter(pk=request.user.pk).exists()):
        return redirect('song_list')

    if request.method == 'POST':
        request_id = request.POST.get('request_id')
        action = request.POST.get('action')
        if not request_id or action not in {'queue', 'load', 'reject', 'delete'}:
            return JsonResponse({'success': False, 'error': _('Paràmetres invàlids.')}, status=400)

        # Delete works on any status — handle before the status-filtered lookup
        if action == 'delete':
            try:
                with transaction.atomic():
                    song_request = SongRequest.objects.select_for_update().get(
                        pk=request_id, party=party
                    )
                    refunded = 0
                    if song_request.coins_charged:
                        refund_user_coins_for_party(
                            song_request.user, party, song_request.coins_cost
                        )
                        refunded = song_request.coins_cost
                    # If queued, remove the song added by this request (it can't have
                    # pre-existed: creation-time check prevents duplicate requests).
                    # Only delete if still unplayed and has no votes.
                    if song_request.status == 'queued' and song_request.spotify_id:
                        Song.objects.filter(
                            party=party,
                            spotify_id=song_request.spotify_id,
                            has_played=False,
                            vote__isnull=True,
                        ).delete()
                    # Delete linked notifications so they disappear from the user's bell
                    Notification.objects.filter(song_request=song_request).delete()
                    song_request.delete()
                if refunded:
                    create_coins_received_notification(
                        song_request.user, refunded,
                        reason=_('Petició cancel·lada: "%(title)s"') % {'title': song_request.title},
                    )
                return JsonResponse({'success': True, 'message': _('Petició eliminada.')})
            except SongRequest.DoesNotExist:
                return JsonResponse({'success': False, 'error': _('Petició no trobada.')}, status=404)
            except Exception:
                logger.exception("[REQUESTS] Error eliminant petició request_id=%s party_id=%s", request_id, party.id)
                return JsonResponse({'success': False, 'error': _('Error intern eliminant la petició.')}, status=500)

        try:
            with transaction.atomic():
                try:
                    song_request = SongRequest.objects.select_for_update().get(
                        pk=request_id,
                        party=party,
                        status__in=['pending', 'queued'],
                    )
                except SongRequest.DoesNotExist:
                    return JsonResponse({'success': False, 'error': _('Petició no trobada o ja processada.')}, status=404)

                if action == 'reject':
                    _reject_song_request(song_request, request.user)
                    refund_msg = _(' (%(coins)s Coins retornats)') % {'coins': song_request.coins_cost} if song_request.coins_charged else ''
                    return JsonResponse({'success': True, 'message': _('Petició rebutjada.') + refund_msg})

                elif action == 'queue':
                    _queue_song_request(song_request, request.user)
                    return JsonResponse({'success': True, 'message': _('Cançó afegida a la maleta!')})

                elif action == 'load':
                    if party.party_status != Party.STATUS_DJJUKEBOX_ACTIVE:
                        return JsonResponse({'success': False, 'error': _('El Jukebox no està actiu.')}, status=400)
                    try:
                        _load_song_request(song_request, request.user)
                    except ValueError:
                        song_request.user.refresh_from_db(fields=['credits'])
                        return JsonResponse({
                            'success': False,
                            'error': _('L\'usuari no té prou Coins (%(current)s/%(required)s)') % {
                                'current': get_user_available_coins(song_request.user, party),
                                'required': song_request.coins_cost,
                            },
                        }, status=400)
                    return JsonResponse({'success': True, 'message': _('🚀 LOAD! Cançó carregada al Jukebox!')})

        except Exception:
            logger.exception("[REQUESTS] Error processant petició request_id=%s action=%s party_id=%s", request_id, action, party.id)
            return JsonResponse({'success': False, 'error': _('Error intern processant la petició.')}, status=500)

    # Llistar peticions actives (pending + queued) i historial
    active_requests = SongRequest.objects.filter(
        party=party, status__in=['pending', 'queued']
    ).select_related('user').order_by('created_at')
    processed_requests = SongRequest.objects.filter(
        party=party
    ).exclude(status__in=['pending', 'queued']).select_related('user', 'processed_by').order_by('-processed_at')[:20]

    return render(request, 'jukebox/manage_song_requests.html', {
        'party': party,
        'active_requests': active_requests,
        'pending_count': active_requests.filter(status='pending').count(),
        'queued_count': active_requests.filter(status='queued').count(),
        'processed_requests': processed_requests,
        'is_jukebox_active': party.party_status == Party.STATUS_DJJUKEBOX_ACTIVE,
    })
