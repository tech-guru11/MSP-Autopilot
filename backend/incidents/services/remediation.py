import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from incidents.models import Incident, RemediationAction
from incidents.services.events import record_incident_event
from incidents.services.policy import (
    can_approve,
    can_execute,
    evaluate_action,
)
from incidents.services.remediation_executors import (
    execute_action,
    rollback_action,
)
from incidents.services.state_machine import transition_incident

PROPOSABLE_STATUSES = {
    Incident.Status.INVESTIGATING,
    Incident.Status.AWAITING_APPROVAL,
    Incident.Status.VERIFYING,
}


def _lock_action(action_id, organization):
    action = (
        RemediationAction.objects.select_for_update()
        .select_related(
            "incident",
            "incident__customer",
            "incident__customer__organization",
        )
        .filter(id=action_id)
        .first()
    )

    if action is None:
        raise ValidationError("Remediation action does not exist.")

    if action.incident.customer.organization_id != organization.id:
        raise ValidationError(
            "Remediation action does not belong to this organization."
        )

    return action


def _try_transition(incident, new_status, actor):
    try:
        return transition_incident(
            incident.id,
            new_status,
            actor=actor,
        )
    except ValidationError:
        return incident


@transaction.atomic
def propose_remediation_action(
    incident,
    action_type,
    parameters,
    actor,
    investigation=None,
    idempotency_key=None,
    rollback_plan="",
):
    if not isinstance(parameters, dict):
        raise ValidationError("Remediation parameters must be a JSON object.")

    locked_incident = (
        Incident.objects.select_for_update()
        .select_related("customer__organization")
        .get(pk=incident.pk)
    )

    if locked_incident.status not in PROPOSABLE_STATUSES:
        raise ValidationError(
            "Incident is not in a state where remediation can be proposed."
        )

    decision = evaluate_action(
        action_type,
        parameters,
        actor,
        locked_incident,
    )

    if not decision.allowed:
        raise ValidationError(decision.reasons)

    key = idempotency_key or uuid.uuid4().hex

    existing = RemediationAction.objects.filter(
        incident=locked_incident,
        idempotency_key=key,
    ).first()

    if existing is not None:
        return existing, False

    action = RemediationAction.objects.create(
        incident=locked_incident,
        investigation=investigation,
        action_type=action_type,
        parameters=parameters,
        risk=decision.risk,
        status=(
            RemediationAction.Status.PENDING_APPROVAL
            if decision.requires_approval
            else RemediationAction.Status.APPROVED
        ),
        requires_approval=decision.requires_approval,
        reversible=decision.reversible,
        rollback_plan=rollback_plan or decision.rollback_plan,
        idempotency_key=key,
        requested_by=actor,
    )

    record_incident_event(
        incident=locked_incident,
        event_type="remediation_proposed",
        description=(f"Remediation action {action.action_type} was proposed."),
        actor=actor,
        metadata={
            "remediation_action_id": str(action.id),
            "risk": action.risk,
            "requires_approval": action.requires_approval,
        },
    )

    if (
        action.requires_approval
        and locked_incident.status == Incident.Status.INVESTIGATING
    ):
        _try_transition(
            locked_incident,
            Incident.Status.AWAITING_APPROVAL,
            actor,
        )

    return action, True


@transaction.atomic
def approve_remediation_action(action_id, actor, organization):
    action = _lock_action(action_id, organization)

    if not can_approve(actor, organization):
        raise ValidationError(
            "Only an organization administrator can approve remediation."
        )

    if action.status != RemediationAction.Status.PENDING_APPROVAL:
        raise ValidationError("Only actions pending approval can be approved.")

    if action.risk == RemediationAction.Risk.CRITICAL:
        raise ValidationError(
            "Critical remediation actions cannot be approved."
        )

    action.status = RemediationAction.Status.APPROVED
    action.approved_by = actor
    action.approved_at = timezone.now()
    action.save(
        update_fields=[
            "status",
            "approved_by",
            "approved_at",
            "updated_at",
        ]
    )

    record_incident_event(
        incident=action.incident,
        event_type="remediation_approved",
        description=(f"Remediation action {action.action_type} was approved."),
        actor=actor,
        metadata={
            "remediation_action_id": str(action.id),
            "risk": action.risk,
        },
    )

    return action


@transaction.atomic
def reject_remediation_action(
    action_id,
    actor,
    organization,
    reason="",
):
    action = _lock_action(action_id, organization)

    if not can_approve(actor, organization):
        raise ValidationError(
            "Only an organization administrator can reject remediation."
        )

    if action.status != RemediationAction.Status.PENDING_APPROVAL:
        raise ValidationError("Only actions pending approval can be rejected.")

    action.status = RemediationAction.Status.REJECTED
    action.rejected_by = actor
    action.rejected_at = timezone.now()
    action.rejection_reason = reason
    action.save(
        update_fields=[
            "status",
            "rejected_by",
            "rejected_at",
            "rejection_reason",
            "updated_at",
        ]
    )

    record_incident_event(
        incident=action.incident,
        event_type="remediation_rejected",
        description=(f"Remediation action {action.action_type} was rejected."),
        actor=actor,
        metadata={
            "remediation_action_id": str(action.id),
            "reason": reason,
        },
    )

    if action.incident.status == Incident.Status.AWAITING_APPROVAL:
        _try_transition(
            action.incident,
            Incident.Status.INVESTIGATING,
            actor,
        )

    return action


@transaction.atomic
def execute_remediation_action(action_id, actor, organization):
    action = _lock_action(action_id, organization)

    if not can_execute(actor, organization):
        raise ValidationError(
            "Only engineers or administrators can execute remediation."
        )

    if action.status == RemediationAction.Status.SUCCEEDED:
        return action

    if action.status != RemediationAction.Status.APPROVED:
        raise ValidationError("Only approved actions can be executed.")

    if action.risk == RemediationAction.Risk.CRITICAL:
        raise ValidationError(
            "Critical remediation actions cannot be executed."
        )

    if action.requires_approval and action.approved_at is None:
        raise ValidationError(
            "This action requires administrator approval before execution."
        )

    action.status = RemediationAction.Status.EXECUTING
    action.save(update_fields=["status", "updated_at"])

    try:
        result = execute_action(action)
    except Exception as exc:
        action.status = RemediationAction.Status.FAILED
        action.result = {"error": str(exc)}
        action.save(update_fields=["status", "result", "updated_at"])
        record_incident_event(
            incident=action.incident,
            event_type="remediation_failed",
            description=(f"Remediation action {action.action_type} failed."),
            actor=actor,
            metadata={
                "remediation_action_id": str(action.id),
                "error": str(exc),
            },
        )
        _try_transition(
            action.incident,
            Incident.Status.INVESTIGATING,
            actor,
        )
        return action

    action.status = RemediationAction.Status.SUCCEEDED
    action.executed_at = timezone.now()
    action.result = result
    action.save(
        update_fields=[
            "status",
            "executed_at",
            "result",
            "updated_at",
        ]
    )

    record_incident_event(
        incident=action.incident,
        event_type="remediation_executed",
        description=(f"Remediation action {action.action_type} was executed."),
        actor=actor,
        metadata={
            "remediation_action_id": str(action.id),
            "result": result,
        },
    )

    if action.incident.status == Incident.Status.AWAITING_APPROVAL:
        action.incident = _try_transition(
            action.incident,
            Incident.Status.REMEDIATING,
            actor,
        )

    if action.incident.status in (
        Incident.Status.REMEDIATING,
        Incident.Status.INVESTIGATING,
    ):
        action.incident = _try_transition(
            action.incident,
            Incident.Status.VERIFYING,
            actor,
        )

    return action


@transaction.atomic
def rollback_remediation_action(action_id, actor, organization):
    action = _lock_action(action_id, organization)

    if not can_execute(actor, organization):
        raise ValidationError(
            "Only engineers or administrators can roll back remediation."
        )

    if action.status != RemediationAction.Status.SUCCEEDED:
        raise ValidationError(
            "Only successfully executed actions can be rolled back."
        )

    if not action.reversible:
        raise ValidationError("This remediation action is not reversible.")

    action.status = RemediationAction.Status.ROLLING_BACK
    action.save(update_fields=["status", "updated_at"])

    try:
        result = rollback_action(action)
    except Exception as exc:
        action.status = RemediationAction.Status.FAILED
        action.result = {
            **action.result,
            "rollback_error": str(exc),
        }
        action.save(update_fields=["status", "result", "updated_at"])
        record_incident_event(
            incident=action.incident,
            event_type="remediation_rollback_failed",
            description=(f"Rollback of {action.action_type} failed."),
            actor=actor,
            metadata={
                "remediation_action_id": str(action.id),
                "error": str(exc),
            },
        )
        return action

    action.status = RemediationAction.Status.ROLLED_BACK
    action.result = {
        **action.result,
        "rollback": result,
    }
    action.save(update_fields=["status", "result", "updated_at"])

    record_incident_event(
        incident=action.incident,
        event_type="remediation_rolled_back",
        description=(
            f"Remediation action {action.action_type} was rolled back."
        ),
        actor=actor,
        metadata={
            "remediation_action_id": str(action.id),
            "result": result,
        },
    )

    if action.incident.status == Incident.Status.VERIFYING:
        _try_transition(
            action.incident,
            Incident.Status.INVESTIGATING,
            actor,
        )

    return action
