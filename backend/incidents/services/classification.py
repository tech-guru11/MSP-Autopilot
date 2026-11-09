from incidents.models import Incident


def map_alert_severity(alert_severity):
    mapping = {
        "critical": Incident.Severity.P1,
        "high": Incident.Severity.P2,
        "medium": Incident.Severity.P3,
        "low": Incident.Severity.P4,
    }
    return mapping.get(alert_severity, Incident.Severity.P3)


def classify_incident(
    affected_users,
    service_criticality,
    service_unavailable,
    workaround_available,
):
    if service_unavailable and (
        affected_users >= 500 or service_criticality == "critical"
    ):
        return {
            "severity": Incident.Severity.P1,
            "priority": Incident.Severity.P1,
        }

    if service_unavailable:
        return {
            "severity": Incident.Severity.P2,
            "priority": Incident.Severity.P2,
        }

    if not workaround_available:
        return {
            "severity": Incident.Severity.P2,
            "priority": Incident.Severity.P2,
        }

    return {
        "severity": Incident.Severity.P3,
        "priority": Incident.Severity.P3,
    }
