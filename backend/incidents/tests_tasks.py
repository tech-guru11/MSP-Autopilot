from unittest.mock import patch

from accounts.models import User
from customers.models import Customer
from django.test import TestCase
from infrastructure.models import Asset
from organizations.models import Membership, Organization
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Incident, Investigation
from .tasks import run_investigation_task

EVIDENCE = {
    "observations": {
        "http_status": 503,
        "db_connection_usage": 98,
        "cpu_usage": 35,
        "recent_deployment": True,
        "log_errors": True,
    }
}


class InvestigationTaskTests(TestCase):
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

    def test_task_runs_investigation(self):
        result = run_investigation_task.apply(
            args=[
                str(self.incident.id),
                EVIDENCE,
                str(self.user.id),
            ]
        )

        self.assertTrue(result.successful(), result.result)
        self.assertEqual(result.result["severity_assessment"], "P1")
        self.assertEqual(
            result.result["incident_id"],
            str(self.incident.id),
        )
        self.assertTrue(
            Investigation.objects.filter(
                incident=self.incident,
            ).exists()
        )


class AsyncInvestigationAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="engineer",
            password="test-password",
        )
        self.organization = Organization.objects.create(name="TechCare")
        Membership.objects.create(
            user=self.user,
            organization=self.organization,
            role=Membership.Role.ENGINEER,
        )
        self.customer = Customer.objects.create(
            organization=self.organization,
            name="Cavendish University",
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
        self.client.force_authenticate(self.user)

    def headers(self):
        return {
            "HTTP_X_ORGANIZATION_ID": str(self.organization.id),
        }

    def test_async_endpoint_queues_investigation(self):
        response = self.client.post(
            f"/api/incidents/{self.incident.id}/investigate/",
            {"evidence": EVIDENCE, "run_async": True},
            format="json",
            **self.headers(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_202_ACCEPTED,
        )
        self.assertEqual(response.data["status"], "queued")
        self.assertIn("task_id", response.data)
        self.assertIn("status_url", response.data)
        self.assertTrue(
            Investigation.objects.filter(
                incident=self.incident,
            ).exists()
        )

    @patch(
        "incidents.views.run_investigation_task.delay",
        side_effect=RuntimeError("broker unavailable"),
    )
    def test_async_endpoint_handles_broker_failure(self, delay):
        response = self.client.post(
            f"/api/incidents/{self.incident.id}/investigate/",
            {"evidence": EVIDENCE, "run_async": True},
            format="json",
            **self.headers(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertEqual(
            Investigation.objects.count(),
            0,
        )
