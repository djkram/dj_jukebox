import uuid
from django.db import models

class Playlist(models.Model):
    spotify_id = models.CharField(max_length=128, unique=True)
    name = models.CharField(max_length=256)
    owner = models.CharField(max_length=128)

    def __str__(self):
        return self.name

class Party(models.Model):
    name = models.CharField(max_length=200)
    playlist = models.ForeignKey(Playlist, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateTimeField()
    code = models.CharField(max_length=12, unique=True, editable=False, default='')

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = uuid.uuid4().hex[:8]  # codi curt, pots fer servir més caràcters si vols
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Song(models.Model):
    party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name='songs', null=True, blank=True)
    title = models.CharField(max_length=200)
    artist = models.CharField(max_length=200)
    spotify_id = models.CharField(max_length=100)
    votes = models.IntegerField(default=0)
    played = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.title} - {self.artist}"
