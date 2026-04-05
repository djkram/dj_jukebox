# views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.translation import gettext as _
from allauth.account.forms import SignupForm
from allauth.socialaccount.models import SocialToken, SocialAccount
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.urls import reverse
from urllib.parse import urlencode

from .models import Song, Party, Playlist, Vote, VotePackage, SongRequest, Notification
from django.db.models import Sum, Count, Q
from .forms import PartyForm, PartySettingsForm
from .notifications import (
    create_song_accepted_notification,
    create_song_played_notification,
    create_coins_purchased_notification,
)
from .spotify_api import (
    SpotifyAuthError,
    _get_getsongbpm_features,
    add_track_to_playlist,
    remove_track_from_playlist,
    get_user_playlists,
    get_playlist_tracks,
    get_playlist_tracks_basic,
    get_audio_features_for_songs,
    search_spotify_tracks,
)
from .votes import get_user_votes_left, get_user_party_coins, ensure_user_has_free_coins
from django.utils import timezone
from datetime import datetime
from .audio_analysis import analyze_song_from_temporary_mp3

from django.contrib.auth import get_user_model
User = get_user_model()

import stripe
import logging

logger = logging.getLogger(__name__)


# Create your views here.


def is_dj_admin(user):
    return user.is_authenticated and user.is_superuser


def _spotify_reconnect_url(request):
    query = urlencode({
        "process": "connect",
        "next": request.get_full_path(),
    })
    return f"{reverse('spotify_login')}?{query}"

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


def _accept_song_request(song_request, processed_by, charge_user):
    charged_amount = None
    if charge_user:
        song_request.user.credits -= song_request.coins_cost
        song_request.user.save(update_fields=['credits'])
        charged_amount = song_request.coins_cost

    Song.objects.create(
        party=song_request.party,
        title=song_request.title,
        artist=song_request.artist,
        spotify_id=song_request.spotify_id,
        album_image_url=song_request.album_image_url,
    )

    song_request.status = 'accepted'
    song_request.processed_at = timezone.now()
    song_request.processed_by = processed_by
    song_request.save(update_fields=['status', 'processed_at', 'processed_by'])

    create_song_accepted_notification(song_request, charged_amount=charged_amount)
    return charged_amount

@user_passes_test(lambda u: u.is_superuser)
def dj_backoffice(request):
    songs = Song.objects.all().order_by('-votes')
    return render(request, 'jukebox/dj_backoffice.html', {'songs': songs})

def register(request):

    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            form.save(request)  # Passa request!
            return redirect('login')
    else:
        form = SignupForm()

    # Afegeix la classe 'form-control' a tots els camps
    for field in form.fields.values():
        field.widget.attrs['class'] = 'form-control'

    return render(request, 'jukebox/register.html', {'form': form})

@login_required
def profile(request):
    user = request.user
    has_spotify = SocialAccount.objects.filter(user=user, provider="spotify").exists()
    return render(request, "jukebox/profile.html", {
        "user": user,
        "has_spotify": has_spotify,
    })

def select_party(request):
    parties = Party.objects.order_by('-date')
    return render(request, "jukebox/select_party.html", {"parties": parties})

def set_party(request, party_id):
    party = get_object_or_404(Party, pk=party_id)
    request.session['selected_party_id'] = party.id
    return redirect("main")

def unset_party(request):
    try:
        del request.session['selected_party_id']
    except KeyError:
        pass
    return redirect('dj_backoffice')  # O on vulguis redirigir!

@login_required
@user_passes_test(is_dj_admin)
def party_settings(request, party_id):
    party = get_object_or_404(Party, pk=party_id)
    has_spotify = SocialAccount.objects.filter(user=request.user, provider="spotify").exists()

    # Processament del formulari
    if request.method == 'POST':
        form = PartySettingsForm(request.POST, instance=party, request=request)
        if form.is_valid():
            # Si es crida via AJAX i hi ha playlist, no carregar cançons
            # (es carregaran després via process_playlist_songs)
            has_playlist = bool(form.cleaned_data.get('spotify_playlist'))
            is_ajax = (
                request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
                request.POST.get('ajax_request') == '1'
            )
            load_songs = not (has_playlist and is_ajax)

            form.save(load_songs=load_songs)

            if is_ajax:
                return JsonResponse({'success': True})
            return redirect('party_settings', party_id=party.id)
    else:
        form = PartySettingsForm(instance=party, request=request)

    # Annotem els vots totals reals per cançó
    songs = party.songs.annotate(
        num_likes=Count('vote', filter=Q(vote__vote_type='like')),
        num_dislikes=Count('vote', filter=Q(vote__vote_type='dislike'))
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
            return redirect(_spotify_reconnect_url(request))

    # Obtenir token de Spotify per Web Playback SDK
    spotify_token = None
    if has_spotify:
        from .spotify_api import _ensure_valid_user_token
        try:
            spotify_token = _ensure_valid_user_token(request.user)
        except Exception as e:
            logger.warning(f"[SPOTIFY] Error obtenint token per Web Playback: {e}")
            has_spotify = False

    return render(request, 'jukebox/party_settings.html', {
        'party':     party,
        'form':      form,
        'songs':     songs,
        'pending_analysis_count': pending_analysis_count,
        'playlists': playlists,
        'has_spotify': has_spotify,
        'spotify_token': spotify_token,
        'only_owned': only_owned,
    })


@login_required
@user_passes_test(is_dj_admin)
def remove_playlist(request, party_id):
    party = get_object_or_404(Party, pk=party_id)
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
    spotify_playlist_id = request.POST.get('spotify_playlist_id', '').strip()

    if not spotify_playlist_id:
        return JsonResponse({'error': _('No s\'ha seleccionat cap playlist.')}, status=400)

    try:
        playlists = get_user_playlists(request)
    except SpotifyAuthError:
        return JsonResponse({
            'error': _('La sessió de Spotify ha caducat. Torna a connectar Spotify per continuar.'),
            'reconnect_url': _spotify_reconnect_url(request),
        }, status=401)

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
    spotify_playlist_id = request.POST.get('spotify_playlist_id')

    if not spotify_playlist_id:
        return JsonResponse({'error': _('No playlist ID provided')}, status=400)

    try:
        # Obtenir les cançons de Spotify (ràpid, només metadata)
        tracks = get_playlist_tracks_basic(request, spotify_playlist_id)

        # Crear un set amb els spotify_ids de la playlist actual
        spotify_ids_in_playlist = {tr['id'] for tr in tracks}

        # Obtenir les cançons existents a la DB
        existing_songs = party.songs.all()
        existing_spotify_ids = {song.spotify_id for song in existing_songs}

        # Identificar cançons a afegir (noves a la playlist)
        new_spotify_ids = spotify_ids_in_playlist - existing_spotify_ids

        # Identificar cançons a eliminar (ja no estan a la playlist)
        removed_spotify_ids = existing_spotify_ids - spotify_ids_in_playlist

        # Eliminar cançons que ja no estan a la playlist
        if removed_spotify_ids:
            party.songs.filter(spotify_id__in=removed_spotify_ids).delete()

        # Afegir noves cançons
        new_songs_count = 0
        for tr in tracks:
            if tr['id'] in new_spotify_ids:
                Song.objects.create(
                    party=party,
                    title=tr['title'],
                    artist=tr['artist'],
                    spotify_id=tr['id'],
                    album_image_url=tr.get('album_image_url'),
                    preview_url=tr.get('preview_url'),
                    bpm=None,
                    key=None,
                )
                new_songs_count += 1

        # Preparar missatge informatiu
        message_parts = []
        if new_songs_count > 0:
            message_parts.append(f'{new_songs_count} cançons noves afegides')
        if removed_spotify_ids:
            message_parts.append(f'{len(removed_spotify_ids)} cançons eliminades')
        if not message_parts:
            message_parts.append('Playlist sincronitzada (sense canvis)')

        message = '. '.join(message_parts) + '.'

        return JsonResponse({
            'success': True,
            'total': len(tracks),
            'new_songs': new_songs_count,
            'removed_songs': len(removed_spotify_ids),
            'message': message
        })
    except SpotifyAuthError:
        return JsonResponse({
            'error': 'La sessió de Spotify ha caducat. Torna a connectar Spotify per continuar.',
            'reconnect_url': _spotify_reconnect_url(request),
        }, status=401)

    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_dj_admin)
def party_settings_search_tracks(request, party_id):
    party = get_object_or_404(Party, pk=party_id)
    query = request.GET.get('search', '').strip()

    if not query:
        return JsonResponse({'tracks': []})

    try:
        tracks = search_spotify_tracks(request, query, limit=12)
    except SpotifyAuthError:
        return JsonResponse({
            'error': 'La sessió de Spotify ha caducat. Torna a connectar Spotify per buscar cançons.',
            'reconnect_url': _spotify_reconnect_url(request),
        }, status=401)

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

        features = get_audio_features_for_songs(request, [{
            'id': spotify_id,
            'title': title,
            'artist': artist,
        }]).get(spotify_id, {})

        song = Song.objects.create(
            party=party,
            title=title,
            artist=artist,
            spotify_id=spotify_id,
            album_image_url=album_image_url or None,
            bpm=features.get('bpm'),
            key=features.get('key'),
        )

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
        return JsonResponse({
            'error': 'La sessió de Spotify ha caducat. Torna a connectar Spotify per continuar.',
            'reconnect_url': _spotify_reconnect_url(request),
        }, status=401)
    except Exception as e:
        logger.error(f"[PLAYLIST_ADD] Error afegint cançó a la festa {party_id}: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(is_dj_admin)
@require_POST
def delete_song_from_party_playlist(request, party_id, song_id):
    party = get_object_or_404(Party, pk=party_id)
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
        return JsonResponse({
            'error': 'La sessió de Spotify ha caducat. Torna a connectar Spotify per continuar.',
            'reconnect_url': _spotify_reconnect_url(request),
        }, status=401)
    except Exception as e:
        logger.error(f"[PLAYLIST_DELETE] Error eliminant cançó {song_id} de la festa {party_id}: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(is_dj_admin)
@require_POST
def process_song_features(request, party_id):
    """
    Processa BPM i clau musical per un chunk de cançons.
    """
    party = get_object_or_404(Party, pk=party_id)
    chunk_size = int(request.POST.get('chunk_size', 10))
    offset = int(request.POST.get('offset', 0))

    try:
        # Obtenir cançons sense features
        songs_to_process = party.songs.filter(bpm__isnull=True)[offset:offset+chunk_size]
        total_pending = party.songs.filter(bpm__isnull=True).count()

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
        features_map = get_audio_features_for_songs(request, songs_metadata)

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
        total_pending_after = party.songs.filter(bpm__isnull=True).count()

        return JsonResponse({
            'success': True,
            'completed': total_pending_after == 0,
            'processed': processed,
            'total_pending': total_pending_after,
            'total_songs': party.songs.count(),
            'message': f'Processat chunk: {processed}/{len(songs_to_process)} cançons amb features'
        })

    except SpotifyAuthError:
        return JsonResponse({
            'error': 'La sessió de Spotify ha caducat. Torna a connectar Spotify per continuar.',
            'reconnect_url': _spotify_reconnect_url(request),
        }, status=401)

    except Exception as e:
        import traceback
        return JsonResponse({
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@login_required
@user_passes_test(lambda u: u.is_superuser)
@require_POST
def analyze_song_audio(request, party_id, song_id):
    """
    Intenta obtenir BPM i Key via GetSongBPM i, si no n'hi ha prou,
    fa fallback a un MP3 temporal analitzat amb librosa.
    """
    party = get_object_or_404(Party, pk=party_id)
    song = get_object_or_404(Song, pk=song_id, party=party)

    try:
        logger.info(f"[ANALYZE_AUDIO] Analitzant cançó: {song.title} - {song.artist}")
        source = "getsongbpm"
        result = _get_getsongbpm_features(song.title, song.artist)

        if not result or not result.get('bpm') or not result.get('key'):
            logger.info(
                f"[ANALYZE_AUDIO] GetSongBPM incomplet per '{song.title}' - '{song.artist}', "
                "provant MP3 temporal"
            )
            temp_result = analyze_song_from_temporary_mp3(song.title, song.artist)
            if temp_result:
                merged_result = {
                    'bpm': result.get('bpm') if result and result.get('bpm') else temp_result.get('bpm'),
                    'key': result.get('key') if result and result.get('key') else temp_result.get('key'),
                    'key_note': temp_result.get('key_note'),
                    'key_mode': temp_result.get('key_mode'),
                }
                result = merged_result
                source = "temporary_mp3"

        if not result or not result.get('bpm') or not result.get('key'):
            return JsonResponse({
                'success': False,
                'error': 'No s\'ha pogut obtenir BPM i Key per aquesta cançó.'
            }, status=500)

        # Actualitzar cançó amb resultats
        song.bpm = result['bpm']
        song.key = result['key']
        song.save()

        logger.info(
            f"[ANALYZE_AUDIO] Cançó analitzada via {source}: "
            f"BPM={result['bpm']}, Key={result['key']}"
        )

        return JsonResponse({
            'success': True,
            'bpm': result['bpm'],
            'key': result['key'],
            'key_note': result.get('key_note'),
            'key_mode': result.get('key_mode'),
            'source': source,
        })

    except Exception as e:
        logger.error(f"[ANALYZE_AUDIO] Error analitzant cançó {song_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())

        return JsonResponse({
            'success': False,
            'error': f'Error analitzant àudio: {str(e)}'
        }, status=500)


@login_required
def song_list(request):
    party_id = request.session.get('selected_party_id')
    if not party_id:
        return redirect('select_party')
    party = get_object_or_404(Party, pk=party_id)
    user = request.user

    # Assegurar que l'usuari tingui els coins gratuïts de festa (si han canviat)
    ensure_user_has_free_coins(user, party)

    # Comprovar vots restants segons límit de la festa
    votes_left = get_user_votes_left(user, party)
    credits = user.credits  # Coins globals de l'usuari
    party_coins = get_user_party_coins(user, party)  # Coins gratuïts de festa

    annotated_songs = party.songs.annotate(
        num_likes=Count('vote', filter=Q(vote__vote_type='like')),
        num_dislikes=Count('vote', filter=Q(vote__vote_type='dislike'))
    )

    if request.method == 'POST':
        # Conversió de Coins a Vots amb bonificació per volum
        if 'action' in request.POST and request.POST['action'] == 'convert_coins':
            coins_to_convert = int(request.POST.get('coins_to_convert', 0))
            if coins_to_convert > 0 and coins_to_convert <= user.credits:
                # Calcular vots amb bonificació
                if coins_to_convert >= 20:
                    votes_to_add = int(coins_to_convert * 3.0)   # 20 Coins -> 60 Vots
                elif coins_to_convert >= 10:
                    votes_to_add = int(coins_to_convert * 2.5)   # 10 Coins -> 25 Vots
                elif coins_to_convert >= 5:
                    votes_to_add = int(coins_to_convert * 2.2)   # 5 Coins -> 11 Vots
                elif coins_to_convert >= 3:
                    votes_to_add = int(coins_to_convert * 2.0)   # 3 Coins -> 6 Vots
                else:
                    votes_to_add = coins_to_convert * 2          # 1-2 Coins -> 2x

                # Crear un VotePackage per registrar la conversió
                VotePackage.objects.create(
                    user=user,
                    party=party,
                    votes_purchased=votes_to_add
                )
                # Restar els Coins utilitzats
                user.credits -= coins_to_convert
                user.save()
                return redirect('song_list')

        # Desfer vot d'una cançó
        elif 'unvote_song_id' in request.POST:
            song = get_object_or_404(Song, pk=request.POST['unvote_song_id'], party=party)
            Vote.objects.filter(user=user, song=song, party=party).delete()
            return redirect('song_list')

        # Votar una cançó
        elif 'vote_song_id' in request.POST:
            song = get_object_or_404(Song, pk=request.POST['vote_song_id'], party=party)
            vote_type = request.POST.get('vote_type', 'like')  # like o dislike

            # Comprovar si l'usuari ja ha votat aquesta cançó
            existing_vote = Vote.objects.filter(user=user, song=song, party=party).first()
            if existing_vote:
                # L'usuari ja ha votat aquesta cançó, no fer res
                return redirect('song_list')

            # Comprovar si té vots disponibles
            if votes_left > 0:
                # Crear el vot (consumeix 1 Vot)
                Vote.objects.create(user=user, song=song, party=party, vote_type=vote_type)
                return redirect('song_list')
            else:
                # Mostra error segons el cas
                if credits > 0:
                    error = "No tens vots! Converteix Coins a Vots per votar."
                else:
                    error = "No tens Coins! Compra Coins i converteix-los a Vots."

                # Afegir badges per mostrar amb error
                error_pending = annotated_songs.filter(has_played=False).order_by('-num_likes', 'title')
                error_played = annotated_songs.filter(has_played=True).order_by('id')

                # Calcular badges (codi duplicat, però necessari per error case)
                all_vote_counts = list(
                    party.songs
                    .annotate(
                        total_interactions=Count('vote', filter=Q(vote__vote_type='like')) +
                                          Count('vote', filter=Q(vote__vote_type='dislike'))
                    )
                    .values_list('total_interactions', flat=True)
                )
                sorted_vote_counts_err = sorted(all_vote_counts)
                total_ranked_songs_err = len(sorted_vote_counts_err)

                def get_badge_err(likes, dislikes):
                    total_interactions = likes + dislikes
                    if total_interactions == 0:
                        return ("INTACTA", "#cbd5e1", "#475569")
                    like_ratio = (likes / total_interactions * 100)
                    percentile = 0
                    if total_ranked_songs_err > 0:
                        songs_below = sum(1 for count in sorted_vote_counts_err if count <= total_interactions)
                        percentile = (songs_below / total_ranked_songs_err) * 100

                    if total_interactions >= 3 and like_ratio >= 90:
                        return ("UNÀNIME", "#e63946", "#ffffff")
                    if percentile >= 90 and like_ratio >= 85:
                        return ("HIMNE", "#ff006e", "#ffffff")
                    if percentile >= 70:
                        if 40 <= like_ratio <= 60:
                            return ("DIVISIVA", "#f77f00", "#000000")
                        elif like_ratio >= 75:
                            return ("PETANT-HO", "#fcbf49", "#000000")
                        else:
                            return ("EXPLOSIVA", "#ef476f", "#ffffff")
                    if percentile >= 60 and like_ratio >= 65:
                        return ("TRENDING", "#06ffa5", "#000000")
                    if percentile >= 40 and like_ratio >= 50:
                        return ("CALENTA", "#ff9e00", "#000000")
                    if total_interactions >= 2 and like_ratio >= 80:
                        return ("JOIA", "#4cc9f0", "#000000")
                    if total_interactions >= 3 and like_ratio < 30:
                        return ("GÈLIDA", "#8338ec", "#ffffff")
                    return ("FRESCA", "#90e0ef", "#000000")

                for song in error_pending:
                    badge_label, badge_bg, badge_text = get_badge_err(song.num_likes, song.num_dislikes)
                    song.badge_label = badge_label
                    song.badge_bg = badge_bg
                    song.badge_text = badge_text

                for song in error_played:
                    badge_label, badge_bg, badge_text = get_badge_err(song.num_likes, song.num_dislikes)
                    song.badge_label = badge_label
                    song.badge_bg = badge_bg
                    song.badge_text = badge_text

                return render(request, "jukebox/song_list.html", {
                    "party": party,
                    "songs": annotated_songs.order_by('-num_likes', 'title'),
                    "pending_songs": error_pending,
                    "played_songs": error_played,
                    "votes_left": votes_left,
                    "credits": credits,
                    "party_coins": party_coins,
                    "error": error,
                })

    # Comptar només els likes per ordenar
    songs = annotated_songs.order_by('-num_likes', 'title')
    pending_songs = annotated_songs.filter(has_played=False).order_by('-num_likes', 'title')
    played_songs = list(annotated_songs.filter(has_played=True).order_by('-id'))

    # Obtenir els vots de l'usuari per mostrar els cors/creus marcats
    user_votes = Vote.objects.filter(user=user, party=party).select_related('song')
    user_votes_dict = {v.song_id: v.vote_type for v in user_votes}

    # Estadístiques per a la vista
    songs_played = party.songs.filter(has_played=True).count()
    user_votes_count = Vote.objects.filter(user=user, party=party, vote_type='like').count()
    total_songs = party.songs.count()
    total_votes = Vote.objects.filter(party=party, vote_type='like').count()

    # KPIs addicionals
    active_users = User.objects.filter(
        Q(vote__party=party) | Q(songrequest__party=party)
    ).distinct().count()

    thirty_min_ago = timezone.now() - timezone.timedelta(minutes=30)
    recent_votes = Vote.objects.filter(party=party, created_at__gte=thirty_min_ago).count()

    pending_requests_count = SongRequest.objects.filter(party=party, status='pending').count()

    songs_with_votes = party.songs.annotate(vote_count=Count('vote')).filter(vote_count__gt=0).count()
    songs_with_votes_percentage = round((songs_with_votes / total_songs * 100) if total_songs > 0 else 0, 1)

    accepted_requests = SongRequest.objects.filter(party=party, status='accepted')
    total_coins_spent = sum([req.coins_cost for req in accepted_requests if req.coins_cost])

    # Cançó que està sonant (la propera en la cua)
    now_playing = party.songs.filter(has_played=False).annotate(
        num_likes=Count('vote', filter=Q(vote__vote_type='like'))
    ).order_by('-num_likes').first()

    # Etiquetes segons percentil d'interaccions dins la festa
    all_vote_counts = list(
        party.songs
        .annotate(
            total_interactions=Count('vote', filter=Q(vote__vote_type='like')) +
                              Count('vote', filter=Q(vote__vote_type='dislike'))
        )
        .values_list('total_interactions', flat=True)
    )
    sorted_vote_counts = sorted(all_vote_counts)
    total_ranked_songs = len(sorted_vote_counts)

    def get_badge_for_song(likes, dislikes):
        """Calcula etiqueta segons likes, dislikes i percentil"""
        total_interactions = likes + dislikes

        # Cas especial: cap interacció
        if total_interactions == 0:
            return ("INTACTA", "#cbd5e1", "#475569")

        # Calcular ratio de likes
        like_ratio = (likes / total_interactions * 100)

        # Calcular percentil segons total d'interaccions
        if total_ranked_songs == 0:
            percentile = 0
        else:
            songs_below_or_equal = sum(1 for count in sorted_vote_counts if count <= total_interactions)
            percentile = (songs_below_or_equal / total_ranked_songs) * 100

        # Classificació amb ganxo per engagement

        # Cas especial: Unànime (quasi tots likes)
        if total_interactions >= 3 and like_ratio >= 90:
            return ("UNÀNIME", "#e63946", "#ffffff")

        # Top tier amb bon ratio
        if percentile >= 90 and like_ratio >= 85:
            return ("HIMNE", "#ff006e", "#ffffff")

        # Moltes interaccions (polèmica o trending)
        if percentile >= 70:
            if 40 <= like_ratio <= 60:
                return ("DIVISIVA", "#f77f00", "#000000")
            elif like_ratio >= 75:
                return ("PETANT-HO", "#fcbf49", "#000000")
            else:
                return ("EXPLOSIVA", "#ef476f", "#ffffff")

        # Trending amb bon ratio
        if percentile >= 60 and like_ratio >= 65:
            return ("TRENDING", "#06ffa5", "#000000")

        # Mitjana amb ratio decent
        if percentile >= 40 and like_ratio >= 50:
            return ("CALENTA", "#ff9e00", "#000000")

        # Baixa interacció però bon ratio (joia amagada)
        if total_interactions >= 2 and like_ratio >= 80:
            return ("JOIA", "#4cc9f0", "#000000")

        # Molts dislikes
        if total_interactions >= 3 and like_ratio < 30:
            return ("GÈLIDA", "#8338ec", "#ffffff")

        # Poc engagement (fresca)
        return ("FRESCA", "#90e0ef", "#000000")

    # Afegir badges a totes les cançons
    for song in pending_songs:
        badge_label, badge_bg, badge_text = get_badge_for_song(song.num_likes, song.num_dislikes)
        song.badge_label = badge_label
        song.badge_bg = badge_bg
        song.badge_text = badge_text

    for index, song in enumerate(played_songs):
        song.display_order = songs_played - index
        badge_label, badge_bg, badge_text = get_badge_for_song(song.num_likes, song.num_dislikes)
        song.badge_label = badge_label
        song.badge_bg = badge_bg
        song.badge_text = badge_text

    # Comprovar si l'usuari té Spotify connectat
    has_spotify = SocialAccount.objects.filter(user=user, provider="spotify").exists()
    spotify_token = None
    if has_spotify:
        from .spotify_api import _ensure_valid_user_token
        try:
            spotify_token = _ensure_valid_user_token(user)
        except Exception as e:
            logger.warning(f"[SPOTIFY] Error obtenint token per Web Playback: {e}")
            has_spotify = False

    return render(request, "jukebox/song_list.html", {
        "party": party,
        "songs": songs,
        "pending_songs": pending_songs,
        "played_songs": played_songs,
        "votes_left": votes_left,
        "credits": credits,
        "party_coins": party_coins,
        "songs_played": songs_played,
        "user_votes_count": user_votes_count,
        "total_songs": total_songs,
        "total_votes": total_votes,
        "now_playing": now_playing,
        "user_votes_dict": user_votes_dict,
        "has_spotify": has_spotify,
        "spotify_token": spotify_token,
        "active_users": active_users,
        "recent_votes": recent_votes,
        "pending_requests_count": pending_requests_count,
        "songs_with_votes": songs_with_votes,
        "songs_with_votes_percentage": songs_with_votes_percentage,
        "total_coins_spent": total_coins_spent,
    })


@user_passes_test(lambda u: u.is_superuser)
def dj_backoffice(request):
    songs = Song.objects.all().order_by('-votes')
    parties = Party.objects.order_by('-date')  # Mostra les més recents primer
    party_form = PartyForm()

    if request.method == 'POST':
        party_form = PartyForm(request.POST)
        if party_form.is_valid():
            party_form.save()
            return redirect('dj_backoffice')  # refresca la pàgina

    return render(request, 'jukebox/dj_backoffice.html', {
        'songs': songs,
        'parties': parties,
        'party_form': party_form,
    })

@login_required
@user_passes_test(is_dj_admin)
def dj_dashboard(request):
    from .recommendation import get_recommended_songs

    party_id = request.session.get('selected_party_id')
    if not party_id:
        return redirect('select_party')

    party = get_object_or_404(Party, pk=party_id)

    # Separar cançons pendents i ja posades
    pending_songs = party.songs.filter(has_played=False).annotate(
        num_likes=Count('vote', filter=Q(vote__vote_type='like')),
        num_dislikes=Count('vote', filter=Q(vote__vote_type='dislike'))
    ).order_by('-num_likes')
    played_songs_list = list(party.songs.filter(has_played=True).annotate(
        num_likes=Count('vote', filter=Q(vote__vote_type='like')),
        num_dislikes=Count('vote', filter=Q(vote__vote_type='dislike'))
    ).order_by('-id'))

    total_songs = party.songs.count()
    total_votes = Vote.objects.filter(party=party).count()
    played_songs_count = len(played_songs_list)
    for index, song in enumerate(played_songs_list):
        song.display_order = played_songs_count - index

    is_djjukebox_active = party.party_status == Party.STATUS_DJJUKEBOX_ACTIVE
    party_status_step_map = {
        Party.STATUS_HIDDEN: 0,
        Party.STATUS_SHOW_PARTY: 1,
        Party.STATUS_REQUESTS_OPEN: 2,
        Party.STATUS_DJJUKEBOX_ACTIVE: 3,
    }
    is_party_finished = party.party_status == Party.STATUS_FINISHED
    party_status_step = party_status_step_map.get(party.party_status, 0)

    if party.party_status == Party.STATUS_HIDDEN:
        party_status_label = 'Festa Pausada'
        party_status_help = "La festa està pausada i encara no és visible pels usuaris."
    elif party.party_status == Party.STATUS_SHOW_PARTY:
        party_status_label = 'Mostrar festa'
        party_status_help = "La festa està visible, però encara no s'han obert les peticions."
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

    # 3. Peticions (ja existeix pending_requests més avall)
    pending_requests_count = SongRequest.objects.filter(party=party, status='pending').count()

    # 4. Temes amb vots
    songs_with_votes = party.songs.annotate(vote_count=Count('vote')).filter(vote_count__gt=0).count()
    songs_with_votes_percentage = round((songs_with_votes / total_songs * 100) if total_songs > 0 else 0, 1)

    # 5. Coins gastats (peticions acceptades)
    # Només comptem coins gastats en peticions, ja que VotePackage no té camp 'coins'
    accepted_requests = SongRequest.objects.filter(party=party, status='accepted')
    total_coins_spent = sum([req.coins_cost for req in accepted_requests if req.coins_cost])

    # Alternativa: comptar VotePackages creats per aquesta party (conversions coins->vots)
    vote_conversions_count = VotePackage.objects.filter(party=party).count()

    # Obtenir recomanacions intel·ligents
    recommended_songs = get_recommended_songs(party, limit=6)
    pending_requests = SongRequest.objects.filter(party=party, status='pending').order_by('created_at')
    unplayed_requested_spotify_ids = list(
        party.songs.filter(has_played=False).values_list('spotify_id', flat=True)
    )
    accepted_unplayed_requests = SongRequest.objects.filter(
        party=party,
        status='accepted',
        spotify_id__in=unplayed_requested_spotify_ids,
    ).order_by('-processed_at')

    unplayed_songs_by_spotify = {
        song.spotify_id: song.id
        for song in party.songs.filter(has_played=False)
    }
    for req in accepted_unplayed_requests:
        req.linked_song_id = unplayed_songs_by_spotify.get(req.spotify_id)

    context = {
        'party': party,
        'pending_songs': pending_songs,
        'played_songs_list': played_songs_list,
        'total_songs': total_songs,
        'total_votes': total_votes,
        'played_songs': played_songs_count,
        'recommended_songs': recommended_songs,
        'pending_requests': pending_requests,
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
    }
    return render(request, 'jukebox/dj_dashboard.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
@require_POST
def update_party_status(request, party_id):
    """Actualitza l'estat operatiu de la festa i l'hora prevista del DJJukebox."""
    party = get_object_or_404(Party, id=party_id)
    requested_status = request.POST.get('party_status', party.party_status)
    allowed_statuses = {
        Party.STATUS_HIDDEN,
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

    logger.info(f"[PARTY_STATUS] Party {party_id} status updated to {party.party_status}")
    return redirect('dj_dashboard')


@login_required
@user_passes_test(is_dj_admin)
@require_POST
def mark_song_played(request, song_id):
    song = get_object_or_404(Song, pk=song_id)
    song.has_played = True
    song.save()

    # Notificar a tots els que van votar aquesta cançó
    create_song_played_notification(song)

    return redirect('dj_dashboard')

@login_required
def buy_votes(request):
    import logging
    logger = logging.getLogger(__name__)

    party_id = request.session.get('selected_party_id')
    if not party_id:
        return redirect('select_party')
    party = Party.objects.get(id=party_id)
    user = request.user

    stripe.api_key = settings.STRIPE_SECRET_KEY  # ← AQUI SEMPRE!
    logger.info(f"[BUY_VOTES] Stripe API key length: {len(stripe.api_key)}")
    logger.info(f"[BUY_VOTES] Stripe API key starts with: {stripe.api_key[:7]}")

    if request.method == 'POST':
        # Conversió de Coins a Vots
        if 'action' in request.POST and request.POST['action'] == 'convert_coins':
            coins_to_convert = int(request.POST.get('coins_to_convert', 0))
            if coins_to_convert > 0 and coins_to_convert <= user.credits:
                # Calcular vots amb bonificació
                if coins_to_convert >= 20:
                    votes_to_add = int(coins_to_convert * 3.0)   # 20 Coins -> 60 Vots
                elif coins_to_convert >= 10:
                    votes_to_add = int(coins_to_convert * 2.5)   # 10 Coins -> 25 Vots
                elif coins_to_convert >= 5:
                    votes_to_add = int(coins_to_convert * 2.2)   # 5 Coins -> 11 Vots
                elif coins_to_convert >= 3:
                    votes_to_add = int(coins_to_convert * 2.0)   # 3 Coins -> 6 Vots
                else:
                    votes_to_add = coins_to_convert * 2          # 1-2 Coins -> 2x

                # Crear un VotePackage per registrar la conversió
                VotePackage.objects.create(
                    user=user,
                    party=party,
                    votes_purchased=votes_to_add
                )
                # Restar els Coins utilitzats
                user.credits -= coins_to_convert
                user.save()
                return redirect('buy_votes')

        # Compra de Coins amb Stripe
        else:
            coins_to_buy = int(request.POST.get('votes', 10))  # 'votes' param name per compatibilitat
            package_prices = {
                10: 2,
                30: 5,
                70: 10,
            }
            price_eur = package_prices.get(coins_to_buy)

            if price_eur is None:
                return render(request, "jukebox/buy_votes.html", {
                    "party": party,
                    "credits": user.credits,
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
            except stripe.error.AuthenticationError as e:
                logger.error(f"[STRIPE] Error d'autenticació: {e}")
                return render(request, "jukebox/buy_votes.html", {
                    "party": party,
                    "credits": user.credits,
                    "votes_left": votes_left,
                    "error": "Error de configuració de pagament. Contacta amb l'administrador."
                })
            except stripe.error.StripeError as e:
                logger.error(f"[STRIPE] Error de Stripe: {e}")
                return render(request, "jukebox/buy_votes.html", {
                    "party": party,
                    "credits": user.credits,
                    "votes_left": votes_left,
                    "error": "Error processant el pagament. Si us plau, torna-ho a provar més tard."
                })

    votes_left = get_user_votes_left(user, party)

    return render(request, "jukebox/buy_votes.html", {
        "party": party,
        "credits": user.credits,
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
                        # Afegir Coins
                        user = request.user
                        logger.info(f"[DEV_WEBHOOK] Simulant webhook per session {session_id}: +{coins} Coins")
                        user.credits += coins
                        user.save()

                        # Registrar la transacció per evitar duplicats
                        party = Party.objects.get(id=party_id)
                        VotePackage.objects.create(
                            user=user,
                            party=party,
                            votes_purchased=0,  # És una compra de Coins, no vots directes
                            payment_id=session_id
                        )

                        # Crear notificació
                        create_coins_purchased_notification(user, coins)

                        logger.info(f"[DEV_WEBHOOK] ✓ {coins} Coins afegits a {user.username} (total: {user.credits})")
                elif already_processed:
                    logger.info(f"[DEV_WEBHOOK] Pagament {session_id} ja processat anteriorment")
            except Exception as e:
                logger.error(f"[DEV_WEBHOOK] Error: {e}")

    return render(request, "jukebox/buy_votes_success.html")


@csrf_exempt
def stripe_webhook(request):
    import logging
    logger = logging.getLogger(__name__)

    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    event = None

    logger.info(f"[STRIPE_WEBHOOK] Rebut webhook de Stripe")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
        logger.info(f"[STRIPE_WEBHOOK] Event verificat: {event['type']}")
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        logger.error(f"[STRIPE_WEBHOOK] Error de verificació: {e}")
        return HttpResponse(status=400)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        session_id = session['id']
        user_id = session['metadata']['user_id']
        coins = int(session['metadata']['votes_purchased'])  # Comprem Coins!
        party_id = session['metadata']['party_id']

        logger.info(f"[STRIPE_WEBHOOK] Processant pagament: session={session_id}, user_id={user_id}, coins={coins}")

        # Comprovar si ja s'ha processat
        already_processed = VotePackage.objects.filter(payment_id=session_id).exists()
        if already_processed:
            logger.warning(f"[STRIPE_WEBHOOK] Pagament {session_id} ja processat anteriorment")
            return HttpResponse(status=200)

        try:
            user = User.objects.get(id=user_id)
            party = Party.objects.get(id=party_id)

            # Afegir Coins
            user.credits += coins  # credits field stores Coins
            user.save()

            # Registrar la transacció
            VotePackage.objects.create(
                user=user,
                party=party,
                votes_purchased=0,  # És una compra de Coins, no vots directes
                payment_id=session_id
            )

            # Crear notificació
            create_coins_purchased_notification(user, coins)

            logger.info(f"[STRIPE_WEBHOOK] ✓ {coins} Coins afegits a l'usuari {user.username} (total: {user.credits})")
        except User.DoesNotExist:
            logger.error(f"[STRIPE_WEBHOOK] ✗ Usuari {user_id} no trobat")
        except Party.DoesNotExist:
            logger.error(f"[STRIPE_WEBHOOK] ✗ Party {party_id} no trobada")

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
                'reconnect_url': _spotify_reconnect_url(request),
            },
            status=401
        )
    if not playlists:
        return JsonResponse(
            {'error': 'No Spotify account linked or no playlists found.'},
            status=400
        )
    return JsonResponse({'playlists': playlists})

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
    """Pàgina pública amb informació i backlink per GetSongBPM"""
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
    user = request.user

    # Assegurar que l'usuari tingui els coins gratuïts de festa
    ensure_user_has_free_coins(user, party)

    votes_left = get_user_votes_left(user, party)
    credits = user.credits
    party_coins = get_user_party_coins(user, party)
    total_likes = Vote.objects.filter(party=party).count()
    total_songs = party.songs.count()

    if request.method == 'POST':
        action = request.POST.get('action')
        song_id = request.POST.get('song_id')

        if action == 'like' and song_id:
            song = get_object_or_404(Song, pk=song_id, party=party)

            # Només necessita vots disponibles per aquesta festa
            if votes_left > 0:
                # Crear el vot (consumeix 1 Vot)
                Vote.objects.create(user=user, song=song, party=party, vote_type='like')

                return JsonResponse({
                    'success': True,
                    'votes_left': get_user_votes_left(user, party),
                    'credits': user.credits
                })
            else:
                # No té vots disponibles
                if credits > 0:
                    return JsonResponse({'success': False, 'error': _('No tens vots! Converteix Coins a Vots per fer like.')}, status=400)
                else:
                    return JsonResponse({'success': False, 'error': _('No tens Coins! Compra Coins i converteix-los a Vots.')}, status=400)

        elif action == 'dislike' and song_id:
            song = get_object_or_404(Song, pk=song_id, party=party)

            # Dislike també consumeix 1 vot
            if votes_left > 0:
                # Crear el vot de tipus dislike (consumeix 1 Vot)
                Vote.objects.create(user=user, song=song, party=party, vote_type='dislike')

                return JsonResponse({
                    'success': True,
                    'votes_left': get_user_votes_left(user, party),
                    'credits': user.credits
                })
            else:
                # No té vots disponibles
                if credits > 0:
                    return JsonResponse({'success': False, 'error': _('No tens vots! Converteix Coins a Vots per continuar.')}, status=400)
                else:
                    return JsonResponse({'success': False, 'error': _('No tens Coins! Compra Coins i converteix-los a Vots.')}, status=400)

        elif action == 'skip' and song_id:
            song = get_object_or_404(Song, pk=song_id, party=party)

            # Skip també consumeix 1 vot
            if votes_left > 0:
                # Crear el vot de tipus skip (consumeix 1 Vot)
                Vote.objects.create(user=user, song=song, party=party, vote_type='skip')

                return JsonResponse({
                    'success': True,
                    'votes_left': get_user_votes_left(user, party),
                    'credits': user.credits
                })
            else:
                # No té vots disponibles
                if credits > 0:
                    return JsonResponse({'success': False, 'error': _('No tens vots! Converteix Coins a Vots per continuar.')}, status=400)
                else:
                    return JsonResponse({'success': False, 'error': _('No tens Coins! Compra Coins i converteix-los a Vots.')}, status=400)

    # Obtenir cançons que l'usuari encara no ha votat
    voted_song_ids = Vote.objects.filter(user=user, party=party).values_list('song_id', flat=True)
    songs = list(
        party.songs
        .annotate(
            num_likes=Count('vote', filter=Q(vote__vote_type='like')),
            num_dislikes=Count('vote', filter=Q(vote__vote_type='dislike'))
        )
        .exclude(id__in=voted_song_ids)
        .order_by('?')
    )
    swiped_count = total_songs - len(songs)

    # Etiquetes tipus DJ segons percentil d'interaccions dins la festa
    all_vote_counts = list(
        party.songs
        .annotate(
            total_interactions=Count('vote', filter=Q(vote__vote_type='like')) +
                              Count('vote', filter=Q(vote__vote_type='dislike'))
        )
        .values_list('total_interactions', flat=True)
    )
    sorted_vote_counts = sorted(all_vote_counts)
    total_ranked_songs = len(sorted_vote_counts)

    def get_badge_for_song(likes, dislikes):
        """Calcula etiqueta segons likes, dislikes i percentil"""
        total_interactions = likes + dislikes

        # Cas especial: cap interacció
        if total_interactions == 0:
            return ("INTACTA", "#cbd5e1", "#475569")

        # Calcular ratio de likes
        like_ratio = (likes / total_interactions * 100)

        # Calcular percentil segons total d'interaccions
        if total_ranked_songs == 0:
            percentile = 0
        else:
            songs_below_or_equal = sum(1 for count in sorted_vote_counts if count <= total_interactions)
            percentile = (songs_below_or_equal / total_ranked_songs) * 100

        # Classificació amb ganxo per engagement

        # Cas especial: Unànime (quasi tots likes)
        if total_interactions >= 3 and like_ratio >= 90:
            return ("UNÀNIME", "#e63946", "#ffffff")

        # Top tier amb bon ratio
        if percentile >= 90 and like_ratio >= 85:
            return ("HIMNE", "#ff006e", "#ffffff")

        # Moltes interaccions (polèmica o trending)
        if percentile >= 70:
            if 40 <= like_ratio <= 60:
                return ("DIVISIVA", "#f77f00", "#000000")
            elif like_ratio >= 75:
                return ("PETANT-HO", "#fcbf49", "#000000")
            else:
                return ("EXPLOSIVA", "#ef476f", "#ffffff")

        # Trending amb bon ratio
        if percentile >= 60 and like_ratio >= 65:
            return ("TRENDING", "#06ffa5", "#000000")

        # Mitjana amb ratio decent
        if percentile >= 40 and like_ratio >= 50:
            return ("CALENTA", "#ff9e00", "#000000")

        # Baixa interacció però bon ratio (joia amagada)
        if total_interactions >= 2 and like_ratio >= 80:
            return ("JOIA", "#4cc9f0", "#000000")

        # Molts dislikes
        if total_interactions >= 3 and like_ratio < 30:
            return ("GÈLIDA", "#8338ec", "#ffffff")

        # Poc engagement (fresca)
        return ("FRESCA", "#90e0ef", "#000000")

    for song in songs:
        badge_label, badge_bg, badge_text = get_badge_for_song(song.num_likes, song.num_dislikes)
        song.badge_label = badge_label
        song.badge_bg = badge_bg
        song.badge_text = badge_text

    # Comprovar si l'usuari té Spotify connectat
    has_spotify = SocialAccount.objects.filter(user=user, provider="spotify").exists()
    spotify_token = None
    if has_spotify:
        from .spotify_api import _ensure_valid_user_token
        try:
            spotify_token = _ensure_valid_user_token(user)
        except Exception as e:
            logger.warning(f"[SPOTIFY] Error obtenint token per Web Playback: {e}")
            has_spotify = False

    return render(request, 'jukebox/song_swipe.html', {
        'party': party,
        'songs': songs,
        'votes_left': votes_left,
        'total_likes': total_likes,
        'total_songs': total_songs,
        'swiped_count': swiped_count,
        'credits': credits,
        'party_coins': party_coins,
        'has_spotify': has_spotify,
        'spotify_token': spotify_token,
    })


@login_required
def request_song(request):
    """Vista per demanar cançons noves"""
    party_id = request.session.get('selected_party_id')
    if not party_id:
        return redirect('select_party')

    party = get_object_or_404(Party, pk=party_id)
    user = request.user

    # Cerca de cançons
    if request.method == 'GET' and 'search' in request.GET:
        query = request.GET.get('search', '').strip()
        if query:
            try:
                tracks = search_spotify_tracks(request, query, limit=20)
            except SpotifyAuthError:
                return JsonResponse({
                    'error': 'La sessió de Spotify ha caducat. Torna a connectar Spotify per buscar cançons.',
                    'reconnect_url': _spotify_reconnect_url(request),
                }, status=401)
            return JsonResponse({'tracks': tracks})
        return JsonResponse({'tracks': []})

    # Enviar petició
    if request.method == 'POST':
        spotify_id = request.POST.get('spotify_id')
        title = request.POST.get('title')
        artist = request.POST.get('artist')
        album_image_url = request.POST.get('album_image_url', '')

        if not spotify_id or not title or not artist:
            return JsonResponse({'success': False, 'error': _('Dades incompletes')}, status=400)

        # Comprovar si la cançó ja està a la llista
        if party.songs.filter(spotify_id=spotify_id).exists():
            return JsonResponse({'success': False, 'error': _('Aquesta cançó ja està a la llista!')}, status=400)

        # Comprovar si ja s'ha demanat
        if SongRequest.objects.filter(party=party, spotify_id=spotify_id, status='pending').exists():
            return JsonResponse({'success': False, 'error': _('Aquesta cançó ja ha estat demanada i està pendent')}, status=400)

        # Crear petició
        SongRequest.objects.create(
            user=user,
            party=party,
            title=title,
            artist=artist,
            spotify_id=spotify_id,
            album_image_url=album_image_url,
            coins_cost=party.song_request_cost,
            status='pending'
        )

        return JsonResponse({'success': True, 'message': _('Petició enviada! Cost: %(cost)s Coins (només si s\'accepta)') % {'cost': party.song_request_cost}})

    # Llistar peticions de l'usuari per aquesta festa
    user_requests = SongRequest.objects.filter(user=user, party=party).order_by('-created_at')

    return render(request, 'jukebox/request_song.html', {
        'party': party,
        'user_requests': user_requests,
        'request_cost': party.song_request_cost,
        'user_credits': user.credits,
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
    party.auto_sync_playlist = not party.auto_sync_playlist
    party.save(update_fields=['auto_sync_playlist'])

    logger.info(f"[AUTO_SYNC] Party {party_id} auto-sync {'enabled' if party.auto_sync_playlist else 'disabled'}")

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
    party.auto_analyze_audio = not party.auto_analyze_audio
    party.save(update_fields=['auto_analyze_audio'])

    # Comptar cançons pendents d'anàlisi
    pending_count = Song.objects.filter(party=party, bpm__isnull=True).count()

    logger.info(f"[AUTO_ANALYZE] Party {party_id} auto-analyze {'enabled' if party.auto_analyze_audio else 'disabled'} - {pending_count} pending songs")

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
        logger.error(f"[FORCE_SYNC] Error for party {party_id}: {e}")
        # Restaurar valors originals en cas d'error
        party.auto_sync_playlist = original_auto_sync
        party.last_sync_at = original_last_sync
        party.save(update_fields=['auto_sync_playlist', 'last_sync_at'])

        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(is_dj_admin)
def manage_song_requests(request):
    """Vista per DJs per gestionar peticions de cançons"""
    party_id = request.session.get('selected_party_id')
    if not party_id:
        return redirect('select_party')

    party = get_object_or_404(Party, pk=party_id)

    if request.method == 'POST':
        request_id = request.POST.get('request_id')
        action = request.POST.get('action')  # 'accept' o 'reject'
        allow_without_charge = request.POST.get('allow_without_charge') == '1'

        song_request = get_object_or_404(
            SongRequest,
            pk=request_id,
            party=party,
            status='pending',
        )

        if action == 'accept':
            if song_request.user.credits >= song_request.coins_cost:
                charged_amount = _accept_song_request(
                    song_request=song_request,
                    processed_by=request.user,
                    charge_user=True,
                )
                return JsonResponse({
                    'success': True,
                    'message': f'Cançó acceptada i afegida! S\'han cobrat {charged_amount} Coins',
                })

            if allow_without_charge:
                _accept_song_request(
                    song_request=song_request,
                    processed_by=request.user,
                    charge_user=False,
                )
                return JsonResponse({
                    'success': True,
                    'message': _('Cançó acceptada i afegida sense càrrec'),
                })

            return JsonResponse({
                'success': False,
                'error': _('L\'usuari no té prou Coins (%(current)s/%(required)s)') % {
                    'current': song_request.user.credits,
                    'required': song_request.coins_cost
                },
            }, status=400)

        elif action == 'reject':
            song_request.status = 'rejected'
            song_request.processed_at = timezone.now()
            song_request.processed_by = request.user
            song_request.save()

            return JsonResponse({'success': True, 'message': _('Cançó rebutjada (sense càrrec)')})

    # Llistar totes les peticions pendents
    pending_requests = SongRequest.objects.filter(party=party, status='pending').order_by('created_at')
    processed_requests = SongRequest.objects.filter(party=party).exclude(status='pending').order_by('-processed_at')[:20]

    return render(request, 'jukebox/manage_song_requests.html', {
        'party': party,
        'pending_requests': pending_requests,
        'processed_requests': processed_requests,
    })
