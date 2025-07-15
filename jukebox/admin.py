from django.contrib import admin
from .models import Song, Party, Playlist


# Register your models here.

admin.site.register(Song)
admin.site.register(Party)
admin.site.register(Playlist)
