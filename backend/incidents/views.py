import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.utils import timezone
from organizations.mixins import OrganizationScopedMixin
from organizations.permissions import (
    IsOrganizationAdmin,
    IsOrganizationEngineer,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import Alert, Incident, RemediationAction
from .serializers import (
    AlertIngestSerializer,
    AlertSerializer,
    IncidentEventSerializer,
    IncidentSerializer,
    IncidentTransitionSerializer,
    InvestigationRequestSerializer,
    InvestigationSerializer,
    RemediationActionCreateSerializer,
    RemediationActionSerializer,
    RemediationRejectSerializer,
)
from .services.alerts import ingest_alert
from .services.correlation import create_incident_for_alert
from .services.investigation import INVESTIGABLE_STATUSES, run_investigation
from .services.remediation import (
    approve_remediation_action,
    execute_remediation_action,
    propose_remediation_action,
    reject_remediation_action,
    rollback_remediation_action,
)
from .services.state_machine import transition_incident
from .tasks import run_investigation_task

logger = logging.getLogger(__name__)


class IncidentViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    serializer_class = IncidentSerializer
    permission_classes = [IsOrganizationEngineer]

    def get_queryset(self):
        organization = self.get_active_organization()
        queryset = Incident.objects.filter(
            customer__organization=organization
        ).select_related("customer", "asset")

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(description__icontains=search)
                | Q(customer__name__icontains=search)
            )

        for field in ("status", "severity", "customer", "asset"):
            value = self.request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})

        ordering = self.request.query_params.get("ordering")
        allowed_ordering = {
            "started_at",
            "-started_at",
            "severity",
            "-severity",
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
            queryset = queryset.order_by("-started_at")

        return queryset

    def perform_create(self, serializer):
        organization = self.get_active_organization()

        customer = serializer.validated_data["customer"]

        if customer.organization_id != organization.id:
            raise ValidationError(
                "Customer does not belong to this organization."
            )

        asset = serializer.validated_data.get("asset")

        if asset and asset.customer_id != customer.id:
            raise ValidationError("Asset does not belong to this customer.")

        serializer.save(started_at=timezone.now())

    @action(detail=True, methods=["post"], url_path="transition")
    def transition(self, request, pk=None):
        incident = self.get_object()
        serializer = IncidentTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            incident = transition_incident(
                incident.id,
                serializer.validated_data["status"],
                actor=request.user,
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc

        output = IncidentSerializer(incident)
        return Response(output.data)

    @action(detail=True, methods=["get"], url_path="events")
    def events(self, request, pk=None):
        incident = self.get_object()
        serializer = IncidentEventSerializer(
            incident.events.select_related("actor").all(),
            many=True,
        )
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="investigate")
    def investigate(self, request, pk=None):
        incident = self.get_object()
        serializer = InvestigationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        evidence = serializer.validated_data["evidence"]

        if serializer.validated_data.get("run_async"):
            if incident.status not in INVESTIGABLE_STATUSES:
                raise ValidationError(
                    "Incident is not in an investigable state."
                )

            try:
                task = run_investigation_task.delay(
                    str(incident.id),
                    evidence,
                    str(request.user.id),
                )
            except Exception:
                logger.exception("Unable to queue investigation task.")
                return Response(
                    {"detail": "Background worker is unavailable."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            return Response(
                {
                    "task_id": task.id,
                    "status": "queued",
                    "status_url": f"/api/tasks/{task.id}/",
                },
                status=status.HTTP_202_ACCEPTED,
            )

        try:
            investigation = run_investigation(
                incident=incident,
                evidence=evidence,
                actor=request.user,
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc

        output = InvestigationSerializer(investigation)
        return Response(
            output.data,
            status=status.HTTP_201_CREATED,
        )


class AlertViewSet(OrganizationScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = AlertSerializer
    permission_classes = [IsOrganizationEngineer]

    def get_queryset(self):
        organization = self.get_active_organization()
        queryset = Alert.objects.filter(
            customer__organization=organization
        ).select_related("customer", "asset", "incident")

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(description__icontains=search)
                | Q(fingerprint__icontains=search)
                | Q(customer__name__icontains=search)
            )

        for field in ("status", "severity", "customer", "asset", "incident"):
            value = self.request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})

        ordering = self.request.query_params.get("ordering")
        allowed_ordering = {
            "last_seen_at",
            "-last_seen_at",
            "first_seen_at",
            "-first_seen_at",
            "severity",
            "-severity",
            "status",
            "-status",
        }
        if ordering in allowed_ordering:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by("-last_seen_at")

        return queryset

    def get_serializer_class(self):
        if self.action == "create":
            return AlertIngestSerializer
        return AlertSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        organization = self.get_active_organization()
        customer = data["customer"]

        if customer.organization_id != organization.id:
            raise ValidationError(
                "Customer does not belong to this organization."
            )

        try:
            alert, created = ingest_alert(
                customer=customer,
                asset=data.get("asset"),
                fingerprint=data.get("fingerprint") or None,
                title=data["title"],
                description=data.get("description", ""),
                severity=data["severity"],
                condition=data.get("condition") or None,
            )
            create_incident_for_alert(alert)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc

        alert.refresh_from_db()
        output = AlertSerializer(alert)
        return Response(
            output.data,
            status=(
                status.HTTP_201_CREATED if created else status.HTTP_200_OK
            ),
        )


class RemediationActionViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsOrganizationEngineer]

    def get_permissions(self):
        if self.action in {"approve", "reject"}:
            return [IsOrganizationAdmin()]
        return [IsOrganizationEngineer()]

    def get_queryset(self):
        organization = self.get_active_organization()
        queryset = RemediationAction.objects.filter(
            incident__customer__organization=organization
        ).select_related(
            "incident",
            "investigation",
            "requested_by",
            "approved_by",
            "rejected_by",
        )

        for field in ("incident", "status", "risk", "action_type"):
            value = self.request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})

        ordering = self.request.query_params.get("ordering")
        allowed_ordering = {
            "created_at",
            "-created_at",
            "updated_at",
            "-updated_at",
            "risk",
            "-risk",
            "status",
            "-status",
        }
        if ordering in allowed_ordering:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by("-created_at")

        return queryset

    def get_serializer_class(self):
        if self.action == "create":
            return RemediationActionCreateSerializer
        if self.action == "reject":
            return RemediationRejectSerializer
        return RemediationActionSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        organization = self.get_active_organization()
        incident = data["incident"]

        if incident.customer.organization_id != organization.id:
            raise ValidationError(
                "Incident does not belong to this organization."
            )

        investigation = data.get("investigation")

        if (
            investigation is not None
            and investigation.incident_id != incident.id
        ):
            raise ValidationError(
                "Investigation does not belong to this incident."
            )

        try:
            action, created = propose_remediation_action(
                incident=incident,
                action_type=data["action_type"],
                parameters=data.get("parameters", {}),
                actor=request.user,
                investigation=investigation,
                idempotency_key=(data.get("idempotency_key") or None),
                rollback_plan=data.get("rollback_plan", ""),
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc

        output = RemediationActionSerializer(action)
        return Response(
            output.data,
            status=(
                status.HTTP_201_CREATED if created else status.HTTP_200_OK
            ),
        )

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        try:
            action = approve_remediation_action(
                pk,
                request.user,
                self.get_active_organization(),
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc

        return Response(RemediationActionSerializer(action).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            action = reject_remediation_action(
                pk,
                request.user,
                self.get_active_organization(),
                reason=serializer.validated_data.get("reason", ""),
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc

        return Response(RemediationActionSerializer(action).data)

    @action(detail=True, methods=["post"])
    def execute(self, request, pk=None):
        try:
            action = execute_remediation_action(
                pk,
                request.user,
                self.get_active_organization(),
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc

        output = RemediationActionSerializer(action)
        return Response(
            output.data,
            status=(
                status.HTTP_400_BAD_REQUEST
                if action.status == RemediationAction.Status.FAILED
                else status.HTTP_200_OK
            ),
        )

    @action(detail=True, methods=["post"])
    def rollback(self, request, pk=None):
        try:
            action = rollback_remediation_action(
                pk,
                request.user,
                self.get_active_organization(),
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc

        output = RemediationActionSerializer(action)
        return Response(
            output.data,
            status=(
                status.HTTP_400_BAD_REQUEST
                if action.status == RemediationAction.Status.FAILED
                else status.HTTP_200_OK
            ),
        )
