from django.db import models
from django.utils.timezone import now

# Create your models here.
from src.accounts.models import Organization


class Customer(models.Model):
    organization = models.ForeignKey(to=Organization, on_delete=models.CASCADE)
    # 🔑 « archived », comme sur `Book`, et PAS « is_active ».
    #
    # Deux raisons, et la seconde compte autant que la première :
    #   1. c'est le mot du produit. Un livre retiré de la circulation est
    #      « archivé » ; un membre qui n'emprunte plus l'est aussi. Deux mots
    #      pour un même geste font diverger l'interface et la documentation ;
    #   2. « is_active » existe DÉJÀ sur `User` (Django), où il veut dire
    #      « ce compte peut se connecter ». Le même nom pour deux choses
    #      différentes dans la même base est un piège à relecture.
    archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=now)
    first_name = models.CharField(max_length=255, unique=False, blank=False, null=False)
    last_name = models.CharField(max_length=255, unique=False, blank=False, null=False)
    email = models.EmailField(max_length=255, unique=False, blank=True, null=True)
    phone = models.CharField(max_length=255, unique=False, blank=True, null=True)
    language = models.CharField(max_length=25, unique=False, blank=True, null=True)
    note = models.CharField(max_length=255, unique=False, blank=True, null=True)

    class Meta:
        unique_together = [
            ["organization", "first_name", "last_name", "email"],
            ["organization", "first_name", "last_name", "phone"],
        ]
        ordering = ["first_name"]
