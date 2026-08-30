"""Tests des sources de métadonnées : réessai et résumé Wikipédia.

Rien ici ne touche le réseau. Ce qui est éprouvé, c'est la conduite du
lookup face à des services qui répondent mal — et le refus de coller un
résumé qu'on n'a pas prouvé.
"""
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
