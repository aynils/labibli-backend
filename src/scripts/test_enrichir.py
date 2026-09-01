"""La commande d'enrichissement, et surtout ce qu'elle ne doit PAS faire.

Elle écrit en production sur des collections réelles. Les trois garanties qui
comptent sont donc négatives : ne rien écraser, ne pas sortir de
l'organisation, et s'arrêter quand les catalogues ne répondent plus.
"""
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from src.helpers.tests import create_admin_user, create_organization, create_user
from src.items.book_lookup import BookDetails
from src.items.models import Book

LOOKUP = "src.scripts.management.commands.enrichir.find_book_details"
RESOLVE = "src.scripts.management.commands.enrichir.find_isbn"
RESUME = "src.scripts.management.commands.enrichir.get_wikipedia_fr_summary"
COUVERTURE = "src.scripts.management.commands.enrichir.get_cover_by_title"
IMAGE = "src.scripts.management.commands.enrichir.download_image"


def details(description="Un résumé de catalogue.", picture="https://exemple.test/c.jpg"):
    return BookDetails(
        isbn="9782764813447", title="Kukum", picture=picture, author="Michel Jean",
        publisher="Libre Expression", published_year="2019",
        description=description, page_count=224, language="fr",
    )


class EnrichirTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.organization = create_organization(owner=cls.user)
        # Créée APRÈS : une requête non cloisonnée tomberait sinon sur la
        # bonne organisation par hasard, et le test passerait quand même.
        cls.voisine = create_organization(owner=create_admin_user())

    def lancer(self, **options):
        sortie = StringIO()
        call_command("enrichir", organization=self.organization.id, stdout=sortie, **options)
        return sortie.getvalue()

    # ── Ce qu'elle doit faire ────────────────────────────────────────────

    @patch(IMAGE, return_value=b"image")
    @patch(LOOKUP, return_value=details())
    def test_remplit_un_resume_et_une_couverture_manquants(self, lookup, image):
        book = Book.objects.create(
            organization=self.organization, title="Kukum", author="Michel Jean",
            isbn="9782764813447",
        )
        self.lancer()
        book.refresh_from_db()
        self.assertEqual(book.description, "Un résumé de catalogue.")
        self.assertTrue(book.picture)

    @patch(IMAGE, return_value=b"image")
    @patch(LOOKUP, return_value=None)
    @patch(COUVERTURE, return_value="https://exemple.test/titre.jpg")
    @patch(RESUME, return_value="Un résumé de Wikipédia.")
    def test_se_rabat_sur_le_titre_quand_aucun_catalogue_ne_repond(
        self, resume, couverture, lookup, image,
    ):
        """Le cas de Siem Reap : pas d'ISBN, ou un ISBN qu'aucun catalogue ne connaît."""
        book = Book.objects.create(
            organization=self.organization, title="Kukum", author="Michel Jean",
        )
        with patch(RESOLVE, return_value=None):
            self.lancer()
        book.refresh_from_db()
        self.assertEqual(book.description, "Un résumé de Wikipédia.")
        self.assertTrue(book.picture)

    # ── ⛔ Ce qu'elle ne doit JAMAIS faire ───────────────────────────────

    @patch(IMAGE, return_value=b"image")
    @patch(LOOKUP, return_value=details(description="Le résumé du catalogue."))
    def test_n_ECRASE_PAS_un_resume_deja_saisi(self, lookup, image):
        """🔴 La garantie qui justifie cette commande.

        Une bibliothèque a pu corriger un résumé à la main, ou en écrire un
        elle-même. Le réimport, lui, l'aurait remplacé sans le dire — c'est
        justement pour ça qu'on ne réimporte pas.
        """
        book = Book.objects.create(
            organization=self.organization, title="Kukum", author="Michel Jean",
            isbn="9782764813447", description="Le résumé écrit par la bibliothécaire.",
        )
        self.lancer()
        book.refresh_from_db()
        self.assertEqual(book.description, "Le résumé écrit par la bibliothécaire.")

    @patch(IMAGE, return_value=b"image")
    @patch(LOOKUP, return_value=details(picture="https://exemple.test/autre.jpg"))
    def test_n_ECRASE_PAS_une_couverture_deja_posee(self, lookup, image):
        """🔴 Même garantie que pour le résumé, et elle manquait.

        Une bibliothèque peut avoir photographié SON exemplaire, ou remplacé
        une jaquette d'une autre édition. La reprendre serait la perte la plus
        visible qu'on puisse infliger — et un mutant l'a montrée : sans ce
        test, écraser la couverture laissait la suite verte.
        """
        book = Book.objects.create(
            organization=self.organization, title="Kukum", author="Michel Jean",
            isbn="9782764813447",
        )
        book.picture.name = "TEST-covers/la-photo-de-la-bibliotheque.jpg"
        book.save(update_fields=["picture"])

        self.lancer()
        book.refresh_from_db()
        # 🔑 La fiche DOIT entrer dans la sélection — il lui manque un résumé —
        # sinon le test ne prouve rien : une fiche complète n'est jamais
        # touchée, et le mutant qui écrase les couvertures survivait.
        self.assertEqual(book.description, "Un résumé de catalogue.")
        self.assertEqual(book.picture.name, "TEST-covers/la-photo-de-la-bibliotheque.jpg")
        image.assert_not_called()

    @patch(IMAGE, return_value=b"image")
    @patch(LOOKUP, return_value=details())
    def test_n_ECRASE_PAS_le_titre_ni_l_auteurice(self, lookup, image):
        """Le catalogue dit « Kukum / Michel Jean » ; la fiche dit autre chose.

        C'est la fiche qui a raison : elle décrit l'exemplaire du rayon.
        """
        book = Book.objects.create(
            organization=self.organization, title="Kukum, un roman",
            author="Jean, Michel", isbn="9782764813447",
        )
        self.lancer()
        book.refresh_from_db()
        self.assertEqual(book.title, "Kukum, un roman")
        self.assertEqual(book.author, "Jean, Michel")

    @patch(IMAGE, return_value=b"image")
    @patch(LOOKUP, return_value=details())
    def test_ne_touche_PAS_a_la_collection_d_une_autre_organisation(self, lookup, image):
        """🔴 Le cloisonnement, sur une commande qui ÉCRIT."""
        voisin = Book.objects.create(
            organization=self.voisine, title="Maus", author="Art Spiegelman",
            isbn="9782081217799",
        )
        self.lancer()
        voisin.refresh_from_db()
        self.assertFalse(voisin.description)
        self.assertFalse(voisin.picture)

    @patch(IMAGE, return_value=b"image")
    @patch(LOOKUP, return_value=details())
    def test_a_blanc_n_ecrit_rien(self, lookup, image):
        book = Book.objects.create(
            organization=self.organization, title="Kukum", author="Michel Jean",
            isbn="9782764813447",
        )
        sortie = self.lancer(dry_run=True)
        book.refresh_from_db()
        self.assertFalse(book.description)
        self.assertFalse(book.picture)
        self.assertIn("rien n'a été écrit", sortie)

    # ── L'arrêt quand les catalogues ne répondent plus ───────────────────

    @patch(IMAGE, return_value=None)
    @patch(COUVERTURE, return_value=None)
    @patch(RESUME, return_value=None)
    @patch(LOOKUP, return_value=None)
    def test_s_ARRETE_apres_N_ouvrages_sans_le_moindre_apport(
        self, lookup, resume, couverture, image,
    ):
        """🔴 La leçon du 31/08.

        La passe de ce jour-là a continué après l'épuisement du quota Google,
        et la qualité s'est dégradée de façon monotone : 30 % de couvertures
        sur la première tranche, 20 % sur la dernière. Persister ne remplit
        rien — ça consomme les fiches qu'il reste à traiter.
        """
        for numero in range(10):
            Book.objects.create(
                organization=self.organization, title=f"Titre {numero}", author="Autrice",
            )
        with patch(RESOLVE, return_value=None):
            sortie = self.lancer(seuil_abandon=3)
        self.assertIn("ARRÊT", sortie)
        # Trois échecs suffisent : les sept autres ne sont pas consommées.
        self.assertNotIn("4/10", sortie)

    @patch(IMAGE, return_value=b"image")
    @patch(LOOKUP, return_value=details())
    def test_est_IDEMPOTENTE(self, lookup, image):
        """Relancer ne refait pas ce qui est fait — c'est ce qui permet
        d'étaler sur plusieurs jours quand la quota est journalière."""
        Book.objects.create(
            organization=self.organization, title="Kukum", author="Michel Jean",
            isbn="9782764813447",
        )
        self.lancer()
        appels_apres_premier_passage = lookup.call_count
        sortie = self.lancer()
        self.assertEqual(lookup.call_count, appels_apres_premier_passage)
        self.assertIn("0 incomplets", sortie)
        self.assertIn("À traiter    : 0", sortie)
