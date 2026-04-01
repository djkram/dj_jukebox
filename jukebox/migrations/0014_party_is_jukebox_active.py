from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jukebox', '0013_alter_vote_vote_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='party',
            name='is_jukebox_active',
            field=models.BooleanField(default=True, help_text='Indica si el jukebox està actiu per aquesta festa'),
        ),
    ]
