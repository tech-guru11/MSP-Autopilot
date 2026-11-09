from customers.models import Customer
from infrastructure.models import Asset
from rest_framework import serializers

from .models import (
    Alert,
    Evidence,
    Incident,
    IncidentEvent,
    Investigation,
    RemediationAction,
)


class IncidentSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(
        source="customer.name",
        read_only=True,
    )
    asset_name = serializers.CharField(
        source="asset.name",
        read_only=True,
        allow_null=True,
    )
    investigations = serializers.SerializerMethodField()
    remediation_actions = serializers.SerializerMethodField()

    class Meta:
        model = Incident
        fields = [
            "id",
            "customer",
            "customer_name",
            "asset",
            "asset_name",
            "title",
            "description",
            "severity",
            "status",
            "started_at",
            "resolved_at",
            "acknowledged_at",
            "acknowledged_by",
            "assigned_to",
            "investigations",
            "remediation_actions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "customer_name",
            "asset_name",
            "status",
            "resolved_at",
            "acknowledged_at",
            "acknowledged_by",
            "assigned_to",
            "investigations",
            "remediation_actions",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "started_at": {"required": False},
        }

    def get_investigations(self, obj):
        return InvestigationSerializer(
            obj.investigations.all()[:5],
            many=True,
        ).data

    def get_remediation_actions(self, obj):
        return RemediationActionSerializer(
            obj.remediation_actions.all()[:10],
            many=True,
        ).data

    def validate_title(self, value):
        if not value.strip():
            raise serializers.ValidationError(
                "Incident title cannot be empty."
            )
        return value.strip()

    def validate(self, attrs):
        organization = self.context.get("organization")

        if "customer" in attrs:
            customer = attrs["customer"]
        elif self.instance is not None:
            customer = self.instance.customer
        else:
            customer = None

        if "asset" in attrs:
            asset = attrs["asset"]
        elif self.instance is not None:
            asset = self.instance.asset
        else:
            asset = None

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

        if (
            asset is not None
            and customer is not None
            and asset.customer_id != customer.id
        ):
            raise serializers.ValidationError(
                {
                    "asset": (
                        "This asset does not belong to the selected customer."
                    )
                }
            )

        return attrs


class EvidenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Evidence
        fields = [
            "id",
            "source",
            "observation",
            "supports",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields


class InvestigationSerializer(serializers.ModelSerializer):
    evidence_items = EvidenceSerializer(many=True, read_only=True)

    class Meta:
        model = Investigation
        fields = [
            "id",
            "incident",
            "requested_by",
            "status",
            "summary",
            "severity_assessment",
            "result",
            "model_provider",
            "model_id",
            "evidence_items",
            "created_at",
        ]
        read_only_fields = fields


class InvestigationRequestSerializer(serializers.Serializer):
    evidence = serializers.JSONField()
    run_async = serializers.BooleanField(
        default=False,
        required=False,
    )

    def validate_evidence(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "Evidence must be a JSON object."
            )
        return value


class IncidentTransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Incident.Status.choices)


class IncidentEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(
        source="actor.username",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = IncidentEvent
        fields = [
            "id",
            "actor",
            "actor_username",
            "event_type",
            "description",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields


class AlertSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(
        source="customer.name",
        read_only=True,
    )
    asset_name = serializers.CharField(
        source="asset.name",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Alert
        fields = [
            "id",
            "customer",
            "customer_name",
            "asset",
            "asset_name",
            "incident",
            "fingerprint",
            "title",
            "description",
            "severity",
            "status",
            "occurrence_count",
            "first_seen_at",
            "last_seen_at",
        ]
        read_only_fields = fields


class RemediationActionSerializer(serializers.ModelSerializer):
    requested_by_username = serializers.CharField(
        source="requested_by.username",
        read_only=True,
        allow_null=True,
    )
    approved_by_username = serializers.CharField(
        source="approved_by.username",
        read_only=True,
        allow_null=True,
    )
    rejected_by_username = serializers.CharField(
        source="rejected_by.username",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = RemediationAction
        fields = [
            "id",
            "incident",
            "investigation",
            "action_type",
            "parameters",
            "risk",
            "status",
            "requires_approval",
            "reversible",
            "rollback_plan",
            "idempotency_key",
            "requested_by",
            "requested_by_username",
            "approved_by",
            "approved_by_username",
            "approved_at",
            "rejected_by",
            "rejected_by_username",
            "rejected_at",
            "rejection_reason",
            "executed_at",
            "result",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class RemediationActionCreateSerializer(serializers.Serializer):
    incident = serializers.PrimaryKeyRelatedField(
        queryset=Incident.objects.all()
    )
    investigation = serializers.PrimaryKeyRelatedField(
        queryset=Investigation.objects.all(),
        required=False,
        allow_null=True,
    )
    action_type = serializers.ChoiceField(
        choices=RemediationAction.ActionType.choices
    )
    parameters = serializers.JSONField(
        required=False,
        default=dict,
    )
    idempotency_key = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )
    rollback_plan = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )

    def validate_parameters(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "Parameters must be a JSON object."
            )
        return value


class RemediationRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )


class AlertIngestSerializer(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all()
    )
    asset = serializers.PrimaryKeyRelatedField(
        queryset=Asset.objects.all(),
        required=False,
        allow_null=True,
    )
    fingerprint = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )
    condition = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )
    title = serializers.CharField()
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )
    severity = serializers.ChoiceField(
        choices=Alert.Severity.choices,
        default=Alert.Severity.MEDIUM,
    )
