from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jukebox', '0023_security_and_schema_fixes'),
    ]

    operations = [
        migrations.AddField(
            model_name='party',
            name='jukebox_ends_at',
            field=models.TimeField(blank=True, help_text='Hora prevista de fi del DJJukebox', null=True),
        ),
        migrations.AddField(
            model_name='party',
            name='party_ends_at',
            field=models.TimeField(blank=True, help_text='Hora prevista de fi de la festa', null=True),
        ),
    ]
