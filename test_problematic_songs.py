#!/usr/bin/env python
"""
Test específic per les cançons problemàtiques
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dj_jukebox.settings')
django.setup()

from jukebox.spotify_api import _get_getsongbpm_features

# Només les 3 cançons problemàtiques
test_songs = [
    ("María Caipirinha (with Dj Dero)", "Carlinhos Brown, DJ Dero"),
    ("Rock This Party (Everybody Dance Now)", "Bob Sinclar, Cutee B., DollarMan, Big Ali, Makedah"),
    ("Papa Americano (dance remix)", "A Cool Beat DJ"),
]

print("=" * 80)
print("TEST DE CANÇONS PROBLEMÀTIQUES")
print("=" * 80)
print()

for title, artist in test_songs:
    print(f"\n{'=' * 80}")
    print(f"Provant: {title}")
    print(f"Artista: {artist}")
    print('=' * 80)

    features = _get_getsongbpm_features(title, artist)

    bpm = features.get('bpm')
    key = features.get('key')

    if bpm or key:
        print(f"\n✓ RESULTAT: BPM={bpm}, Key={key}")
    else:
        print(f"\n✗ NO TROBAT")

    print()
