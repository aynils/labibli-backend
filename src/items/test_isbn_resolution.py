"""Tests de la résolution titre + auteur → ISBN.

Ce qui est éprouvé ici n'est pas le réseau, c'est le JUGEMENT : quels
candidats sont acceptés, lesquels sont rejetés. Un appariement trop
permissif ferait entrer dans le catalogue d'une bibliothèque un ouvrage
qu'elle ne possède pas, et personne ne s'en apercevrait.
"""
from unittest.mock import patch

from django.test import SimpleTestCase

from src.items import isbn_resolution
from src.helpers.text_matching import shares_surname, split_authors
from src.items.isbn_resolution import (
    AUTHOR_THRESHOLD,
    same_volume,
    volume_number,
    TITLE_THRESHOLD,
    author_similarity,
    find_isbn,
    isbn13,
    normalize,
    title_similarity,
    title_variants,
)


class NormalizationTests(SimpleTestCase):
    def test_ignore_la_casse_les_accents_et_la_ponctuation(self):
        self.assertEqual(normalize("L'Été, meurtrier !"), "l ete meurtrier")

    def test_une_valeur_absente_vaut_la_chaine_vide(self):
        self.assertEqual(normalize(None), "")


class TitleSimilarityTests(SimpleTestCase):
    def test_reconnait_un_titre_identique_ecrit_autrement(self):
        # Apostrophe typographique contre apostrophe droite, casse différente.
        self.assertGreater(title_similarity("L'énigme de l'atlantide", "L'énigme de l'Atlantide"), 0.95)

    def test_ignore_la_mention_d_edition_ajoutee_par_le_catalogue(self):
        self.assertGreater(title_similarity("Chien-loup", "Chien-loup : roman"), 0.9)

    def test_accepte_un_titre_abrege_par_l_inventaire(self):
        # « Trois petit cochons » pour « Les trois petits cochons » : article
        # absent et pluriel oublié, ce qui reste le même ouvrage.
        score = title_similarity("Trois petit cochons", "Les trois petits cochons")
        self.assertGreaterEqual(score, TITLE_THRESHOLD)

    def test_accepte_un_titre_entierement_contenu_dans_celui_du_catalogue(self):
        # Le catalogue préfixe par la série ; les mots du titre cherché y sont
        # tous, ce qui suffit à l'accepter.
        score = title_similarity("La couronne d'Ogotaï", "Thorgal. 21, La couronne d'Ogotaï")
        self.assertGreaterEqual(score, 0.9)

    def test_rejette_deux_titres_differents(self):
        self.assertLess(title_similarity("Kukum", "Maria Chapdelaine"), 0.82)


class AuthorSimilarityTests(SimpleTestCase):
    def test_ignore_l_ordre_du_nom_et_du_prenom(self):
        self.assertEqual(author_similarity("André Marcel adamek", "Adamek, André-Marcel"), 1.0)

    def test_accepte_un_nom_de_famille_seul(self):
        self.assertGreaterEqual(author_similarity("atwood", "Atwood, Margaret"), 0.34)

    def test_tolere_une_faute_de_frappe_sur_le_prenom(self):
        # « Nathan littell » pour Jonathan Littell : le nom de famille tient.
        self.assertGreaterEqual(author_similarity("Nathan littell", "Littell, Jonathan"), 0.34)

    def test_rejette_un_auteur_sans_rapport(self):
        self.assertLess(author_similarity("Michel Jean", "Margaret Atwood"), 0.34)


class TitleVariantTests(SimpleTestCase):
    """Chaque variante dit aussi si le numéro de tome reste exigible."""

    def labels(self, title):
        return [label for label, require_volume in title_variants(title)]

    def test_retire_la_serie_et_le_tome_places_devant(self):
        self.assertIn("La couronne d'Ogotaï", self.labels("Thorgal 21 - La couronne d'Ogotaï"))

    def test_retire_le_numero_de_tome_place_derriere(self):
        self.assertIn("421, Les enfants de la porte", self.labels("421, Les enfants de la porte (6)"))

    def test_retire_le_sous_titre(self):
        self.assertIn("Sur la télévision", self.labels("Sur la télévision ; l'emprise du journalisme"))

    def test_laisse_un_titre_simple_intact(self):
        self.assertEqual(self.labels("La servante écarlate"), ["La servante écarlate"])

    def test_essaie_toujours_le_titre_ecrit_en_premier(self):
        variants = title_variants("Thorgal 21 - La couronne d'Ogotaï")
        self.assertEqual(variants[0], ("Thorgal 21 - La couronne d'Ogotaï", True))

    def test_un_titre_propre_extrait_n_exige_plus_le_tome(self):
        """« La couronne d'Ogotaï » est distinctif : le catalogue peut le
        publier sans le numéro de la série."""
        variants = dict(title_variants("Thorgal 21 - La couronne d'Ogotaï"))
        self.assertFalse(variants["La couronne d'Ogotaï"])

    def test_un_titre_de_serie_ampute_exige_toujours_le_tome(self):
        """« Vernon subutex » sans numéro désigne la série entière : sans
        cette exigence, tous les tomes recevraient le même ISBN."""
        for label, require_volume in title_variants("Vernon subutex tome 2"):
            self.assertTrue(require_volume, label)


class Isbn13Tests(SimpleTestCase):
    def test_prefere_un_isbn_13(self):
        self.assertEqual(isbn13(["2859202684", "9782875681362"]), "9782875681362")

    def test_accepte_un_isbn_10_faute_de_mieux(self):
        self.assertEqual(isbn13(["2859202684"]), "2859202684")

    def test_ecarte_ce_qui_n_est_pas_un_isbn(self):
        self.assertIsNone(isbn13(["ark:/12148/cb357918028", "", None]))


class FindIsbnTests(SimpleTestCase):
    """Le jugement d'ensemble, sources simulées."""

    def sources(self, bnf=(), google=(), openlibrary=()):
        return [
            ("bnf", lambda title, author: list(bnf)),
            ("google", lambda title, author: list(google)),
            ("openlibrary", lambda title, author: list(openlibrary)),
        ]

    def test_retient_un_candidat_qui_concorde(self):
        candidates = [("9782875681362", "L'oiseau des morts : roman", "Adamek, André-Marcel")]
        with patch.object(isbn_resolution, "SOURCES", self.sources(bnf=candidates)):
            match = find_isbn(title="L'oiseau des morts", author="André Marcel adamek")
        self.assertEqual(match.isbn, "9782875681362")
        self.assertEqual(match.source, "bnf")

    def test_rejette_un_candidat_au_bon_titre_mais_au_mauvais_auteur(self):
        """Le garde-fou qui empêche d'importer le livre d'un autre.

        Beaucoup de titres sont partagés par plusieurs ouvrages sans rapport ;
        seul l'auteur permet de trancher.
        """
        candidates = [("9782070360000", "Antigone", "Sophocle")]
        with patch.object(isbn_resolution, "SOURCES", self.sources(bnf=candidates)):
            match = find_isbn(title="Antigone", author="Jean Anouilh")
        self.assertIsNone(match)

    def test_rejette_un_candidat_au_titre_trop_eloigne(self):
        candidates = [("9782070360000", "Antigone", "Jean Anouilh")]
        with patch.object(isbn_resolution, "SOURCES", self.sources(bnf=candidates)):
            match = find_isbn(title="La cantatrice chauve", author="Jean Anouilh")
        self.assertIsNone(match)

    def test_se_rabat_sur_la_source_suivante(self):
        candidates = [("9780140256116", "Lives of girls and women", "Munro, Alice")]
        with patch.object(isbn_resolution, "SOURCES", self.sources(openlibrary=candidates)):
            match = find_isbn(title="Lives of Girls and Women", author="Alice Munro")
        self.assertEqual(match.source, "openlibrary")

    def test_reessaie_sans_le_nom_de_la_serie(self):
        """Le second essai n'a lieu qu'après l'échec du titre tel qu'écrit."""
        candidates = [("9782803632619", "La couronne d'Ogotaï", "Rosinski, Grzegorz")]

        def bnf(title, author):
            # Le catalogue ne connaît pas « Thorgal 21 - … », seulement le titre.
            return list(candidates) if title == "La couronne d'Ogotaï" else []

        with patch.object(isbn_resolution, "SOURCES", [("bnf", bnf)]):
            match = find_isbn(title="Thorgal 21 - La couronne d'Ogotaï", author="Rosinski")
        self.assertEqual(match.isbn, "9782803632619")

    def test_garde_le_meilleur_candidat_parmi_plusieurs(self):
        candidates = [
            ("1111111111111", "La servante", "Atwood, Margaret"),
            ("2221103769", "La servante écarlate", "Atwood, Margaret"),
        ]
        with patch.object(isbn_resolution, "SOURCES", self.sources(bnf=candidates)):
            match = find_isbn(title="La servante écarlate", author="Margaret atwood")
        self.assertEqual(match.isbn, "2221103769")

    def test_sans_titre_il_n_y_a_rien_a_chercher(self):
        self.assertIsNone(find_isbn(title="", author="Michel Jean"))


class SurnameGuardTests(SimpleTestCase):
    """Le prénom ne prouve rien : seul le nom de famille identifie."""

    def test_rejette_deux_auteurs_qui_ne_partagent_que_le_prenom(self):
        self.assertFalse(shares_surname("Jean Anouilh", "Jean Racine"))
        self.assertFalse(shares_surname("Charles Perrault", "Charles Dickens"))
        self.assertFalse(shares_surname("Gabrielle Roy", "Gabrielle Filteau-Chiba"))

    def test_accepte_le_meme_auteur_ecrit_dans_l_autre_sens(self):
        self.assertTrue(shares_surname("André Marcel adamek", "Adamek, André-Marcel"))
        self.assertTrue(shares_surname("Michel Jean", "Jean, Michel"))

    def test_accepte_un_nom_de_famille_seul(self):
        self.assertTrue(shares_surname("atwood", "Atwood, Margaret"))

    def test_tolere_une_faute_sur_le_prenom(self):
        self.assertTrue(shares_surname("Nathan littell", "Littell, Jonathan"))

    def test_accepte_l_un_des_auteurs_d_une_mention_multiple(self):
        self.assertTrue(shares_surname("Diane Summers et Eric Valli", "Summers, Diane"))

    def test_s_abstient_quand_un_des_deux_noms_manque(self):
        self.assertFalse(shares_surname("", "Atwood, Margaret"))
        self.assertFalse(shares_surname("Margaret Atwood", ""))


class ThresholdTests(SimpleTestCase):
    """Les deux constantes portent tout l'argument de sûreté du module.

    Les assertions portent sur des VALEURS FIXES, jamais sur la constante
    elle-même : un test qui se compare au seuil qu'il teste passe quelle que
    soit sa valeur, et ne prouve donc rien.
    """

    def sources(self, candidates):
        return [("bnf", lambda title, author: list(candidates))]

    def test_le_seuil_de_titre_rejette_un_titre_a_moitie_ressemblant(self):
        score = title_similarity("Le grand cahier", "Le grand meaulnes")
        self.assertLess(score, TITLE_THRESHOLD)
        self.assertGreater(score, 0.5)

    def test_le_seuil_de_titre_accepte_une_variante_d_ecriture(self):
        self.assertGreaterEqual(
            title_similarity("L'énigme de l'atlantide", "L'énigme de l'Atlantide"), TITLE_THRESHOLD
        )

    def test_rejette_un_auteur_reconnu_a_un_quart_seulement(self):
        """Un seul mot sur quatre en commun ne fait pas le même auteur.

        Le score vaut 0,25 : au-dessus d'un seuil trop bas, en dessous du
        seuil retenu. C'est ce cas qui tient la borne inférieure.
        """
        self.assertAlmostEqual(
            author_similarity("Jean Pierre Marie Dupont", "Dupont"), 0.25, places=2
        )
        candidates = [("9782070360004", "Un titre singulier", "Dupont")]
        with patch.object(isbn_resolution, "SOURCES", self.sources(candidates)):
            match = find_isbn(title="Un titre singulier", author="Jean Pierre Marie Dupont")
        self.assertIsNone(match)

    def test_accepte_un_auteur_reconnu_a_moitie(self):
        """« Margaret Atwood » contre « Atwood » : 0,5, et c'est le même
        auteur. C'est ce cas qui tient la borne supérieure."""
        self.assertAlmostEqual(author_similarity("Margaret Atwood", "Atwood"), 0.5, places=2)
        candidates = [("2221103769", "La servante écarlate", "Atwood")]
        with patch.object(isbn_resolution, "SOURCES", self.sources(candidates)):
            match = find_isbn(title="La servante écarlate", author="Margaret Atwood")
        self.assertEqual(match.isbn, "2221103769")


class FalseMatchTests(SimpleTestCase):
    """Les contre-exemples qui passaient avant le garde-fou du nom."""

    def sources(self, candidates):
        return [("bnf", lambda title, author: list(candidates))]

    def test_n_importe_pas_l_antigone_de_racine_pour_celle_d_anouilh(self):
        candidates = [("9782070360000", "Antigone", "Racine, Jean")]
        with patch.object(isbn_resolution, "SOURCES", self.sources(candidates)):
            self.assertIsNone(find_isbn(title="Antigone", author="Jean Anouilh"))

    def test_n_importe_pas_les_contes_de_dickens_pour_ceux_de_perrault(self):
        candidates = [("9782070360001", "Contes", "Dickens, Charles")]
        with patch.object(isbn_resolution, "SOURCES", self.sources(candidates)):
            self.assertIsNone(find_isbn(title="Contes", author="Charles Perrault"))

    def test_n_importe_pas_le_roman_d_une_homonyme(self):
        candidates = [("9782070360002", "Bonheur d'occasion", "Filteau-Chiba, Gabrielle")]
        with patch.object(isbn_resolution, "SOURCES", self.sources(candidates)):
            self.assertIsNone(find_isbn(title="Bonheur d'occasion", author="Gabrielle Roy"))

    def test_accepte_toujours_le_bon_auteur(self):
        candidates = [("9782070360003", "Antigone", "Anouilh, Jean")]
        with patch.object(isbn_resolution, "SOURCES", self.sources(candidates)):
            match = find_isbn(title="Antigone", author="Jean Anouilh")
        self.assertEqual(match.isbn, "9782070360003")


class VolumeTests(SimpleTestCase):
    """Le numéro de tome, seul élément qui sépare deux volumes d'une série.

    Constaté en production le 31/08/2026 : « Vernon subutex tome 2 » et
    « tome 3 » avaient reçu le MÊME ISBN, donc la même couverture et le même
    résumé — la réécriture qui retire le tome les rendait indiscernables.
    """

    def test_lit_le_numero_sous_ses_formes_courantes(self):
        self.assertEqual(volume_number("Vernon subutex tome 2"), "2")
        self.assertEqual(volume_number("Le radeau de bambou, tome 1 l'initiation"), "1")
        self.assertEqual(volume_number("421, Les enfants de la porte (6)"), "6")
        self.assertEqual(volume_number("Thorgal 21 - La couronne d'Ogotaï"), "21")

    def test_un_titre_sans_tome_n_en_porte_pas(self):
        self.assertIsNone(volume_number("Antigone"))
        self.assertIsNone(volume_number(""))

    def test_un_titre_sans_tome_n_impose_rien(self):
        self.assertTrue(same_volume("Antigone", "Antigone"))

    def test_refuse_un_candidat_sans_le_tome_demande(self):
        self.assertFalse(same_volume("Vernon subutex tome 2", "Vernon Subutex"))

    def test_refuse_un_candidat_portant_un_autre_tome(self):
        self.assertFalse(same_volume("Vernon subutex tome 3", "Vernon Subutex. 2"))

    def test_refuse_un_recueil_de_plusieurs_tomes(self):
        """L'intégrale n'est pas le tome cherché.

        La BnF publie « Vernon Subutex. Tome 1, tome 2, tome 3 » pour le
        volume qui les réunit : il contient bien le tome demandé, mais lui
        donner cet ISBN attribuerait à deux fiches distinctes la même
        couverture et le même résumé. Constaté en production le 31/08/2026.
        """
        recueil = "Vernon Subutex. Tome 1, tome 2, tome 3"
        self.assertFalse(same_volume("Vernon subutex tome 2", recueil))
        self.assertFalse(same_volume("Vernon subutex tome 3", recueil))

    def test_accepte_le_tome_ecrit_autrement_par_le_catalogue(self):
        self.assertTrue(same_volume("Vernon subutex tome 2", "Vernon Subutex. 2"))
        self.assertTrue(same_volume("Thorgal 21 - La couronne d'Ogotaï",
                                    "Thorgal. 21, La couronne d'Ogotaï"))


class CrossVolumeMatchTests(SimpleTestCase):
    """Le défaut tel qu'il s'est produit, de bout en bout."""

    def sources(self, candidates):
        return [("bnf", lambda title, author: list(candidates))]

    def test_deux_tomes_ne_recoivent_pas_le_meme_isbn(self):
        catalogue = [("9782298141498", "Vernon Subutex. Tome 1, tome 2, tome 3", "Despentes, Virginie")]
        with patch.object(isbn_resolution, "SOURCES", self.sources(catalogue)):
            tome2 = find_isbn(title="Vernon subutex tome 2", author="Virginie despentes")
            tome3 = find_isbn(title="Vernon subutex tome 3", author="Virginie despentes")
        self.assertIsNone(tome2)
        self.assertIsNone(tome3)

    def test_le_bon_tome_est_toujours_retenu(self):
        catalogue = [("9782246813378", "Vernon Subutex. 2", "Despentes, Virginie")]
        with patch.object(isbn_resolution, "SOURCES", self.sources(catalogue)):
            match = find_isbn(title="Vernon subutex tome 2", author="Virginie despentes")
        self.assertEqual(match.isbn, "9782246813378")


class MultiCreatorNoticeTests(SimpleTestCase):
    """Les notices à plusieurs créateurs, forme catalogue.

    La BnF joint tous ses `dc:creator` : un roman traduit donne « Anouilh,
    Jean, Sartre, Jean-Paul ». Découper naïvement sur les virgules rendait
    « jean » comme nom de famille acceptable, et rouvrait le faux
    appariement que le garde-fou existe pour fermer.
    """

    def test_decoupe_deux_createurs_ecrits_nom_prenom(self):
        self.assertEqual(split_authors("Anouilh, Jean, Racine, Jean"), ["Anouilh", "Racine"])

    def test_decoupe_un_seul_createur_ecrit_nom_prenom(self):
        self.assertEqual(split_authors("Anouilh, Jean"), ["Anouilh"])

    def test_garde_deux_auteurs_ecrits_prenom_nom(self):
        self.assertEqual(split_authors("Jean Anouilh, Sophie Hanna"), ["Jean Anouilh", "Sophie Hanna"])

    def test_refuse_l_homonyme_malgre_une_notice_a_deux_createurs(self):
        self.assertFalse(shares_surname("Anouilh, Jean, Sartre, Jean-Paul", "Jean Racine"))

    def test_accepte_toujours_le_bon_auteur_dans_une_notice_a_deux_createurs(self):
        self.assertTrue(shares_surname("Anouilh, Jean, Sartre, Jean-Paul", "Jean Anouilh"))


class NumericTitleTests(SimpleTestCase):
    """Les titres qui finissent par un nombre ne sont pas des tomes.

    C'est la ponctuation exigée devant le nombre qui les protège : sans
    elle, « Fahrenheit 451 » devient le tome 51.
    """

    def test_un_titre_numerique_ne_porte_pas_de_tome(self):
        for titre in ("Fahrenheit 451", "1984", "Catch 22", "Le 15e homme"):
            self.assertIsNone(volume_number(titre), titre)

    def test_un_nombre_precede_d_une_ponctuation_reste_un_tome(self):
        self.assertEqual(volume_number("Vernon Subutex. 2"), "2")
        self.assertEqual(volume_number("Harry Potter, 3"), "3")

    def test_un_titre_numerique_ne_bloque_pas_l_appariement(self):
        self.assertTrue(same_volume("Fahrenheit 451", "Fahrenheit 451 : roman"))
