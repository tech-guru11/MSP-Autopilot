from rest_framework import serializers

from .models import Asset


class AssetSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(
        source="customer.name",
        read_only=True,
    )

    class Meta:
        model = Asset
        fields = [
            "id",
            "customer",
            "customer_name",
            "name",
            "asset_type",
            "status",
            "external_identifier",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Asset name cannot be empty.")
        return value.strip()

    def validate(self, attrs):
        organization = self.context.get("organization")
        customer = attrs.get("customer")

        if customer is None and self.instance is not None:
            customer = self.instance.customer

        if (
            organization is not None
            and customer is not None
            and customer.organization_id != organization.id
        ):
            raise serializers.ValidationError(
                {
                    "customer": (
                        "This customer does not belong to your organization."
                    )
                }
            )

        return attrs
