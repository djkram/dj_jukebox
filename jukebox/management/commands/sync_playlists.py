# sync_playlists.py

from django.core.management.base import BaseCommand
from jukebox.spotify_sync import sync_all_parties
import json


class Command(BaseCommand):
    help = 'Sync all auto-sync enabled parties with Spotify'

    def add_arguments(self, parser):
        parser.add_argument(
            '--party-id',
            type=int,
            help='Sync only a specific party by ID',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output for each party',
        )

    def handle(self, *args, **options):
        party_id = options.get('party_id')
        verbose = options.get('verbose')

        if party_id:
            # Sync només una festa específica
            from jukebox.spotify_sync import sync_playlist_with_spotify
            self.stdout.write(f"Syncing party {party_id}...")
            result = sync_playlist_with_spotify(party_id)

            if result.get('success'):
                self.stdout.write(self.style.SUCCESS(
                    f"✓ Party {party_id} synced: +{result['added']} -{result['removed']} (total: {result['total']})"
                ))
            elif result.get('skipped'):
                self.stdout.write(self.style.WARNING(
                    f"⊘ Party {party_id} skipped: {result['reason']}"
                ))
            else:
                self.stdout.write(self.style.ERROR(
                    f"✗ Party {party_id} error: {result.get('error')}"
                ))
        else:
            # Sync totes les festes amb auto-sync activat
            self.stdout.write("Syncing all auto-sync enabled parties...")
            result = sync_all_parties()

            self.stdout.write(f"\nTotal parties: {result['total_parties']}")
            self.stdout.write(self.style.SUCCESS(f"✓ Synced: {result['synced']}"))
            self.stdout.write(self.style.WARNING(f"⊘ Skipped: {result['skipped']}"))
            if result['errors'] > 0:
                self.stdout.write(self.style.ERROR(f"✗ Errors: {result['errors']}"))

            if verbose and result['results']:
                self.stdout.write("\nDetailed results:")
                for party_result in result['results']:
                    party_name = party_result.get('party_name', 'Unknown')
                    party_id = party_result.get('party_id', '?')

                    if party_result.get('success'):
                        self.stdout.write(
                            f"  • {party_name} (#{party_id}): "
                            f"+{party_result['added']} -{party_result['removed']}"
                        )
                    elif party_result.get('skipped'):
                        self.stdout.write(
                            f"  • {party_name} (#{party_id}): skipped ({party_result['reason']})"
                        )
                    else:
                        self.stdout.write(
                            f"  • {party_name} (#{party_id}): error ({party_result.get('error')})"
                        )

        self.stdout.write(self.style.SUCCESS("\nSync completed!"))
