from django import forms
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
        label="Playlist de Spotify",
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    class Meta:
        model = Party
        fields = ['name', 'date']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'date': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'type': 'datetime-local', 'class': 'form-control'},
            ),
        }

    def __init__(self, *args, instance=None, request=None, **kwargs):
        self.request = request
        super().__init__(*args, instance=instance, **kwargs)

        # 1) Només anem a Spotify si NO tenim playlist assignada
        choices = [('', '--- Selecciona una playlist ---')]
        if request and (instance is None or instance.playlist is None):
            for pl in get_user_playlists(request):
                choices.append((pl['id'], f"{pl['name']} ({pl['owner']})"))
        self.fields['spotify_playlist'].choices = choices

        # 2) Si ja en tenim, posem l’inicial només per controlar el select,
        #    encara que en el template n’ocultem el form
        if instance and instance.playlist:
            self.fields['spotify_playlist'].initial = instance.playlist.spotify_id

    def save(self, commit=True):
        # ➍ guardem name i date
        party = super().save(commit=False)

        sp_id = self.cleaned_data.get('spotify_playlist')
        if sp_id:
            # ➎ construïm o recuperem l’objecte Playlist amb aquest spotify_id
            pl_data = next((p for p in get_user_playlists(self.request) if p['id'] == sp_id), None)
            defaults = {'name': pl_data['name'], 'owner': pl_data['owner']} if pl_data else {}
            playlist_obj, _ = Playlist.objects.get_or_create(
                spotify_id=sp_id,
                defaults=defaults
            )
            # ➏ assignem l’objecte (no la cadena) al FK
            party.playlist = playlist_obj

        if commit:
            party.save()

            # ➐ si hem triat playlist, eliminem i recreem les cançons
            if sp_id:
                party.songs.all().delete()
                for tr in get_playlist_tracks(self.request, sp_id):
                    Song.objects.create(
                        party=party,
                        title=tr['title'],
                        artist=tr['artist'],
                        spotify_id=tr['id'],
                    )

        return party
