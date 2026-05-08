from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('jukebox', '0024_party_time_fields')]
    operations = [
        migrations.AddField(
            model_name='song',
            name='played_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
