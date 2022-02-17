# Generated by Django 3.2.9 on 2022-01-28 02:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0004_auto_20220128_0037'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subscription',
            name='interval',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='subscription',
            name='plan',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='subscription',
            name='stripe_customer_id',
            field=models.CharField(max_length=255, unique=True),
        ),
    ]