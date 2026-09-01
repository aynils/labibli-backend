"""Une date française correcte le premier du mois.

Django écrit « 1 septembre 2026 ». Le français écrit « 1er septembre 2026 ».
L'écart ne se voit qu'un jour sur trente — mais ce jour-là, il se voit dans
chaque courriel envoyé à chaque membre de chaque bibliothèque, et c'est de la
correspondance qui porte notre nom.

⚠️ Ce filtre ne sert QUE dans les gabarits français. L'anglais n'a pas ce
problème : `date:"F j, Y"` sous `translation.override("en")` rend déjà
« September 1, 2026 ».
"""
from django import template
from django.template.defaultfilters import date as date_django

register = template.Library()


@register.filter
def date_fr(valeur):
    """« 1er septembre 2026 », « 20 août 2026 »."""
    if not valeur:
        return ""
    jour = "1er" if valeur.day == 1 else str(valeur.day)
    return f"{jour} {date_django(valeur, 'F Y')}"
