# Lesson 7: Policy-Controlled Remediation

This lesson adds a remediation workflow that is intentionally conservative:
the system can recommend and prepare actions, but it cannot bypass policy or
human approval.

## Action catalog

Actions are defined in `backend/incidents/services/policy.py`.

| Action | Risk | Approval | Reversible | Allowed |
| --- | --- | --- | --- | --- |
| `inspect_connection_pool` | low | no | yes | yes |
| `clear_cache` | low | no | yes | yes |
| `restart_service` | medium | yes | yes | yes |
| `scale_out` | medium | yes | yes | yes |
| `rollback_deployment` | high | admin | yes | yes |
| `failover_database` | high | admin | yes | yes |
| `delete_database` | critical | yes | no | no |
| `change_iam_policy` | critical | yes | no | no |

Critical actions are prohibited regardless of actor role. Viewers cannot
propose remediation. Medium and high-risk actions require approval; high-risk
actions require an administrator.

## Workflow

1. An engineer proposes an action with `POST /api/remediation-actions/`.
2. Policy evaluates the action, actor role, incident, and target asset/customer.
3. Low-risk actions become `approved` immediately.
4. Medium/high-risk actions become `pending_approval` and the incident moves to
   `awaiting_approval`.
5. An administrator approves or rejects with
   `POST /api/remediation-actions/{id}/approve/` or `/reject/`.
6. An engineer or administrator executes with
   `POST /api/remediation-actions/{id}/execute/`.
7. Successful execution moves the incident to `verifying`.
8. A successful action can be rolled back with
   `POST /api/remediation-actions/{id}/rollback/`.

Every step writes an `IncidentEvent`, so the incident timeline is the audit log.

## Execution safety

`backend/incidents/services/remediation_executors.py` simulates execution and
rollback. It does not call cloud APIs or change infrastructure. This keeps the
workflow testable and prevents accidental damage while real adapters are built.

Set `REMEDIATION_EXECUTION_MODE` in the environment when real execution modes
are added. The default is `simulate`.

## Tenant and role enforcement

- Actions are filtered by the active organization.
- Cross-tenant action IDs are hidden.
- Proposal checks the actor's membership in the incident customer's
  organization.
- Approval is admin-only.
- Execution and rollback require engineer or admin.
- Target assets must belong to the incident customer.

## Data model

`RemediationAction` stores:

- incident and optional investigation
- action type, parameters, risk, status
- approval requirement and reversibility
- rollback plan
- idempotency key
- requester, approver, rejector and timestamps
- execution result

The idempotency key prevents duplicate actions from retries.
