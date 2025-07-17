from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required, user_passes_test
from allauth.account.forms import SignupForm
from allauth.socialaccount.models import SocialToken, SocialAccount
from django.http import JsonResponse

from .models import Song, Party, Vote, VotePackage
from django.db.models import Count
from .forms import PartyForm, PartySettingsForm
from .spotify_api import get_user_playlists
from .votes import get_user_votes_left



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
    # 1) Obtenir la festa seleccionada
    party_id = request.session.get('selected_party_id')
    if not party_id:
        return redirect('select_party')
    party = get_object_or_404(Party, pk=party_id)

    # 2) Comprovar vots restants
    votes_left = get_user_votes_left(request.user, party)

    # 3) Si POST, intentar votar
    if request.method == 'POST' and 'vote_song_id' in request.POST:
        song = get_object_or_404(Song, pk=request.POST['vote_song_id'], party=party)
        if votes_left > 0:
            # Crear el vot
            Vote.objects.create(user=request.user, song=song, party=party)
            # Opcional: pots fer servir un missatge de confirmació (django.contrib.messages)
            return redirect('song_list')
        else:
            # No té vots restants: mostrar missatge d'error
            return render(request, "jukebox/song_list.html", {
                "party": party,
                "songs": party.songs.all().order_by('-votes', 'title'),
                "votes_left": votes_left,
                "error": "Has esgotat els teus vots per aquesta festa!"
            })

    # 4) Ordena les cançons segons vots reals (comptem vots per cançó!)
    songs = party.songs.annotate(num_votes=Count('vote')).order_by('-num_votes', 'title')

    return render(request, "jukebox/song_list.html", {
        "party": party,
        "songs": songs,
        "votes_left": votes_left,
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
def buy_votes(request):
    party_id = request.session.get('selected_party_id')
    if not party_id:
        return redirect('select_party')
    party = Party.objects.get(id=party_id)

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
