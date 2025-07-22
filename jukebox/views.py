from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from allauth.account.forms import SignupForm
from allauth.socialaccount.models import SocialToken, SocialAccount
from django.http import JsonResponse, HttpResponse
from django.conf import settings

from .models import Song, Party, Vote, VotePackage
from django.db.models import Sum, Count
from .forms import PartyForm, PartySettingsForm
from .spotify_api import get_user_playlists
from .votes import get_user_votes_left

from django.contrib.auth import get_user_model
User = get_user_model()

import stripe


# Create your views here.

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
def party_settings(request, party_id):
    party = get_object_or_404(Party, pk=party_id)

    if request.method == 'POST':
        form = PartySettingsForm(request.POST, instance=party, request=request)
        if form.is_valid():
            form.save()
            return redirect('party_settings', party_id=party.id)
    else:
        form = PartySettingsForm(instance=party, request=request)

    # Ara anotem els vots totals reals per cançó:
    songs = party.songs.annotate(num_votes=Count('vote')).order_by('-num_votes', 'title')

    # Si la festa NO té playlist, carreguem-les ara
    playlists = []
    if not party.playlist:
        playlists = get_user_playlists(request)

    return render(request, 'jukebox/party_settings.html', {
        'party': party,
        'form': form,
        'songs': songs,
        'playlists': playlists,
    })

@login_required
def remove_playlist(request, party_id):
    party = get_object_or_404(Party, pk=party_id)
    # només serveix si la festa ja té playlist
    if party.playlist:
        party.playlist = None
        party.songs.all().delete()   # opcional: neteja també les cançons
        party.save()
    return redirect('party_settings', party_id=party.id)


@login_required
def song_list(request):
    party_id = request.session.get('selected_party_id')
    if not party_id:
        return redirect('select_party')
    party = get_object_or_404(Party, pk=party_id)
    user = request.user

    # Comprovar vots restants segons límit de la festa
    votes_left = get_user_votes_left(user, party)
    credits = user.credits  # crèdits globals de l'usuari

    if request.method == 'POST' and 'vote_song_id' in request.POST:
        song = get_object_or_404(Song, pk=request.POST['vote_song_id'], party=party)
        if votes_left > 0 and credits > 0:
            # Crear el vot i restar crèdit
            Vote.objects.create(user=user, song=song, party=party)
            user.credits -= 1
            user.save()
            return redirect('song_list')
        else:
            # Mostra error segons el cas
            if credits == 0:
                error = "No tens crèdits disponibles!"
            else:
                error = "Has esgotat els teus vots per aquesta festa!"
            return render(request, "jukebox/song_list.html", {
                "party": party,
                "songs": party.songs.annotate(num_votes=Count('vote')).order_by('-num_votes', 'title'),
                "votes_left": votes_left,
                "credits": credits,
                "error": error,
            })

    songs = party.songs.annotate(num_votes=Count('vote')).order_by('-num_votes', 'title')

    return render(request, "jukebox/song_list.html", {
        "party": party,
        "songs": songs,
        "votes_left": votes_left,
        "credits": credits,
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

def dj_dashboard(request):
    songs = Song.objects.all().order_by('-votes')
    total_songs = songs.count()
    total_votes = songs.aggregate(total=Sum('votes'))['total'] or 0
    played_songs = songs.filter(has_played=True).count()
    context = {
        'songs': songs,
        'total_songs': total_songs,
        'total_votes': total_votes,
        'played_songs': played_songs,
    }
    return render(request, 'jukebox/dj_dashboard.html', context)

@require_POST
def mark_song_played(request, song_id):
    song = get_object_or_404(Song, pk=song_id)
    song.has_played = True
    song.save()
    return redirect('dj_dashboard')

@login_required
def buy_votes(request):
    party_id = request.session.get('selected_party_id')
    if not party_id:
        return redirect('select_party')
    party = Party.objects.get(id=party_id)

    stripe.api_key = settings.STRIPE_SECRET_KEY  # ← AQUI SEMPRE!

    if request.method == 'POST':
        votes_to_buy = int(request.POST.get('votes', 5))
        # Calcula el preu (ex: 1€ cada 5 vots)
        price_eur = 1 * (votes_to_buy // 5)
        if price_eur == 0:
            price_eur = 1  # mínim 1€
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'product_data': {
                        'name': f'Paquet de {votes_to_buy} vots per {party.name}',
                    },
                    'unit_amount': int(price_eur * 100),
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=request.build_absolute_uri('/buy-votes/success/'),
            cancel_url=request.build_absolute_uri('/buy-votes/'),
            metadata={
                'user_id': request.user.id,
                'party_id': party.id,
                'votes_purchased': votes_to_buy,
            }
        )
        return redirect(session.url, code=303)

    return render(request, "jukebox/buy_votes.html", {"party": party})

@login_required
def buy_votes_success(request):
    return render(request, "jukebox/buy_votes_success.html")


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    event = None

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session['metadata']['user_id']
        credits = int(session['metadata']['votes_purchased'])  # Comprem crèdits, no vots!
        try:
            user = User.objects.get(id=user_id)
            user.credits += credits
            user.save()
        except User.DoesNotExist:
            pass  # Si vols, afegeix log/error

    return HttpResponse(status=200)

@login_required
def get_spotify_playlists(request):
    """
    Retorna JSON amb la llista de playlists de l'usuari logat a Spotify.
    Si no està enllaçat o no hi ha playlists, retorna error 400.
    """
    playlists = get_user_playlists(request)
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
