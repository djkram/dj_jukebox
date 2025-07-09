from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required, user_passes_test


from .models import Song


# Create your views here.

# def song_list(request):
#     songs = Song.objects.filter(played=False).order_by('-votes')
#     return render(request, 'jukebox/song_list.html', {'songs': songs})
#
# def main(request):
#     return render(request, 'jukebox/admin_base.html')

def main(request):
    songs = Song.objects.filter(played=False).order_by('-votes')
    return render(request, 'jukebox/song_list.html', {'songs': songs})

@user_passes_test(lambda u: u.is_superuser)
def dj_backoffice(request):
    songs = Song.objects.all().order_by('-votes')
    return render(request, 'jukebox/dj_backoffice.html', {'songs': songs})

def register(request):
    print(">>>> ENTRO A REGISTER <<<<")
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = UserCreationForm()

    # Afegeix la classe 'form-control' a tots els camps
    for field in form.fields.values():
        field.widget.attrs['class'] = 'form-control'

    print(form)
    print(form.errors)
    print(form.fields)

    return render(request, 'jukebox/register.html', {'form': form})

@login_required
def profile(request):
    return render(request, 'jukebox/profile.html')


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
