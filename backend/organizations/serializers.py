from rest_framework import serializers

from .models import Membership, Organization


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]


class MembershipSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(
        source="organization.name",
        read_only=True,
    )
    user_username = serializers.CharField(
        source="user.username",
        read_only=True,
    )

    class Meta:
        model = Membership
        fields = [
            "id",
            "organization",
            "organization_name",
            "user",
            "user_username",
            "role",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "organization_name",
            "user_username",
            "created_at",
        ]
