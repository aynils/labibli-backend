"""Les paliers de relance : combien de fois on écrit, et quand on s'arrête.

🔴 Le cas qui a fait écrire ce module AVANT le code : une bibliothèque qui
allume les rappels un matin a des prêts en retard depuis des mois. Un prêt de
quarante-cinq jours a « manqué » les paliers 0, 7 et 30. S'il les recevait
tous, la même personne recevrait TROIS courriels d'affilée, à la seconde même
où on active la fonction, et ça sur dix-sept organisations à la fois. C'est
la panne la plus chère que ce chantier puisse produire, et elle n'arrive
qu'une fois : le jour de l'activation, quand tout le monde regarde.

La règle retenue, et elle tient en une phrase : **on n'envoie jamais un
palier inférieur ou égal à un palier déjà envoyé.** Le prêt de quarante-cinq
jours reçoit donc le palier 30, une fois, et plus rien ensuite.

Le reste du fichier est écrit au négatif, comme le reste du dépôt.
"""
import datetime
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core import mail
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APITestCase
from django.utils.timezone import now

from src.accounts.models import Organization
from src.customers.models import Customer
from src.helpers.tests import (
    authenticate_user,
    create_admin_user,
    create_organization,
    create_user,
)
from src.items.models import Book, Lending, LendingReminder, LibrarianDigest  # noqa: F401
from src.helpers.paliers import normaliser_paliers, palier_atteint
from src.items.models import CLIENT, LIBRAIRE
from src.items.reminders import prets_en_retard


class PalierAtteintTests(SimpleTestCase):
    """La fonction qui décide, isolée de toute base de données."""

    PALIERS = [0, 7, 30]

    def test_le_jour_du_retard_franchit_le_premier_palier(self):
        self.assertEqual(palier_atteint(0, self.PALIERS), 0)

    def test_entre_deux_paliers_c_est_le_PRECEDENT_qui_vaut(self):
        """Six jours de retard, ce n'est pas encore le palier de sept."""
        for jours in (1, 3, 6):
            self.assertEqual(palier_atteint(jours, self.PALIERS), 0, jours)
        for jours in (7, 8, 29):
            self.assertEqual(palier_atteint(jours, self.PALIERS), 7, jours)

    def test_au_dela_du_DERNIER_palier_le_dernier_reste(self):
        """⛔ Il ne repart pas à zéro, et il n'en invente pas un quatrième :
        c'est ce qui garantit qu'on finit par se taire."""
        for jours in (30, 45, 400):
            self.assertEqual(palier_atteint(jours, self.PALIERS), 30, jours)

    def test_aucun_palier_franchi_quand_le_premier_est_dans_le_futur(self):
        """Une bibliothèque qui règle « 3, 10 » ne dit rien les trois
        premiers jours."""
        self.assertIsNone(palier_atteint(0, [3, 10]))
        self.assertIsNone(palier_atteint(2, [3, 10]))
        self.assertEqual(palier_atteint(3, [3, 10]), 3)


class NormaliserPaliersTests(SimpleTestCase):
    """⛔ Une valeur invalide se refuse à L'ÉCRITURE.

    Pas à 8 h du matin, dans une tâche planifiée que personne ne regarde, sous
    la forme d'une exception qui n'envoie ni les rappels de cette
    organisation-là ni ceux des seize autres.
    """

    def test_trie_et_dedoublonne(self):
        self.assertEqual(normaliser_paliers([30, 0, 7, 7]), [0, 7, 30])

    def test_accepte_les_entiers_ecrits_en_texte(self):
        """L'interface envoie du JSON, mais un import ou un shell envoie ce
        qu'il veut."""
        self.assertEqual(normaliser_paliers(["0", "7"]), [0, 7])

    def test_REFUSE_une_liste_vide(self):
        """Zéro palier voudrait dire « activé mais muet » : deux façons de
        dire non, et la bibliothèque ne saurait pas laquelle est vraie."""
        with self.assertRaises(ValidationError):
            normaliser_paliers([])

    def test_REFUSE_un_jour_negatif(self):
        """Relancer avant l'échéance n'est pas un rappel de retard."""
        with self.assertRaises(ValidationError):
            normaliser_paliers([-1, 7])

    def test_REFUSE_ce_qui_n_est_pas_un_nombre(self):
        for valeur in ("0,7,30", [None], ["sept"], [1.5], 7):
            with self.assertRaises(ValidationError):
                normaliser_paliers(valeur)

    def test_REFUSE_une_liste_absurdement_longue(self):
        """Quarante relances, c'est quarante courriels à la même personne."""
        with self.assertRaises(ValidationError):
            normaliser_paliers(list(range(0, 80)))

    def test_REFUSE_un_delai_absurde(self):
        """La faute de frappe « 3000 » au lieu de « 30 » ne doit pas dormir
        dix ans dans la base."""
        with self.assertRaises(ValidationError):
            normaliser_paliers([0, 3000])


class PaliersEnBaseTests(TestCase):
    """Le réglage lui-même, et son refus d'avaler n'importe quoi."""

    def test_le_defaut_est_zero_sept_trente(self):
        organization = Organization.objects.create(
            name="Bibliothèque neuve", owner=create_user()
        )
        self.assertEqual(organization.reminder_schedule_days, [0, 7, 30])

    def test_la_valeur_est_NORMALISEE_a_l_ecriture(self):
        organization = Organization.objects.create(
            name="Bibliothèque neuve", owner=create_user()
        )
        organization.reminder_schedule_days = [30, 7, 0, 30]
        organization.save()
        organization.refresh_from_db()
        self.assertEqual(organization.reminder_schedule_days, [0, 7, 30])

    def test_une_valeur_invalide_est_REFUSEE_a_l_ecriture(self):
        """🔴 Même depuis un shell, même sans passer par un formulaire.

        C'est la seule barrière qui tienne : l'API et l'admin valident déjà,
        mais c'est le `manage.py shell` d'un soir de correctif qui pose les
        valeurs impossibles.
        """
        organization = Organization.objects.create(
            name="Bibliothèque neuve", owner=create_user()
        )
        organization.reminder_schedule_days = [-3]
        with self.assertRaises(ValidationError):
            organization.save()


class RelancesSuccessivesTests(TestCase):
    """Le déroulé complet d'un prêt qui ne revient jamais."""

    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.organization = create_organization(owner=cls.user)
        cls.organization.member_reminders_enabled = True
        cls.organization.librarian_digest_enabled = False
        cls.organization.reminder_schedule_days = [0, 7, 30]
        cls.organization.save()
        cls.voisine = create_organization(owner=create_admin_user())
        cls.voisine.name = "Bibliotheque voisine"
        cls.voisine.member_reminders_enabled = True
        cls.voisine.save()

    def setUp(self):
        mail.outbox = []

    def membre(self, organization=None, prenom="Jeanne", **champs):
        return Customer.objects.create(
            organization=organization or self.organization,
            first_name=prenom,
            last_name="Tremblay",
            email=champs.pop("email", f"{prenom.lower()}@exemple.test"),
            language="fr",
            **champs,
        )

    def pret(self, customer, titre="Kukum", retard_jours=0, organization=None, **champs):
        organization = organization or customer.organization
        book = Book.objects.create(
            organization=organization, title=titre, author="Michel Jean"
        )
        return Lending.objects.create(
            organization=organization,
            customer=customer,
            book=book,
            allowance_days=31,
            lent_at=now() - datetime.timedelta(days=31 + retard_jours),
            **champs,
        )

    def lancer(self, **options):
        sortie = StringIO()
        call_command("rappels", stdout=sortie, stderr=sortie, **options)
        return sortie.getvalue()

    def vieillir(self, lending, jours):
        """Reculer le prêt : c'est le seul moyen de faire passer le temps
        sans mentir à l'horloge du système."""
        lending.lent_at = now() - datetime.timedelta(days=31 + jours)
        lending.save(update_fields=["lent_at"])

    # ── 🔴 Le cas de l'activation ────────────────────────────────────────

    def test_un_retard_ANCIEN_ne_recoit_QU_UN_courriel_le_jour_de_l_activation(self):
        """🔴 Le test écrit avant le code.

        Quarante-cinq jours de retard, paliers 0/7/30 : les trois sont
        franchis. Envoyer les trois, c'est trois courriels d'affilée à la même
        personne, à la minute où la bibliothèque coche la case — et sur dix-
        sept organisations qui ont toutes des retards dormants.
        """
        membre = self.membre()
        self.pret(membre, retard_jours=45)

        self.lancer()

        self.assertEqual(len(mail.outbox), 1)
        traces = LendingReminder.objects.filter(recipient=CLIENT)
        self.assertEqual([t.step_days for t in traces], [30])

    def test_ce_retard_ancien_ne_recoit_ensuite_PLUS_JAMAIS_rien(self):
        """Le dernier palier est le dernier. Passé lui, on se tait."""
        membre = self.membre()
        pret = self.pret(membre, retard_jours=45)
        self.lancer()
        mail.outbox = []

        for jours in (46, 60, 120, 400):
            self.vieillir(pret, jours)
            self.lancer()
        self.assertEqual(mail.outbox, [])
        self.assertEqual(LendingReminder.objects.filter(recipient=CLIENT).count(), 1)

    # ── Le déroulé normal ────────────────────────────────────────────────

    def test_trois_relances_puis_LE_SILENCE(self):
        """La question de Séraphin — « combien de rappels ? » — a maintenant
        une réponse : la longueur de la liste."""
        membre = self.membre()
        pret = self.pret(membre, retard_jours=0)

        recus = []
        for jours in range(0, 60):
            self.vieillir(pret, jours)
            self.lancer()
            recus.append(len(mail.outbox))

        self.assertEqual(len(mail.outbox), 3)
        # Et ils tombent bien aux jours 0, 7 et 30.
        jours_d_envoi = [jour for jour in range(1, 60) if recus[jour] > recus[jour - 1]]
        self.assertEqual([0] + jours_d_envoi, [0, 7, 30])

    def test_un_jour_SANS_palier_n_envoie_rien(self):
        membre = self.membre()
        pret = self.pret(membre, retard_jours=0)
        self.lancer()
        mail.outbox = []

        for jours in (1, 2, 3, 4, 5, 6):
            self.vieillir(pret, jours)
            self.lancer()
        self.assertEqual(mail.outbox, [])

    def test_une_JOURNEE_MANQUEE_ne_perd_pas_la_relance(self):
        """🔴 La tâche de 8 h peut échouer — c'est arrivé chez Feuille de
        temps, huit heures durant, sans que rien ne l'annonce.

        Si le palier se lisait « le retard vaut exactement 7 jours », une
        journée sautée perdrait la relance pour toujours, en silence. Il se
        lit « le retard a dépassé 7 jours », donc elle repart le lendemain.
        """
        membre = self.membre()
        pret = self.pret(membre, retard_jours=0)
        self.lancer()
        mail.outbox = []

        # Le matin du septième jour, la tâche ne tourne pas. On saute à huit.
        self.vieillir(pret, 8)
        self.lancer()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            list(
                LendingReminder.objects.filter(recipient=CLIENT)
                .order_by("step_days")
                .values_list("step_days", flat=True)
            ),
            [0, 7],
        )

    def test_les_paliers_de_CHAQUE_organisation_sont_les_siens(self):
        """🔴 Le cloisonnement, sur le réglage lui-même.

        La voisine garde les paliers par défaut ; celle-ci n'en a qu'un. Lire
        les paliers de la mauvaise organisation ne lèverait aucune erreur : ça
        enverrait simplement le mauvais nombre de courriels, aux bonnes
        personnes, ce qui est indétectable.
        """
        self.organization.reminder_schedule_days = [0]
        self.organization.save()
        chez_nous = self.membre()
        pret_a_nous = self.pret(chez_nous, titre="Kukum", retard_jours=0)
        chez_elle = self.membre(organization=self.voisine, prenom="Amir")
        pret_voisin = self.pret(chez_elle, titre="Maus", retard_jours=0)

        self.lancer()
        mail.outbox = []
        self.vieillir(pret_a_nous, 7)
        self.vieillir(pret_voisin, 7)
        self.lancer()

        # Nous : un seul palier, donc plus rien au septième jour.
        # La voisine : paliers par défaut, donc une relance.
        self.assertEqual([m.to for m in mail.outbox], [["amir@exemple.test"]])

    # ── ⛔ Ce qui ne doit JAMAIS arriver ─────────────────────────────────

    def test_une_relance_n_est_JAMAIS_envoyee_DEUX_FOIS(self):
        membre = self.membre()
        self.pret(membre, retard_jours=7)
        self.lancer()
        self.lancer()
        self.lancer()
        self.assertEqual(len(mail.outbox), 1)

    def test_un_prêt_RENDU_entre_deux_paliers_n_est_plus_relance(self):
        membre = self.membre()
        pret = self.pret(membre, retard_jours=0)
        self.lancer()
        mail.outbox = []

        pret.returned_at = now()
        pret.save(update_fields=["returned_at"])
        self.vieillir(pret, 30)
        self.lancer()
        self.assertEqual(mail.outbox, [])


class PaliersDuRecapitulatifTests(TestCase):
    """La bibliothécaire suit les mêmes paliers, avec sa PROPRE histoire."""

    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.organization = create_organization(owner=cls.user)
        cls.organization.librarian_digest_enabled = True
        cls.organization.member_reminders_enabled = False
        cls.organization.reminder_schedule_days = [0, 7, 30]
        cls.organization.save()

    def setUp(self):
        mail.outbox = []
        self.membre = Customer.objects.create(
            organization=self.organization,
            first_name="Jeanne",
            last_name="Tremblay",
            email="jeanne@exemple.test",
        )

    def pret(self, titre="Kukum", retard_jours=0, customer=None):
        book = Book.objects.create(
            organization=self.organization, title=titre, author="Michel Jean"
        )
        return Lending.objects.create(
            organization=self.organization,
            customer=customer or self.membre,
            book=book,
            allowance_days=31,
            lent_at=now() - datetime.timedelta(days=31 + retard_jours),
        )

    def vieillir(self, lending, jours):
        lending.lent_at = now() - datetime.timedelta(days=31 + jours)
        lending.save(update_fields=["lent_at"])

    def lancer(self, **options):
        sortie = StringIO()
        call_command("rappels", stdout=sortie, stderr=sortie, **options)
        return sortie.getvalue()

    def test_la_MEME_ligne_ne_revient_PAS_tous_les_matins(self):
        """🔴 Le défaut vu d'en face.

        Un courriel qui répète la même chose chaque jour devient un courriel
        qu'on n'ouvre plus — et c'est dedans que le nouveau retard se
        cachera.
        """
        pret = self.pret()
        self.lancer()
        self.assertEqual(len(mail.outbox), 1)

        for jours in (1, 2, 3, 4, 5, 6):
            self.vieillir(pret, jours)
            self.lancer()
        self.assertEqual(len(mail.outbox), 1)

        self.vieillir(pret, 7)
        self.lancer()
        self.assertEqual(len(mail.outbox), 2)

    def test_un_jour_ou_AUCUN_pret_n_atteint_de_palier_n_envoie_RIEN(self):
        pret = self.pret()
        self.lancer()
        mail.outbox = []
        self.vieillir(pret, 3)
        sortie = self.lancer()
        self.assertEqual(mail.outbox, [])
        self.assertEqual(LibrarianDigest.objects.count(), 1)
        self.assertIn("aucune relance", sortie)

    def test_l_histoire_de_la_bibliothecaire_est_SEPAREE_de_celle_des_membres(self):
        """⛔ Les rappels aux membres sont éteints depuis le début ici.

        Si les deux destinataires partageaient une histoire, le récapitulatif
        trouverait les paliers « déjà faits » par un envoi qui n'a jamais eu
        lieu, et la bibliothécaire ne recevrait jamais rien.
        """
        self.pret()
        self.lancer()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(LendingReminder.objects.filter(recipient=CLIENT).count(), 0)
        self.assertEqual(LendingReminder.objects.filter(recipient=LIBRAIRE).count(), 1)

    def test_un_retard_ANCIEN_ne_paraît_QU_UNE_fois_a_l_activation(self):
        """Le pendant du cas de l'activation, côté bibliothécaire."""
        pret = self.pret(retard_jours=45)
        self.lancer()
        self.assertEqual(len(mail.outbox), 1)

        mail.outbox = []
        for jours in (46, 90, 300):
            self.vieillir(pret, jours)
            self.lancer()
        self.assertEqual(mail.outbox, [])


class PretsEnRetardTests(TestCase):
    """Le contrat de `prets_en_retard`, éprouvé directement.

    🔑 Pourquoi ne pas s'en tenir aux tests de bout en bout : depuis les
    paliers, le filtre « l'échéance est passée » est devenu INOBSERVABLE de
    l'extérieur. Un prêt qui n'est pas encore dû a un retard négatif, donc il
    ne franchit aucun palier, donc rien ne part — même si la fonction le
    rendait. Une épreuve par mutation l'a montré : on pouvait retirer le
    filtre et la suite restait verte.

    Il reste, pour deux raisons. Il rend la fonction honnête vis-à-vis de son
    nom, ce dont dépendra le prochain appelant ; et il évite de calculer un
    palier pour chacun des trois mille prêts en cours d'une collection quand
    trois sont en retard. Une garantie qu'aucun test ne tient est une garantie
    qui disparaîtra au premier nettoyage : celui-ci la tient.
    """

    @classmethod
    def setUpTestData(cls):
        cls.organization = create_organization(owner=create_user())
        cls.voisine = create_organization(owner=create_admin_user())

    def pret(self, organization, retard_jours, **champs):
        customer = Customer.objects.create(
            organization=organization, first_name="Jeanne", last_name="Tremblay",
            email=f"j{retard_jours}@exemple.test",
        )
        book = Book.objects.create(
            organization=organization, title="Kukum", author="Michel Jean"
        )
        return Lending.objects.create(
            organization=organization, customer=customer, book=book,
            allowance_days=31,
            lent_at=now() - datetime.timedelta(days=31 + retard_jours),
            **champs,
        )

    def test_rend_un_pret_dont_l_echeance_est_passee(self):
        pret = self.pret(self.organization, retard_jours=1)
        self.assertEqual(prets_en_retard(self.organization), [pret])

    def test_ne_rend_PAS_un_pret_dont_l_echeance_est_a_venir(self):
        self.pret(self.organization, retard_jours=-5)
        self.assertEqual(prets_en_retard(self.organization), [])

    def test_ne_rend_PAS_un_pret_deja_rendu(self):
        self.pret(self.organization, retard_jours=10, returned_at=now())
        self.assertEqual(prets_en_retard(self.organization), [])

    def test_ne_rend_JAMAIS_le_pret_d_une_AUTRE_organisation(self):
        """🔴 Le cloisonnement, sur la fonction dont TOUT le reste dépend."""
        self.pret(self.voisine, retard_jours=10)
        self.assertEqual(prets_en_retard(self.organization), [])


class ApiDesPaliersTests(APITestCase):
    """Le chemin que l'interface empruntera — « Mon compte → Notifications ».

    ⛔ Une valeur invalide doit revenir en 400, avec un message lisible. Si
    elle passait, elle ne se verrait qu'à 8 h le lendemain matin, sous la forme
    d'une tâche planifiée qui lève — et ce matin-là, aucune des dix-sept
    organisations n'est servie, pas seulement celle qui a la mauvaise valeur.
    """

    def setUp(self):
        self.user = create_user()
        self.organization = create_organization(owner=self.user)
        authenticate_user(self)
        self.url = f"/api/accounts/organizations/{self.organization.id}/"

    def test_la_proprietaire_regle_ses_paliers(self):
        reponse = self.client.patch(
            self.url, {"reminder_schedule_days": [0, 14, 45]}, format="json"
        )
        self.assertEqual(reponse.status_code, 200)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.reminder_schedule_days, [0, 14, 45])

    def test_les_paliers_reviennent_TRIES(self):
        """L'interface peut envoyer ce que la personne a tapé, dans l'ordre où
        elle l'a tapé."""
        reponse = self.client.patch(
            self.url, {"reminder_schedule_days": [30, 0, 7]}, format="json"
        )
        self.assertEqual(reponse.json()["reminder_schedule_days"], [0, 7, 30])

    def test_REFUSE_un_palier_negatif(self):
        reponse = self.client.patch(
            self.url, {"reminder_schedule_days": [-1]}, format="json"
        )
        self.assertEqual(reponse.status_code, 400)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.reminder_schedule_days, [0, 7, 30])

    def test_REFUSE_une_liste_vide(self):
        reponse = self.client.patch(
            self.url, {"reminder_schedule_days": []}, format="json"
        )
        self.assertEqual(reponse.status_code, 400)

    def test_REFUSE_du_texte(self):
        reponse = self.client.patch(
            self.url, {"reminder_schedule_days": ["sept"]}, format="json"
        )
        self.assertEqual(reponse.status_code, 400)
