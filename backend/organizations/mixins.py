from rest_framework.exceptions import NotAuthenticated

from .context import get_active_organization


class OrganizationScopedMixin:
    def get_active_organization(self):
        if not self.request.user.is_authenticated:
            raise NotAuthenticated("Authentication is required.")

        if not hasattr(self, "_active_organization"):
            self._active_organization = get_active_organization(self.request)

        return self._active_organization

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["organization"] = self.get_active_organization()
        return context

    def get_queryset(self):
        raise NotImplementedError("Implement a tenant-scoped queryset.")
