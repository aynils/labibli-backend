"""L'export, et surtout l'aller-retour.

Le test qui compte n'est pas « le fichier se télécharge » : c'est
« le fichier se RECHARGE ». Un export que notre propre import ne sait pas
relire ne rend pas la collection, il en rend une photo — et la promesse
« vous partez avec vos données » devient décorative.
"""
from io import BytesIO

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from src.helpers.tests import (
    authenticate_admin,
    authenticate_user,
    create_admin_user,
    create_organization,
    create_user,
)
from src.imports.readers import read_rows
from src.imports.runner import run_import
from src.items.book_export import COLUMNS, export
from src.items.book_import import COLUMNS as IMPORT_COLUMNS
from src.items.book_import import BookImporter
from src.items.models import Book, Category


def sheet_of(content):
    workbook = openpyxl.load_workbook(filename=BytesIO(content), data_only=True)
    return [list(values) for values in workbook.worksheets[0].iter_rows(values_only=True)]


class BookExportTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.admin_user = create_admin_user()
        cls.organization = create_organization(owner=cls.user)
        # Créée APRÈS : une lecture non cloisonnée tomberait sinon sur la
        # bonne organisation par hasard et le test passerait quand même.
        cls.admin_organization = create_organization(owner=cls.admin_user)

        cls.roman = Category.objects.create(
            organization=cls.organization, name="Roman"
        )
        cls.jeunesse = Category.objects.create(
            organization=cls.organization, name="Jeunesse"
        )
        cls.book = Book.objects.create(
            organization=cls.organization,
            title="Kukum",
            author="Michel Jean",
            isbn="9782764813447",
            publisher="Libre Expression",
            published_year="2019",
            lang="fr",
            location="Rayon 3",
            description="Almanda Siméon chez les Innus.",
        )
        cls.book.categories.set([cls.roman, cls.jeunesse])
        cls.archive = Book.objects.create(
            organization=cls.organization,
            title="Le petit prince",
            author="Antoine de Saint-Exupéry",
            archived=True,
        )
        # L'ouvrage du voisin : il ne doit apparaître dans aucun export.
        cls.book_ailleurs = Book.objects.create(
            organization=cls.admin_organization,
            title="Maus",
            author="Art Spiegelman",
        )

    def test_l_export_ne_contient_que_la_collection_de_l_organisation(self):
        """🔴 Le cas qui ne doit jamais arriver : la collection du voisin."""
        rows = sheet_of(export(organization_id=self.organization.id))
        titles = [values[0] for values in rows[1:]]
        self.assertIn("Kukum", titles)
        self.assertNotIn("Maus", titles)

    def test_l_export_contient_les_ouvrages_archives(self):
        """Archivé vaut caché, pas effacé : les omettre perdrait la donnée."""
        rows = sheet_of(export(organization_id=self.organization.id))
        self.assertIn("Le petit prince", [values[0] for values in rows[1:]])

    def test_les_en_tetes_sont_ceux_que_l_import_reconnait(self):
        """Le contrat du format, vérifié en tant que tel.

        Si un en-tête cesse d'être reconnu, la colonne est perdue au
        réimport SANS erreur : `header_placement` laisse simplement vide ce
        qu'il ne sait pas nommer.
        """
        rows = sheet_of(export(organization_id=self.organization.id))
        placed = read_rows(
            self.upload(export(organization_id=self.organization.id)),
            columns=IMPORT_COLUMNS,
        )
        self.assertEqual(rows[0], [header for _, header in COLUMNS])
        for field, _ in COLUMNS:
            self.assertIn(field, placed[0], f"« {field} » n'est pas relu")

    def upload(self, content, name="collection.xlsx"):
        return SimpleUploadedFile(name, content)

    def test_aller_retour_l_export_se_recharge_a_l_identique(self):
        """Le test qui tient la promesse : export, réimport, comparaison.

        Le réimport se fait dans une AUTRE organisation, sans réseau : dans
        la même, chaque ligne serait un doublon et le test ne prouverait
        rien.
        """
        content = export(organization_id=self.organization.id)
        records = read_rows(self.upload(content), columns=IMPORT_COLUMNS)
        report = run_import(
            records=records,
            importer=BookImporter(resolve_isbn=False, enrich=False),
            organization_id=self.admin_organization.id,
        )
        self.assertEqual(report.errors, [])
        self.assertEqual(report.not_found, [])

        recharge = Book.objects.get(
            organization=self.admin_organization, title="Kukum"
        )
        for field in (
            "title", "author", "isbn", "publisher",
            "published_year", "lang", "location", "description",
        ):
            self.assertEqual(
                getattr(recharge, field),
                getattr(self.book, field),
                f"« {field} » ne survit pas à l'aller-retour",
            )
        # Les deux catégories, pas une seule fondue en « Roman; Jeunesse ».
        self.assertEqual(
            sorted(category.name for category in recharge.categories.all()),
            ["Jeunesse", "Roman"],
        )
        # Et les catégories rechargées appartiennent à l'organisation qui
        # importe, pas à celle qui a exporté.
        for category in recharge.categories.all():
            self.assertEqual(category.organization_id, self.admin_organization.id)

    def test_l_ouvrage_archive_survit_aussi_a_l_aller_retour(self):
        """Et il revient ARCHIVÉ, pas seulement présent.

        La version précédente de ce test se contentait de `exists()`. Elle
        passait donc alors même que l'état archivé se perdait en route — un
        ouvrage désherbé revenait actif, en rayon, sans que rien ne l'annonce.
        « Archivé vaut caché, pas effacé » ne tient que si ça survit à la
        sortie ET au retour.
        """
        content = export(organization_id=self.organization.id)
        run_import(
            records=read_rows(self.upload(content), columns=IMPORT_COLUMNS),
            importer=BookImporter(resolve_isbn=False, enrich=False),
            organization_id=self.admin_organization.id,
        )
        revenu = Book.objects.get(
            organization=self.admin_organization, title="Le petit prince"
        )
        self.assertTrue(revenu.archived)
        # Et l'ouvrage actif ne devient pas archivé au passage.
        self.assertFalse(
            Book.objects.get(
                organization=self.admin_organization, title="Kukum"
            ).archived
        )

    def test_un_titre_commencant_par_egal_n_est_pas_ecrit_en_formule(self):
        """🔴 Deux pannes en une, et toutes deux silencieuses.

        openpyxl écrit « =SOMME(A1:A9) » comme une FORMULE. Au réimport, la
        cellule rend None : l'ouvrage tombe en « introuvable » sans la moindre
        erreur. Et c'est une injection de formule dans un fichier qu'une
        personne bénévole ouvre sur son poste.

        Un titre commençant par « = » n'est pas une hypothèse d'école : les
        inventaires saisis au tableur en produisent, et le nôtre les accepte.
        """
        Book.objects.create(
            organization=self.organization, title="=SOMME(A1:A9)", author="Tableur",
        )
        content = export(organization_id=self.organization.id)
        lignes = read_rows(self.upload(content), columns=IMPORT_COLUMNS)
        titres = [ligne["title"] for ligne in lignes]
        self.assertIn("=SOMME(A1:A9)", titres)

    def test_un_caractere_de_controle_ne_fait_pas_echouer_tout_l_export(self):
        """🔴 UN caractère suffisait à faire tomber l'export entier, en 500.

        Et il part dès `append()`, pas à l'enregistrement — c'est pour ça que
        le nettoyage est dans `row()` et pas plus loin. La description vient de
        Wikipédia, de Google Books, de la BnF et des fichiers reçus : ce sont
        exactement les sources qui en charrient.
        """
        Book.objects.create(
            organization=self.organization,
            title="Fiche abîmée",
            author="Source extérieure",
            description="avant\x0bmilieu\x07après",
        )
        content = export(organization_id=self.organization.id)
        lignes = read_rows(self.upload(content), columns=IMPORT_COLUMNS)
        abimee = next(l for l in lignes if l["title"] == "Fiche abîmée")
        self.assertNotIn("\x0b", abimee["description"])
        self.assertIn("milieu", abimee["description"])
        # Et les autres ouvrages sont toujours là : l'export n'a pas été
        # amputé, il a été nettoyé.
        self.assertIn("Kukum", [l["title"] for l in lignes])

    def test_le_point_d_entree_rend_un_classeur(self):
        authenticate_user(self)
        response = self.client.get(reverse("export_books"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("attachment;", response["Content-Disposition"])
        titles = [values[0] for values in sheet_of(response.content)[1:]]
        self.assertIn("Kukum", titles)

    def test_le_point_d_entree_ne_rend_que_la_collection_de_l_appelant(self):
        """🔴 Le même utilisateur, l'autre organisation : rien du voisin."""
        authenticate_admin(self)
        response = self.client.get(reverse("export_books"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [values[0] for values in sheet_of(response.content)[1:]]
        self.assertEqual(titles, ["Maus"])

    def test_le_point_d_entree_refuse_les_anonymes(self):
        response = self.client.get(reverse("export_books"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
