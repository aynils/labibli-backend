"""Le réimport complète — et surtout, ce qu'il ne doit JAMAIS faire.

Ces tests sont écrits au négatif à dessein. Un import qui crée des fiches se
voit tout de suite ; un import qui en abîme ne se voit qu'au moment où une
bibliothécaire cherche quelque chose qu'elle avait saisi et ne le trouve plus,
des mois plus tard, sans savoir quand ni pourquoi.

Les trois garanties : ne rien écraser, ne rien retirer, ne pas sortir de
l'organisation.
"""
from unittest.mock import patch

from django.test import TestCase

from src.customers.customer_import import CustomerImporter
from src.customers.models import Customer
from src.helpers.tests import create_admin_user, create_organization, create_user
from src.imports.runner import run_import
from src.items.book_import import BookImporter
from src.items.models import Book, Category

TELECHARGEMENT = "src.items.book_import.download_image"


def ligne(**champs):
    """Une ligne de fichier : toutes les colonnes, vides par défaut."""
    base = {
        "isbn": None, "title": None, "author": None, "publisher": None,
        "published_year": None, "lang": None, "category": None,
        "cover_url": None, "description": None, "location": None, "archived": None,
    }
    base.update(champs)
    return base


class CompletionDesOuvragesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.organization = create_organization(owner=cls.user)
        # Créée APRÈS : une requête non cloisonnée tomberait sinon sur la
        # bonne organisation par hasard, et le test passerait quand même.
        cls.voisine = create_organization(owner=create_admin_user())

    def importer(self):
        # Ni résolution ni enrichissement : le complément ne doit se servir
        # que du fichier, et un test qui sort sur le réseau ne prouve rien.
        return BookImporter(resolve_isbn=False, enrich=False)

    def jouer(self, *lignes, **options):
        return run_import(
            records=list(lignes), importer=self.importer(),
            organization_id=self.organization.id, **options,
        )

    # ── Ce que le complément doit faire ─────────────────────────────────

    def test_comble_les_champs_vides_au_lieu_de_sauter_la_ligne(self):
        """🔑 Le défaut que ce chantier corrige.

        Avant le 01/09/2026 cette ligne partait en « doublon » et pas une
        seule des colonnes ajoutées au tableur n'entrait.
        """
        book = Book.objects.create(
            organization=self.organization, title="Kukum", author="Michel Jean",
        )
        report = self.jouer(ligne(
            title="Kukum", author="Michel Jean",
            publisher="Libre Expression", published_year="2019", location="R JEA",
        ))
        book.refresh_from_db()
        self.assertEqual(book.publisher, "Libre Expression")
        self.assertEqual(book.published_year, "2019")
        self.assertEqual(book.location, "R JEA")
        self.assertEqual(report.as_dict()["updated_count"], 1)
        self.assertEqual(report.as_dict()["duplicates_count"], 0)

    def test_complete_a_l_interieur_d_un_MEME_fichier(self):
        """Un inventaire tenu à la main répète ses fiches, en morceaux.

        87 lignes redondantes chez l'Alliance Française de Siem Reap. La
        seconde ligne doit achever la première, pas être jetée.
        """
        report = self.jouer(
            ligne(title="Kukum", author="Michel Jean", publisher="Libre Expression"),
            ligne(title="Kukum", author="Michel Jean", publisher="Libre Expression",
                  location="R JEA"),
        )
        book = Book.objects.get(organization=self.organization, title="Kukum")
        self.assertEqual(book.location, "R JEA")
        self.assertEqual(report.as_dict()["created_count"], 1)
        self.assertEqual(report.as_dict()["updated_count"], 1)

    def test_AJOUTE_une_categorie_sans_en_retirer(self):
        book = Book.objects.create(
            organization=self.organization, title="Kukum", author="Michel Jean",
        )
        rayon = Category.objects.create(organization=self.organization, name="Romans")
        book.categories.add(rayon)

        self.jouer(ligne(title="Kukum", author="Michel Jean", category="Récits"))
        book.refresh_from_db()
        # ⛔ « Romans » n'est pas dans le fichier et doit rester : un
        # rayonnage se range dans l'application, pas dans le tableur qui a
        # servi à la reprise il y a six mois.
        self.assertEqual(
            sorted(category.name for category in book.categories.all()),
            ["Romans", "Récits"],
        )

    # ── ⛔ Ce qu'il ne doit JAMAIS faire ────────────────────────────────

    def test_n_ECRASE_PAS_un_champ_deja_rempli_et_SIGNALE_l_ecart(self):
        """🔴 La règle qui rend le complément sûr par défaut.

        On ne sait pas si le fichier est une correction ou une vieille copie.
        Deviner à la place de la bibliothèque est exactement ce qui fait
        perdre du travail.
        """
        book = Book.objects.create(
            organization=self.organization, title="Kukum", author="Jean, Michel",
            isbn="9782764813447", publisher="Libre Expression",
        )
        report = self.jouer(ligne(
            isbn="9782764813447", title="Kukum", author="Jean, Michel",
            publisher="Libre Expression", description="Le résumé du fichier.",
        ))
        # La description était vide : elle se comble.
        book.refresh_from_db()
        self.assertEqual(book.description, "Le résumé du fichier.")
        self.assertEqual(report.as_dict()["discrepancies_count"], 0)

        # ⚠️ L'auteur corrigé ne se reconnaît QUE par l'ISBN : titre et auteur
        # forment l'identité de repli, donc une fiche sans ISBN dont l'auteur
        # change est, pour ce code, un autre ouvrage. C'est assumé — et c'est
        # pour ça que 90 % des fiches de production en portent un.
        report = self.jouer(ligne(
            isbn="9782764813447", title="Kukum", author="Michel Jean",
            publisher="Libre Expression",
        ))
        book.refresh_from_db()
        self.assertEqual(book.author, "Jean, Michel")
        ecarts = report.as_dict()["discrepancies"]
        self.assertEqual([e["field"] for e in ecarts], ["author"])
        self.assertEqual(ecarts[0]["existing"], "Jean, Michel")
        self.assertEqual(ecarts[0]["file"], "Michel Jean")

    @patch(TELECHARGEMENT, return_value=b"image")
    def test_n_ECRASE_PAS_une_couverture_deja_posee(self, telecharger):
        """🔴 La perte la plus visible qu'on puisse infliger.

        La fiche DOIT entrer dans le complément — il lui manque un résumé —
        sinon le test ne prouve rien : une fiche complète n'est jamais
        touchée, et c'est ainsi qu'un mutant a survécu sur `enrichir`.
        """
        book = Book.objects.create(
            organization=self.organization, title="Kukum", author="Michel Jean",
        )
        book.picture.name = "TEST-covers/la-photo-de-la-bibliotheque.jpg"
        book.save(update_fields=["picture"])

        self.jouer(ligne(
            title="Kukum", author="Michel Jean",
            description="Un résumé.", cover_url="https://exemple.test/autre.jpg",
        ))
        book.refresh_from_db()
        self.assertEqual(book.description, "Un résumé.")
        self.assertEqual(book.picture.name, "TEST-covers/la-photo-de-la-bibliotheque.jpg")
        # 🔑 La garde est AVANT le téléchargement, pas après.
        telecharger.assert_not_called()

    def test_ne_DESARCHIVE_pas_et_signale_l_ecart(self):
        """🔴 Un booléen est TOUJOURS rempli : il n'y a jamais de vide à combler.

        Désarchiver toute une collection parce qu'un tableur n'a pas la
        colonne « Archivé » serait la perte la plus spectaculaire que ce code
        puisse causer. Le fichier dit le contraire de la fiche : on le
        signale, on ne l'applique pas.
        """
        book = Book.objects.create(
            organization=self.organization, title="Kukum", author="Michel Jean",
            archived=True,
        )
        report = self.jouer(ligne(
            title="Kukum", author="Michel Jean", archived="Non",
            description="Un résumé.",
        ))
        book.refresh_from_db()
        self.assertTrue(book.archived)
        ecarts = [e for e in report.as_dict()["discrepancies"] if e["field"] == "archived"]
        self.assertEqual(len(ecarts), 1)
        self.assertEqual(ecarts[0]["existing"], True)
        self.assertEqual(ecarts[0]["file"], False)

    def test_refuse_de_completer_quand_l_ISBN_designe_un_AUTRE_ouvrage(self):
        """🔴 Six cas réels dans la seule collection de Siem Reap.

        La résolution par titre a donné à « Durandal 1 », « Durandal 2 » et
        « Durandal 3 » le MÊME ISBN, celui du tome 1. Tant que ces lignes
        étaient jetées, la donnée fausse dormait. Les compléter écrirait
        l'année du tome 2 sur le tome 1 — plausible, faux, et silencieux.
        """
        tome1 = Book.objects.create(
            organization=self.organization, title="Durandal 1 - La marche de Bretagne",
            author="Bec", isbn="9782302010864", published_year="2010",
        )
        report = self.jouer(ligne(
            isbn="9782302010864", title="Durandal 2 - La marche de Bretagne",
            author="Bec", published_year="2011", location="BD BEC",
        ))
        tome1.refresh_from_db()
        # ⛔ Le tome 1 n'a RIEN reçu du tome 2.
        self.assertEqual(tome1.published_year, "2010")
        self.assertIsNone(tome1.location)
        # Et la ligne n'a pas non plus créé de fiche : la contrainte
        # d'unicité (isbn, organisation, titre) rendrait une erreur brute.
        self.assertEqual(report.as_dict()["duplicates_count"], 1)
        self.assertEqual(report.as_dict()["created_count"], 0)
        ecarts = report.as_dict()["discrepancies"]
        self.assertEqual([e["field"] for e in ecarts], ["identité"])

    def test_un_fichier_d_ISBN_NUS_reste_accepte(self):
        """Le format de l'Alliance Française d'Ottawa : une colonne, des ISBN.

        Sans titre, il n'y a rien à comparer — refuser ces lignes rendrait la
        garde d'identité plus coûteuse que le défaut qu'elle évite.
        """
        book = Book.objects.create(
            organization=self.organization, title="Kukum", author="Michel Jean",
            isbn="9782764813447",
        )
        self.jouer(ligne(isbn="9782764813447", location="R JEA"))
        book.refresh_from_db()
        self.assertEqual(book.location, "R JEA")

    def test_ne_touche_PAS_a_la_collection_d_une_autre_organisation(self):
        """🔴 Le cloisonnement, sur un code qui ÉCRIT dans des fiches existantes."""
        voisin = Book.objects.create(
            organization=self.voisine, title="Kukum", author="Michel Jean",
        )
        report = self.jouer(ligne(
            title="Kukum", author="Michel Jean", publisher="Libre Expression",
        ))
        voisin.refresh_from_db()
        self.assertIsNone(voisin.publisher)
        # Et la ligne crée bien la fiche CHEZ NOUS au lieu d'aller compléter
        # celle de la voisine.
        self.assertEqual(report.as_dict()["created_count"], 1)
        self.assertEqual(
            Book.objects.filter(organization=self.organization).count(), 1
        )

    @patch(TELECHARGEMENT, return_value=b"image")
    def test_a_blanc_n_ecrit_RIEN(self, telecharger):
        book = Book.objects.create(
            organization=self.organization, title="Kukum", author="Michel Jean",
        )
        report = self.jouer(
            ligne(title="Kukum", author="Michel Jean", publisher="Libre Expression",
                  cover_url="https://exemple.test/c.jpg"),
            dry_run=True,
        )
        book.refresh_from_db()
        self.assertIsNone(book.publisher)
        self.assertFalse(book.picture)
        telecharger.assert_not_called()
        # Mais il ANNONCE ce qu'il aurait fait : c'est tout son intérêt.
        self.assertEqual(report.as_dict()["updated_count"], 1)

    def test_sans_completer_retrouve_le_comportement_d_avant(self):
        book = Book.objects.create(
            organization=self.organization, title="Kukum", author="Michel Jean",
        )
        report = self.jouer(
            ligne(title="Kukum", author="Michel Jean", publisher="Libre Expression"),
            complete=False,
        )
        book.refresh_from_db()
        self.assertIsNone(book.publisher)
        self.assertEqual(report.as_dict()["duplicates_count"], 1)
        self.assertEqual(report.as_dict()["updated_count"], 0)

    def test_un_reimport_a_l_identique_n_annonce_AUCUNE_modification(self):
        """Sans quoi le nombre affiché ne veut plus rien dire."""
        depart = ligne(
            title="Kukum", author="Michel Jean", publisher="Libre Expression",
            location="R JEA", category="Romans;Récits",
        )
        self.jouer(depart)
        report = self.jouer(depart)
        # 🔑 Les catégories comptent dans ce contrôle : `categories.add()` est
        # idempotent en base, donc réajouter une catégorie déjà posée ne casse
        # rien — mais la ligne serait annoncée « complétée » alors qu'elle
        # n'apporte rien, et le nombre affiché cesserait de vouloir dire
        # quelque chose.
        book = Book.objects.get(organization=self.organization, title="Kukum")
        self.assertEqual(book.categories.count(), 2)
        self.assertEqual(report.as_dict()["updated_count"], 0)
        self.assertEqual(report.as_dict()["duplicates_count"], 1)
        self.assertEqual(report.as_dict()["discrepancies_count"], 0)


class CompletionDesMembresTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.organization = create_organization(owner=cls.user)

    def jouer(self, *lignes, **options):
        return run_import(
            records=list(lignes), importer=CustomerImporter(),
            organization_id=self.organization.id, **options,
        )

    def membre(self, **champs):
        base = {
            "first_name": None, "last_name": None, "email": None,
            "phone": None, "language": None, "note": None,
        }
        base.update(champs)
        return base

    def test_complete_un_membre_sans_telephone(self):
        """Le cas ordinaire : la liste part sans les téléphones, ils sont
        collectés au fil de l'année, et le fichier revient enrichi."""
        customer = Customer.objects.create(
            organization=self.organization, first_name="Claire", last_name="Dubois",
            email="claire@exemple.test",
        )
        report = self.jouer(self.membre(
            first_name="Claire", last_name="Dubois",
            email="claire@exemple.test", phone="506-555-0100",
        ))
        customer.refresh_from_db()
        self.assertEqual(customer.phone, "506-555-0100")
        self.assertEqual(report.as_dict()["updated_count"], 1)

    def test_a_blanc_n_ecrit_RIEN(self):
        customer = Customer.objects.create(
            organization=self.organization, first_name="Claire", last_name="Dubois",
            email="claire@exemple.test",
        )
        report = self.jouer(
            self.membre(
                first_name="Claire", last_name="Dubois",
                email="claire@exemple.test", phone="506-555-0100",
            ),
            dry_run=True,
        )
        customer.refresh_from_db()
        self.assertIsNone(customer.phone)
        # Mais il ANNONCE ce qu'il aurait fait : c'est tout son intérêt.
        self.assertEqual(report.as_dict()["updated_count"], 1)

        # 🔑 Et il n'émet AUCUNE requête d'écriture. Vérifier l'état final ne
        # suffit pas : `save()` sur un objet resté intact laisse la base
        # identique, donc un mode à blanc qui écrit passerait inaperçu — c'est
        # ce qu'une mutation a montré le 01/09. Ici on compte les requêtes.
        importer = CustomerImporter()
        with self.assertNumQueries(0):
            importer.merge(
                customer,
                self.membre(
                    first_name="Claire", last_name="Dubois",
                    email="claire@exemple.test", phone="506-555-0100",
                ),
                dry_run=True,
            )

    def test_reinscrire_une_fiche_ARCHIVEE_ne_VIDE_pas_ses_champs(self):
        """🔴 Une perte silencieuse qui existait avant ce chantier.

        `build` affectait les champs directement : réimporter une liste sans
        colonne « note » effaçait les notes de suivi écrites dans
        l'application, et la personne revenait sans son historique de
        contact. Rien ne le signalait.
        """
        customer = Customer.objects.create(
            organization=self.organization, first_name="Claire", last_name="Dubois",
            email="claire@exemple.test", phone="506-555-0100",
            note="Bénévole le mardi.", archived=True,
        )
        self.jouer(self.membre(
            first_name="Claire", last_name="Dubois", email="claire@exemple.test",
        ))
        customer.refresh_from_db()
        self.assertFalse(customer.archived)
        self.assertEqual(customer.note, "Bénévole le mardi.")
        self.assertEqual(customer.phone, "506-555-0100")
