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
    max_votes_per_user = models.PositiveIntegerField(default=5)  # Vots gratuïts per usuari
    free_coins_per_user = models.PositiveIntegerField(default=0)  # Coins gratuïts per usuari (per festa)
    song_request_cost = models.PositiveIntegerField(default=10)  # Cost en Coins per demanar una cançó

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
    album_image_url = models.URLField(max_length=500, null=True, blank=True)  # URL de la caràtula
    preview_url = models.URLField(max_length=500, null=True, blank=True)  # URL del preview de 30s
    bpm = models.FloatField(null=True, blank=True)           # ← Nou camp
    key = models.CharField(max_length=4, null=True, blank=True)  # ← Nou camp (ex. “8B”)
    has_played = models.BooleanField(default=False)
    votes = models.IntegerField(default=0)
    played = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.title} - {self.artist}"

class Vote(models.Model):
    VOTE_TYPES = [
        ('like', 'M\'agrada'),
        ('dislike', 'No m\'agrada'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    song = models.ForeignKey(Song, related_name='vote', on_delete=models.CASCADE)
    party = models.ForeignKey(Party, on_delete=models.CASCADE)
    vote_type = models.CharField(max_length=10, choices=VOTE_TYPES, default='like')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'song', 'party']  # Un usuari només pot votar una cançó un cop per festa


class VotePackage(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    party = models.ForeignKey(Party, on_delete=models.CASCADE)
    votes_purchased = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    payment_id = models.CharField(max_length=128, blank=True, null=True)  # per Stripe/Paypal


class PartyCoinsGrant(models.Model):
    """
    Registra coins gratuïts donats per festa.
    Permet ajustar dinàmicament els coins gratuïts sense afectar els ja utilitzats.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    party = models.ForeignKey(Party, on_delete=models.CASCADE)
    coins_granted = models.IntegerField()  # Pot ser positiu (donar) o negatiu (retirar disponibles)
    created_at = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=100, default='free_coins')  # 'free_coins', 'adjustment', etc.

    class Meta:
        ordering = ['-created_at']


class SongRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pendent'),
        ('accepted', 'Acceptada'),
        ('rejected', 'Rebutjada'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    party = models.ForeignKey(Party, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    artist = models.CharField(max_length=200)
    spotify_id = models.CharField(max_length=100)
    album_image_url = models.URLField(max_length=500, null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    coins_cost = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_requests')

    def __str__(self):
        return f"{self.title} - {self.artist} ({self.status})"


class Notification(models.Model):
    TYPE_CHOICES = [
        ('song_accepted', 'Cançó acceptada'),
        ('song_played', 'Cançó reproduïda'),
        ('coins_purchased', 'Coins comprats'),
        ('coins_received', 'Coins rebuts'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    song = models.ForeignKey(Song, on_delete=models.SET_NULL, null=True, blank=True)
    song_request = models.ForeignKey(SongRequest, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.IntegerField(null=True, blank=True)  # Per Coins
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.title}"
