from django.core.management.base import BaseCommand

from jukebox.models import Song
from jukebox.spotify_api import _get_getsongbpm_features


class Command(BaseCommand):
    help = "Fill missing BPM and key values using the GetSongBPM fallback API."

    def add_arguments(self, parser):
        parser.add_argument("--party-id", type=int, help="Limit the backfill to one party.")

    def handle(self, *args, **options):
        queryset = Song.objects.filter(bpm__isnull=True, key__isnull=True).order_by("id")
        if options["party_id"]:
            queryset = queryset.filter(party_id=options["party_id"])

        updated = 0
        checked = 0

        for song in queryset.iterator():
            checked += 1
            features = _get_getsongbpm_features(song.title, song.artist)
            if features["bpm"] is None and not features["key"]:
                continue

            song.bpm = features["bpm"]
            song.key = features["key"]
            song.save(update_fields=["bpm", "key"])
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(f"Checked {checked} songs, updated {updated}.")
        )
