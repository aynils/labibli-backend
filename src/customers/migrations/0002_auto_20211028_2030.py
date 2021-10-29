# Generated by Django 3.1 on 2021-10-28 20:30

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_user_employee_of_organization'),
        ('customers', '0001_initial'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='customer',
            unique_together={('organization', 'first_name', 'last_name', 'phone'), ('organization', 'first_name', 'last_name', 'email')},
        ),
    ]
