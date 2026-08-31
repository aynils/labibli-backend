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


def split_authors(author: str) -> list:
    """Découpe une mention d'auteur en personnes distinctes.

    « et », « & », « ; » et « / » séparent toujours. La virgule, elle, est
    ambiguë : « Anouilh, Jean » est une personne écrite à l'envers, tandis
    que « Jean Anouilh, Sophie Hanna » en désigne deux. On tranche sur ce qui
    suit la virgule — un mot seul est un prénom, plusieurs mots sont un autre
    auteur.
    """
    segments = []
    for part in re.split(r"\bet\b|[;&/]", author):
        pieces = [piece.strip() for piece in part.split(",") if piece.strip()]
        index = 0
        while index < len(pieces):
            suivant = pieces[index + 1] if index + 1 < len(pieces) else None
            if suivant and len(suivant.split()) == 1:
                # « Nom, Prénom » : une seule personne, le nom d'abord. Les
                # paires se consomment deux par deux, sinon une notice à
                # plusieurs créateurs — « Anouilh, Jean, Racine, Jean », que
                # la BnF produit pour un auteur et son traducteur — rendrait
                # les prénoms comme noms de famille acceptables.
                segments.append(pieces[index])
                index += 2
            else:
                segments.append(pieces[index])
                index += 1
    return segments


def surname_candidates(author: str) -> list:
    """Les noms de famille probables d'une mention d'auteur.

    Un inventaire écrit « Prénom Nom », un catalogue « Nom, Prénom » : dans
    les deux cas le nom de famille est le mot qui identifie, le prénom ne
    prouve rien. « Antigone / Jean Anouilh » et « Antigone / Jean Racine »
    partagent la moitié de leurs mots — assez pour passer un seuil, pas
    assez pour être le même livre.

    Une mention peut porter plusieurs auteurs (« Diane Summers et Eric
    Valli ») : chaque segment donne son propre candidat.

    ⚠️ Toutes les virgules ne séparent pas des personnes. Les catalogues
    écrivent « Anouilh, Jean » pour UNE personne, et couper là rendrait
    « jean » comme nom de famille acceptable : la couverture de l'Antigone de
    Racine passait alors pour celle d'Anouilh. Une virgule suivie d'un seul
    mot est donc lue comme « Nom, Prénom », pas comme deux auteurs.
    """
    if not author:
        return []
    names = []
    for segment in split_authors(author):
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


# Le numéro de tome, sous les formes qu'un inventaire tenu à la main emploie.
# L'ordre compte : « tome 2 » est explicite, « (6) » l'est presque, un nombre
# collé à un tiret ne l'est qu'en dernier recours.
VOLUME_PATTERNS = (
    re.compile(r"\b(?:tomes?|t\.|vol\.?|volumes?)\s*(\d{1,3})\b", re.IGNORECASE),
    re.compile(r"[\(\[](\d{1,3})[\)\]]\s*$"),
    re.compile(r"\s(\d{1,3})\s*[-–—:]"),
    # Les catalogues numérotent sans marqueur : « Vernon Subutex. 2 ».
    # ⚠️ C'est la PONCTUATION exigée devant le nombre qui protège les titres
    # numériques — sans elle, « Fahrenheit 451 » devient un tome 51 et
    # « 1984 » un tome 84. La borne à deux chiffres ne fait que réduire la
    # casse. Retirer l'une ou l'autre rouvre le défaut.
    re.compile(r"[.,]\s*(\d{1,2})\s*$"),
)


def volume_number(title: str) -> str:
    """Le numéro de tome porté par un titre, s'il en porte un."""
    if not title:
        return None
    for pattern in VOLUME_PATTERNS:
        found = pattern.search(title)
        if found:
            return found.group(1).lstrip("0") or "0"
    return None


def volume_numbers(title: str) -> set:
    """TOUS les numéros de tome cités par un titre.

    Sert à reconnaître les recueils : la BnF publie « Vernon Subutex. Tome 1,
    tome 2, tome 3 » pour l'intégrale des trois volumes.
    """
    if not title:
        return set()
    numbers = set()
    for pattern in VOLUME_PATTERNS:
        for found in pattern.finditer(title):
            numbers.add(found.group(1).lstrip("0") or "0")
    return numbers


def same_volume(wanted: str, candidate: str) -> bool:
    """Vrai si le candidat ne contredit pas le tome demandé.

    Un titre sans tome n'impose rien. Un titre qui en porte un exige que le
    candidat porte le même : sans ce contrôle, « Vernon subutex tome 2 » et
    « tome 3 » recevaient le MÊME ISBN, donc la même couverture et le même
    résumé — constaté en production le 31/08/2026.
    """
    number = volume_number(wanted)
    if number is None:
        return True
    # Un recueil n'est pas le tome qu'on cherche. « Vernon Subutex. Tome 1,
    # tome 2, tome 3 » est l'intégrale : elle contient bien le tome demandé,
    # mais lui attribuer cet ISBN donnerait à deux fiches distinctes la même
    # couverture et le même résumé. Mieux vaut aucun ISBN qu'un ISBN commun.
    if len(volume_numbers(candidate)) > 1:
        return False
    if volume_number(candidate) == number:
        return True
    return number in normalize(candidate).split()
