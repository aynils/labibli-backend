from rest_framework import generics, permissions

from src.customers.membership import find_removed, remove
from src.customers.models import Customer
from src.customers.serializers import CustomerSerializer
from src.labibli import permissions as custom_permissions


class CustomerDetail(generics.RetrieveUpdateDestroyAPIView):
    """Consulter, modifier ou retirer un membre.

    L'édition et le retrait manquaient à l'interface comme à l'API : on
    pouvait inscrire un membre, jamais corriger son courriel ni le sortir
    des listes.
    """

    permission_classes = [
        permissions.IsAuthenticated,
        custom_permissions.IsEmployeeOfOrganization,
    ]
    serializer_class = CustomerSerializer

    def get_queryset(self):
        """🔴 Le cloisonnement, en plus de la permission d'objet.

        `IsEmployeeOfOrganization` compare bien `obj.organization` à celle
        de l'utilisateur, mais c'est une seconde barrière, pas la première :
        un queryset non filtré laisse l'existence d'une fiche d'une autre
        bibliothèque se déduire d'un 403 là où il faut un 404, et il suffit
        qu'une vue oublie la permission pour que tout s'ouvre. Le filtre est
        ici parce que c'est ici qu'il ne peut pas être oublié.
        """
        return Customer.objects.filter(
            organization=self.request.user.employee_of_organization
        )

    def perform_destroy(self, instance):
        """Retirer, pas supprimer — voir `src/customers/membership.py`.

        `Lending.customer` est en `on_delete=CASCADE` : un `delete()` réel
        emporterait l'historique des prêts, que la documentation promet de
        conserver.
        """
        remove(instance)


class CustomersList(generics.ListCreateAPIView):
    permission_classes = [
        permissions.IsAuthenticated,
        custom_permissions.IsEmployeeOfOrganization,
    ]
    serializer_class = CustomerSerializer

    def get_queryset(self):
        user = self.request.user
        # `select_related` : le sérialiseur rend `organization.name`, donc
        # sans lui chaque ligne de la liste traverse la clé étrangère —
        # mesuré à 31 requêtes sur `accounts_organization` pour 30 membres.
        return (
            Customer.objects.filter(
                organization=user.employee_of_organization, is_active=True
            )
            .select_related("organization")
        )

    def perform_create(self, serializer):
        """Inscrit le membre, ou réinscrit la fiche retirée qu'il désigne.

        Sans ce détour, rajouter un membre qu'on venait de retirer se
        heurtait à `unique_together` et rendait le texte brut de l'erreur
        Postgres, sans dire que la fiche existait toujours, masquée.
        """
        organization = self.request.user.employee_of_organization
        data = serializer.validated_data
        removed = find_removed(
            organization_id=organization.id if organization else None,
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            email=data.get("email"),
            phone=data.get("phone"),
        )
        if removed is not None:
            serializer.instance = removed
        serializer.save(organization=organization, is_active=True)
