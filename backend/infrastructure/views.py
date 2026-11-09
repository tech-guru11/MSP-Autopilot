from django.db.models import Q
from organizations.mixins import OrganizationScopedMixin
from organizations.permissions import IsOrganizationEngineer
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

from .models import Asset
from .serializers import AssetSerializer


class AssetViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    serializer_class = AssetSerializer
    permission_classes = [IsOrganizationEngineer]

    def get_queryset(self):
        organization = self.get_active_organization()
        queryset = Asset.objects.filter(
            customer__organization=organization
        ).select_related("customer")

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(external_identifier__icontains=search)
                | Q(customer__name__icontains=search)
            )

        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        asset_type = self.request.query_params.get("asset_type")
        if asset_type:
            queryset = queryset.filter(asset_type=asset_type)

        customer_id = self.request.query_params.get("customer")
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)

        ordering = self.request.query_params.get("ordering")
        allowed_ordering = {
            "name",
            "-name",
            "status",
            "-status",
            "asset_type",
            "-asset_type",
            "created_at",
            "-created_at",
            "updated_at",
            "-updated_at",
        }
        if ordering in allowed_ordering:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by("name")

        return queryset

    def perform_create(self, serializer):
        organization = self.get_active_organization()

        customer = serializer.validated_data["customer"]

        if customer.organization_id != organization.id:
            raise ValidationError(
                "This customer does not belong to your organization."
            )

        serializer.save()
