"""Comparer des titres et des noms d'auteur écrits par des humains.

Un inventaire de bibliothèque écrit « André Marcel adamek », un catalogue
« Adamek, André-Marcel », une page Wikipédia « Antonine Maillet ». Aucune
comparaison stricte ne survit à ça. Ce module tient les règles communes, et
il ne dépend de rien : `isbn_resolution` s'en sert pour juger un candidat,
`book_lookup` pour vérifier qu'un article parle bien du bon livre.
"""
import re
from difflib import SequenceMatcher

from unidecode import unidecode

# Mentions d'édition que les catalogues collent au titre et que les
# inventaires n'ont pas.
TITLE_NOISE = re.compile(
    r"\s*[:;]\s*(roman|récit|nouvelles?|essai|poèmes?|théâtre|conte[s]?|album)\b.*$",
    re.IGNORECASE,
)
ARTICLES = {"le", "la", "les", "l", "un", "une", "des", "du", "de", "d", "the", "a", "an"}


def normalize(text: str) -> str:
    """Minuscules, sans accents ni ponctuation, espaces réduits."""
    if not text:
        return ""
    text = unidecode(text).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def significant_words(text: str) -> set:
    return {word for word in normalize(text).split() if word not in ARTICLES and len(word) > 1}


def title_similarity(wanted: str, candidate: str) -> float:
    """Ressemblance de deux titres, sous-titre d'édition retiré."""
    left = normalize(TITLE_NOISE.sub("", wanted))
    right = normalize(TITLE_NOISE.sub("", candidate))
    if not left or not right:
        return 0.0
    ratio = SequenceMatcher(None, left, right).ratio()
    # « Trois petit cochons » contre « Les trois petits cochons » : le titre
    # cherché est contenu dans le candidat, c'est le même ouvrage.
    words_left, words_right = significant_words(left), significant_words(right)
    if words_left and words_left <= words_right:
        ratio = max(ratio, 0.9)
    return ratio


def author_similarity(wanted: str, candidate: str) -> float:
    """Part des mots de l'auteur cherché qu'on retrouve chez le candidat.

    Un inventaire écrit « André Marcel adamek », la BnF « Adamek,
    André-Marcel » : l'ordre et la casse ne veulent rien dire, seul le
    vocabulaire compte. Une faute de prénom ne doit pas tuer l'appariement
    si le nom de famille est là, d'où la ressemblance mot à mot.
    """
    words_wanted = significant_words(wanted)
    words_candidate = significant_words(candidate)
    if not words_wanted or not words_candidate:
        return 0.0
    hits = 0
    for word in words_wanted:
        if word in words_candidate:
            hits += 1
        elif any(SequenceMatcher(None, word, other).ratio() >= 0.85 for other in words_candidate):
            hits += 1
    return hits / len(words_wanted)


def surname_candidates(author: str) -> list:
    """Les noms de famille probables d'une mention d'auteur.

    Un inventaire écrit « Prénom Nom », un catalogue « Nom, Prénom » : dans
    les deux cas le nom de famille est le mot qui identifie, le prénom ne
    prouve rien. « Antigone / Jean Anouilh » et « Antigone / Jean Racine »
    partagent la moitié de leurs mots — assez pour passer un seuil, pas
    assez pour être le même livre.

    Une mention peut porter plusieurs auteurs (« Diane Summers et Eric
    Valli ») : chaque segment donne son propre candidat.
    """
    if not author:
        return []
    names = []
    for segment in re.split(r"\bet\b|[,;&/]", author):
        words = [word for word in normalize(segment).split() if len(word) > 1]
        if words:
            # Seul le DERNIER mot est retenu. Y ajouter le premier ferait
            # repasser le prénom, et « Jean Anouilh » redeviendrait
            # compatible avec « Jean Racine ». Le catalogue, lui, est
            # comparé sur tous ses mots : l'ordre « Nom, Prénom » y est
            # donc sans conséquence.
            names.append(words[-1])
    return names


def shares_surname(wanted: str, candidate: str) -> bool:
    """Vrai si les deux mentions ont un nom de famille en commun.

    C'est la condition qui empêche d'importer le livre d'un homonyme de
    prénom. Sans auteur d'un côté ou de l'autre, on ne peut rien prouver :
    on répond faux plutôt que d'accepter au bénéfice du doute.
    """
    wanted_names = surname_candidates(wanted)
    candidate_words = significant_words(candidate)
    if not wanted_names or not candidate_words:
        return False
    for name in wanted_names:
        if name in candidate_words:
            return True
        # Une faute de frappe sur le nom ne doit pas tout perdre.
        if any(SequenceMatcher(None, name, word).ratio() >= 0.9 for word in candidate_words):
            return True
    return False
