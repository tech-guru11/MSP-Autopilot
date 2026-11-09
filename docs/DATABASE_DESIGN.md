# MSP Autopilot — Database Design

## 1. Multi-tenant architecture decision

MSP Autopilot uses a **shared PostgreSQL database with shared tables and tenant
identifiers**.

- One **Organization** (the MSP) manages many **Customers** (tenants).
- Every tenant-owned row carries a `customer_id`, and every customer belongs to
  exactly one organization.
- Tenant isolation is enforced in the **backend query/service layer**, never in
  the frontend.

Alternatives considered:

| Approach | Trade-off |
| --- | --- |
| Shared database, shared tables | Cost-effective; requires strict isolation |
| Shared database, separate schemas | More separation; more management complexity |
| Separate database per tenant | Strongest isolation; highest operational overhead |

The shared-table approach was chosen for the initial project because it is
simple to operate, efficient for many MSP customers, and works well with Django
and PostgreSQL.

## 2. Entity relationships

```
Organization 1 ── * Membership * ── 1 User
Organization 1 ── * Customer
Customer     1 ── * Asset
Customer     1 ── * Alert
Customer     1 ── * Incident
Asset        1 ── * Alert
Asset        1 ── * Incident
Incident     1 ── * Alert
Incident     1 ── * IncidentEvent
User         1 ── * IncidentEvent (actor, optional)
```

- Organization → Customer: one-to-many
- Customer → Asset: one-to-many
- Customer → Incident: one-to-many
- Incident → Alert: one-to-many
- Incident → IncidentEvent: one-to-many

## 3. Primary and foreign key strategy

- All business entities use **UUID primary keys**
  (`UUIDField(primary_key=True, default=uuid.uuid4, editable=False)`).
- UUIDs avoid easy enumeration and are safe to expose as external identifiers.
- **Knowing a UUID never grants access.** Authorization is always checked
  separately.
- Foreign keys use `PROTECT` for critical business records (Organization,
  Customer, Asset, Incident, IncidentEvent) so records cannot be deleted
  accidentally. `Alert.incident` uses `SET_NULL` so an alert can outlive an
  incident; `IncidentEvent.actor` uses `SET_NULL` so history survives user
  deletion.

## 4. The seven core models

| Model | App | Purpose |
| --- | --- | --- |
| User | `accounts` | Engineers and administrators (custom user model) |
| Organization | `organizations` | The MSP company (tenant root) |
| Membership | `organizations` | User role within an organization |
| Customer | `customers` | A business managed by the MSP |
| Asset | `infrastructure` | Server, database, website, network device, application |
| Incident | `incidents` | Operational problem requiring investigation |
| Alert | `incidents` | Detected condition, correlated to an incident |
| IncidentEvent | `incidents` | Append-only incident timeline entry |

`AUTH_USER_MODEL = "accounts.User"` is configured before the first migration.

## 5. Tenant isolation requirements

- Every query for tenant data must be scoped through the authenticated
  membership's organization and the requested customer.
- A user may belong to multiple organizations; the active organization must be
  selected and validated per request.
- The service layer must verify that a referenced asset/customer actually
  belongs to the same customer and organization.
- Unauthorized access must return `404 Not Found` (not `403`) so the existence
  of another tenant's records is not revealed.
- These rules are enforced at the API level with automated tests, not only in
  the React frontend.

Example intended filter (illustrative, not production-ready on its own):

```python
Incident.objects.filter(customer__organization=active_organization)
```

## 6. Incident lifecycle statuses

```
new → triaging → investigating → awaiting_approval → remediating
    → verifying → resolved → closed
```

Additional states: `escalated`.

The database stores the allowed status values; valid **transitions** are
enforced by a dedicated service layer in a later lesson. An incident must not
jump directly from `new` to `closed`.

## 7. Alert fingerprinting and correlation

An alert `fingerprint` is a normalized value describing the underlying
condition, for example:

```
customer:UNIVERSITY-001|asset:university-web-01|condition:high_cpu
```

- Repeated alerts with the same fingerprint increment `occurrence_count` and
  update `last_seen_at` instead of creating new incidents.
- Fingerprinting is a correlation heuristic, not proof of a shared root cause;
  time windows and incident status are also considered.
- Indexed on `(customer, fingerprint)` and `(customer, status)`.

## 8. Audit event design

`IncidentEvent` is the incident timeline and audit trail:

- Fields: `incident`, `actor` (nullable), `event_type`, `description`,
  `metadata` (JSON), `created_at`.
- Ordered by `created_at`; indexed on `(incident, created_at)`.
- Treated as **append-only** in application logic: events are added, never
  edited or deleted by normal workflows.
- Stronger tamper resistance (database permissions, protected audit exports)
  will be added later.

## 9. Lifecycle coverage

| Incident stage | Database responsibility |
| --- | --- |
| Detection | Asset, Alert |
| Intake and correlation | Alert fingerprint, occurrence count |
| Classification | Incident severity and status |
| Investigation | Investigation, Evidence (later) |
| Remediation recommendation | RemediationAction (later) |
| Authorization | Approval (later) |
| Controlled execution | RemediationAction + audit records |
| Verification | IncidentEvent + verification evidence |
| Closure and learning | Incident, IncidentEvent, post-incident records |

The design is intentionally incremental: establish the core relationships
first, then extend.
