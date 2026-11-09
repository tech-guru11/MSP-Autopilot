from ai_engine.diagnostics import investigate_incident
from django.core.exceptions import ValidationError
from django.db import transaction

from incidents.models import Evidence, Incident, Investigation
from incidents.services.events import record_incident_event

INVESTIGABLE_STATUSES = {
    Incident.Status.INVESTIGATING,
}


@transaction.atomic
def run_investigation(
    incident,
    evidence,
    actor=None,
    model_provider="",
    model_id="",
):
    if not isinstance(evidence, dict):
        raise ValidationError("Evidence must be a JSON object.")

    locked_incident = Incident.objects.select_for_update().get(pk=incident.pk)

    if locked_incident.status not in INVESTIGABLE_STATUSES:
        raise ValidationError("Incident is not in an investigable state.")

    result = investigate_incident(evidence)

    investigation = Investigation.objects.create(
        incident=locked_incident,
        requested_by=actor,
        status=Investigation.Status.COMPLETED,
        summary=result.incident_summary,
        severity_assessment=result.severity_assessment,
        result=result.model_dump(),
        model_provider=model_provider,
        model_id=model_id,
    )

    Evidence.objects.bulk_create(
        [
            Evidence(
                investigation=investigation,
                source=item.source,
                observation=item.observation,
                supports=item.supports,
            )
            for item in result.evidence
        ]
    )

    record_incident_event(
        incident=locked_incident,
        event_type="investigation_completed",
        description="Diagnostic investigation completed.",
        actor=actor,
        metadata={
            "investigation_id": str(investigation.id),
            "severity_assessment": result.severity_assessment,
            "hypothesis_count": len(result.hypotheses),
            "evidence_count": len(result.evidence),
            "model_provider": model_provider,
            "model_id": model_id,
        },
    )

    return investigation
