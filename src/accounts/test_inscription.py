"""L'inscription pose le nom de la bibliothèque, ou un nom qui ne fuit rien.

🔴 Ce qui est éprouvé ici a été payé en production le 01/09/2026 : le nom
d'attente contenait l'adresse courriel, il se propageait au nom de la
collection, et la vitrine publique l'affichait en titre.
"""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from src.accounts.models import NOM_PAR_DEFAUT, Organization, User
from src.items.models import Collection


class InscriptionTests(APITestCase):
    def inscrire(self, courriel="nouvelle@exemple.test", **extra):
        return self.client.post(
            reverse("signup"),
            {"email": courriel, "password": "un-mot-de-passe-solide", **extra},
        )

    def test_pose_le_nom_de_la_bibliotheque_donne(self):
        self.inscrire(organization_name="Alliance française de Siem Reap")
        organisation = User.objects.get(email="nouvelle@exemple.test").employee_of_organization
        self.assertEqual(organisation.name, "Alliance française de Siem Reap")

    def test_la_COLLECTION_prend_le_meme_nom(self):
        """C'est elle que la vitrine publique affiche en titre."""
        self.inscrire(organization_name="Médiathèque de Ligueil")
        collection = Collection.objects.get(organization__owner__email="nouvelle@exemple.test")
        self.assertEqual(collection.name, "Médiathèque de Ligueil")

    # ── ⛔ Ce qui ne doit JAMAIS arriver ─────────────────────────────────

    def test_aucun_nom_ne_contient_le_COURRIEL_sans_nom_donne(self):
        """🔴 La fuite du 01/09 : « <courriel> - default organization ».

        Elle atterrissait dans le nom de la collection, donc en titre de la
        vitrine publique — l'adresse de la direction sur une page ouverte à
        tous. Vingt-deux bibliothèques.
        """
        self.inscrire()
        organisation = User.objects.get(email="nouvelle@exemple.test").employee_of_organization
        collection = Collection.objects.get(organization=organisation)
        for nom in (organisation.name, collection.name):
            self.assertNotIn("@", nom)
            self.assertNotIn("default", nom.lower())
        self.assertEqual(organisation.name, NOM_PAR_DEFAUT)

    def test_un_courriel_DEJA_PRIS_ne_renomme_la_bibliotheque_de_personne(self):
        """⛔ Sinon un formulaire anonyme renomme une bibliothèque existante."""
        self.inscrire(organization_name="La vraie bibliothèque")
        utilisateur = User.objects.get(email="nouvelle@exemple.test")
        utilisateur.is_verified = True
        utilisateur.save()

        reponse = self.inscrire(organization_name="Tentative de renommage")

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        utilisateur.employee_of_organization.refresh_from_db()
        self.assertEqual(
            utilisateur.employee_of_organization.name, "La vraie bibliothèque"
        )

    def test_un_nom_vide_laisse_le_nom_d_attente(self):
        self.inscrire(organization_name="   ")
        organisation = User.objects.get(email="nouvelle@exemple.test").employee_of_organization
        self.assertEqual(organisation.name, NOM_PAR_DEFAUT)

    def test_l_inscription_SANS_nom_fonctionne_toujours(self):
        """Le champ est facultatif : l'ancien formulaire ne doit pas casser."""
        reponse = self.inscrire()
        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Organization.objects.filter(name=NOM_PAR_DEFAUT).count(), 1)


class AdresseDeContactTests(APITestCase):
    """L'adresse PUBLIQUE de la bibliothèque, distincte de celle du compte."""

    def test_une_nouvelle_bibliotheque_part_avec_une_adresse_de_contact(self):
        """Sans quoi sa vitrine ne dirait à personne à qui s'adresser."""
        self.client.post(
            reverse("signup"),
            {"email": "neuve@exemple.test", "password": "un-mot-de-passe-solide",
             "organization_name": "Alliance de Saint-Quentin"},
        )
        organisation = User.objects.get(email="neuve@exemple.test").employee_of_organization
        self.assertEqual(organisation.contact_email, "neuve@exemple.test")

    def test_elle_se_change_SANS_toucher_a_l_adresse_du_compte(self):
        """🔑 Tout l'intérêt du champ : la vitrine cesse de publier l'adresse
        de connexion de la propriétaire dès qu'elle en choisit une autre."""
        self.client.post(
            reverse("signup"),
            {"email": "proprietaire@exemple.test", "password": "un-mot-de-passe-solide"},
        )
        utilisateur = User.objects.get(email="proprietaire@exemple.test")
        organisation = utilisateur.employee_of_organization
        organisation.contact_email = "bibliotheque@saint-quentin.test"
        organisation.save()

        utilisateur.refresh_from_db()
        self.assertEqual(utilisateur.email, "proprietaire@exemple.test")
        self.assertEqual(
            Organization.objects.get(pk=organisation.pk).contact_email,
            "bibliotheque@saint-quentin.test",
        )
