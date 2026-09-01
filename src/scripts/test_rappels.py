"""Les rappels de retard, et surtout ce qu'ils ne doivent JAMAIS faire.

Ces tests sont écrits au négatif à dessein. Un rappel qui part n'a rien de
remarquable ; un rappel qui part de travers ne se voit pas chez nous — il se
voit chez une personne qui n'est pas notre cliente, au nom d'une bibliothèque
qui n'a rien demandé. Et il n'y a pas de rattrapage : un courriel envoyé est
envoyé.

Les sept garanties, toutes négatives :

  * rien tant que l'organisation ne l'a pas ACTIVÉ ;
  * rien aux membres d'une AUTRE organisation ;
  * jamais deux fois le même rappel, même relancé le même jour ;
  * rien sur un prêt déjà rendu ;
  * rien à un membre archivé, rien à un membre sans adresse ;
  * rien avant l'échéance ;
  * rien du tout en `--dry-run`.
"""
import datetime
from io import StringIO
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils.timezone import now

from src.accounts.models import Organization
from src.customers.models import Customer
from src.helpers.tests import (
    create_admin_user, create_organization, create_subscription, create_user,
)
from src.items.models import (
    CLIENT,
    LIBRAIRE,
    Book,
    Lending,
    LendingReminder,
    LibrarianDigest,
)
from src.items.templatetags.dates_fr import date_fr
from src.items.reminders import (
    envoyer_le_recapitulatif,
    envoyer_les_rappels,
    normaliser_langue,
)

ENVOI = "src.items.reminders.envoyer_un_rappel"
RECAP = "src.items.reminders.envoyer_un_recapitulatif"


class NormaliserLangueTests(SimpleTestCase):
    """Le champ est une chaîne libre, saisie à la main, depuis le début."""

    def test_reconnait_l_anglais_sous_toutes_ses_formes(self):
        for valeur in ("en", "EN", "en-CA", "en_US", " English ", "english"):
            self.assertEqual(normaliser_langue(valeur), "en", repr(valeur))

    def test_tout_le_reste_retombe_sur_le_francais(self):
        """Le défaut doit être le moins surprenant : la base est québécoise."""
        for valeur in (None, "", "fr", "FR", "fr-CA", "français", "espagnol", "?"):
            self.assertEqual(normaliser_langue(valeur), "fr", repr(valeur))


class DateFrTests(SimpleTestCase):
    """⛔ « 1 septembre » n'est pas du français.

    L'écart ne se voit qu'un jour sur trente — mais ce jour-là il se voit dans
    chaque courriel envoyé à chaque membre de chaque bibliothèque.
    """

    def test_le_premier_du_mois_prend_son_ordinal(self):
        self.assertEqual(date_fr(datetime.date(2026, 9, 1)), "1er septembre 2026")

    def test_les_autres_jours_n_en_prennent_pas(self):
        self.assertEqual(date_fr(datetime.date(2026, 8, 20)), "20 août 2026")
        self.assertEqual(date_fr(datetime.date(2026, 7, 31)), "31 juillet 2026")

    def test_une_date_absente_ne_fait_pas_tomber_le_courriel(self):
        self.assertEqual(date_fr(None), "")


class RappelsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.organization = create_organization(owner=cls.user)
        # ⚠️ Un envoi demande un abonnement actif depuis le 01/09/2026 :
        # sans cette ligne, tous ces tests décrivent une bibliothèque qui ne
        # recevrait rien, et ils passeraient pour la mauvaise raison.
        create_subscription(organization=cls.organization, active=True)
        cls.organization.member_reminders_enabled = True
        cls.organization.member_reminder_frequency_days = 7
        cls.organization.save()

        # Créée APRÈS, et elle AUSSI activée : une requête non cloisonnée
        # tomberait sinon sur la bonne organisation par hasard, ou serait
        # arrêtée par le mauvais motif, et le test passerait quand même.
        cls.voisine = create_organization(owner=create_admin_user())
        # ⚠️ Un envoi demande un abonnement actif depuis le 01/09/2026 :
        # sans cette ligne, tous ces tests décrivent une bibliothèque qui ne
        # recevrait rien, et ils passeraient pour la mauvaise raison.
        create_subscription(organization=cls.voisine, active=True)
        cls.voisine.name = "Bibliotheque voisine"
        cls.voisine.member_reminders_enabled = True
        cls.voisine.save()

    def setUp(self):
        mail.outbox = []

    # ── Fabriques ────────────────────────────────────────────────────────

    def membre(self, organization=None, prenom="Jeanne", langue="fr", **champs):
        return Customer.objects.create(
            organization=organization or self.organization,
            first_name=prenom,
            last_name="Tremblay",
            email=champs.pop("email", f"{prenom.lower()}@exemple.test"),
            language=langue,
            **champs,
        )

    def pret(self, customer, titre="Kukum", retard_jours=10, organization=None, **champs):
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

    # ── Ce que la commande doit faire ────────────────────────────────────

    def test_envoie_un_rappel_pour_un_pret_en_retard(self):
        membre = self.membre()
        self.pret(membre)
        self.lancer()

        self.assertEqual(len(mail.outbox), 1)
        courriel = mail.outbox[0]
        self.assertEqual(courriel.to, ["jeanne@exemple.test"])
        self.assertIn("Kukum", courriel.body)
        self.assertEqual(LendingReminder.objects.count(), 1)

    def test_un_membre_en_retard_sur_TROIS_livres_recoit_UN_courriel(self):
        """Trois courriels pour trois livres, c'est ainsi qu'on se fait
        marquer comme indésirable — par le membre, puis par son fournisseur,
        et la réputation d'envoi est commune à toutes les bibliothèques."""
        membre = self.membre()
        for titre in ("Kukum", "Maus", "Nikolski"):
            self.pret(membre, titre=titre)
        self.lancer()

        self.assertEqual(len(mail.outbox), 1)
        for titre in ("Kukum", "Maus", "Nikolski"):
            self.assertIn(titre, mail.outbox[0].body)
        # La trace, elle, est par prêt : sans ça, rendre un seul des trois
        # livres rouvrirait l'envoi pour les deux autres.
        self.assertEqual(LendingReminder.objects.count(), 3)

    def test_ecrit_dans_la_langue_du_MEMBRE_et_pas_dans_celle_de_l_organisation(self):
        """🔴 Une Alliance Française tient sa collection en français et prête
        à des gens qui apprennent tout juste cette langue-là."""
        francophone = self.membre(prenom="Jeanne", langue="fr")
        anglophone = self.membre(prenom="Mary", langue="en")
        self.pret(francophone)
        self.pret(anglophone)
        self.lancer()

        par_adresse = {courriel.to[0]: courriel for courriel in mail.outbox}
        self.assertIn("Rappel", par_adresse["jeanne@exemple.test"].subject)
        self.assertIn("Bonjour", par_adresse["jeanne@exemple.test"].body)
        self.assertIn("Reminder", par_adresse["mary@exemple.test"].subject)
        self.assertIn("Hello", par_adresse["mary@exemple.test"].body)
        # ⛔ Et surtout pas l'inverse : un mutant qui prendrait la langue de
        # l'organisation enverrait les deux dans la même.
        self.assertNotIn("Bonjour", par_adresse["mary@exemple.test"].body)

    def test_la_DATE_aussi_est_dans_la_langue_du_membre(self):
        """⛔ Le défaut qu'on ne voit qu'en ouvrant le courriel.

        Le filtre `date` formate selon la langue ACTIVE, pas selon le fichier
        de gabarit. Le produit tourne en `fr-fr` : le gabarit anglais partait
        donc avec « due on août 18, 2026 ». La phrase en anglais, le mois en
        français.
        """
        anglophone = self.membre(prenom="Mary", langue="en")
        pret = self.pret(anglophone)
        self.lancer()

        mois_anglais = pret.due_at.strftime("%B")  # « August », « March »…
        self.assertIn(mois_anglais, mail.outbox[0].body)

    def test_n_envoie_RIEN_quand_l_organisation_n_a_PAS_active_les_rappels(self):
        """🔴 La garde la plus chère du lot.

        Dix-sept organisations sont en production, avec des prêts en retard
        depuis des mois, et pas une de leurs membres n'a jamais reçu un
        courriel de La Bibli. Une première exécution sans cette garde en
        enverrait des centaines, d'un coup, au nom de bibliothèques qui n'ont
        rien demandé.
        """
        self.organization.member_reminders_enabled = False
        self.organization.save()
        membre = self.membre()
        self.pret(membre)

        sortie = self.lancer()
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(LendingReminder.objects.count(), 0)
        # La voisine, elle, est activée : la commande tourne bel et bien.
        # C'est CETTE organisation-ci qui ne doit pas y figurer.
        self.assertNotIn(f"(id {self.organization.id})", sortie)
        self.assertIn("Bibliotheque voisine", sortie)

    def test_NOMMER_une_organisation_ne_l_active_pas(self):
        """`--organization` est un filtre, pas un interrupteur.

        Sans ça, la commande deviendrait le moyen d'écrire aux membres d'une
        bibliothèque sans son accord — depuis un shell de production, un
        soir, sans que personne ne le sache.
        """
        self.organization.member_reminders_enabled = False
        self.organization.save()
        membre = self.membre()
        self.pret(membre)

        self.lancer(organization=self.organization.id)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(LendingReminder.objects.count(), 0)

    def test_n_ecrit_JAMAIS_au_membre_d_une_AUTRE_organisation(self):
        """🔴 La pire panne que ce produit puisse produire.

        Le membre de la bibliothèque voisine recevrait, au nom d'une
        bibliothèque où il n'est pas inscrit, la liste des livres qu'il a
        empruntés ailleurs. Aucune erreur ne serait levée : la requête est
        valide, elle est juste fausse.
        """
        voisin = self.membre(organization=self.voisine, prenom="Amir")
        self.pret(voisin, titre="Le voisin", organization=self.voisine)
        chez_nous = self.membre()
        self.pret(chez_nous)

        self.lancer(organization=self.organization.id)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["jeanne@exemple.test"])
        self.assertNotIn("Le voisin", mail.outbox[0].body)
        self.assertEqual(
            list(LendingReminder.objects.values_list("organization_id", flat=True)),
            [self.organization.id],
        )

    def test_n_envoie_PAS_DEUX_FOIS_le_meme_rappel_le_meme_jour(self):
        """🔴 La commande tourne toutes les nuits, et se relance à la main.

        Un prêt en retard depuis six mois vaudrait cent quatre-vingts
        courriels identiques.
        """
        membre = self.membre()
        self.pret(membre)
        self.lancer()
        self.lancer()
        self.lancer()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(LendingReminder.objects.count(), 1)

    def test_n_envoie_RIEN_sur_un_pret_DEJA_RENDU(self):
        """Le livre est revenu au comptoir. Le réclamer est la façon la plus
        sûre de faire douter une bibliothèque de son propre outil."""
        membre = self.membre()
        self.pret(membre, returned_at=now() - datetime.timedelta(days=1))

        self.lancer()
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(LendingReminder.objects.count(), 0)

    def test_n_envoie_RIEN_a_un_membre_ARCHIVE(self):
        """Archiver un membre, c'est le sortir de la circulation. Continuer à
        lui écrire est exactement ce que le geste voulait empêcher."""
        membre = self.membre(archived=True)
        self.pret(membre)

        self.lancer()
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(LendingReminder.objects.count(), 0)

    def test_n_envoie_RIEN_a_un_membre_SANS_ADRESSE(self):
        """Une liste de membres réelle comporte toujours des personnes sans
        courriel : `email` est « blank=True, null=True » dans le modèle.

        Les deux formes du vide comptent — `None` ET la chaîne vide — parce
        que le formulaire produit l'une et l'import produit l'autre.
        """
        sans_adresse = self.membre(prenom="Paul", email=None)
        adresse_vide = self.membre(prenom="Yves", email="")
        self.pret(sans_adresse)
        self.pret(adresse_vide)

        self.lancer()
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(LendingReminder.objects.count(), 0)

    def test_n_envoie_RIEN_avant_l_echeance(self):
        """C'est un rappel de RETARD. Écrire la veille du retour à quelqu'un
        qui n'a rien fait de mal transforme un service en harcèlement."""
        membre = self.membre()
        self.pret(membre, retard_jours=-5)  # échéance dans cinq jours

        self.lancer()
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(LendingReminder.objects.count(), 0)

    def test_n_envoie_RIEN_pour_une_organisation_DESACTIVEE(self):
        membre = self.membre()
        self.pret(membre)
        self.organization.is_active = False
        self.organization.save()

        self.lancer()
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(LendingReminder.objects.count(), 0)

    def test_A_BLANC_n_envoie_rien_et_n_ecrit_rien(self):
        """Le contrôle qu'on passe avant d'activer une bibliothèque : il doit
        pouvoir se lancer sur la production sans aucune conséquence."""
        membre = self.membre()
        self.pret(membre)

        sortie = self.lancer(dry_run=True)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(LendingReminder.objects.count(), 0)
        # Et il doit quand même DIRE ce qu'il ferait, sinon il ne sert à rien.
        self.assertIn("jeanne@exemple.test", sortie)
        self.assertIn("rien n'a été envoyé", sortie)

    def test_ne_met_PERSONNE_en_copie_cachee(self):
        """⛔ `authemail` copie `EMAIL_BCC` sur tous ses courriels.

        Reprendre ce réflexe ici copierait à Aynils l'adresse de chaque membre
        de chaque bibliothèque, à chaque rappel : une fuite de données
        personnelles, et un envoi de masse vers une seule boîte.
        """
        membre = self.membre()
        self.pret(membre)
        self.lancer()

        self.assertEqual(mail.outbox[0].bcc, [])
        self.assertEqual(mail.outbox[0].cc, [])
        self.assertEqual(mail.outbox[0].recipients(), ["jeanne@exemple.test"])

    def test_un_ECHEC_d_envoi_ne_laisse_AUCUNE_trace(self):
        """Sinon le rappel serait compté comme envoyé et ne repartirait
        jamais : le membre n'entendrait plus parler de son retard, et la
        bibliothèque croirait l'avoir prévenu."""
        membre = self.membre()
        self.pret(membre)

        with patch(ENVOI, side_effect=RuntimeError("SMTP indisponible")):
            sortie = self.lancer()

        self.assertEqual(LendingReminder.objects.count(), 0)
        self.assertIn("SMTP indisponible", sortie)

        # Et au passage suivant, il repart.
        self.lancer()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(LendingReminder.objects.count(), 1)


class ReglagesParOrganisationTests(TestCase):
    """Les deux réglages, et leur défaut — qui est la garde elle-même."""

    def test_les_DEUX_envois_sont_ETEINTS_a_la_creation(self):
        """🔴 Le défaut EST la protection des dix-sept organisations déjà en
        production. Retourner l'un OU l'autre suffirait à tout envoyer."""
        organization = Organization.objects.create(
            name="Bibliothèque neuve", owner=create_user()
        )
        self.assertFalse(organization.member_reminders_enabled)
        self.assertFalse(organization.librarian_digest_enabled)
        self.assertEqual(organization.reminder_schedule_days, [0, 7, 30])


class ModuleDEnvoiTests(TestCase):
    """`envoyer_les_rappels` appelé DIRECTEMENT, sans passer par la commande.

    🔑 Pourquoi ces deux tests existent : la commande filtre déjà les
    organisations activées, si bien que les mêmes gardes, dans le module, ne
    sont jamais atteintes depuis elle. Une épreuve par mutation l'a montré —
    on pouvait les retirer toutes les deux et la suite restait verte.

    Or le module est le point d'entrée réutilisable : le jour où un bouton
    « envoyer les rappels maintenant » apparaît dans l'interface, ou une tâche
    déclenchée par un webhook, c'est LUI qui sera appelé, pas la commande. Une
    garde qui n'existe qu'en amont ne protège que le chemin d'aujourd'hui.
    """

    @classmethod
    def setUpTestData(cls):
        cls.organization = create_organization(owner=create_user())
        # ⚠️ Un envoi demande un abonnement actif depuis le 01/09/2026 :
        # sans cette ligne, tous ces tests décrivent une bibliothèque qui ne
        # recevrait rien, et ils passeraient pour la mauvaise raison.
        create_subscription(organization=cls.organization, active=True)

    def setUp(self):
        mail.outbox = []
        self.membre = Customer.objects.create(
            organization=self.organization,
            first_name="Jeanne",
            last_name="Tremblay",
            email="jeanne@exemple.test",
            language="fr",
        )
        book = Book.objects.create(
            organization=self.organization, title="Kukum", author="Michel Jean"
        )
        Lending.objects.create(
            organization=self.organization,
            customer=self.membre,
            book=book,
            allowance_days=31,
            lent_at=now() - datetime.timedelta(days=41),
        )

    def test_refuse_d_ecrire_pour_une_organisation_qui_n_a_PAS_active(self):
        self.organization.member_reminders_enabled = False
        self.organization.save()

        rapport = envoyer_les_rappels(self.organization)

        self.assertTrue(rapport.desactive)
        self.assertEqual(rapport.prevus, [])
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(LendingReminder.objects.count(), 0)

    def test_refuse_d_ecrire_pour_une_organisation_DESACTIVEE(self):
        self.organization.member_reminders_enabled = True
        self.organization.is_active = False
        self.organization.save()

        rapport = envoyer_les_rappels(self.organization)

        self.assertTrue(rapport.inactive)
        self.assertEqual(rapport.prevus, [])
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(LendingReminder.objects.count(), 0)


class RecapitulatifTests(TestCase):
    """Le récapitulatif à la bibliothécaire — celui que promet la page d'accueil.

    ⚠️ Le décor est monté à l'envers du bon sens, exprès : les rappels aux
    MEMBRES sont ÉTEINTS et seul le récapitulatif est allumé. C'est la
    configuration qui prouve que les deux interrupteurs sont indépendants — et
    c'est aussi la configuration réelle du premier jour d'une bibliothèque qui
    veut voir ses retards avant d'oser écrire à qui que ce soit.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.organization = create_organization(owner=cls.user)
        # ⚠️ Un envoi demande un abonnement actif depuis le 01/09/2026 :
        # sans cette ligne, tous ces tests décrivent une bibliothèque qui ne
        # recevrait rien, et ils passeraient pour la mauvaise raison.
        create_subscription(organization=cls.organization, active=True)
        cls.organization.librarian_digest_enabled = True
        cls.organization.member_reminders_enabled = False
        cls.organization.save()

        # Créée APRÈS, et elle aussi activée : une requête non cloisonnée
        # tomberait sinon sur la bonne organisation par hasard.
        cls.voisine = create_organization(owner=create_admin_user())
        # ⚠️ Un envoi demande un abonnement actif depuis le 01/09/2026 :
        # sans cette ligne, tous ces tests décrivent une bibliothèque qui ne
        # recevrait rien, et ils passeraient pour la mauvaise raison.
        create_subscription(organization=cls.voisine, active=True)
        cls.voisine.name = "Bibliotheque voisine"
        cls.voisine.librarian_digest_enabled = True
        cls.voisine.save()

    def setUp(self):
        mail.outbox = []

    # ── Fabriques ────────────────────────────────────────────────────────

    def membre(self, organization=None, prenom="Jeanne", **champs):
        return Customer.objects.create(
            organization=organization or self.organization,
            first_name=prenom,
            last_name="Tremblay",
            email=champs.pop("email", f"{prenom.lower()}@exemple.test"),
            language=champs.pop("langue", "fr"),
            **champs,
        )

    def pret(self, customer, titre="Kukum", retard_jours=10, organization=None, **champs):
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

    def recapitulatifs(self):
        return [m for m in mail.outbox if m.to == [self.user.email]]

    # ── Ce qu'il doit faire ──────────────────────────────────────────────

    def test_envoie_UN_seul_courriel_a_la_bibliothecaire(self):
        """Un courriel par passage, pas un par prêt : c'est un état, pas une
        pile de notifications."""
        membre = self.membre()
        for titre in ("Kukum", "Maus", "Nikolski"):
            self.pret(membre, titre=titre)
        autre = self.membre(prenom="Amir")
        self.pret(autre, titre="Nikolski II")

        self.lancer()

        self.assertEqual(len(self.recapitulatifs()), 1)
        courriel = self.recapitulatifs()[0]
        for titre in ("Kukum", "Maus", "Nikolski", "Nikolski II"):
            self.assertIn(titre, courriel.body)
        self.assertIn("Jeanne Tremblay", courriel.body)
        self.assertIn("Amir Tremblay", courriel.body)
        self.assertEqual(LibrarianDigest.objects.count(), 1)
        self.assertEqual(LibrarianDigest.objects.get().lendings_count, 4)

    def test_classe_le_PLUS_EN_RETARD_en_premier(self):
        """C'est une liste de tâches, pas un journal : elle en lit trois
        lignes et elle agit. Rendu dans l'ordre de la requête, le retard de
        quarante jours se retrouvait coincé entre deux retards de trois."""
        membre = self.membre()
        self.pret(membre, titre="Recent", retard_jours=3)
        self.pret(membre, titre="Ancien", retard_jours=41)
        self.pret(membre, titre="Moyen", retard_jours=12)

        self.lancer()

        corps = self.recapitulatifs()[0].body
        self.assertLess(corps.index("Ancien"), corps.index("Moyen"))
        self.assertLess(corps.index("Moyen"), corps.index("Recent"))

    def test_INCLUT_les_membres_que_le_rappel_automatique_n_atteint_PAS(self):
        """🔑 C'est la valeur du récapitulatif, pas un détail.

        Un membre archivé et un membre sans adresse ont eux aussi un livre qui
        n'est pas revenu. Ce sont précisément les seuls que rien d'automatique
        ne relancera : les cacher à la bibliothécaire lui ferait croire que
        tout est pris en charge.
        """
        self.organization.member_reminders_enabled = True
        self.organization.save()
        joignable = self.membre(prenom="Jeanne")
        archive = self.membre(prenom="Paul", archived=True)
        sans_adresse = self.membre(prenom="Yves", email=None)
        self.pret(joignable, titre="Kukum")
        self.pret(archive, titre="Maus")
        self.pret(sans_adresse, titre="Nikolski")

        self.lancer()

        recap = self.recapitulatifs()[0].body
        for titre in ("Kukum", "Maus", "Nikolski"):
            self.assertIn(titre, recap)
        self.assertIn("fiche archivée", recap)
        self.assertIn("aucune adresse courriel", recap)
        # ⛔ Et ces deux-là n'ont évidemment reçu aucun rappel, eux.
        self.assertEqual(
            sorted(m.to[0] for m in mail.outbox if m.to != [self.user.email]),
            ["jeanne@exemple.test"],
        )

    def test_DIT_LIGNE_PAR_LIGNE_si_le_membre_a_ete_prevenu(self):
        """Sans ça, la bibliothécaire attend un retour que personne n'a demandé.

        ⚠️ L'information est lue dans la TRACE, pas déduite du commutateur :
        même rappels allumés, la personne sans adresse n'a rien reçu.
        """
        self.organization.member_reminders_enabled = True
        self.organization.save()
        self.pret(self.membre(prenom="Jeanne"), titre="Kukum")
        self.pret(self.membre(prenom="Yves", email=None), titre="Nikolski")

        self.lancer()

        corps = self.recapitulatifs()[0].body
        ligne_jeanne = corps[corps.index("Kukum"):corps.index("Nikolski")]
        ligne_yves = corps[corps.index("Nikolski"):]
        # ⚠️ « à la personne » et « prévenue » : le texte est en écriture
        # inclusive depuis le 01/09/2026, et ce test le tient. Un libellé qui
        # repart au masculin fera rougir ici — c'est le seul endroit du dépôt
        # qui empêche la régression, l'œil ayant déjà laissé passer trois fois.
        self.assertIn("rappel envoyé à la personne", ligne_jeanne)
        self.assertIn("n'a PAS été prévenue", ligne_yves)
        self.assertIn("aucune adresse courriel", ligne_yves)

    def test_DIT_que_les_rappels_aux_membres_sont_ETEINTS(self):
        """Douze relances se lisent comme un reproche quand on ignore que
        personne n'a été relancé — et elle ne peut pas le deviner."""
        self.assertFalse(self.organization.member_reminders_enabled)
        self.pret(self.membre())

        self.lancer()

        corps = self.recapitulatifs()[0].body
        self.assertIn("n'a PAS été prévenu", corps)
        self.assertIn("rappels aux membres désactivés", corps)

    def test_une_organisation_qui_n_a_QUE_le_recapitulatif_est_balayee(self):
        """⚠️ Le `OR` de la sélection.

        Avec un `AND`, une bibliothèque qui n'aurait allumé que le
        récapitulatif serait écartée sans que rien ne le dise : elle coche la
        case, elle ne reçoit rien, et le seul symptôme est un silence.
        """
        self.assertFalse(self.organization.member_reminders_enabled)
        self.pret(self.membre())

        self.lancer()
        self.assertEqual(len(self.recapitulatifs()), 1)

    # ── ⛔ L'indépendance des deux interrupteurs ─────────────────────────

    def test_l_interrupteur_des_MEMBRES_ne_commande_PAS_celui_de_la_bibliothecaire(self):
        """🔴 Le mutant à écrire en premier.

        Confondre les deux ferait partir un envoi que personne n'a demandé,
        au motif qu'un AUTRE envoi, lui, a été autorisé.
        """
        self.organization.member_reminders_enabled = False
        self.organization.librarian_digest_enabled = True
        self.organization.save()
        self.pret(self.membre())

        self.lancer()

        self.assertEqual(len(self.recapitulatifs()), 1)
        # Aucun courriel à un membre.
        self.assertEqual([m for m in mail.outbox if m.to != [self.user.email]], [])
        # ⚠️ `recipient=CLIENT` : depuis les paliers, la même table porte AUSSI
        # l'histoire de la bibliothécaire, qui, elle, doit bien exister.
        self.assertEqual(LendingReminder.objects.filter(recipient=CLIENT).count(), 0)

    def test_l_interrupteur_de_la_BIBLIOTHECAIRE_ne_commande_PAS_celui_des_membres(self):
        """🔴 Le symétrique, et il compte autant.

        Une bibliothèque qui coupe son récapitulatif — parce qu'elle en a
        assez de le recevoir — ne doit pas couper du même geste, et sans le
        savoir, les rappels que ses membres attendent.
        """
        self.organization.member_reminders_enabled = True
        self.organization.librarian_digest_enabled = False
        self.organization.save()
        self.pret(self.membre())

        self.lancer()

        self.assertEqual(self.recapitulatifs(), [])
        self.assertEqual(LibrarianDigest.objects.count(), 0)
        self.assertEqual(
            [m.to for m in mail.outbox if m.to != [self.user.email]],
            [["jeanne@exemple.test"]],
        )
        self.assertEqual(LendingReminder.objects.filter(recipient=CLIENT).count(), 1)
        self.assertEqual(LendingReminder.objects.filter(recipient=LIBRAIRE).count(), 0)

    # ── ⛔ Ce qu'il ne doit JAMAIS faire ─────────────────────────────────

    def test_ne_met_JAMAIS_le_pret_d_une_AUTRE_bibliotheque_dans_le_recapitulatif(self):
        """🔴 Le récapitulatif porte le NOM et l'ADRESSE de chaque membre en
        retard. C'est la pièce la plus sensible que ce produit envoie : une
        ligne de trop, et une bibliothèque lit le fichier des membres d'une
        autre."""
        voisin = self.membre(organization=self.voisine, prenom="Amir")
        self.pret(voisin, titre="Le livre du voisin", organization=self.voisine)
        self.pret(self.membre(), titre="Kukum")

        self.lancer(organization=self.organization.id)

        self.assertEqual(len(self.recapitulatifs()), 1)
        corps = self.recapitulatifs()[0].body
        self.assertIn("Kukum", corps)
        self.assertNotIn("Le livre du voisin", corps)
        self.assertNotIn("Amir", corps)
        self.assertEqual(
            list(LibrarianDigest.objects.values_list("organization_id", flat=True)),
            [self.organization.id],
        )

    def test_n_envoie_RIEN_quand_il_n_y_a_AUCUN_retard(self):
        """Un récapitulatif vide est un courriel de plus dans une boîte déjà
        pleine — c'est ainsi qu'on apprend aux gens à ne plus nous lire."""
        self.membre()
        sortie = self.lancer()

        self.assertEqual(self.recapitulatifs(), [])
        self.assertEqual(LibrarianDigest.objects.count(), 0)
        self.assertIn("aucune relance due aujourd'hui", sortie)

    def test_n_envoie_PAS_DEUX_FOIS_le_recapitulatif_le_meme_jour(self):
        """🔴 Le matin où le déploiement de 8 h échoue et où on rejoue la
        commande à 8 h 10.

        ⚠️ Ce n'est plus une garde « un par jour » qui l'empêche — elle a
        été retirée le 01/09/2026 parce qu'elle taisait des relances
        légitimes. C'est l'histoire des paliers : les relances de ce matin
        sont tracées, donc au second passage il n'en reste aucune de neuve.

        Et il ne suffit pas de compter les courriels : le chemin doit être
        PROPRE. Un journal qui crie au loup tous les matins est un journal
        qu'on cesse de lire, et c'est dedans que la vraie panne SMTP se
        cachera.
        """
        self.pret(self.membre())
        self.lancer()
        seconde = self.lancer()
        troisieme = self.lancer()

        self.assertEqual(len(self.recapitulatifs()), 1)
        self.assertEqual(LibrarianDigest.objects.count(), 1)
        for sortie in (seconde, troisieme):
            self.assertIn("aucune relance due aujourd'hui", sortie)
            self.assertNotIn("❌", sortie)

    def test_n_inscrit_RIEN_pour_un_pret_deja_rendu(self):
        membre = self.membre()
        self.pret(membre, titre="Kukum", returned_at=now() - datetime.timedelta(days=1))
        self.pret(membre, titre="Maus")

        self.lancer()

        corps = self.recapitulatifs()[0].body
        self.assertIn("Maus", corps)
        self.assertNotIn("Kukum", corps)
        self.assertEqual(LibrarianDigest.objects.get().lendings_count, 1)

    def test_n_inscrit_RIEN_avant_l_echeance(self):
        membre = self.membre()
        self.pret(membre, titre="Kukum", retard_jours=-5)
        self.pret(membre, titre="Maus")

        self.lancer()

        corps = self.recapitulatifs()[0].body
        self.assertIn("Maus", corps)
        self.assertNotIn("Kukum", corps)

    def test_n_envoie_RIEN_quand_la_bibliothecaire_n_a_PAS_d_adresse(self):
        self.user.email = ""
        self.user.save()
        self.pret(self.membre())

        sortie = self.lancer()

        self.assertEqual(mail.outbox, [])
        self.assertEqual(LibrarianDigest.objects.count(), 0)
        self.assertIn("aucune adresse de destinataire", sortie)

    def test_A_BLANC_n_envoie_rien_et_n_ecrit_rien(self):
        self.pret(self.membre())
        sortie = self.lancer(dry_run=True)

        self.assertEqual(mail.outbox, [])
        self.assertEqual(LibrarianDigest.objects.count(), 0)
        self.assertIn(self.user.email, sortie)
        self.assertIn("rien n'a été envoyé", sortie)

    def test_ne_met_PERSONNE_en_copie_cachee(self):
        """⛔ Le récapitulatif liste les membres nommément. Une copie cachée
        chez Aynils serait une fuite de données personnelles."""
        self.pret(self.membre())
        self.lancer()

        courriel = self.recapitulatifs()[0]
        self.assertEqual(courriel.bcc, [])
        self.assertEqual(courriel.cc, [])
        self.assertEqual(courriel.recipients(), [self.user.email])

    def test_un_ECHEC_d_envoi_ne_laisse_AUCUNE_trace(self):
        """Sinon la journée serait comptée comme faite et le récapitulatif
        ne repartirait pas — la bibliothécaire ne saurait jamais qu'il
        manque."""
        self.pret(self.membre())

        with patch(RECAP, side_effect=RuntimeError("SMTP indisponible")):
            sortie = self.lancer()

        self.assertEqual(LibrarianDigest.objects.count(), 0)
        self.assertIn("SMTP indisponible", sortie)

        self.lancer()
        self.assertEqual(len(self.recapitulatifs()), 1)
        self.assertEqual(LibrarianDigest.objects.count(), 1)


class ModuleDuRecapitulatifTests(TestCase):
    """`envoyer_le_recapitulatif` appelé DIRECTEMENT, sans la commande.

    Même raison que pour `ModuleDEnvoiTests` : la commande filtre déjà les
    organisations, si bien que les gardes du module ne sont jamais atteintes
    depuis elle. C'est pourtant lui qu'un bouton « envoyer maintenant »
    appellera.
    """

    @classmethod
    def setUpTestData(cls):
        cls.organization = create_organization(owner=create_user())
        # ⚠️ Un envoi demande un abonnement actif depuis le 01/09/2026 :
        # sans cette ligne, tous ces tests décrivent une bibliothèque qui ne
        # recevrait rien, et ils passeraient pour la mauvaise raison.
        create_subscription(organization=cls.organization, active=True)

    def setUp(self):
        mail.outbox = []
        membre = Customer.objects.create(
            organization=self.organization,
            first_name="Jeanne",
            last_name="Tremblay",
            email="jeanne@exemple.test",
        )
        book = Book.objects.create(
            organization=self.organization, title="Kukum", author="Michel Jean"
        )
        Lending.objects.create(
            organization=self.organization,
            customer=membre,
            book=book,
            allowance_days=31,
            lent_at=now() - datetime.timedelta(days=41),
        )

    def test_refuse_quand_le_recapitulatif_n_est_PAS_active(self):
        self.organization.librarian_digest_enabled = False
        # ⚠️ Et l'autre interrupteur est allumé : s'il commandait celui-ci,
        # le courriel partirait quand même.
        self.organization.member_reminders_enabled = True
        self.organization.save()

        rapport = envoyer_le_recapitulatif(self.organization)

        self.assertTrue(rapport.desactive)
        self.assertEqual(mail.outbox, [])
        self.assertEqual(LibrarianDigest.objects.count(), 0)

    def test_refuse_pour_une_organisation_DESACTIVEE(self):
        self.organization.librarian_digest_enabled = True
        self.organization.is_active = False
        self.organization.save()

        rapport = envoyer_le_recapitulatif(self.organization)

        self.assertTrue(rapport.inactive)
        self.assertEqual(mail.outbox, [])
        self.assertEqual(LibrarianDigest.objects.count(), 0)


class AbonnementTests(TestCase):
    """🔴 Rien ne part sans abonnement actif — décidé le 01/09/2026.

    ⚠️ Cette garde ne peut RIEN attraper aujourd'hui : l'enregistrement d'un
    prêt est déjà derrière l'abonnement, donc une bibliothèque qui ne paie pas
    n'a aucun prêt, donc aucun retard. Mesuré en production : 21 organisations
    sans abonnement actif, zéro prêt en cours entre elles toutes.

    Elle existe pour le cas qui viendra : une bibliothèque qui a PAYÉ, créé ses
    prêts, puis résilié. Ses prêts restent en base — on n'efface pas
    l'historique de quelqu'un qui part — et sans elle La Bibli continuerait
    d'écrire à ses membres en son nom, indéfiniment.
    """

    @classmethod
    def setUpTestData(cls):
        cls.organization = create_organization(owner=create_user())
        cls.organization.member_reminders_enabled = True
        cls.organization.librarian_digest_enabled = True
        cls.organization.save()
        cls.abonnement = create_subscription(organization=cls.organization, active=True)

    def un_retard(self):
        livre = Book.objects.create(
            organization=self.organization, title="Kukum", author="Michel Jean"
        )
        membre = Customer.objects.create(
            organization=self.organization, first_name="Claire",
            last_name="Dubois", email="claire@exemple.test",
        )
        # ⚠️ `due_at` est CALCULÉ — `lent_at + allowance_days` — et n'a pas de
        # setter. Un retard se fabrique en reculant la date de prêt, pas en
        # posant l'échéance.
        return Lending.objects.create(
            organization=self.organization, book=livre, customer=membre,
            allowance_days=31,
            lent_at=now() - datetime.timedelta(days=31 + 10),
        )

    def test_le_RAPPEL_ne_part_pas_apres_une_resiliation(self):
        self.un_retard()
        self.abonnement.active = False
        self.abonnement.save()

        rapport = envoyer_les_rappels(self.organization)

        self.assertTrue(rapport.sans_abonnement)
        self.assertEqual(rapport.envoyes, 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_le_RECAPITULATIF_ne_part_pas_apres_une_resiliation(self):
        self.un_retard()
        self.abonnement.active = False
        self.abonnement.save()

        rapport = envoyer_le_recapitulatif(self.organization)

        self.assertTrue(rapport.sans_abonnement)
        self.assertFalse(rapport.envoye)
        self.assertEqual(len(mail.outbox), 0)

    def test_avec_un_abonnement_ACTIF_le_rappel_part(self):
        """Le pendant : sans lui, la garde pourrait tout bloquer sans qu'on le voie."""
        self.un_retard()

        rapport = envoyer_les_rappels(self.organization)

        self.assertFalse(rapport.sans_abonnement)
        self.assertEqual(rapport.envoyes, 1)

    def test_la_COMMANDE_ne_balaie_pas_une_organisation_resiliee(self):
        """La sélection filtre aussi : on ne parcourt pas ses prêts pour rien."""
        self.un_retard()
        self.abonnement.active = False
        self.abonnement.save()

        sortie = StringIO()
        call_command("rappels", stdout=sortie)

        self.assertEqual(len(mail.outbox), 0)
        self.assertIn("Aucune organisation", sortie.getvalue())
