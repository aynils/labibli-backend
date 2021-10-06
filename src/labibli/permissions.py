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
    /!\ Not working on lists
    """

    def has_object_permission(self, request, view, obj):
        return obj.owner == request.user


class IsSelf(permissions.BasePermission):
    """
    Custom permission to only allow user to access itself.
    /!\ Not working on lists
    """

    def has_object_permission(self, request, view, obj):
        return obj == request.user


class IsEmployeeOfOrganization(permissions.BasePermission):
    """
    Custom permission to only allow employees of an organization to access objects from this organization.
    /!\ Not working on lists
    """

    def has_object_permission(self, request, view, obj):
        return obj.organization == request.user.employee_of_organization


class IsEmployeeOfAnOrganization(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.employee_of_organization is not None


class AllowSafeOrEmployeeOfOrganization(permissions.BasePermission):
    """
    Custom permission to only allow employees of an organization to update objects from this organization.
    /!\ Not working on lists
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
