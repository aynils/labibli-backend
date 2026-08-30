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
from src.items.book_lookup import get_with_retry, get_wikipedia_fr_summary


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


class FindBookDetailsTests(SimpleTestCase):
    def test_complete_un_resume_manquant_par_wikipedia(self):
        book = {"title": "Kukum", "author": "Michel Jean", "description": None}
        with patch.object(book_lookup, "get_book_information", return_value=book), \
             patch.object(book_lookup, "get_cover", return_value=None), \
             patch.object(book_lookup, "get_wikipedia_fr_summary", return_value="Un résumé.") as wikipedia:
            details = book_lookup.find_book_details(isbn="9782764813447")
        self.assertEqual(details.description, "Un résumé.")
        wikipedia.assert_called_once()

    def test_ne_remplace_pas_un_resume_deja_obtenu(self):
        book = {"title": "Kukum", "author": "Michel Jean", "description": "Le résumé du catalogue."}
        with patch.object(book_lookup, "get_book_information", return_value=book), \
             patch.object(book_lookup, "get_cover", return_value=None), \
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
