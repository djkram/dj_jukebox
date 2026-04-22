# forms.py

from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Party, Playlist, Song
from .spotify_api import get_user_playlists, get_playlist_tracks

class PartyForm(forms.ModelForm):
    class Meta:
        model = Party
        fields = ['name', 'date']
        widgets = {
            'date': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-control'},
                format='%Y-%m-%dT%H:%M'
            ),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Perquè el camp es mostri correctament quan editis
        if self.instance and self.instance.pk:
            self.fields['date'].initial = self.instance.date.strftime('%Y-%m-%dT%H:%M')


class PartySettingsForm(forms.ModelForm):
    spotify_playlist = forms.ChoiceField(
        label=_("Playlist de Spotify"),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    class Meta:
        model = Party
        fields = ['name', 'date', 'code', 'cover_image', 'is_public', 'require_join_code', 'max_votes_per_user', 'free_coins_per_user', 'song_request_cost', 'allow_song_requests']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'date': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'type': 'datetime-local', 'class': 'form-control'},
            ),
            'code': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'maxlength': 12,
                    'style': 'text-transform: uppercase;',
                    'placeholder': _('Ex: G30A'),
                }
            ),
            'cover_image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'require_join_code': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'allow_song_requests': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'max_votes_per_user': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 0}
            ),
            'free_coins_per_user': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 0}
            ),
            'song_request_cost': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 0}
            ),
        }
        labels = {
            'name': _('Nom de la festa'),
            'date': _('Data i hora'),
            'code': _('Codi d\'entrada'),
            'cover_image': _('Imatge de portada'),
            'is_public': _('Festa pública (llistada)'),
            'require_join_code': _('Requerir codi per unir-se'),
            'max_votes_per_user': _('Vots gratuïts per usuari'),
            'free_coins_per_user': _('Coins gratuïts per usuari'),
            'song_request_cost': _('Cost per demanar cançó (Coins)'),
            'allow_song_requests': _('Permetre peticions de cançons'),
        }

    def __init__(self, *args, instance=None, request=None, **kwargs):
        self.request = request
        super().__init__(*args, instance=instance, **kwargs)

        # 1) Si no hi ha playlist assignada, carreguem opcions de Spotify
        choices = [('', _('--- Selecciona una playlist ---'))]
        if request and (instance is None or instance.playlist is None):
            playlists = get_user_playlists(request)
            if not playlists and request.user.is_authenticated:
                # Si no hi ha playlists, potser el token ha expirat
                choices.append(('', _('⚠️ Reconnecta Spotify per veure playlists')))
            else:
                for pl in playlists:
                    choices.append((pl['id'], f"{pl['name']} ({pl['owner']})"))
        self.fields['spotify_playlist'].choices = choices

        # 2) Si ja existeix playlist, inicialitzem perquè el select la mostri
        if instance and instance.playlist:
            self.fields['spotify_playlist'].initial = instance.playlist.spotify_id

    def clean_code(self):
        code = Party.normalize_code(self.cleaned_data.get('code'))
        if len(code) < 4:
            raise forms.ValidationError(_("El codi ha de tenir almenys 4 caràcters alfanumèrics."))

        qs = Party.objects.filter(code=code)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(_("Aquest codi ja està en ús. Tria'n un altre."))
        return code

    def save(self, commit=True, load_songs=True):
        # ➍ Guardem els camps del Party (name, date, max_votes_per_user)
        party = super().save(commit=False)
        sp_id = self.cleaned_data.get('spotify_playlist')

        if sp_id:
            # ➎ Recuperem o creem l'objecte Playlist
            pl_data = next(
                (p for p in get_user_playlists(self.request) if p['id'] == sp_id),
                None
            )
            defaults = {
                'name': pl_data['name'],
                'owner': pl_data['owner']
            } if pl_data else {}
            playlist_obj, _ = Playlist.objects.get_or_create(
                spotify_id=sp_id,
                defaults=defaults
            )
            party.playlist = playlist_obj

        if commit:
            party.save()

            # ➐ Si hem seleccionat una nova playlist i load_songs=True, carregar cançons
            if sp_id and load_songs:
                party.songs.all().delete()
                for tr in get_playlist_tracks(self.request, sp_id):
                    Song.objects.create(
                        party=party,
                        title=tr['title'],
                        artist=tr['artist'],
                        spotify_id=tr['id'],
                        album_image_url=tr.get('album_image_url'),
                        bpm=tr.get('bpm'),
                        key=tr.get('key'),
                    )

        return party
