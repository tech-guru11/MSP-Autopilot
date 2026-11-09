from ai_engine.schemas import (
    CauseHypothesis,
    EvidenceItem,
    InvestigationResult,
    RemediationRecommendation,
)

SERVICE_ERROR_STATUSES = range(500, 600)


def _observations(evidence):
    if not isinstance(evidence, dict):
        return {}

    observations = evidence.get("observations", evidence)

    if not isinstance(observations, dict):
        return {}

    return observations


def _number(value):
    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return value

    return None


def _build_evidence(observations):
    evidence = []
    http_status = _number(observations.get("http_status"))
    db_usage = _number(observations.get("db_connection_usage"))
    cpu_usage = _number(observations.get("cpu_usage"))

    if http_status is not None:
        evidence.append(
            EvidenceItem(
                source="external_monitor",
                observation=f"Service returned HTTP {http_status}.",
                supports="Service availability",
            )
        )

    if db_usage is not None:
        evidence.append(
            EvidenceItem(
                source="database_monitor",
                observation=(
                    "Database connection usage is at "
                    f"{db_usage}% of the configured limit."
                ),
                supports="Database capacity",
            )
        )

    if cpu_usage is not None:
        evidence.append(
            EvidenceItem(
                source="infrastructure_metrics",
                observation=f"CPU utilization is at {cpu_usage}%.",
                supports="Compute capacity",
            )
        )

    if observations.get("recent_deployment"):
        evidence.append(
            EvidenceItem(
                source="deployment_history",
                observation=(
                    "A deployment occurred shortly before the incident."
                ),
                supports="Recent change correlation",
            )
        )

    if observations.get("dns_failure"):
        evidence.append(
            EvidenceItem(
                source="external_monitor",
                observation=("DNS resolution failed from external probes."),
                supports="Name resolution",
            )
        )

    if observations.get("log_errors"):
        evidence.append(
            EvidenceItem(
                source="application_logs",
                observation=(
                    "Application logs were provided and contain "
                    "error data that requires correlation."
                ),
                supports="Application errors",
            )
        )

    return evidence


def _build_hypotheses(observations):
    hypotheses = []
    db_usage = _number(observations.get("db_connection_usage"))
    cpu_usage = _number(observations.get("cpu_usage"))

    if db_usage is not None and db_usage >= 90:
        hypotheses.append(
            CauseHypothesis(
                title="Possible database connection exhaustion",
                explanation=(
                    "Database connections are close to their "
                    "configured maximum."
                ),
                confidence="high",
                evidence_sources=["database_monitor"],
            )
        )

    if cpu_usage is not None and cpu_usage >= 90:
        hypotheses.append(
            CauseHypothesis(
                title="Possible CPU saturation",
                explanation=(
                    "CPU utilization is near capacity and may be "
                    "preventing the service from responding promptly."
                ),
                confidence="high",
                evidence_sources=["infrastructure_metrics"],
            )
        )

    if observations.get("recent_deployment"):
        hypotheses.append(
            CauseHypothesis(
                title="Possible deployment-related regression",
                explanation=(
                    "A recent deployment may be related to the "
                    "service failure."
                ),
                confidence="medium",
                evidence_sources=["deployment_history"],
            )
        )

    if observations.get("dns_failure"):
        hypotheses.append(
            CauseHypothesis(
                title="Possible DNS resolution failure",
                explanation=(
                    "External probes could not resolve the service "
                    "name, which can make the service unreachable."
                ),
                confidence="high",
                evidence_sources=["external_monitor"],
            )
        )

    if not hypotheses:
        hypotheses.append(
            CauseHypothesis(
                title="Cause not established",
                explanation=(
                    "Available evidence is insufficient to identify "
                    "a likely cause."
                ),
                confidence="low",
                evidence_sources=[],
            )
        )

    return hypotheses


def _assess_severity(observations):
    http_status = _number(observations.get("http_status"))
    db_usage = _number(observations.get("db_connection_usage"))
    cpu_usage = _number(observations.get("cpu_usage"))

    if observations.get("service_unavailable"):
        return "P1"

    if http_status is not None and http_status in SERVICE_ERROR_STATUSES:
        return "P1"

    if observations.get("dns_failure"):
        return "P2"

    if db_usage is not None and db_usage >= 90:
        return "P2"

    if cpu_usage is not None and cpu_usage >= 90:
        return "P2"

    return "P3"


def _missing_information(observations):
    missing = []
    http_status = _number(observations.get("http_status"))
    db_usage = _number(observations.get("db_connection_usage"))
    cpu_usage = _number(observations.get("cpu_usage"))

    if http_status is None:
        missing.append("Confirm service availability from external probes.")

    if db_usage is None:
        missing.append(
            "Collect database connection usage and timeout metrics."
        )

    if cpu_usage is None:
        missing.append("Collect CPU utilization metrics.")

    if not observations.get("log_errors"):
        missing.append("Collect application error logs around the incident.")

    if "recent_deployment" not in observations:
        missing.append(
            "Check deployment history immediately before the incident."
        )

    if "dns_failure" not in observations:
        missing.append("Test DNS resolution from external probes.")

    if observations.get("recent_deployment"):
        missing.append(
            "Compare error rates before and after the most recent deployment."
        )

    if not missing:
        missing.append(
            "Validate the leading hypothesis against historical baselines."
        )

    return missing


def _recommendation(hypotheses):
    title = hypotheses[0].title

    if title == "Possible database connection exhaustion":
        return RemediationRecommendation(
            action=(
                "Inspect the database connection pool, active "
                "sessions, and slow queries."
            ),
            reason=(
                "Connection exhaustion is the leading hypothesis "
                "supported by the current evidence."
            ),
            risk="low",
            reversible=True,
            requires_approval=False,
        )

    if title == "Possible CPU saturation":
        return RemediationRecommendation(
            action=(
                "Inspect CPU-heavy processes and recent traffic patterns."
            ),
            reason=(
                "CPU saturation is the leading hypothesis supported "
                "by the current evidence."
            ),
            risk="low",
            reversible=True,
            requires_approval=False,
        )

    if title == "Possible deployment-related regression":
        return RemediationRecommendation(
            action=(
                "Compare the recent deployment with the previous "
                "release and review error rates."
            ),
            reason=(
                "A recent deployment may be related to the service "
                "failure, but causation is not established."
            ),
            risk="low",
            reversible=True,
            requires_approval=False,
        )

    if title == "Possible DNS resolution failure":
        return RemediationRecommendation(
            action=(
                "Verify DNS records and resolution from multiple regions."
            ),
            reason=(
                "DNS resolution failure is supported by external "
                "probe evidence."
            ),
            risk="low",
            reversible=True,
            requires_approval=False,
        )

    return RemediationRecommendation(
        action="Collect additional evidence before changing infrastructure.",
        reason=(
            "Available evidence is insufficient to justify a "
            "remediation action."
        ),
        risk="low",
        reversible=True,
        requires_approval=False,
    )


def _verification_steps(observations):
    steps = [
        "Check service availability from multiple regions.",
        "Test a representative user journey.",
        "Monitor error rate and latency for a stable window.",
    ]

    db_usage = _number(observations.get("db_connection_usage"))

    if db_usage is not None:
        steps.append("Monitor database connection usage after any change.")

    return steps


def investigate_incident(evidence):
    observations = _observations(evidence)
    hypotheses = _build_hypotheses(observations)
    evidence_items = _build_evidence(observations)
    http_status = _number(observations.get("http_status"))

    if http_status is not None:
        incident_summary = (
            f"Service is returning HTTP {http_status} and requires "
            "investigation."
        )
    else:
        incident_summary = (
            "Incident evidence was reviewed and requires further "
            "investigation."
        )

    return InvestigationResult(
        incident_summary=incident_summary,
        severity_assessment=_assess_severity(observations),
        hypotheses=hypotheses,
        evidence=evidence_items,
        missing_information=_missing_information(observations),
        recommendation=_recommendation(hypotheses),
        verification_steps=_verification_steps(observations),
    )
