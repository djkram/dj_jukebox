# models.py

import re
import uuid
import unicodedata
from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    credits = models.PositiveIntegerField(default=0)

class Playlist(models.Model):
    spotify_id = models.CharField(max_length=128, unique=True)
    name = models.CharField(max_length=256)
    owner = models.CharField(max_length=128)

    def __str__(self):
        return self.name

class Party(models.Model):
    STATUS_HIDDEN = 'hidden'
    STATUS_SHOW_PARTY = 'show_party'
    STATUS_REQUESTS_OPEN = 'requests_open'
    STATUS_DJJUKEBOX_ACTIVE = 'djjukebox_active'
    STATUS_FINISHED = 'finished'
    STATUS_CHOICES = [
        (STATUS_HIDDEN, _('Festa oculta')),
        (STATUS_SHOW_PARTY, _('Mostrar festa')),
        (STATUS_REQUESTS_OPEN, _('Obrir peticions')),
        (STATUS_DJJUKEBOX_ACTIVE, _('Iniciar Jukebox')),
        (STATUS_FINISHED, _('Acabar festa')),
    ]

    name = models.CharField(max_length=200)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, help_text=_("Creador de la festa (necessari per Spotify sync)"))
    playlist = models.ForeignKey(Playlist, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateTimeField()
    code = models.CharField(max_length=12, unique=True, editable=True, default='')
    cover_image = models.ImageField(upload_to='party_covers/', null=True, blank=True, help_text=_("Imatge de portada de la festa"))
    require_join_code = models.BooleanField(default=False, help_text=_("Requerir codi per unir-se a la festa"))
    is_public = models.BooleanField(default=True, help_text=_("Festa pública (llistada) o privada (no llistada)"))
    max_votes_per_user = models.PositiveIntegerField(default=5)  # Vots gratuïts per usuari
    free_coins_per_user = models.PositiveIntegerField(default=0)  # Coins gratuïts per usuari (per festa)
    song_request_cost = models.PositiveIntegerField(default=10)  # Cost en Coins per demanar una cançó
    allow_song_requests = models.BooleanField(default=True, help_text=_("Permetre als usuaris demanar cançons noves (es paguen amb Coins)"))
    party_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_HIDDEN)
    jukebox_starts_at = models.TimeField(null=True, blank=True, help_text=_("Hora prevista d'activació del DJJukebox"))
    is_jukebox_active = models.BooleanField(default=True, help_text=_("Indica si el jukebox està actiu per aquesta festa"))
    auto_sync_playlist = models.BooleanField(default=False, help_text=_("Sincronitzar automàticament amb Spotify cada 5 minuts"))
    last_sync_at = models.DateTimeField(null=True, blank=True, help_text=_("Última sincronització exitosa"))
    auto_analyze_audio = models.BooleanField(default=False, help_text=_("Analitzar automàticament àudio cada 5 minuts"))
    last_analyze_at = models.DateTimeField(null=True, blank=True, help_text=_("Última anàlisi automàtica"))

    @staticmethod
    def normalize_code(raw_code):
        normalized = unicodedata.normalize('NFKD', raw_code or '')
        ascii_only = normalized.encode('ascii', 'ignore').decode('ascii')
        cleaned = re.sub(r'[^A-Za-z0-9]', '', ascii_only).upper()
        return cleaned[:12]

    @staticmethod
    def _build_acronym_code(name):
        normalized = unicodedata.normalize('NFKD', name or '')
        ascii_only = normalized.encode('ascii', 'ignore').decode('ascii')
        tokens = re.findall(r'[A-Za-z0-9]+', ascii_only)

        acronym = ''.join(token[0] for token in tokens if token).upper()
        digits = ''.join(ch for ch in ascii_only if ch.isdigit())
        year_hint = digits[-2:] if digits else ''

        compact = ''.join(tokens).upper()
        base = f"{acronym}{year_hint}" if acronym else compact
        if len(base) < 4:
            base = f"{base}{compact}"
        if len(base) < 4:
            base = f"{base}DJBX"
        return base[:12]

    def _generate_unique_code(self):
        base = self._build_acronym_code(self.name)
        if not base:
            base = uuid.uuid4().hex[:8].upper()

        if not Party.objects.exclude(pk=self.pk).filter(code=base).exists():
            return base

        for i in range(1, 1000):
            suffix = f"{i:02d}"
            prefix_len = 12 - len(suffix)
            candidate = f"{base[:prefix_len]}{suffix}"
            if not Party.objects.exclude(pk=self.pk).filter(code=candidate).exists():
                return candidate

        return uuid.uuid4().hex[:8].upper()

    def save(self, *args, **kwargs):
        self.code = self.normalize_code(self.code)
        if not self.code:
            self.code = self._generate_unique_code()
        self.is_jukebox_active = self.party_status == self.STATUS_DJJUKEBOX_ACTIVE
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
        ('like', _('M\'agrada')),
        ('dislike', _('No m\'agrada')),
        ('skip', _('Passar')),
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
        ('pending', _('Pendent')),
        ('accepted', _('Acceptada')),
        ('rejected', _('Rebutjada')),
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
        ('song_accepted', _('Cançó acceptada')),
        ('song_played', _('Cançó reproduïda')),
        ('coins_purchased', _('Coins comprats')),
        ('coins_received', _('Coins rebuts')),
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
