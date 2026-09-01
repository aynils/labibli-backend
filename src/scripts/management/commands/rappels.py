"""Envoyer les rappels de retard : aux membres, et à la bibliothécaire.

Cette commande est faite pour tourner toute seule, tous les matins à 8 h,
heure de l'Est, sans `--organization`. C'est ce chemin-là — le balayage de
toutes les organisations — qui doit être irréprochable, pas le chemin
manuel. Trois choses, donc, comptent plus que ce qu'elle envoie.

🔴 **Elle n'envoie rien à une organisation qui ne l'a pas demandé, et chaque
envoi a SON interrupteur.** `member_reminders_enabled` commande les rappels
aux membres, `librarian_digest_enabled` commande le récapitulatif à la
bibliothécaire. Ni l'un ni l'autre n'est allumé par défaut, et surtout :
⛔ aucun des deux ne commande l'autre. Une bibliothèque qui veut voir ses
retards sans encore écrire à ses membres doit pouvoir le faire — c'est même
le premier pas naturel. Dix-sept bibliothèques sont en production avec des
prêts en retard depuis des mois : une première exécution sans ces gardes
enverrait des centaines de courriels, en leur nom, à des gens qui n'ont
jamais reçu un seul message de La Bibli. Ça ne se rattrape pas — on ne
dé-envoie pas un courriel.

🔴 **Elle ne renvoie jamais deux fois la même chose.** Chaque envoi laisse
une trace : `LendingReminder` pour un rappel, `LibrarianDigest` pour un
récapitulatif. Relancée le même jour, après une coupure, ou deux fois de
suite par erreur, elle ne repart pas — et c'est le cas réel du matin où le
déploiement de 8 h échoue et où on rejoue la commande à 8 h 10. La base
elle-même refuse deux traces pour le même prêt le même jour, et deux
récapitulatifs pour la même organisation le même jour.

🔴 **`--dry-run` n'écrit et n'envoie RIEN.** Il sort avant la boucle d'envoi,
pas dans une branche à l'intérieur.

    manage.py rappels --dry-run                  # toutes celles qui l'ont activé
    manage.py rappels --organization 12 --dry-run
    manage.py rappels                            # pour de vrai

⚠️ Sans `--organization`, elle balaie toutes les organisations qui ont
activé AU MOINS un des deux envois — c'est le mode de la tâche planifiée.
`--organization` la restreint à une seule, et refuse quand même d'écrire si
cette organisation n'a rien activé : nommer une organisation n'est pas
l'activer.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils.timezone import now

from src.accounts.models import Organization
from src.items.reminders import envoyer_le_recapitulatif, envoyer_les_rappels


class Command(BaseCommand):
    help = "Envoie les rappels de retard aux membres et le récapitulatif aux bibliothécaires."

    def add_arguments(self, parser):
        parser.add_argument(
            "--organization", type=int, default=None,
            help="N'envoyer que pour cette organisation. Par défaut : toutes "
                 "celles qui ont activé les rappels.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Dire à qui on écrirait, sans écrire ni envoyer quoi que ce "
                 "soit. Le contrôle à passer avant d'activer une bibliothèque.",
        )

    def handle(self, *args, **options):
        a_blanc = options["dry_run"]
        organizations = self.get_organizations(options["organization"])
        instant = now()

        self.stdout.write("")
        if a_blanc:
            self.stdout.write("  ⚠️ À BLANC : aucun courriel ne partira, aucune trace ne sera écrite.")
        if not organizations:
            self.stdout.write(
                "  Aucune organisation n'a activé de rappel. Rien à faire.\n"
                "  (`member_reminders_enabled` et `librarian_digest_enabled` sont\n"
                "   à False partout : c'est le défaut.)\n"
            )
            return

        courriels_membres = prets_rappeles = recapitulatifs = 0
        for organization in organizations:
            self.stdout.write(
                f"\n  Organisation : « {organization.name} » (id {organization.id})"
            )

            # ── Les membres ──────────────────────────────────────────────
            rapport = envoyer_les_rappels(organization, at=instant, dry_run=a_blanc)
            courriels_membres += len(rapport.prevus) if a_blanc else rapport.envoyes
            prets_rappeles += (
                sum(len(prevu.lendings) for prevu in rapport.prevus)
                if a_blanc
                else rapport.prets_rappeles
            )
            self.raconter_les_rappels(rapport, a_blanc)

            # ── La bibliothécaire ────────────────────────────────────────
            #
            # 🔴 Appelé INCONDITIONNELLEMENT, quel que soit le sort des
            # rappels aux membres. Le mettre dans un `else`, ou le sauter
            # quand les membres sont éteints, ferait dépendre un envoi de
            # l'autre — c'est précisément ce que les deux interrupteurs
            # séparés servent à empêcher.
            recap = envoyer_le_recapitulatif(organization, at=instant, dry_run=a_blanc)
            recapitulatifs += 1 if (recap.envoye or (a_blanc and recap.retards)) else 0
            self.raconter_le_recapitulatif(recap, a_blanc)

        self.stdout.write(
            f"\n  {'à envoyer' if a_blanc else 'envoyés'} :\n"
            f"    {courriels_membres} rappel(s) aux membres, "
            f"pour {prets_rappeles} prêt(s) en retard\n"
            f"    {recapitulatifs} récapitulatif(s) aux bibliothécaires\n"
        )
        if a_blanc:
            self.stdout.write(self.style.WARNING("  Exécution à blanc : rien n'a été envoyé.\n"))

    def get_organizations(self, identifiant):
        """Les organisations qui ont activé AU MOINS un des deux envois.

        ⚠️ Un `OR`, pas un `AND`. Avec un `AND`, une bibliothèque qui n'aurait
        allumé que le récapitulatif serait écartée du balayage sans que rien
        ne le dise : elle cocherait la case, elle ne recevrait rien, et le
        seul symptôme serait un silence.

        Nommer une organisation avec `--organization` ne l'active pas : c'est
        un filtre, pas un interrupteur. Sans ça, la commande deviendrait le
        moyen d'écrire aux membres d'une bibliothèque sans son accord.
        """
        queryset = Organization.objects.filter(is_active=True).filter(
            Q(member_reminders_enabled=True) | Q(librarian_digest_enabled=True)
        )
        if identifiant is None:
            return list(queryset.select_related("owner").order_by("id"))

        if not Organization.objects.filter(pk=identifiant).exists():
            raise CommandError(f"Organisation {identifiant} introuvable.")
        return list(queryset.filter(pk=identifiant).select_related("owner"))

    def raconter_les_rappels(self, rapport, a_blanc):
        if rapport.desactive:
            self.stdout.write("    ·  membres : rappels non activés")
            return
        if not rapport.prevus:
            self.stdout.write("    ∅  membres : aucun rappel dû")
            return
        for prevu in rapport.prevus:
            titres = ", ".join(f"« {lending.book.title[:36]} »" for lending in prevu.lendings)
            self.stdout.write(
                f"    {'○' if a_blanc else '✅'} membre {prevu.email:34} "
                f"[{prevu.langue}] {titres}"
            )
        for echec in rapport.echecs:
            self.stdout.write(self.style.ERROR(f"    ❌ {echec}"))

    def raconter_le_recapitulatif(self, recap, a_blanc):
        if recap.desactive:
            self.stdout.write("    ·  bibliothécaire : récapitulatif non activé")
        elif recap.sans_destinataire:
            self.stdout.write(
                self.style.WARNING("    ⚠️ bibliothécaire : aucune adresse de destinataire")
            )
        elif not recap.retards:
            self.stdout.write("    ∅  bibliothécaire : aucune relance due aujourd'hui")
        elif recap.echec:
            self.stdout.write(self.style.ERROR(f"    ❌ {recap.echec}"))
        else:
            self.stdout.write(
                f"    {'○' if a_blanc else '✅'} bibliothécaire {recap.destinataire:26} "
                f"{len(recap.retards)} relance(s)"
            )
