from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .context import get_active_membership
from .models import Membership


class HasActiveOrganization(BasePermission):
    message = "A valid active organization is required."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        try:
            get_active_membership(request)
        except PermissionDenied:
            return False

        return True


class OrganizationRolePermission(BasePermission):
    read_roles = set(Membership.Role.values)
    write_roles = {
        Membership.Role.ADMIN,
        Membership.Role.ENGINEER,
    }
    message = "Your organization role does not allow this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        try:
            membership = get_active_membership(request)
        except PermissionDenied:
            return False

        if request.method in SAFE_METHODS:
            return membership.role in self.read_roles

        return membership.role in self.write_roles


class IsOrganizationEngineer(OrganizationRolePermission):
    pass


class IsOrganizationAdmin(OrganizationRolePermission):
    read_roles = {Membership.Role.ADMIN}
    write_roles = {Membership.Role.ADMIN}


class IsOrganizationViewer(OrganizationRolePermission):
    write_roles = set()
