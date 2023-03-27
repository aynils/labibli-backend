# Generated by Django 4.0.6 on 2023-03-27 10:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('items', '0015_alter_lending_book_book_items_book_author_892de8_idx_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='book',
            options={'ordering': ['-created_at', 'title']},
        ),
        migrations.AddField(
            model_name='book',
            name='location',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
