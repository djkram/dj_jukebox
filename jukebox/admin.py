from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Song, Party, Playlist, User, SongRequest, Notification


# Register your models here.

admin.site.register(User, UserAdmin)
admin.site.register(Song)
admin.site.register(Party)
admin.site.register(Playlist)
admin.site.register(SongRequest)
admin.site.register(Notification)
