# Generated by Django 3.1 on 2021-09-01 12:54

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='myuser',
            name='nickname',
        ),
    ]
