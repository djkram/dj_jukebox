from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jukebox', '0015_party_status_and_jukebox_starts_at'),
    ]

    operations = [
        migrations.AlterField(
            model_name='party',
            name='party_status',
            field=models.CharField(
                choices=[
                    ('show_party', 'Mostrar festa'),
                    ('requests_open', 'Obrir peticions'),
                    ('djjukebox_active', 'Iniciar Jukebox'),
                    ('finished', 'Acabar festa'),
                ],
                default='show_party',
                max_length=20,
            ),
        ),
    ]
