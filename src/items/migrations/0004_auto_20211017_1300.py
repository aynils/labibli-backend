# Generated by Django 3.1 on 2021-10-17 13:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('items', '0003_book_inventory'),
    ]

    operations = [
        migrations.AlterField(
            model_name='book',
            name='isbn',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
