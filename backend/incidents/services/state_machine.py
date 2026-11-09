from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from incidents.models import Incident

from .events import record_incident_event

ALLOWED_TRANSITIONS = {
    Incident.Status.NEW: [
        Incident.Status.TRIAGING,
        Incident.Status.ESCALATED,
    ],
    Incident.Status.TRIAGING: [
        Incident.Status.INVESTIGATING,
        Incident.Status.ESCALATED,
    ],
    Incident.Status.INVESTIGATING: [
        Incident.Status.AWAITING_APPROVAL,
        Incident.Status.VERIFYING,
        Incident.Status.ESCALATED,
    ],
    Incident.Status.AWAITING_APPROVAL: [
        Incident.Status.REMEDIATING,
        Incident.Status.INVESTIGATING,
        Incident.Status.ESCALATED,
    ],
    Incident.Status.REMEDIATING: [
        Incident.Status.VERIFYING,
        Incident.Status.INVESTIGATING,
        Incident.Status.ESCALATED,
    ],
    Incident.Status.VERIFYING: [
        Incident.Status.RESOLVED,
        Incident.Status.INVESTIGATING,
        Incident.Status.ESCALATED,
    ],
    Incident.Status.RESOLVED: [
        Incident.Status.CLOSED,
    ],
    Incident.Status.ESCALATED: [
        Incident.Status.TRIAGING,
        Incident.Status.INVESTIGATING,
        Incident.Status.CLOSED,
    ],
    Incident.Status.CLOSED: [],
}


@transaction.atomic
def transition_incident(incident_id, new_status, actor=None):
    try:
        incident = Incident.objects.select_for_update().get(id=incident_id)
    except Incident.DoesNotExist as exc:
        raise ValidationError("Incident does not exist.") from exc

    new_status = getattr(new_status, "value", new_status)

    if new_status not in Incident.Status.values:
        raise ValidationError(f"Unknown incident status: {new_status}.")

    current_status = incident.status

    if new_status == current_status:
        return incident

    allowed = ALLOWED_TRANSITIONS.get(current_status, [])

    if new_status not in allowed:
        raise ValidationError(
            f"Cannot transition from {current_status} to {new_status}."
        )

    incident.status = new_status
    update_fields = ["status", "updated_at"]

    if new_status == Incident.Status.RESOLVED and incident.resolved_at is None:
        incident.resolved_at = timezone.now()
        update_fields.append("resolved_at")

    if (
        new_status
        not in (
            Incident.Status.RESOLVED,
            Incident.Status.CLOSED,
        )
        and incident.resolved_at is not None
    ):
        incident.resolved_at = None
        update_fields.append("resolved_at")

    incident.save(update_fields=update_fields)

    record_incident_event(
        incident=incident,
        event_type="status_changed",
        description=(
            f"Incident status changed from {current_status} to {new_status}."
        ),
        actor=actor,
        metadata={
            "from": current_status,
            "to": new_status,
        },
    )

    return incident
