from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from .models import Membership, Organization
from .permissions import IsOrganizationAdmin
from .serializers import MembershipSerializer, OrganizationSerializer


class OrganizationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Organization.objects.filter(memberships__user=self.request.user)
            .distinct()
            .order_by("name")
        )


class MembershipViewSet(viewsets.ModelViewSet):
    serializer_class = MembershipSerializer
    permission_classes = [IsOrganizationAdmin]

    def get_active_organization(self):
        from .context import get_active_organization

        if not hasattr(self, "_active_organization"):
            self._active_organization = get_active_organization(self.request)
        return self._active_organization

    def get_queryset(self):
        return (
            Membership.objects.filter(
                organization=self.get_active_organization()
            )
            .select_related("organization", "user")
            .order_by("user__username")
        )

    def perform_create(self, serializer):
        serializer.save(organization=self.get_active_organization())

    def perform_destroy(self, instance):
        organization = self.get_active_organization()
        admin_count = Membership.objects.filter(
            organization=organization,
            role=Membership.Role.ADMIN,
        ).count()

        if instance.role == Membership.Role.ADMIN and admin_count <= 1:
            raise ValidationError(
                "The last organization administrator cannot be removed."
            )

        instance.delete()

    def perform_update(self, serializer):
        instance = serializer.instance
        organization = self.get_active_organization()
        new_role = serializer.validated_data.get(
            "role",
            instance.role,
        )

        admin_count = Membership.objects.filter(
            organization=organization,
            role=Membership.Role.ADMIN,
        ).count()

        if (
            instance.role == Membership.Role.ADMIN
            and new_role != Membership.Role.ADMIN
            and admin_count <= 1
        ):
            raise ValidationError(
                "The last organization administrator cannot be demoted."
            )

        try:
            serializer.save()
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
