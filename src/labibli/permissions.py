from rest_framework import permissions


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the owner of the snippet.
        return obj.owner == request.user


class IsOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to access it.
    ! Not working on lists
    """

    def has_object_permission(self, request, view, obj):
        return obj.owner == request.user


class IsSelf(permissions.BasePermission):
    """
    Custom permission to only allow user to access itself.
    ! Not working on lists
    """

    def has_object_permission(self, request, view, obj):
        return obj == request.user


class IsEmployeeOfOrganization(permissions.BasePermission):
    """N'autorise l'accès qu'aux objets de l'organisation de la personne.

    ⚠️ `has_object_permission` n'est appelé QUE par les vues génériques, depuis
    `get_object()`. Sur une `APIView` brute, DRF ne l'appelle jamais : la
    permission passe alors pour appliquée alors qu'elle ne s'exécute pas.
    C'est ce qui a laissé `ReturnLending` marquer comme rendu le prêt de
    n'importe quelle bibliothèque, en production, jusqu'au 01/09/2026.

    🔑 D'où `has_permission` : il ne remplace pas le cloisonnement — seule la
    requête peut le porter — mais il ferme la porte à qui n'appartient à aucune
    organisation, et il fait échouer proprement là où la classe rendait « oui »
    par défaut. ⛔ Ne jamais s'en remettre à cette classe seule sur une
    `APIView` : la requête doit porter `organization`.
    """

    def has_permission(self, request, view):
        # `getattr` : `AnonymousUser` n'a pas cet attribut, et le lire
        # directement rendait un 500 là où il faut un 401.
        return getattr(request.user, "employee_of_organization", None) is not None

    def has_object_permission(self, request, view, obj):
        return obj.organization == request.user.employee_of_organization


class IsEmployeeOfAnOrganization(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.employee_of_organization is not None


class AllowSafeOrEmployeeOfOrganization(permissions.BasePermission):
    """
    Custom permission to only allow employees of an organization to update objects from this organization.
    ! Not working on lists
    """

    def has_permission(self, request, view):
        if (
            request.method in permissions.SAFE_METHODS
            or request.user
            and request.user.is_authenticated
            and request.user.employee_of_organization
        ):
            return True

        return False

    def has_object_permission(self, request, view, obj):
        return (
            request.method in permissions.SAFE_METHODS
            or request.user.employee_of_organization == obj.organization
        )
