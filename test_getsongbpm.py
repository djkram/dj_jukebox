#!/usr/bin/env python
"""
Script de test per provar la cerca de BPM amb GetSongBPM
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dj_jukebox.settings')
django.setup()

from jukebox.spotify_api import _get_getsongbpm_features

# Cançons problemàtiques dels logs anteriors
test_songs = [
    ("Samba do Brasil", "Bellini"),
    ("Samba de Janeiro", "Bellini"),
    ("María Caipirinha (with Dj Dero)", "Carlinhos Brown, DJ Dero"),
    ("Sexy And I Know It", "LMFAO"),
    ("Rock This Party (Everybody Dance Now)", "Bob Sinclar, Cutee B., DollarMan, Big Ali, Makedah"),
    ("Papa Americano (dance remix)", "A Cool Beat DJ"),
    ("I Know You Want Me (Calle Ocho)", "Pitbull"),
    ("Bamboléo", "Gipsy Kings"),
    ("Barbra Streisand - Radio Edit", "Duck Sauce"),
]

print("=" * 80)
print("TEST DE CERCA DE BPM AMB GETSONGBPM")
print("=" * 80)
print()

results = []
for title, artist in test_songs:
    print(f"\n{'=' * 80}")
    print(f"Provant: {title} - {artist}")
    print('=' * 80)

    features = _get_getsongbpm_features(title, artist)

    bpm = features.get('bpm')
    key = features.get('key')

    success = bpm is not None or key is not None
    results.append({
        'title': title,
        'artist': artist,
        'bpm': bpm,
        'key': key,
        'success': success
    })

    if success:
        print(f"✓ TROBAT: BPM={bpm}, Key={key}")
    else:
        print(f"✗ NO TROBAT")

# Resum final
print("\n\n" + "=" * 80)
print("RESUM")
print("=" * 80)
found = sum(1 for r in results if r['success'])
total = len(results)
print(f"Trobats: {found}/{total} ({found/total*100:.1f}%)")
print()

for r in results:
    status = "✓" if r['success'] else "✗"
    bpm_str = f"BPM={r['bpm']}" if r['bpm'] else "BPM=--"
    key_str = f"Key={r['key']}" if r['key'] else "Key=--"
    print(f"{status} {r['title']:<50} {bpm_str:<12} {key_str}")
