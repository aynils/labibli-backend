"""Lecture des paramètres d'URL qui portent un oui ou un non.

Un navigateur envoie « true », un script « 1 », une personne « yes ». La
liste était recopiée dans chaque vue qui en avait besoin ; elle vit ici pour
que « archivé » et « disponible » ne se lisent pas de deux façons.
"""
TRUE_VALUES = ("true", "1", "t", "y", "yes")


def is_true(value) -> bool:
    """Vrai seulement si le paramètre demande explicitement oui.

    Un paramètre absent, vide ou incompris vaut non : ce sens par défaut est
    celui qui masque les ouvrages archivés, donc le moins surprenant.
    """
    return value is not None and str(value).strip().lower() in TRUE_VALUES


def positive_int(value, default: int) -> int:
    """Un entier strictement positif tiré d'un paramètre d'URL.

    Les vitrines sont publiques : n'importe qui peut taper `?page=abc` ou
    `?size=0`. Un `int()` nu y répondait par une erreur 500, et une taille de
    page nulle faisait tomber le paginateur. Tout ce qui n'est pas un entier
    positif retombe donc sur la valeur par défaut.
    """
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default
