# Lesson 6 Security Notes

## 1. Prompt injection through logs

Application logs, monitoring responses, ticket text and deployment messages are
treated as untrusted evidence, never as instructions. The agent system prompt
states this explicitly, and the read-only tools return data without executing
anything from that data. The deterministic diagnostic engine also does not
interpret log text as commands. In production, raw log content should remain
quarantined as evidence and should never be allowed to alter tool permissions,
tenant scope or policy decisions.

## 2. One customer accessing another customer's evidence

The investigation API is authenticated, requires a valid `X-Organization-ID`,
and loads the incident through the tenant-scoped `IncidentViewSet` queryset.
An incident belonging to another organization returns `404`. The investigation
service only receives an already-authorized incident. The demonstration tools
also reject any service name outside their approved allow-list. In production,
each monitoring integration must derive the permitted services from trusted
backend authorization, not from a model-supplied customer or service name.

## 3. Unauthorized infrastructure changes

The diagnostic agent has read-only tools only: service health, database
metrics, recent logs and deployment history. It has no shell, restart, deploy,
delete or IAM tools. The investigation result is stored as data. Completing an
investigation does not change the incident status and does not execute any
recommendation. The `requires_approval` field is a model recommendation, not a
permission decision; the future policy and approval layer must independently
authorize any remediation.

## 4. AI recommendations mistaken for approved actions

Recommendations are persisted inside the `Investigation.result` record and are
surfaced as advisory output. The incident remains in `INVESTIGATING`, and an
`investigation_completed` event is written to the incident timeline. There is
no code path from an investigation result to an infrastructure change. Lesson 7
will add the policy engine, approval workflow, action risk evaluation and
auditable execution path.

## Prototype limitation

The current `POST /api/incidents/{id}/investigate/` endpoint accepts evidence in
the request body so the deterministic engine can be exercised locally. A
production implementation should collect evidence server-side through approved
integrations and should not trust client-supplied observations as authoritative.
