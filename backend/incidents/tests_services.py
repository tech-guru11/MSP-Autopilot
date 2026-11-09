from datetime import timedelta
from io import StringIO

from customers.models import Customer
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from infrastructure.models import Asset
from organizations.models import Organization

from .models import Alert, Incident
from .services.alerts import generate_fingerprint, ingest_alert
from .services.classification import classify_incident, map_alert_severity
from .services.correlation import create_incident_for_alert
from .services.sla import (
    calculate_elapsed_minutes,
    calculate_resolution_minutes,
)
from .services.state_machine import transition_incident


class IncidentServiceTestCase(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="TechCare")
        self.customer = Customer.objects.create(
            organization=self.organization,
            name="Cavendish University",
        )
        self.other_customer = Customer.objects.create(
            organization=self.organization,
            name="Example Hospital",
        )
        self.asset = Asset.objects.create(
            customer=self.customer,
            name="university-web-01",
            asset_type=Asset.AssetType.WEBSITE,
        )
        self.other_asset = Asset.objects.create(
            customer=self.customer,
            name="university-db-01",
            asset_type=Asset.AssetType.DATABASE,
        )
        self.foreign_asset = Asset.objects.create(
            customer=self.other_customer,
            name="hospital-api-01",
            asset_type=Asset.AssetType.APPLICATION,
        )

    def ingest(
        self,
        fingerprint="fingerprint-1",
        asset=None,
        condition=None,
        title="Website unavailable",
        severity=Alert.Severity.CRITICAL,
    ):
        return ingest_alert(
            customer=self.customer,
            asset=asset or self.asset,
            fingerprint=fingerprint,
            title=title,
            severity=severity,
            description="Website health check failed.",
            condition=condition,
        )


class FingerprintTests(IncidentServiceTestCase):
    def test_fingerprint_is_deterministic(self):
        first = generate_fingerprint(
            self.customer.id,
            self.asset.id,
            "website-down",
        )
        second = generate_fingerprint(
            self.customer.id,
            self.asset.id,
            "website-down",
        )

        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_fingerprint_changes_with_condition(self):
        first = generate_fingerprint(
            self.customer.id,
            self.asset.id,
            "website-down",
        )
        second = generate_fingerprint(
            self.customer.id,
            self.asset.id,
            "high-cpu",
        )

        self.assertNotEqual(first, second)

    def test_ingest_generates_fingerprint_when_missing(self):
        alert, created = ingest_alert(
            customer=self.customer,
            asset=self.asset,
            title="Website unavailable",
            severity=Alert.Severity.CRITICAL,
            condition="website-down",
        )

        self.assertTrue(created)
        self.assertEqual(
            alert.fingerprint,
            generate_fingerprint(
                self.customer.id,
                self.asset.id,
                "website-down",
            ),
        )


class AlertIngestionTests(IncidentServiceTestCase):
    def test_first_alert_is_created(self):
        alert, created = self.ingest()

        self.assertTrue(created)
        self.assertEqual(Alert.objects.count(), 1)
        self.assertEqual(alert.occurrence_count, 1)

    def test_repeated_alert_is_deduplicated(self):
        first, first_created = self.ingest()
        second, second_created = self.ingest()

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first.id, second.id)
        self.assertEqual(Alert.objects.count(), 1)
        self.assertEqual(second.occurrence_count, 2)

    def test_alert_outside_window_creates_new_alert(self):
        first, _ = self.ingest()

        Alert.objects.filter(pk=first.pk).update(
            last_seen_at=timezone.now() - timedelta(minutes=11),
        )

        second, created = self.ingest()

        self.assertTrue(created)
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(Alert.objects.count(), 2)

    def test_asset_must_belong_to_customer(self):
        with self.assertRaises(ValidationError):
            ingest_alert(
                customer=self.customer,
                asset=self.foreign_asset,
                fingerprint="fingerprint-1",
                title="Invalid asset",
                severity=Alert.Severity.HIGH,
            )

    def test_unknown_severity_is_rejected(self):
        with self.assertRaises(ValidationError):
            ingest_alert(
                customer=self.customer,
                asset=self.asset,
                fingerprint="fingerprint-1",
                title="Invalid severity",
                severity="urgent",
            )


class CorrelationTests(IncidentServiceTestCase):
    def test_incident_is_created_from_alert(self):
        alert, _ = self.ingest()

        incident, created = create_incident_for_alert(alert)

        self.assertTrue(created)
        self.assertEqual(Incident.objects.count(), 1)
        self.assertEqual(incident.severity, Incident.Severity.P1)
        self.assertEqual(incident.status, Incident.Status.NEW)

        alert.refresh_from_db()
        self.assertEqual(alert.incident_id, incident.id)
        self.assertTrue(
            incident.events.filter(
                event_type="incident_created",
            ).exists()
        )

    def test_related_alert_reuses_incident(self):
        first, _ = self.ingest(fingerprint="fingerprint-1")
        incident, _ = create_incident_for_alert(first)

        second, _ = self.ingest(fingerprint="fingerprint-2")
        reused, created = create_incident_for_alert(second)

        self.assertFalse(created)
        self.assertEqual(incident.id, reused.id)
        self.assertEqual(Incident.objects.count(), 1)
        self.assertTrue(
            reused.events.filter(
                event_type="alert_correlated",
            ).exists()
        )

    def test_unrelated_alert_creates_separate_incident(self):
        first, _ = self.ingest(fingerprint="fingerprint-1")
        incident_a, _ = create_incident_for_alert(first)

        second, _ = self.ingest(
            fingerprint="fingerprint-2",
            asset=self.other_asset,
        )
        incident_b, created = create_incident_for_alert(second)

        self.assertTrue(created)
        self.assertNotEqual(incident_a.id, incident_b.id)
        self.assertEqual(Incident.objects.count(), 2)

    def test_correlation_is_idempotent(self):
        alert, _ = self.ingest()

        first, first_created = create_incident_for_alert(alert)
        second, second_created = create_incident_for_alert(alert)

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first.id, second.id)
        self.assertEqual(Incident.objects.count(), 1)

    def test_resolved_incident_is_not_reused(self):
        Incident.objects.create(
            customer=self.customer,
            asset=self.asset,
            title="Previous outage",
            severity=Incident.Severity.P1,
            status=Incident.Status.RESOLVED,
            started_at=timezone.now() - timedelta(hours=2),
            resolved_at=timezone.now() - timedelta(hours=1),
        )

        alert, _ = self.ingest(fingerprint="fingerprint-new")
        incident, created = create_incident_for_alert(alert)

        self.assertTrue(created)
        self.assertEqual(Incident.objects.count(), 2)
        self.assertEqual(incident.status, Incident.Status.NEW)

    def test_alert_asset_from_other_customer_is_rejected(self):
        alert = Alert.objects.create(
            customer=self.customer,
            asset=self.foreign_asset,
            fingerprint="fingerprint-1",
            title="Invalid alert",
            severity=Alert.Severity.HIGH,
        )

        with self.assertRaises(ValidationError):
            create_incident_for_alert(alert)


class ClassificationTests(IncidentServiceTestCase):
    def test_map_alert_severity(self):
        self.assertEqual(
            map_alert_severity("critical"),
            Incident.Severity.P1,
        )
        self.assertEqual(
            map_alert_severity("high"),
            Incident.Severity.P2,
        )
        self.assertEqual(
            map_alert_severity("medium"),
            Incident.Severity.P3,
        )
        self.assertEqual(
            map_alert_severity("low"),
            Incident.Severity.P4,
        )
        self.assertEqual(
            map_alert_severity("unknown"),
            Incident.Severity.P3,
        )

    def test_critical_unavailable_service_is_p1(self):
        result = classify_incident(
            affected_users=10,
            service_criticality="critical",
            service_unavailable=True,
            workaround_available=False,
        )

        self.assertEqual(result["severity"], Incident.Severity.P1)

    def test_many_affected_users_is_p1(self):
        result = classify_incident(
            affected_users=500,
            service_criticality="standard",
            service_unavailable=True,
            workaround_available=False,
        )

        self.assertEqual(result["severity"], Incident.Severity.P1)

    def test_unavailable_service_is_p2(self):
        result = classify_incident(
            affected_users=20,
            service_criticality="standard",
            service_unavailable=True,
            workaround_available=True,
        )

        self.assertEqual(result["severity"], Incident.Severity.P2)

    def test_no_workaround_is_p2(self):
        result = classify_incident(
            affected_users=20,
            service_criticality="standard",
            service_unavailable=False,
            workaround_available=False,
        )

        self.assertEqual(result["severity"], Incident.Severity.P2)

    def test_minor_issue_is_p3(self):
        result = classify_incident(
            affected_users=2,
            service_criticality="low",
            service_unavailable=False,
            workaround_available=True,
        )

        self.assertEqual(result["severity"], Incident.Severity.P3)


class StateMachineTests(IncidentServiceTestCase):
    def make_incident(self, status=Incident.Status.NEW):
        return Incident.objects.create(
            customer=self.customer,
            asset=self.asset,
            title="University website unavailable",
            severity=Incident.Severity.P1,
            status=status,
        )

    def test_valid_transition_chain(self):
        incident = self.make_incident()

        for status in [
            Incident.Status.TRIAGING,
            Incident.Status.INVESTIGATING,
            Incident.Status.AWAITING_APPROVAL,
            Incident.Status.REMEDIATING,
            Incident.Status.VERIFYING,
            Incident.Status.RESOLVED,
            Incident.Status.CLOSED,
        ]:
            incident = transition_incident(incident.id, status)
            self.assertEqual(incident.status, status)

        incident.refresh_from_db()
        self.assertIsNotNone(incident.resolved_at)
        self.assertEqual(incident.events.count(), 7)

    def test_invalid_transition_is_rejected(self):
        incident = self.make_incident()

        with self.assertRaises(ValidationError):
            transition_incident(
                incident.id,
                Incident.Status.CLOSED,
            )

        incident.refresh_from_db()
        self.assertEqual(incident.status, Incident.Status.NEW)

    def test_unknown_status_is_rejected(self):
        incident = self.make_incident()

        with self.assertRaises(ValidationError):
            transition_incident(incident.id, "flying")

    def test_same_status_is_idempotent(self):
        incident = self.make_incident()

        result = transition_incident(
            incident.id,
            Incident.Status.NEW,
        )

        self.assertEqual(result.status, Incident.Status.NEW)
        self.assertEqual(incident.events.count(), 0)

    def test_escalation_path(self):
        incident = self.make_incident()

        transition_incident(
            incident.id,
            Incident.Status.ESCALATED,
        )
        incident = transition_incident(
            incident.id,
            Incident.Status.INVESTIGATING,
        )

        self.assertEqual(
            incident.status,
            Incident.Status.INVESTIGATING,
        )

    def test_missing_incident_is_rejected(self):
        with self.assertRaises(ValidationError):
            transition_incident(
                "00000000-0000-0000-0000-000000000000",
                Incident.Status.TRIAGING,
            )


class SLATests(IncidentServiceTestCase):
    def test_elapsed_minutes_with_explicit_end(self):
        start = timezone.now() - timedelta(minutes=10)

        elapsed = calculate_elapsed_minutes(
            start,
            start + timedelta(minutes=10),
        )

        self.assertAlmostEqual(elapsed, 10, places=3)

    def test_elapsed_minutes_uses_now(self):
        start = timezone.now() - timedelta(minutes=5)

        elapsed = calculate_elapsed_minutes(start)

        self.assertAlmostEqual(elapsed, 5, delta=0.5)

    def test_resolution_minutes(self):
        incident = Incident.objects.create(
            customer=self.customer,
            asset=self.asset,
            title="University website unavailable",
            severity=Incident.Severity.P1,
            started_at=timezone.now() - timedelta(minutes=30),
            resolved_at=timezone.now() - timedelta(minutes=5),
        )

        elapsed = calculate_resolution_minutes(incident)

        self.assertAlmostEqual(elapsed, 25, delta=0.5)


class SimulateOutageCommandTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="TechCare")
        self.customer = Customer.objects.create(
            organization=self.organization,
            name="Cavendish University",
        )
        self.asset = Asset.objects.create(
            customer=self.customer,
            name="university-web-01",
            asset_type=Asset.AssetType.WEBSITE,
        )

    def test_running_twice_reuses_alert_and_incident(self):
        call_command("simulate_outage", stdout=StringIO())

        self.assertEqual(Alert.objects.count(), 1)
        self.assertEqual(Incident.objects.count(), 1)

        call_command("simulate_outage", stdout=StringIO())

        self.assertEqual(Alert.objects.count(), 1)
        self.assertEqual(Incident.objects.count(), 1)

        alert = Alert.objects.get()
        self.assertEqual(alert.occurrence_count, 2)
