# Generated by Django 3.2.9 on 2021-11-26 18:28

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0002_auto_20211111_1827'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subscription',
            name='created_at',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]