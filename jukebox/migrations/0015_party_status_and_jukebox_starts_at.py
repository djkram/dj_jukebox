from django.db import migrations, models


def sync_party_status_from_legacy_flag(apps, schema_editor):
    Party = apps.get_model('jukebox', 'Party')
    for party in Party.objects.all():
        party.party_status = 'djjukebox_active' if party.is_jukebox_active else 'requests_open'
        party.save(update_fields=['party_status'])


class Migration(migrations.Migration):

    dependencies = [
        ('jukebox', '0014_party_is_jukebox_active'),
    ]

    operations = [
        migrations.AddField(
            model_name='party',
            name='jukebox_starts_at',
            field=models.TimeField(blank=True, help_text="Hora prevista d'activació del DJJukebox", null=True),
        ),
        migrations.AddField(
            model_name='party',
            name='party_status',
            field=models.CharField(
                choices=[
                    ('requests_open', 'Peticions obertes'),
                    ('djjukebox_active', 'DJJukebox actiu'),
                    ('finished', 'Festa acabada'),
                ],
                default='requests_open',
                max_length=20,
            ),
        ),
        migrations.RunPython(sync_party_status_from_legacy_flag, migrations.RunPython.noop),
    ]
