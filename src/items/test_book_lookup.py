"""Tests des sources de métadonnées : réessai et résumé Wikipédia.

Rien ici ne touche le réseau. Ce qui est éprouvé, c'est la conduite du
lookup face à des services qui répondent mal — et le refus de coller un
résumé qu'on n'a pas prouvé.
"""
import time
from contextlib import ExitStack, contextmanager
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from src.items import book_lookup
from src.items.book_lookup import (
    get_cover_by_title,
    get_with_retry,
    get_wikipedia_fr_summary,
    with_best_cover,
)


def response(status_code=200, payload=None):
    fake = Mock()
    fake.status_code = status_code
    fake.json.return_value = payload if payload is not None else {}
    return fake


class RetryTests(SimpleTestCase):
    def test_rend_la_reponse_du_premier_coup_quand_le_service_repond(self):
        with patch.object(book_lookup.requests, "get", return_value=response(200)) as get:
            result = get_with_retry("https://exemple.test")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(get.call_count, 1)

    def test_reessaie_apres_un_503_puis_reussit(self):
        """Google Books alterne les 503 : c'est le cas qui vidait les fiches."""
        with patch.object(book_lookup, "RETRY_PAUSE", 0), \
             patch.object(book_lookup.requests, "get",
                          side_effect=[response(503), response(200)]) as get:
            result = get_with_retry("https://exemple.test")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(get.call_count, 2)

    def test_abandonne_apres_les_tentatives_prevues(self):
        with patch.object(book_lookup, "RETRY_PAUSE", 0), \
             patch.object(book_lookup.requests, "get", return_value=response(503)) as get:
            result = get_with_retry("https://exemple.test")
        self.assertIsNone(result)
        self.assertEqual(get.call_count, book_lookup.RETRY_ATTEMPTS)

    def test_ne_reessaie_pas_un_quota_epuise(self):
        """Un 429 annonce un quota épuisé, que trois tentatives ne rouvrent pas.

        Insister coûterait 1,2 s par ouvrage pour le même échec, sur un
        import de collection entière.
        """
        with patch.object(book_lookup.requests, "get", return_value=response(429)) as get:
            result = get_with_retry("https://exemple.test")
        self.assertEqual(result.status_code, 429)
        self.assertEqual(get.call_count, 1)

    def test_annonce_un_quota_epuise(self):
        """Un quota épuisé ne doit pas être silencieux.

        Sur un import de collection entière, tout ce qui suit revient vide :
        sans trace, la fin du fichier se dégrade sans que rien ne l'annonce.
        C'est la classe de panne du 18/08.
        """
        with patch.object(book_lookup, "quota_announced", set()), \
             patch.object(book_lookup.requests, "get", return_value=response(429)), \
             self.assertLogs("src.items.book_lookup", level="WARNING") as journal:
            result = get_with_retry("https://exemple.test")
            get_with_retry("https://exemple.test")
        self.assertEqual(result.status_code, 429)
        self.assertIn("Quota", journal.output[0])
        # Une seule fois : sur 927 lignes, l'avertissement noierait le reste.
        self.assertEqual(len(journal.output), 1)

    def test_ne_reessaie_pas_une_reponse_definitive(self):
        """Un 404 est une réponse : insister ne changerait rien."""
        with patch.object(book_lookup.requests, "get", return_value=response(404)) as get:
            result = get_with_retry("https://exemple.test")
        self.assertEqual(result.status_code, 404)
        self.assertEqual(get.call_count, 1)


class WikipediaSummaryTests(SimpleTestCase):
    def summary(self, page_type="standard", extract=""):
        return response(200, {"type": page_type, "extract": extract})

    def test_rend_le_resume_quand_l_article_cite_l_auteur(self):
        extract = "Pélagie-la-Charrette est le septième roman de l'autrice acadienne Antonine Maillet."
        with patch.object(book_lookup, "search_wikipedia_fr_articles", return_value=["Pélagie-la-Charrette"]), \
             patch.object(book_lookup.requests, "get", return_value=self.summary(extract=extract)):
            result = get_wikipedia_fr_summary(title="Pélagie-la-Charrette", author="Antonine Maillet")
        self.assertEqual(result, extract)

    def test_ecarte_une_page_d_homonymie(self):
        """« Anges et démons » est une page d'homonymie, pas un livre."""
        with patch.object(book_lookup, "search_wikipedia_fr_articles", return_value=["Anges et démons"]), \
             patch.object(book_lookup.requests, "get",
                          return_value=self.summary("disambiguation", "Anges et Démons est le titre de plusieurs œuvres")):
            result = get_wikipedia_fr_summary(title="Anges et démons", author="Dan Brown")
        self.assertIsNone(result)

    def test_refuse_un_article_qui_ne_parle_pas_du_bon_auteur(self):
        """Le garde-fou contre le résumé d'un homonyme.

        Un résumé faux sur la fiche d'une bibliothèque est pire qu'une fiche
        sans résumé : personne ne va le vérifier.
        """
        with patch.object(book_lookup, "search_wikipedia_fr_articles", return_value=["Le Mur"]), \
             patch.object(book_lookup.requests, "get",
                          return_value=self.summary(extract="Le Mur est un film de Yılmaz Güney sorti en 1983.")):
            result = get_wikipedia_fr_summary(title="Le Mur", author="Jean-Paul Sartre")
        self.assertIsNone(result)

    def test_s_abstient_quand_l_auteur_est_inconnu(self):
        """Sans auteur, aucun appariement ne peut se prouver."""
        with patch.object(book_lookup, "search_wikipedia_fr_articles", return_value=["Un titre"]), \
             patch.object(book_lookup.requests, "get", return_value=self.summary(extract="Un texte quelconque.")):
            result = get_wikipedia_fr_summary(title="Un titre", author="")
        self.assertIsNone(result)

    def test_essaie_l_article_suivant_si_le_premier_ne_convient_pas(self):
        pages = [
            self.summary("disambiguation", "plusieurs œuvres"),
            self.summary(extract="Kukum est un roman de Michel Jean paru en 2019."),
        ]
        with patch.object(book_lookup, "search_wikipedia_fr_articles", return_value=["Kukum", "Kukum (roman)"]), \
             patch.object(book_lookup.requests, "get", side_effect=pages):
            result = get_wikipedia_fr_summary(title="Kukum", author="Michel Jean")
        self.assertIn("Michel Jean", result)

    def test_sans_titre_il_n_y_a_rien_a_chercher(self):
        self.assertIsNone(get_wikipedia_fr_summary(title="", author="Michel Jean"))

    def test_cherche_le_titre_NETTOYE_de_sa_mention_d_edition(self):
        """Ce qui est CHERCHÉ compte autant que ce qui est retenu.

        Le titre vient d'une notice de catalogue : « La servante écarlate :
        roman » ne trouve aucun article, « La servante écarlate » le trouve du
        premier coup. Le nettoyage existait pour les couvertures et pas ici :
        la moitié des fiches de la médiathèque de démonstration ressortaient
        sans résumé pour cette seule raison, le 31/08/2026.

        Sans assertion sur l'argument de recherche, on peut chercher
        n'importe quoi et la suite reste verte.
        """
        extract = "La Servante écarlate est un roman de Margaret Atwood."
        with patch.object(book_lookup, "search_wikipedia_fr_articles",
                          return_value=["La Servante écarlate"]) as cherche, \
             patch.object(book_lookup.requests, "get", return_value=self.summary(extract=extract)):
            result = get_wikipedia_fr_summary(title="La servante écarlate : roman",
                                              author="Atwood, Margaret")
        self.assertEqual(result, extract)
        self.assertEqual(cherche.call_args_list[0].kwargs["title"], "La servante écarlate")
        # L'auteur cherché est tronqué au nom de famille — « Atwood, Margaret »
        # ne rend rien tel quel.
        self.assertEqual(cherche.call_args_list[0].kwargs["author"], "Atwood")

    def test_replie_sur_la_partie_avant_le_deux_points(self):
        """« Maus : un survivant raconte » ne trouve rien, « Maus » trouve."""
        extract = "Maus est un roman graphique d'Art Spiegelman."
        with patch.object(book_lookup, "search_wikipedia_fr_articles",
                          side_effect=[[], ["Maus"]]) as cherche, \
             patch.object(book_lookup.requests, "get", return_value=self.summary(extract=extract)):
            result = get_wikipedia_fr_summary(title="Maus : un survivant raconte",
                                              author="Spiegelman, Art")
        self.assertEqual(result, extract)
        self.assertEqual([appel.kwargs["title"] for appel in cherche.call_args_list],
                         ["Maus : un survivant raconte", "Maus"])

    def test_ne_replie_jamais_sur_le_titre_d_une_serie(self):
        """⛔ Le repli rouvrait le défaut que `same_volume` a fermé.

        « Vernon Subutex : tome 2 » ne trouve rien sous son titre complet ;
        tronqué, il trouve l'article de la SÉRIE, et les trois tomes
        recevraient le même résumé. C'est exactement quand le titre complet
        échoue que le repli est seul en lice : il doit être refusé là.
        """
        with patch.object(book_lookup, "search_wikipedia_fr_articles",
                          return_value=["Vernon Subutex"]) as cherche, \
             patch.object(book_lookup.requests, "get", return_value=self.summary(
                 extract="Vernon Subutex est une trilogie de Virginie Despentes.")):
            result = get_wikipedia_fr_summary(title="Vernon Subutex : tome 2",
                                              author="Despentes, Virginie")
        self.assertIsNone(result)
        # Un seul essai : le tronqué n'est même pas construit.
        self.assertEqual(len(cherche.call_args_list), 1)

    def test_un_prenom_partage_ne_prouve_pas_l_auteur(self):
        """🔴 « Margaret Laurence » n'est pas « Margaret Atwood ».

        Le contrôle portait sur une intersection de mots quelconques : le
        prénom suffisait. C'est la leçon de `shares_surname`, écrite pour les
        couvertures et jamais appliquée aux résumés.
        """
        with patch.object(book_lookup, "search_wikipedia_fr_articles", return_value=["Un roman"]), \
             patch.object(book_lookup.requests, "get", return_value=self.summary(
                 extract="Ce roman de Margaret Laurence paraît en 1964.")):
            result = get_wikipedia_fr_summary(title="Le cycle des géants", author="Atwood, Margaret")
        self.assertIsNone(result)

    def test_ne_sort_pas_sur_le_reseau_sans_auteur(self):
        """Le contrôle d'auteur passe AVANT les requêtes, pas après.

        Sans lui, un ouvrage sans auteur coûtait jusqu'à deux recherches et
        six récupérations, à cinq secondes chacune, pour jeter le résultat.
        """
        with patch.object(book_lookup, "search_wikipedia_fr_articles") as cherche, \
             patch.object(book_lookup.requests, "get") as recupere:
            self.assertIsNone(get_wikipedia_fr_summary(title="Un titre", author=""))
        cherche.assert_not_called()
        recupere.assert_not_called()


class FindBookDetailsTests(SimpleTestCase):
    def test_complete_un_resume_manquant_par_wikipedia(self):
        book = {"title": "Kukum", "author": "Michel Jean", "description": None}
        with patch.object(book_lookup, "get_book_information", return_value=book), \
             patch.object(book_lookup, "get_cover", return_value=None), \
             patch.object(book_lookup, "get_cover_by_title", return_value=None), \
             patch.object(book_lookup, "get_wikipedia_fr_summary", return_value="Un résumé.") as wikipedia:
            details = book_lookup.find_book_details(isbn="9782764813447")
        self.assertEqual(details.description, "Un résumé.")
        wikipedia.assert_called_once()

    def test_ne_remplace_pas_un_resume_deja_obtenu(self):
        book = {"title": "Kukum", "author": "Michel Jean", "description": "Le résumé du catalogue."}
        with patch.object(book_lookup, "get_book_information", return_value=book), \
             patch.object(book_lookup, "get_cover", return_value=None), \
             patch.object(book_lookup, "get_cover_by_title", return_value=None), \
             patch.object(book_lookup, "get_wikipedia_fr_summary") as wikipedia:
            details = book_lookup.find_book_details(isbn="9782764813447")
        self.assertEqual(details.description, "Le résumé du catalogue.")
        wikipedia.assert_not_called()


WIKIPEDIA_BOOK = {"title": "Titre Wikipédia", "author": "Une autrice", "description": "Résumé Wikipédia"}
GOOGLE_BOOK = {"title": "Titre Google", "author": "Une autrice", "description": "Résumé Google"}
BNF_BOOK = {"title": "Titre BnF", "author": "Une autrice", "description": None}
OPEN_LIBRARY_BOOK = {"title": "Titre OpenLibrary", "author": "Une autrice", "description": "Résumé OpenLibrary"}

CATALOG_FUNCTIONS = {
    "wikipedia": "get_wikipedia_book_information",
    "google": "get_google_book_information",
    "bnf": "get_bnf_book_information",
    "open_library": "get_open_library_book_information",
}


def patch_kwargs(reply):
    """Une réponse de catalogue devient un mock, une panne devient un mock qui lève."""
    if isinstance(reply, list) or isinstance(reply, BaseException) or (
        isinstance(reply, type) and issubclass(reply, BaseException)
    ):
        return {"side_effect": reply}
    return {"return_value": reply}


@contextmanager
def catalogs(**replies):
    """Fait répondre les quatre catalogues comme le test le décide.

    Une exception passée en réponse est levée par la source : c'est ainsi
    qu'on éprouve qu'un catalogue en panne n'emporte pas les autres.
    """
    with ExitStack() as stack:
        mocks = {}
        for key, name in CATALOG_FUNCTIONS.items():
            reply = replies.get(key)
            mocks[key] = stack.enter_context(
                patch.object(book_lookup, name, **patch_kwargs(reply))
            )
        yield mocks


class FetchInParallelTests(SimpleTestCase):
    def test_rend_un_resultat_par_nom(self):
        results = book_lookup.fetch_in_parallel({"un": lambda: 1, "deux": lambda: 2})
        self.assertEqual(results, {"un": 1, "deux": 2})

    def test_isole_la_tache_qui_leve(self):
        """Une source qui casse ne doit jamais emporter les autres."""
        def panne():
            raise ValueError("le catalogue a rendu du charabia")

        results = book_lookup.fetch_in_parallel({"panne": panne, "saine": lambda: "ça va"})
        self.assertIsNone(results["panne"])
        self.assertEqual(results["saine"], "ça va")

    def test_supporte_l_absence_de_tache(self):
        self.assertEqual(book_lookup.fetch_in_parallel({}), {})


class SourcePreferenceTests(SimpleTestCase):
    """L'ordre Wikipédia → Google → BnF → OpenLibrary est une préférence de
    qualité de notice : la parallélisation ne doit rien y changer."""

    def test_wikipedia_l_emporte_quand_les_quatre_repondent(self):
        with catalogs(wikipedia=dict(WIKIPEDIA_BOOK), google=dict(GOOGLE_BOOK),
                      bnf=dict(BNF_BOOK), open_library=dict(OPEN_LIBRARY_BOOK)):
            book = book_lookup.get_book_information(isbn="9782070368228")
        self.assertEqual(book["title"], "Titre Wikipédia")

    def test_google_prend_le_relais_quand_wikipedia_se_tait(self):
        with catalogs(google=dict(GOOGLE_BOOK), bnf=dict(BNF_BOOK),
                      open_library=dict(OPEN_LIBRARY_BOOK)):
            book = book_lookup.get_book_information(isbn="9782070368228")
        self.assertEqual(book["title"], "Titre Google")

    def test_la_bnf_passe_avant_openlibrary(self):
        """La BnF est la meilleure source du francophone : elle ne cède
        qu'aux deux premières."""
        with catalogs(bnf=dict(BNF_BOOK), open_library=dict(OPEN_LIBRARY_BOOK)):
            book = book_lookup.get_book_information(isbn="9782070368228")
        self.assertEqual(book["title"], "Titre BnF")

    def test_openlibrary_est_le_dernier_recours(self):
        with catalogs(open_library=dict(OPEN_LIBRARY_BOOK)):
            book = book_lookup.get_book_information(isbn="9782070368228")
        self.assertEqual(book["title"], "Titre OpenLibrary")

    def test_rend_rien_quand_aucun_catalogue_ne_repond(self):
        with catalogs():
            self.assertIsNone(book_lookup.get_book_information(isbn="9782070368228"))

    def test_google_complete_le_resume_manquant_de_wikipedia(self):
        muette = dict(WIKIPEDIA_BOOK, description=None)
        with catalogs(wikipedia=muette, google=dict(GOOGLE_BOOK)):
            book = book_lookup.get_book_information(isbn="9782070368228")
        self.assertEqual(book["title"], "Titre Wikipédia")
        self.assertEqual(book["description"], "Résumé Google")

    def test_la_bnf_reprend_le_resume_de_google_a_la_seconde_tentative(self):
        """Une notice BnF n'a pas de résumé, et Google alterne les 503 : la
        seconde chance de la cascade doit survivre à la parallélisation."""
        with catalogs(bnf=dict(BNF_BOOK), google=[None, dict(GOOGLE_BOOK)]) as mocks:
            book = book_lookup.get_book_information(isbn="9782070368228")
        self.assertEqual(book["title"], "Titre BnF")
        self.assertEqual(book["description"], "Résumé Google")
        self.assertEqual(mocks["google"].call_count, 2)


class ParallelLookupTests(SimpleTestCase):
    def test_interroge_les_quatre_catalogues_meme_si_wikipedia_repond(self):
        """La préférence se joue au dépouillement, pas à l'appel : c'est ce
        qui permet de tout lancer de front."""
        with catalogs(wikipedia=dict(WIKIPEDIA_BOOK), google=dict(GOOGLE_BOOK),
                      bnf=dict(BNF_BOOK), open_library=dict(OPEN_LIBRARY_BOOK)) as mocks:
            book_lookup.get_book_information(isbn="9782070368228")
        for key, mock in mocks.items():
            self.assertEqual(mock.call_count, 1, f"{key} n'a pas été interrogé")

    def test_les_catalogues_partent_ensemble(self):
        """Quatre sources d'un quart de seconde doivent coûter un quart de
        seconde, pas une seconde : c'est tout l'objet du changement."""
        def lente(reply):
            def source(isbn):
                time.sleep(0.25)
                return dict(reply) if reply else None
            return source

        with ExitStack() as stack:
            for key, name in CATALOG_FUNCTIONS.items():
                reply = OPEN_LIBRARY_BOOK if key == "open_library" else None
                stack.enter_context(patch.object(book_lookup, name, lente(reply)))
            start = time.perf_counter()
            book = book_lookup.get_book_information(isbn="9782070368228")
            elapsed = time.perf_counter() - start

        self.assertEqual(book["title"], "Titre OpenLibrary")
        self.assertLess(elapsed, 0.6)

    def test_un_catalogue_en_panne_ne_fait_pas_tomber_le_lookup(self):
        """Le scan d'une bibliothécaire ne doit pas échouer parce qu'un
        catalogue rend du charabia : les autres suffisent."""
        with catalogs(wikipedia=ValueError("réponse illisible"),
                      google=dict(GOOGLE_BOOK), bnf=dict(BNF_BOOK)):
            book = book_lookup.get_book_information(isbn="9782070368228")
        self.assertEqual(book["title"], "Titre Google")

    def test_une_panne_de_la_source_preferee_laisse_descendre_la_hierarchie(self):
        with catalogs(wikipedia=ValueError("réponse illisible"),
                      google=RuntimeError("réseau coupé"),
                      bnf=dict(BNF_BOOK), open_library=dict(OPEN_LIBRARY_BOOK)):
            book = book_lookup.get_book_information(isbn="9782070368228")
        self.assertEqual(book["title"], "Titre BnF")

    def test_la_couverture_est_cherchee_pendant_que_les_catalogues_repondent(self):
        def lente(*args, **kwargs):
            time.sleep(0.25)
            return "https://exemple.test/couverture.jpg"

        with patch.object(book_lookup, "get_book_information",
                          side_effect=lambda isbn: (time.sleep(0.25), dict(GOOGLE_BOOK))[1]), \
             patch.object(book_lookup, "get_cover", side_effect=lente):
            start = time.perf_counter()
            details = book_lookup.find_book_details(isbn="9782070368228")
            elapsed = time.perf_counter() - start

        self.assertEqual(details.picture, "https://exemple.test/couverture.jpg")
        self.assertLess(elapsed, 0.4)


class BestCoverTests(SimpleTestCase):
    """La notice préférée n'a pas toujours l'image.

    Wikipédia est la source préférée et ne rend JAMAIS de couverture : sans
    cet emprunt, celle que Google ou la BnF avaient déjà rendue était perdue.
    Mesuré sur un import réel : 11 couvertures pour 24 ouvrages trouvés.
    """

    def test_emprunte_la_couverture_d_une_autre_source(self):
        book = {"title": "Kukum", "cover": None}
        catalogs = {"google": {"cover": "https://exemple.test/google.jpg"}, "bnf": None}
        self.assertEqual(with_best_cover(book, catalogs)["cover"], "https://exemple.test/google.jpg")

    def test_ne_remplace_pas_une_couverture_deja_presente(self):
        book = {"cover": "https://exemple.test/sienne.jpg"}
        catalogs = {"google": {"cover": "https://exemple.test/google.jpg"}}
        self.assertEqual(with_best_cover(book, catalogs)["cover"], "https://exemple.test/sienne.jpg")

    def test_suit_l_ordre_de_preference_des_images(self):
        book = {"cover": None}
        catalogs = {
            "google": {"cover": "https://exemple.test/google.jpg"},
            "bnf": {"cover": "https://exemple.test/bnf.jpg"},
        }
        self.assertEqual(with_best_cover(book, catalogs)["cover"], "https://exemple.test/google.jpg")

    def test_se_rabat_sur_la_source_suivante(self):
        book = {"cover": None}
        catalogs = {"google": None, "bnf": {"cover": "https://exemple.test/bnf.jpg"}}
        self.assertEqual(with_best_cover(book, catalogs)["cover"], "https://exemple.test/bnf.jpg")

    def test_reste_sans_image_si_personne_n_en_a(self):
        book = {"cover": None}
        self.assertIsNone(with_best_cover(book, {"google": None, "bnf": {"cover": None}})["cover"])

    def test_n_emprunte_que_l_image_pas_les_metadonnees(self):
        """La source des métadonnées ne doit pas changer d'un iota."""
        book = {"title": "Kukum", "author": "Michel Jean", "cover": None}
        catalogs = {"google": {"title": "AUTRE", "author": "AUTRE", "cover": "https://exemple.test/g.jpg"}}
        result = with_best_cover(book, catalogs)
        self.assertEqual(result["title"], "Kukum")
        self.assertEqual(result["author"], "Michel Jean")


class CoverByTitleTests(SimpleTestCase):
    """Le rattrapage des éditions de club.

    Les inventaires de médiathèque listent des éditions France Loisirs ou
    Grand Livre du Mois, dont l'ISBN n'est référencé nulle part alors que
    l'œuvre a des couvertures partout. Mesuré : 6 récupérations sur 10.
    """

    def open_library(self, docs):
        return response(200, {"docs": docs})

    def test_retient_la_couverture_d_une_autre_edition(self):
        docs = [{"cover_i": 42, "title": "Vipère au poing", "author_name": ["Hervé Bazin"]}]
        with patch.object(book_lookup, "get_with_retry", return_value=self.open_library(docs)):
            url = get_cover_by_title(title="Vipère au poing", author="Hervé Bazin")
        self.assertEqual(url, "https://covers.openlibrary.org/b/id/42-L.jpg")

    def test_refuse_la_couverture_d_un_autre_ouvrage(self):
        """Le garde-fou qui compte : une jaquette fausse est pire que rien."""
        docs = [{"cover_i": 42, "title": "Le Grand Meaulnes", "author_name": ["Alain-Fournier"]}]
        with patch.object(book_lookup, "get_with_retry", return_value=self.open_library(docs)):
            url = get_cover_by_title(title="Vipère au poing", author="Hervé Bazin")
        self.assertIsNone(url)

    def test_refuse_un_autre_titre_du_meme_auteur(self):
        """Ce cas est tenu par le SEUIL, pas par le nom de l'auteur.

        Sans lui, le seuil était décoratif : le ramener à 0 ne cassait aucun
        test, alors qu'il accepte alors n'importe quel titre.
        """
        docs = [{"cover_i": 42, "title": "Cri de la chouette", "author_name": ["Hervé Bazin"]}]
        with patch.object(book_lookup, "get_with_retry", return_value=self.open_library(docs)):
            url = get_cover_by_title(title="Vipère au poing", author="Hervé Bazin")
        self.assertIsNone(url)

    def test_refuse_la_couverture_d_un_autre_tome(self):
        """Le seuil de titre est aveugle au numéro : 0,94 entre deux tomes.

        Sans contrôle de tome ici, deux volumes dont on vient de séparer les
        ISBN se verraient redonner la même jaquette.
        """
        docs = [{"cover_i": 42, "title": "Vernon Subutex 1", "author_name": ["Virginie Despentes"]}]
        with patch.object(book_lookup, "get_with_retry", return_value=self.open_library(docs)):
            url = get_cover_by_title(title="Vernon Subutex. 2", author="Despentes, Virginie")
        self.assertIsNone(url)

    def test_accepte_la_couverture_du_bon_tome(self):
        docs = [{"cover_i": 42, "title": "Vernon Subutex. 2", "author_name": ["Virginie Despentes"]}]
        with patch.object(book_lookup, "get_with_retry", return_value=self.open_library(docs)):
            url = get_cover_by_title(title="Vernon Subutex. 2", author="Despentes, Virginie")
        self.assertEqual(url, "https://covers.openlibrary.org/b/id/42-L.jpg")

    def test_refuse_un_homonyme_avec_l_auteur_ecrit_par_le_catalogue(self):
        """La forme réelle du site d'appel, « Anouilh, Jean ».

        L'auteur vient d'une NOTICE, pas de l'inventaire : la virgule y sépare
        le nom du prénom, et la lire comme un séparateur de co-auteurs faisait
        de « jean » un nom de famille acceptable — la couverture de l'Antigone
        de Racine passait pour celle d'Anouilh.
        """
        docs = [{"cover_i": 42, "title": "Antigone", "author_name": ["Jean Racine"]}]
        with patch.object(book_lookup, "get_with_retry", return_value=self.open_library(docs)):
            url = get_cover_by_title(title="Antigone", author="Anouilh, Jean")
        self.assertIsNone(url)

    def test_accepte_le_bon_auteur_ecrit_par_le_catalogue(self):
        docs = [{"cover_i": 42, "title": "Antigone", "author_name": ["Jean Anouilh"]}]
        with patch.object(book_lookup, "get_with_retry", return_value=self.open_library(docs)):
            url = get_cover_by_title(title="Antigone", author="Anouilh, Jean")
        self.assertEqual(url, "https://covers.openlibrary.org/b/id/42-L.jpg")

    def test_refuse_un_homonyme_de_prenom(self):
        docs = [{"cover_i": 42, "title": "Antigone", "author_name": ["Jean Racine"]}]
        with patch.object(book_lookup, "get_with_retry", return_value=self.open_library(docs)):
            url = get_cover_by_title(title="Antigone", author="Jean Anouilh")
        self.assertIsNone(url)

    def test_se_rabat_sur_google_quand_openlibrary_n_a_rien(self):
        """Et il faut QUATRE réponses, pas deux : chaque source est interrogée
        d'abord en français, puis sans filtre.

        C'est ce qui empêche « Asterix The Gaul » de s'afficher sur une fiche
        française. Le test l'énonce en simulant la séquence complète — sans
        quoi il tombait sur un StopIteration, ce qui ressemble à une panne du
        code alors que c'est le simulacre qui est trop court.
        """
        google = response(200, {"items": [{"volumeInfo": {
            "title": "Tu vivras, mon fils", "authors": ["Pin Yathay"],
            "imageLinks": {"thumbnail": "https://exemple.test/g.jpg"}}}]})
        reponses = [self.open_library([]), self.open_library([]), google]
        with patch.object(book_lookup, "get_with_retry", side_effect=reponses) as get:
            url = get_cover_by_title(title="Tu vivras, mon fils", author="Pin yathay")
        self.assertEqual(url, "https://exemple.test/g.jpg")
        # 🔑 L'ORDRE est le correctif : le français d'abord, sans filtre ensuite.
        # Sans cette assertion, inverser les deux passages laisserait le test
        # vert tout en réintroduisant les couvertures anglaises.
        appels = [appel.args[1] for appel in get.call_args_list]
        self.assertEqual(appels[0].get("language"), "fre")
        self.assertNotIn("language", appels[1])
        self.assertEqual(appels[2].get("langRestrict"), "fr")

    def test_cherche_sans_la_mention_d_edition_du_catalogue(self):
        """Le catalogue colle « : roman » au titre ; la recherche échoue avec.

        C'est ce détail qui faisait retomber le taux de couverture de 77 % à
        46 % : les URL étaient trouvées en isolation, jamais dans la chaîne.
        """
        docs = [{"cover_i": 7, "title": "Moi d'abord", "author_name": ["Katherine Pancol"]}]
        with patch.object(book_lookup, "get_with_retry", return_value=self.open_library(docs)) as get:
            get_cover_by_title(title="Moi d'abord: roman", author="Katherine Pancol, Sophie Hanna")
        params = get.call_args[0][1]
        self.assertEqual(params["title"], "Moi d'abord")
        self.assertEqual(params["author"], "Katherine Pancol")

    def test_sans_auteur_on_ne_peut_rien_prouver(self):
        with patch.object(book_lookup, "get_with_retry") as get:
            self.assertIsNone(get_cover_by_title(title="Un titre", author=""))
        get.assert_not_called()

    def test_survit_a_des_sources_muettes(self):
        with patch.object(book_lookup, "get_with_retry", return_value=None):
            self.assertIsNone(get_cover_by_title(title="Vipère au poing", author="Hervé Bazin"))


class CoverChainTests(SimpleTestCase):
    """La chaîne, pas seulement les morceaux.

    Les tests précédents éprouvaient chaque fonction en isolation :
    neutraliser complètement le repli par titre laissait la suite verte,
    alors que c'est lui qui fait passer le taux de couverture de 40 % à 70 %.
    """

    def find(self, book, cover=None, by_title="https://exemple.test/repli.jpg"):
        with patch.object(book_lookup, "get_book_information", return_value=book), \
             patch.object(book_lookup, "get_cover", return_value=cover), \
             patch.object(book_lookup, "get_cover_by_title", return_value=by_title), \
             patch.object(book_lookup, "get_wikipedia_fr_summary", return_value=None):
            return book_lookup.find_book_details(isbn="9782764813447")

    def test_se_rabat_sur_la_recherche_par_titre(self):
        details = self.find({"title": "Kukum", "author": "Michel Jean", "cover": None})
        self.assertEqual(details.picture, "https://exemple.test/repli.jpg")

    def test_ne_se_rabat_pas_quand_l_isbn_a_deja_donne_une_image(self):
        details = self.find({"title": "Kukum", "author": "Michel Jean", "cover": None},
                            cover="https://exemple.test/isbn.jpg")
        self.assertEqual(details.picture, "https://exemple.test/isbn.jpg")

    def test_ne_se_rabat_pas_quand_la_notice_porte_une_image(self):
        details = self.find({"title": "Kukum", "author": "Michel Jean",
                             "cover": "https://exemple.test/notice.jpg"})
        self.assertEqual(details.picture, "https://exemple.test/notice.jpg")

    def test_reste_sans_image_si_le_repli_ne_trouve_rien(self):
        details = self.find({"title": "Kukum", "author": "Michel Jean", "cover": None}, by_title=None)
        self.assertIsNone(details.picture)


class CoverBorrowedFromOtherSourceTests(SimpleTestCase):
    """L'emprunt entre sources, éprouvé là où il sert.

    Les fixtures de préférence de source ne portaient aucune clé « cover » :
    remettre le comportement d'avant ne cassait donc aucun test, alors que
    c'est la cause nº 1 du taux de 40 %.
    """

    def catalogs(self, **sources):
        base = {"wikipedia": None, "google": None, "bnf": None, "open_library": None}
        base.update(sources)
        return base

    def test_wikipedia_emprunte_l_image_de_google(self):
        wikipedia = {"title": "Kukum", "description": "Un résumé.", "cover": None}
        google = {"title": "Kukum", "description": "Autre", "cover": "https://exemple.test/g.jpg"}
        with patch.object(book_lookup, "fetch_in_parallel",
                          return_value=self.catalogs(wikipedia=wikipedia, google=google)):
            book = book_lookup.get_book_information(isbn="9782764813447")
        self.assertEqual(book["cover"], "https://exemple.test/g.jpg")
        # La notice reste celle de Wikipédia : seule l'image est empruntée.
        self.assertEqual(book["description"], "Un résumé.")

    def test_wikipedia_emprunte_l_image_de_la_bnf_faute_de_google(self):
        wikipedia = {"title": "Kukum", "description": "Un résumé.", "cover": None}
        bnf = {"title": "Kukum", "cover": "https://exemple.test/bnf.jpg"}
        with patch.object(book_lookup, "fetch_in_parallel",
                          return_value=self.catalogs(wikipedia=wikipedia, bnf=bnf)):
            book = book_lookup.get_book_information(isbn="9782764813447")
        self.assertEqual(book["cover"], "https://exemple.test/bnf.jpg")
