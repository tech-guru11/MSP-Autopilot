from django.conf import settings
from django.core.exceptions import ValidationError

from incidents.models import RemediationAction

SIMULATED_ACTIONS = {
    RemediationAction.ActionType.INSPECT_CONNECTION_POOL,
    RemediationAction.ActionType.CLEAR_CACHE,
    RemediationAction.ActionType.RESTART_SERVICE,
    RemediationAction.ActionType.SCALE_OUT,
    RemediationAction.ActionType.ROLLBACK_DEPLOYMENT,
    RemediationAction.ActionType.FAILOVER_DATABASE,
}


def _simulate(action, operation):
    if action.action_type not in SIMULATED_ACTIONS:
        raise ValidationError("This remediation action is not permitted.")

    mode = getattr(
        settings,
        "REMEDIATION_EXECUTION_MODE",
        "simulate",
    )

    if mode != "simulate":
        raise ValidationError(
            "Only simulated remediation execution is enabled."
        )

    return {
        "simulated": True,
        "operation": operation,
        "action_type": action.action_type,
        "incident_id": str(action.incident_id),
        "parameters": action.parameters,
        "message": (
            f"Simulated {operation} for {action.action_type}. "
            "No infrastructure was changed."
        ),
    }


def execute_action(action):
    return _simulate(action, "execute")


def rollback_action(action):
    return _simulate(action, "rollback")
