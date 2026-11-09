from celery import shared_task
from django.core.exceptions import ValidationError


@shared_task(bind=True, max_retries=3)
def run_investigation_task(
    self,
    incident_id,
    evidence,
    actor_id=None,
    model_provider="",
    model_id="",
):
    from accounts.models import User

    from incidents.models import Incident
    from incidents.services.investigation import run_investigation

    try:
        incident = Incident.objects.get(pk=incident_id)
        actor = User.objects.filter(pk=actor_id).first() if actor_id else None
        investigation = run_investigation(
            incident=incident,
            evidence=evidence,
            actor=actor,
            model_provider=model_provider,
            model_id=model_id,
        )
    except (ValidationError, Incident.DoesNotExist):
        raise
    except Exception as exc:
        raise self.retry(
            exc=exc,
            countdown=min(60, 2**self.request.retries),
        ) from exc

    return {
        "investigation_id": str(investigation.id),
        "incident_id": str(incident.id),
        "severity_assessment": investigation.severity_assessment,
    }
