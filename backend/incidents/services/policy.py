from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from infrastructure.models import Asset
from organizations.models import Membership

from incidents.models import RemediationAction

ActionType = RemediationAction.ActionType
Risk = RemediationAction.Risk

ACTION_POLICIES = {
    ActionType.INSPECT_CONNECTION_POOL: {
        "risk": Risk.LOW,
        "requires_approval": False,
        "reversible": True,
        "allowed": True,
        "rollback_plan": "No infrastructure change; stop the inspection.",
    },
    ActionType.CLEAR_CACHE: {
        "risk": Risk.LOW,
        "requires_approval": False,
        "reversible": True,
        "allowed": True,
        "rollback_plan": "Cache repopulates automatically; no rollback needed.",
    },
    ActionType.RESTART_SERVICE: {
        "risk": Risk.MEDIUM,
        "requires_approval": True,
        "reversible": True,
        "allowed": True,
        "rollback_plan": "Restart the service again and confirm health checks.",
    },
    ActionType.SCALE_OUT: {
        "risk": Risk.MEDIUM,
        "requires_approval": True,
        "reversible": True,
        "allowed": True,
        "rollback_plan": "Scale back to the previous capacity.",
    },
    ActionType.ROLLBACK_DEPLOYMENT: {
        "risk": Risk.HIGH,
        "requires_approval": True,
        "reversible": True,
        "allowed": True,
        "rollback_plan": "Redeploy the previous known-good version.",
    },
    ActionType.FAILOVER_DATABASE: {
        "risk": Risk.HIGH,
        "requires_approval": True,
        "reversible": True,
        "allowed": True,
        "rollback_plan": "Fail back to the primary after verification.",
    },
    ActionType.DELETE_DATABASE: {
        "risk": Risk.CRITICAL,
        "requires_approval": True,
        "reversible": False,
        "allowed": False,
        "rollback_plan": "This action is prohibited.",
    },
    ActionType.CHANGE_IAM_POLICY: {
        "risk": Risk.CRITICAL,
        "requires_approval": True,
        "reversible": False,
        "allowed": False,
        "rollback_plan": "This action is prohibited.",
    },
}


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    risk: str
    requires_approval: bool
    reversible: bool
    reasons: list[str] = field(default_factory=list)
    rollback_plan: str = ""


def get_membership(actor, organization):
    if actor is None or not getattr(actor, "is_authenticated", False):
        return None

    return Membership.objects.filter(
        user=actor, organization=organization
    ).first()


def evaluate_action(action_type, parameters, actor, incident):
    action_type = getattr(action_type, "value", action_type)

    if action_type not in ACTION_POLICIES:
        raise ValidationError(f"Unknown remediation action: {action_type}.")

    policy = ACTION_POLICIES[action_type]
    organization = incident.customer.organization
    membership = get_membership(actor, organization)
    reasons = []
    allowed = policy["allowed"]

    if membership is None:
        allowed = False
        reasons.append("The actor is not a member of this organization.")
    elif membership.role == Membership.Role.VIEWER:
        allowed = False
        reasons.append("Viewers cannot propose remediation actions.")

    if not policy["allowed"]:
        reasons.append("This action is prohibited by the remediation policy.")

    asset_id = parameters.get("asset_id")

    if asset_id:
        asset = Asset.objects.filter(id=asset_id).first()

        if asset is None:
            allowed = False
            reasons.append("The target asset does not exist.")
        elif asset.customer_id != incident.customer_id:
            allowed = False
            reasons.append(
                "The target asset does not belong to this incident's customer."
            )

    customer_id = parameters.get("customer_id")

    if customer_id and str(customer_id) != str(incident.customer_id):
        allowed = False
        reasons.append(
            "The target customer does not match this incident's customer."
        )

    requires_approval = policy["requires_approval"]

    if policy["risk"] in (Risk.MEDIUM, Risk.HIGH, Risk.CRITICAL):
        requires_approval = True

    if (
        policy["risk"] == Risk.HIGH
        and membership is not None
        and membership.role != Membership.Role.ADMIN
    ):
        reasons.append("A high-risk action requires administrator approval.")

    return PolicyDecision(
        allowed=allowed,
        risk=policy["risk"],
        requires_approval=requires_approval,
        reversible=policy["reversible"],
        reasons=reasons,
        rollback_plan=policy["rollback_plan"],
    )


def can_approve(actor, organization):
    membership = get_membership(actor, organization)
    return membership is not None and membership.role == Membership.Role.ADMIN


def can_execute(actor, organization):
    membership = get_membership(actor, organization)
    return membership is not None and membership.role in (
        Membership.Role.ADMIN,
        Membership.Role.ENGINEER,
    )
