# Generated by Django 5.2.4 on 2025-07-16 10:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jukebox', '0003_party_code'),
    ]

    operations = [
        migrations.AddField(
            model_name='party',
            name='max_votes_per_user',
            field=models.PositiveIntegerField(default=3),
        ),
    ]
