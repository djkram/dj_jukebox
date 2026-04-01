from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jukebox', '0016_alter_party_party_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='party',
            name='party_status',
            field=models.CharField(
                choices=[
                    ('hidden', 'Festa oculta'),
                    ('show_party', 'Mostrar festa'),
                    ('requests_open', 'Obrir peticions'),
                    ('djjukebox_active', 'Iniciar Jukebox'),
                    ('finished', 'Acabar festa'),
                ],
                default='hidden',
                max_length=20,
            ),
        ),
    ]
