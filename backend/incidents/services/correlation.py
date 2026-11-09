from django.core.exceptions import ValidationError
from django.db import transaction

from incidents.models import Alert, Incident

from .classification import map_alert_severity
from .events import record_incident_event
from .notifications import notify_incident_created

ACTIVE_STATUSES = [
    Incident.Status.NEW,
    Incident.Status.TRIAGING,
    Incident.Status.INVESTIGATING,
    Incident.Status.AWAITING_APPROVAL,
    Incident.Status.REMEDIATING,
    Incident.Status.VERIFYING,
]


@transaction.atomic
def create_incident_for_alert(alert):
    alert = (
        Alert.objects.select_for_update(of=("self",))
        .select_related("customer", "asset", "incident")
        .get(pk=alert.pk)
    )

    if (
        alert.asset is not None
        and alert.asset.customer_id != alert.customer_id
    ):
        raise ValidationError(
            "The alert asset does not belong to the alert customer."
        )

    if alert.incident_id is not None:
        return alert.incident, False

    existing = (
        Incident.objects.select_for_update()
        .filter(
            customer=alert.customer,
            asset=alert.asset,
            status__in=ACTIVE_STATUSES,
        )
        .order_by("-started_at")
        .first()
    )

    if existing is not None:
        alert.incident = existing
        alert.save(update_fields=["incident"])
        record_incident_event(
            incident=existing,
            event_type="alert_correlated",
            description=f"Related alert received: {alert.title}",
            metadata={"alert_id": str(alert.id)},
        )
        return existing, False

    incident = Incident.objects.create(
        customer=alert.customer,
        asset=alert.asset,
        title=alert.title,
        description=alert.description,
        severity=map_alert_severity(alert.severity),
        status=Incident.Status.NEW,
        started_at=alert.first_seen_at,
    )

    alert.incident = incident
    alert.save(update_fields=["incident"])

    record_incident_event(
        incident=incident,
        event_type="incident_created",
        description=f"Incident created from alert: {alert.title}",
        metadata={"alert_id": str(alert.id)},
    )

    transaction.on_commit(lambda: notify_incident_created(incident.id))

    return incident, True
