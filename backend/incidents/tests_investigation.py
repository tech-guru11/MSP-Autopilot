from accounts.models import User
from customers.models import Customer
from django.core.exceptions import ValidationError
from django.test import TestCase
from infrastructure.models import Asset
from organizations.models import Membership, Organization
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Evidence, Incident, Investigation
from .services.investigation import run_investigation

EVIDENCE = {
    "observations": {
        "http_status": 503,
        "db_connection_usage": 98,
        "cpu_usage": 35,
        "recent_deployment": True,
        "log_errors": True,
    }
}


class InvestigationServiceTests(TestCase):
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
        self.user = User.objects.create_user(
            username="engineer",
            password="test-password",
        )
        self.incident = Incident.objects.create(
            customer=self.customer,
            asset=self.asset,
            title="University website unavailable",
            severity=Incident.Severity.P1,
            status=Incident.Status.INVESTIGATING,
        )

    def test_investigation_persists_result_and_event(self):
        investigation = run_investigation(
            self.incident,
            EVIDENCE,
            actor=self.user,
        )

        self.assertEqual(Investigation.objects.count(), 1)
        self.assertEqual(investigation.incident_id, self.incident.id)
        self.assertEqual(investigation.requested_by_id, self.user.id)
        self.assertEqual(investigation.severity_assessment, "P1")
        self.assertIn("hypotheses", investigation.result)
        self.assertTrue(investigation.evidence_items.exists())
        self.assertTrue(
            self.incident.events.filter(
                event_type="investigation_completed",
            ).exists()
        )

        self.incident.refresh_from_db()
        self.assertEqual(
            self.incident.status,
            Incident.Status.INVESTIGATING,
        )

    def test_investigation_requires_investigating_status(self):
        self.incident.status = Incident.Status.NEW
        self.incident.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            run_investigation(self.incident, EVIDENCE)

        self.assertEqual(Investigation.objects.count(), 0)
        self.assertEqual(Evidence.objects.count(), 0)

    def test_investigation_rejects_non_object_evidence(self):
        with self.assertRaises(ValidationError):
            run_investigation(self.incident, ["not", "an", "object"])

        self.assertEqual(Investigation.objects.count(), 0)


class InvestigationAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="engineer",
            password="test-password",
        )
        self.organization = Organization.objects.create(name="TechCare")
        self.other_organization = Organization.objects.create(name="CloudCare")
        Membership.objects.create(
            user=self.user,
            organization=self.organization,
            role=Membership.Role.ENGINEER,
        )
        self.customer = Customer.objects.create(
            organization=self.organization,
            name="Cavendish University",
        )
        self.other_customer = Customer.objects.create(
            organization=self.other_organization,
            name="Example Hospital",
        )
        self.asset = Asset.objects.create(
            customer=self.customer,
            name="university-web-01",
            asset_type=Asset.AssetType.WEBSITE,
        )
        self.incident = Incident.objects.create(
            customer=self.customer,
            asset=self.asset,
            title="University website unavailable",
            severity=Incident.Severity.P1,
            status=Incident.Status.INVESTIGATING,
        )
        self.other_incident = Incident.objects.create(
            customer=self.other_customer,
            title="Hospital API unavailable",
            severity=Incident.Severity.P1,
            status=Incident.Status.INVESTIGATING,
        )
        self.client.force_authenticate(self.user)

    def headers(self):
        return {
            "HTTP_X_ORGANIZATION_ID": str(self.organization.id),
        }

    def test_investigate_endpoint_returns_investigation(self):
        response = self.client.post(
            f"/api/incidents/{self.incident.id}/investigate/",
            {"evidence": EVIDENCE},
            format="json",
            **self.headers(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(response.data["status"], "completed")
        self.assertEqual(response.data["severity_assessment"], "P1")
        self.assertTrue(response.data["evidence_items"])

        self.incident.refresh_from_db()
        self.assertEqual(
            self.incident.status,
            Incident.Status.INVESTIGATING,
        )

    def test_investigate_endpoint_rejects_wrong_status(self):
        self.incident.status = Incident.Status.NEW
        self.incident.save(update_fields=["status"])

        response = self.client.post(
            f"/api/incidents/{self.incident.id}/investigate/",
            {"evidence": EVIDENCE},
            format="json",
            **self.headers(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(Investigation.objects.count(), 0)

    def test_investigate_endpoint_rejects_cross_tenant_incident(self):
        response = self.client.post(
            f"/api/incidents/{self.other_incident.id}/investigate/",
            {"evidence": EVIDENCE},
            format="json",
            **self.headers(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(Investigation.objects.count(), 0)

    def test_investigate_endpoint_requires_evidence(self):
        response = self.client.post(
            f"/api/incidents/{self.incident.id}/investigate/",
            {},
            format="json",
            **self.headers(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_investigate_endpoint_rejects_non_object_evidence(self):
        response = self.client.post(
            f"/api/incidents/{self.incident.id}/investigate/",
            {"evidence": ["not", "an", "object"]},
            format="json",
            **self.headers(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
