import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Incident(models.Model):
    class Severity(models.TextChoices):
        P1 = "P1", "Critical"
        P2 = "P2", "High"
        P3 = "P3", "Medium"
        P4 = "P4", "Low"

    class Status(models.TextChoices):
        NEW = "new", "New"
        TRIAGING = "triaging", "Triaging"
        INVESTIGATING = "investigating", "Investigating"
        AWAITING_APPROVAL = "awaiting_approval", "Awaiting Approval"
        REMEDIATING = "remediating", "Remediating"
        VERIFYING = "verifying", "Verifying"
        RESOLVED = "resolved", "Resolved"
        ESCALATED = "escalated", "Escalated"
        CLOSED = "closed", "Closed"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="incidents",
    )
    asset = models.ForeignKey(
        "infrastructure.Asset",
        on_delete=models.PROTECT,
        related_name="incidents",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    severity = models.CharField(
        max_length=2,
        choices=Severity.choices,
        default=Severity.P3,
    )
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.NEW,
    )
    started_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="acknowledged_incidents",
        null=True,
        blank=True,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="assigned_incidents",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["customer", "severity"]),
        ]

    def __str__(self):
        return f"[{self.severity}] {self.title}"


class Alert(models.Model):
    class Severity(models.TextChoices):
        CRITICAL = "critical", "Critical"
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        RESOLVED = "resolved", "Resolved"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="alerts",
    )
    asset = models.ForeignKey(
        "infrastructure.Asset",
        on_delete=models.PROTECT,
        related_name="alerts",
        null=True,
        blank=True,
    )
    incident = models.ForeignKey(
        Incident,
        on_delete=models.SET_NULL,
        related_name="alerts",
        null=True,
        blank=True,
    )
    fingerprint = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    severity = models.CharField(
        max_length=20,
        choices=Severity.choices,
        default=Severity.MEDIUM,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )
    occurrence_count = models.PositiveIntegerField(default=1)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["customer", "fingerprint"]),
            models.Index(fields=["customer", "status"]),
        ]

    def __str__(self):
        return self.title


class Investigation(models.Model):
    class Status(models.TextChoices):
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    incident = models.ForeignKey(
        Incident,
        on_delete=models.PROTECT,
        related_name="investigations",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="investigations",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.COMPLETED,
    )
    summary = models.TextField(blank=True)
    severity_assessment = models.CharField(
        max_length=2,
        choices=Incident.Severity.choices,
        blank=True,
    )
    result = models.JSONField(default=dict, blank=True)
    model_provider = models.CharField(max_length=100, blank=True)
    model_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["incident", "created_at"]),
        ]

    def __str__(self):
        return f"Investigation {self.id} for {self.incident_id}"


class Evidence(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    investigation = models.ForeignKey(
        Investigation,
        on_delete=models.CASCADE,
        related_name="evidence_items",
    )
    source = models.CharField(max_length=255)
    observation = models.TextField()
    supports = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["investigation", "created_at"]),
        ]

    def __str__(self):
        return f"{self.source}: {self.observation[:60]}"


class RemediationAction(models.Model):
    class ActionType(models.TextChoices):
        INSPECT_CONNECTION_POOL = (
            "inspect_connection_pool",
            "Inspect Connection Pool",
        )
        CLEAR_CACHE = "clear_cache", "Clear Cache"
        RESTART_SERVICE = "restart_service", "Restart Service"
        SCALE_OUT = "scale_out", "Scale Out"
        ROLLBACK_DEPLOYMENT = "rollback_deployment", "Rollback Deployment"
        FAILOVER_DATABASE = "failover_database", "Failover Database"
        DELETE_DATABASE = "delete_database", "Delete Database"
        CHANGE_IAM_POLICY = "change_iam_policy", "Change IAM Policy"

    class Risk(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        PENDING_APPROVAL = "pending_approval", "Pending Approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        EXECUTING = "executing", "Executing"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        ROLLING_BACK = "rolling_back", "Rolling Back"
        ROLLED_BACK = "rolled_back", "Rolled Back"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    incident = models.ForeignKey(
        Incident,
        on_delete=models.PROTECT,
        related_name="remediation_actions",
    )
    investigation = models.ForeignKey(
        Investigation,
        on_delete=models.SET_NULL,
        related_name="remediation_actions",
        null=True,
        blank=True,
    )
    action_type = models.CharField(
        max_length=50,
        choices=ActionType.choices,
    )
    parameters = models.JSONField(default=dict, blank=True)
    risk = models.CharField(
        max_length=20,
        choices=Risk.choices,
        default=Risk.MEDIUM,
    )
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PROPOSED,
    )
    requires_approval = models.BooleanField(default=True)
    reversible = models.BooleanField(default=True)
    rollback_plan = models.TextField(blank=True)
    idempotency_key = models.CharField(
        max_length=255,
        default=uuid.uuid4,
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="requested_remediation_actions",
        null=True,
        blank=True,
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="approved_remediation_actions",
        null=True,
        blank=True,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="rejected_remediation_actions",
        null=True,
        blank=True,
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    result = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["incident", "idempotency_key"],
                name="unique_remediation_idempotency",
            )
        ]
        indexes = [
            models.Index(fields=["incident", "status"]),
            models.Index(fields=["incident", "created_at"]),
        ]

    def __str__(self):
        return f"{self.action_type} ({self.status})"


class IncidentEvent(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    incident = models.ForeignKey(
        Incident,
        on_delete=models.PROTECT,
        related_name="events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    event_type = models.CharField(max_length=100)
    description = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["incident", "created_at"]),
        ]

    def __str__(self):
        return f"{self.incident_id}: {self.event_type}"
