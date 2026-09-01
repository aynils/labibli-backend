"""Les deux traces d'envoi — ce sont elles qui empêchent le doublon.

Aucune des deux n'est décorative : ce sont les seules garanties que la BASE,
et pas seulement le code, refuse un second envoi.

  * `LendingReminder`, unique sur (prêt, jour) : jamais deux rappels pour le
    même prêt le même jour ;
  * `LibrarianDigest`, unique sur (organisation, jour) : jamais deux
    récapitulatifs à la même bibliothèque le même jour.

Elles tiennent même si deux exécutions se croisent, si quelqu'un règle la
fréquence à un jour, ou si la commande est rejouée à la main à 8 h 10 parce
que celle de 8 h a échoué.
"""

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_rappels_par_organisation'),
        ('items', '0016_alter_book_options_book_location'),
    ]

    operations = [
        migrations.CreateModel(
            name='LendingReminder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sent_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('sent_on', models.DateField()),
                ('to_email', models.EmailField(max_length=255)),
                ('language', models.CharField(blank=True, max_length=25, null=True)),
                ('lending', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reminders', to='items.lending')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.organization')),
            ],
            options={
                'ordering': ['-sent_at'],
                'indexes': [models.Index(fields=['organization', 'sent_at'], name='items_lendi_organiz_bc12c4_idx')],
                'unique_together': {('lending', 'sent_on')},
            },
        ),
        migrations.CreateModel(
            name='LibrarianDigest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sent_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('sent_on', models.DateField()),
                ('to_email', models.EmailField(max_length=255)),
                ('lendings_count', models.IntegerField(default=0)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.organization')),
            ],
            options={
                'ordering': ['-sent_at'],
                'unique_together': {('organization', 'sent_on')},
            },
        ),
    ]
