# models.py

import uuid
from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    credits = models.PositiveIntegerField(default=0)

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
    max_votes_per_user = models.PositiveIntegerField(default=5)  # NOVETAT

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = uuid.uuid4().hex[:8]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Song(models.Model):
    party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name='songs', null=True, blank=True)
    title = models.CharField(max_length=200)
    artist = models.CharField(max_length=200)
    spotify_id = models.CharField(max_length=100)
    bpm = models.FloatField(null=True, blank=True)           # ← Nou camp
    key = models.CharField(max_length=4, null=True, blank=True)  # ← Nou camp (ex. “8B”)
    has_played = models.BooleanField(default=False)
    votes = models.IntegerField(default=0)
    played = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.title} - {self.artist}"

class Vote(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    song = models.ForeignKey(Song, related_name='vote', on_delete=models.CASCADE)
    party = models.ForeignKey(Party, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)


class VotePackage(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    party = models.ForeignKey(Party, on_delete=models.CASCADE)
    votes_purchased = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    payment_id = models.CharField(max_length=128, blank=True, null=True)  # per Stripe/Paypal
