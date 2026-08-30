"""Tests du socle d'import : lecture de fichier et conduite de la boucle.

Le socle n'était éprouvé qu'à travers la vue, ce qui a laissé passer un
défaut visible dès le premier fichier réel : l'en-tête français pris pour un
ouvrage.
"""
from io import BytesIO

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from src.imports.readers import MAX_UPLOAD_BYTES, ImportFileError, read_rows
from src.imports.runner import Importer, ImportReport, run_import

BOOK_COLUMNS = ("isbn", "title", "author", "publisher")
CUSTOMER_COLUMNS = ("first_name", "last_name", "email", "phone")


def xlsx(rows, name="fichier.xlsx"):
    workbook = openpyxl.Workbook()
    for row in rows:
        workbook.active.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return SimpleUploadedFile(name, buffer.getvalue())


def csv_file(text, name="fichier.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"))


class HeaderDetectionTests(SimpleTestCase):
    def test_reconnait_un_en_tete_francais(self):
        """Le fichier du RFNB commence par « isbn ; titre ; auteur »."""
        rows = read_rows(
            xlsx([("ISBN", "Titre", "Auteur", "Éditeur"),
                  ("9782764813447", "Kukum", "Michel Jean", "Libre Expression")]),
            columns=BOOK_COLUMNS,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Kukum")

    def test_reconnait_un_en_tete_de_membres_en_francais(self):
        rows = read_rows(
            csv_file("Prénom;Nom;Courriel;Téléphone\nJosette;COUTURE;j@example.com;613\n"),
            columns=CUSTOMER_COLUMNS,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["first_name"], "Josette")

    def test_reconnait_un_en_tete_anglais(self):
        rows = read_rows(
            xlsx([("isbn", "title", "author", "publisher"), ("9782764813447", "Kukum", "M. Jean", "LE")]),
            columns=BOOK_COLUMNS,
        )
        self.assertEqual(len(rows), 1)

    def test_lit_un_fichier_sans_en_tete(self):
        """La liste des membres de l'AF d'Ottawa n'en avait pas."""
        rows = read_rows(
            csv_file("Josette;COUTURE;j@example.com;613\nFrancoys;CREPEAU;f@example.com;614\n"),
            columns=CUSTOMER_COLUMNS,
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["first_name"], "Josette")

    def test_un_ouvrage_dont_le_titre_ressemble_a_un_libelle_reste_un_ouvrage(self):
        """Une seule cellule reconnue ne fait pas un en-tête."""
        rows = read_rows(
            xlsx([("9782764813447", "Note", "Michel Jean", "Libre Expression")]),
            columns=BOOK_COLUMNS,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Note")


class ReadRowsTests(SimpleTestCase):
    def test_ignore_les_lignes_entierement_vides(self):
        rows = read_rows(xlsx([("9782764813447", "Kukum"), (None, None), ("", "")]), columns=BOOK_COLUMNS)
        self.assertEqual(len(rows), 1)

    def test_refuse_un_fichier_vide(self):
        with self.assertRaises(ImportFileError):
            read_rows(csv_file(""), columns=BOOK_COLUMNS)

    def test_refuse_un_fichier_trop_volumineux(self):
        """Trois workers sur 512 Mo : un classeur ne doit pas les emporter."""
        gros = SimpleUploadedFile("gros.csv", b"a;b;c\n" * (MAX_UPLOAD_BYTES // 4))
        with self.assertRaises(ImportFileError):
            read_rows(gros, columns=BOOK_COLUMNS)

    def test_refuse_un_flux_trop_volumineux_qui_n_annonce_pas_sa_taille(self):
        """Tout objet fichier n'a pas d'attribut `size` : la lecture doit
        être bornée elle aussi, sinon le plafond se contourne."""

        class FluxSansTaille:
            name = "gros.csv"

            def read(self, taille=-1):
                return b"a;b;c\n" * (MAX_UPLOAD_BYTES // 4)

        with self.assertRaises(ImportFileError):
            read_rows(FluxSansTaille(), columns=BOOK_COLUMNS)

    def test_accepte_un_gros_fichier_quand_le_plafond_est_leve(self):
        """La commande de gestion lève le plafond, et ça doit tenir.

        Le plafond protège le service web de ses téléversements ; la commande
        existe justement pour charger un fichier local que ce plafond
        refuserait. Sans ce test, le rétablir en douce ne casserait rien.
        """
        lignes = b"9782764813447;Kukum;Michel Jean;Libre Expression\n"
        gros = SimpleUploadedFile("gros.csv", lignes * (MAX_UPLOAD_BYTES // len(lignes) + 10))
        rows = read_rows(gros, columns=BOOK_COLUMNS, max_bytes=None)
        self.assertGreater(len(rows), 0)
        self.assertEqual(rows[0]["title"], "Kukum")

    def test_lit_un_csv_quel_que_soit_son_encodage(self):
        latin = SimpleUploadedFile("m.csv", "Josette;COUTURÉ;j@example.com;613\n".encode("latin-1"))
        rows = read_rows(latin, columns=CUSTOMER_COLUMNS)
        self.assertEqual(rows[0]["last_name"], "COUTURÉ")


class FakeImporter(Importer):
    """Un importateur d'essai : il retient ce qu'on lui donne."""

    def __init__(self, existing=(), refuse=(), explose=()):
        self.existing = set(existing)
        self.refuse = set(refuse)
        self.explose = set(explose)
        self.built = []

    def label(self, record):
        return record["name"]

    def dedupe_keys(self, record):
        return [record["name"]]

    def existing_keys(self, organization_id):
        return self.existing

    def build(self, record, organization_id):
        if record["name"] in self.explose:
            raise ValueError("boum")
        if record["name"] in self.refuse:
            return None
        self.built.append((record["name"], organization_id))
        return record


class RunImportTests(SimpleTestCase):
    def records(self, *names):
        return [{"name": name} for name in names]

    def test_classe_chaque_ligne_dans_la_bonne_categorie(self):
        importer = FakeImporter(existing={"déjà"}, refuse={"introuvable"}, explose={"cassée"})
        report = run_import(self.records("neuve", "déjà", "introuvable", "cassée"), importer, 7)
        summary = report.as_dict()
        self.assertEqual(summary["created"], ["neuve"])
        self.assertEqual(summary["duplicates"], ["déjà"])
        self.assertEqual(summary["not_found"], ["introuvable"])
        self.assertEqual(summary["errors"][0]["line"], "cassée")
        self.assertEqual(summary["total"], 4)

    def test_transmet_l_organisation_a_chaque_ligne(self):
        importer = FakeImporter()
        run_import(self.records("une", "deux"), importer, 42)
        self.assertEqual([org for _, org in importer.built], [42, 42])

    def test_refuse_d_importer_hors_organisation(self):
        """Rien de ce que produit un import ne doit exister sans organisation."""
        with self.assertRaises(ValueError):
            run_import(self.records("une"), FakeImporter(), None)

    def test_dedoublonne_a_l_interieur_du_fichier(self):
        report = run_import(self.records("même", "même"), FakeImporter(), 7)
        self.assertEqual(report.as_dict()["created_count"], 1)
        self.assertEqual(report.as_dict()["duplicates_count"], 1)

    def test_une_ligne_en_echec_ne_devient_pas_un_doublon(self):
        """Une ligne qui a explosé doit pouvoir être rejouée."""
        importer = FakeImporter(explose={"cassée"})
        report = run_import(self.records("cassée", "cassée"), importer, 7)
        self.assertEqual(report.as_dict()["errors_count"], 2)
        self.assertEqual(report.as_dict()["duplicates_count"], 0)

    def test_le_rapport_garde_les_listes_a_cote_des_totaux(self):
        report = ImportReport(errors=[{"line": "a", "reason": "b"}])
        self.assertEqual(report.as_dict()["errors"], [{"line": "a", "reason": "b"}])
        self.assertEqual(report.as_dict()["errors_count"], 1)


class ProgressTests(SimpleTestCase):
    """Le suivi de progression, sans lequel un import d'une heure est aveugle."""

    def records(self, *names):
        return [{"name": name} for name in names]

    def test_annonce_chaque_ligne_avec_son_sort(self):
        vus = []
        run_import(
            self.records("neuve", "déjà", "introuvable", "cassée"),
            FakeImporter(existing={"déjà"}, refuse={"introuvable"}, explose={"cassée"}),
            7,
            on_progress=lambda index, total, label, outcome: vus.append((index, label, outcome)),
        )
        self.assertEqual(vus, [
            (1, "neuve", "created"),
            (2, "déjà", "duplicate"),
            (3, "introuvable", "not_found"),
            (4, "cassée", "error"),
        ])

    def test_annonce_le_total_des_le_depart(self):
        totaux = []
        run_import(
            self.records("une", "deux", "trois"), FakeImporter(), 7,
            on_progress=lambda index, total, label, outcome: totaux.append(total),
        )
        self.assertEqual(totaux, [3, 3, 3])

    def test_un_affichage_qui_echoue_ne_coute_pas_l_import(self):
        """Le défaut le plus cher possible ici.

        Une console qui refuse un caractère ferait perdre une heure d'import
        ET son compte rendu, en laissant des lignes déjà écrites en base.
        """
        def casse(index, total, label, outcome):
            raise UnicodeEncodeError("ascii", "✅", 0, 1, "console rétive")

        report = run_import(self.records("une", "deux"), FakeImporter(), 7, on_progress=casse)
        self.assertEqual(report.as_dict()["created_count"], 2)

    def test_fonctionne_sans_suivi(self):
        report = run_import(self.records("une"), FakeImporter(), 7)
        self.assertEqual(report.as_dict()["created_count"], 1)
