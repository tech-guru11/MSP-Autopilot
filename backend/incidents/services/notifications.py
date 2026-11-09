import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def notify_incident(incident, subject, message):
    recipient = incident.customer.contact_email

    if not recipient:
        return False

    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=True,
        )
    except Exception:
        logger.exception(
            "Failed to send incident notification for %s",
            incident.id,
        )
        return False

    return True


def notify_incident_created(incident_id):
    from incidents.models import Incident

    incident = (
        Incident.objects.select_related("customer")
        .filter(id=incident_id)
        .first()
    )

    if incident is None:
        return False

    if incident.severity not in (
        Incident.Severity.P1,
        Incident.Severity.P2,
    ):
        return False

    return notify_incident(
        incident,
        f"[{incident.severity}] {incident.title}",
        (
            f"Incident: {incident.title}\n"
            f"Severity: {incident.severity}\n"
            f"Customer: {incident.customer.name}\n"
            f"Status: {incident.status}\n"
        ),
    )
