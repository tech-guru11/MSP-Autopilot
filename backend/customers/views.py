from django.db.models import Q
from organizations.mixins import OrganizationScopedMixin
from organizations.permissions import IsOrganizationEngineer
from rest_framework import viewsets

from .models import Customer
from .serializers import CustomerSerializer


class CustomerViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    permission_classes = [IsOrganizationEngineer]

    def get_queryset(self):
        organization = self.get_active_organization()
        queryset = Customer.objects.filter(organization=organization)

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(contact_email__icontains=search)
            )

        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        ordering = self.request.query_params.get("ordering")
        allowed_ordering = {
            "name",
            "-name",
            "status",
            "-status",
            "created_at",
            "-created_at",
            "updated_at",
            "-updated_at",
        }
        if ordering in allowed_ordering:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by("name")

        return queryset.distinct()

    def perform_create(self, serializer):
        organization = self.get_active_organization()

        serializer.save(organization=organization)
