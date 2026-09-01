"""La garde « un récapitulatif par jour » disparaît — elle faisait perdre des relances.

Depuis que le récapitulatif suit les paliers (`items.0018`), la
non-répétition est tenue par `LendingReminder (lending, step_days,
recipient)` : un palier ne peut pas partir deux fois, jamais, quel que soit le
jour. La contrainte quotidienne sur `LibrarianDigest` faisait donc double
emploi — et c'est la plus faible des deux qui l'emportait, en taisant une
relance légitime au seul motif qu'un courriel était déjà parti le matin même.

`LibrarianDigest` reste, comme journal : elle répond à « est-ce que le
récapitulatif du 12 est parti, et à quelle adresse ? ».

⚠️ On RETIRE une contrainte : la migration inverse la remet, et elle peut
alors échouer si deux récapitulatifs ont été envoyés le même jour entre-temps.
C'est le sens normal d'un retour arrière sur une contrainte d'unicité, et
c'est dit ici pour que personne ne le découvre à chaud.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("items", "0018_paliers_et_destinataire"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="librariandigest",
            unique_together=set(),
        ),
    ]
