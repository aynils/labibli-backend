"""Les paliers de relance : « 0, 7, 30 » veut dire trois relances, puis rien.

Ce module ne connaît ni la base ni les courriels. Il répond à deux questions,
et elles se relisent seules :

  * `normaliser_paliers` — cette valeur est-elle acceptable, et sous quelle
    forme la range-t-on ?
  * `palier_atteint` — pour un retard de N jours, quel palier est franchi ?

🔑 Pourquoi une suite de paliers et non un intervalle. Un intervalle
(« tous les sept jours ») se répète SANS FIN : une personne qui ne rend jamais
son livre reçoit un courriel par semaine, indéfiniment, en notre nom et au nom
de sa bibliothèque. Ce n'est plus une relance, c'est du harcèlement
automatisé. Une suite finit — et sa longueur répond du même coup à la question
« combien de rappels envoie-t-on ? », qui n'avait aucune réponse avant.
"""
from django.core.exceptions import ValidationError

# Douze relances pour un même prêt, c'est déjà au-delà du raisonnable ; au-delà
# c'est une faute de saisie qu'on ne veut pas laisser dormir dans la base.
MAX_PALIERS = 12

# Deux ans. « 3000 » au lieu de « 30 » est la faute de frappe qu'on attend, et
# elle ne se verrait qu'en ne recevant jamais la troisième relance.
MAX_JOURS = 730

PALIERS_PAR_DEFAUT = [0, 7, 30]


def paliers_par_defaut():
    """Callable, parce qu'une liste en `default=` serait partagée par toutes
    les organisations — le piège classique de l'argument mutable."""
    return list(PALIERS_PAR_DEFAUT)


def un_entier(valeur):
    """Un entier de jours, ou une erreur. Jamais une conversion silencieuse.

    ⛔ `int(1.5)` vaut 1 : accepter un flottant transformerait « 1,5 jour » en
    « 1 jour » sans que personne ne l'apprenne. Et `isinstance(True, int)` est
    vrai en Python, d'où le refus explicite des booléens.
    """
    if isinstance(valeur, bool):
        raise ValidationError("Un palier doit être un nombre de jours, pas un booléen.")
    if isinstance(valeur, int):
        return valeur
    if isinstance(valeur, str) and valeur.strip().lstrip("-").isdigit():
        return int(valeur.strip())
    raise ValidationError(
        f"« {valeur} » n'est pas un nombre de jours. Attendu : une liste "
        "d'entiers, par exemple [0, 7, 30]."
    )


def normaliser_paliers(valeur):
    """Trie, dédoublonne, et REFUSE tout ce qui n'a pas de sens.

    🔴 Le refus doit tomber à l'écriture. Une valeur invalide découverte à 8 h
    du matin par la tâche planifiée, c'est une exception dans un journal que
    personne ne lit, et ce matin-là aucune des dix-sept organisations n'est
    servie — pas seulement celle qui a la mauvaise valeur.
    """
    if not isinstance(valeur, (list, tuple)):
        raise ValidationError(
            "Les paliers doivent être une liste de jours, par exemple [0, 7, 30]."
        )
    paliers = sorted({un_entier(element) for element in valeur})

    if not paliers:
        # ⛔ Zéro palier voudrait dire « activé, mais muet ». Deux façons de
        # dire non, et la bibliothèque ne saurait pas laquelle est vraie.
        raise ValidationError(
            "Il faut au moins un palier. Pour ne rien envoyer, décochez plutôt "
            "les rappels."
        )
    if len(paliers) > MAX_PALIERS:
        raise ValidationError(
            f"Au plus {MAX_PALIERS} paliers : au-delà, c'est autant de courriels "
            "à la même personne."
        )
    if paliers[0] < 0:
        raise ValidationError(
            "Un palier se compte en jours APRÈS l'échéance. « 0 » est le jour "
            "où le retard commence ; un nombre négatif n'a pas de sens ici."
        )
    if paliers[-1] > MAX_JOURS:
        raise ValidationError(
            f"Au plus {MAX_JOURS} jours après l'échéance. Au-delà, c'est presque "
            "toujours une faute de frappe — « 3000 » pour « 30 »."
        )
    return paliers


def palier_atteint(jours_de_retard, paliers):
    """Le plus haut palier franchi, ou `None` si aucun ne l'est encore.

    ⚠️ « Franchi », et non « atteint exactement ». La nuance porte toute la
    robustesse : si la relance du septième jour exigeait un retard de
    *exactement* sept jours, une tâche planifiée qui ne tourne pas ce matin-là
    perdrait la relance POUR TOUJOURS, en silence. Chez Feuille de temps, un
    build a échoué huit heures sans que rien ne l'annonce — c'est la panne
    ordinaire, pas le cas rare.

    Et parce que c'est le plus HAUT palier franchi qui compte, un prêt en
    retard de quarante-cinq jours le jour où la bibliothèque active les
    rappels n'en reçoit qu'un seul, le dernier — pas les trois d'un coup.
    """
    franchis = [palier for palier in paliers if palier <= jours_de_retard]
    return max(franchis) if franchis else None
