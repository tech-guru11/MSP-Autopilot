from incidents.models import IncidentEvent


def record_incident_event(
    incident,
    event_type,
    description,
    actor=None,
    metadata=None,
):
    return IncidentEvent.objects.create(
        incident=incident,
        actor=actor,
        event_type=event_type,
        description=description,
        metadata=metadata or {},
    )
