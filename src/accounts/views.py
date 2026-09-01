from rest_framework import generics, permissions

from src.accounts.models import NOM_PAR_DEFAUT, Organization, User
from src.accounts.serializers import OrganizationSerializer, UserSerializer
from src.labibli import permissions as custom_permissions
from src.payment.models import Subscription
from src.payment.serializers import SubscriptionSerializer
from authemail.views import Signup as AuthemailSignup


class OrganizationCreate(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer

    def perform_create(self, serializer):
        user = self.request.user
        organization = serializer.save(owner=user)
        user.employee_of_organization = organization
        user.save()


class OrganizationDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [custom_permissions.IsOwner]
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer


class OrganizationCurrent(generics.RetrieveAPIView):
    permission_classes = [custom_permissions.IsOwner]
    serializer_class = OrganizationSerializer

    def get_object(self):
        return self.request.user.employee_of_organization


class SubscriptionCurrent(generics.RetrieveAPIView):
    permission_classes = [custom_permissions.IsEmployeeOfOrganization]
    serializer_class = SubscriptionSerializer

    def get_object(self):
        organization = self.request.user.employee_of_organization
        return (
            Subscription.objects.filter(organization=organization)
            .order_by("-created_at")
            .first()
        )


class UserList(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAdminUser]
    queryset = User.objects.all()
    serializer_class = UserSerializer


class UserDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [custom_permissions.IsSelf]
    queryset = Organization.objects.all()
    serializer_class = UserSerializer


class SignupAvecOrganisation(AuthemailSignup):
    """L'inscription d'authemail, plus le nom de la bibliothèque.

    🔑 On se place DEVANT la vue d'authemail plutôt que de la forker :
    `django-rest-authemail` est figé depuis 2023, et sa `SignupSerializer` est
    un `Serializer` à champs fixes qui ignore silencieusement tout attribut
    supplémentaire. Envoyer `organization_name` dans la charge utile ne
    suffisait donc pas — il partait au néant sans que rien ne le signale.

    ⚠️ Le nom est posé APRÈS l'appel à la vue parente, parce que c'est elle qui
    crée la personne, et que l'organisation naît d'un signal `post_save` sur
    `User`. Il n'existe aucun point d'accroche avant.

    ⛔ Et il n'est posé QUE si l'inscription a réussi. Sur un courriel déjà pris
    et vérifié, authemail rend un 400 sans rien créer : renommer là écraserait
    le nom d'une bibliothèque existante depuis un formulaire d'inscription
    anonyme.
    """

    def post(self, request, format=None):
        reponse = super().post(request, format=format)

        nom = (request.data.get("organization_name") or "").strip()
        if reponse.status_code >= 400 or not nom:
            return reponse

        # 🔴 La personne qui vient d'être créée, et elle seule. On la retrouve
        # par le courriel de la requête, pas par une recherche large.
        courriel = (request.data.get("email") or "").strip()
        utilisateur = User.objects.filter(email__iexact=courriel).first()
        if utilisateur is None or utilisateur.employee_of_organization is None:
            return reponse

        organisation = utilisateur.employee_of_organization
        organisation.name = nom[:255]
        organisation.save()
        # La collection créée par le signal porte l'ancien nom d'attente : elle
        # est le titre de la vitrine publique, elle doit suivre.
        organisation.collection_set.filter(name=NOM_PAR_DEFAUT).update(name=nom[:255])
        return reponse
