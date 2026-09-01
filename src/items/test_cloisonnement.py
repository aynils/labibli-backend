"""🔴 Le prêt d'une AUTRE bibliothèque peut-il être marqué comme rendu ?"""
from rest_framework import status
from rest_framework.test import APITestCase
from django.urls import reverse

from src.helpers.tests import (
    authenticate_user, create_admin_user, create_organization, create_user,
)
from src.items.models import Book, Lending
from src.customers.models import Customer


class FuiteRetourPretTests(APITestCase):
    """🔴 Le cloisonnement sur une vue qui ÉCRIT, et hors des vues génériques."""

    def test_ne_peut_PAS_rendre_le_pret_d_une_autre_organisation(self):
        # La voisine, avec son prêt en cours.
        voisin = create_admin_user()
        organisation_voisine = create_organization(owner=voisin)
        livre = Book.objects.create(
            organization=organisation_voisine, title="Kukum", author="Michel Jean"
        )
        membre = Customer.objects.create(
            organization=organisation_voisine, first_name="Claire", last_name="Dubois"
        )
        pret = Lending.objects.create(
            organization=organisation_voisine, book=livre, customer=membre
        )

        # Nous, employée d'une organisation SANS aucun rapport.
        self.user = create_user()
        self.organization = create_organization(owner=self.user)
        authenticate_user(self)

        reponse = self.client.post(reverse("return_lending", kwargs={"pk": pret.id}))

        pret.refresh_from_db()
        self.assertIsNone(
            pret.returned_at,
            "Le prêt d'une autre bibliothèque a été marqué comme RENDU.",
        )
        self.assertIn(
            reponse.status_code,
            (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
            f"L'API a répondu {reponse.status_code} au lieu de refuser.",
        )

    def test_une_personne_SANS_organisation_est_refusee(self):
        """La garde de `has_permission`, sans laquelle la classe rend « oui ».

        `IsEmployeeOfOrganization` n'avait que `has_object_permission`. Sur une
        vue générique, DRF l'appelle depuis `get_object()` ; sur une `APIView`
        brute, jamais. La classe passait alors pour appliquée sans jamais
        s'exécuter — et rien ne le disait.
        """
        proprietaire = create_admin_user()
        organisation = create_organization(owner=proprietaire)
        livre = Book.objects.create(
            organization=organisation, title="Kukum", author="Michel Jean"
        )
        membre = Customer.objects.create(
            organization=organisation, first_name="Claire", last_name="Dubois"
        )
        pret = Lending.objects.create(
            organization=organisation, book=livre, customer=membre
        )

        # Authentifiée, mais rattachée à AUCUNE organisation.
        # ⚠️ Il faut le forcer : tout compte reçoit une organisation par défaut
        # à sa création, si bien que ce cas ne se produit jamais par accident.
        # Il reste atteignable — une organisation supprimée, une reprise de
        # données — et c'est la seule chose que `has_permission` protège.
        self.user = create_user()
        self.user.employee_of_organization = None
        self.user.save()
        authenticate_user(self)

        reponse = self.client.post(reverse("return_lending", kwargs={"pk": pret.id}))

        pret.refresh_from_db()
        self.assertIsNone(pret.returned_at)
        self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)
