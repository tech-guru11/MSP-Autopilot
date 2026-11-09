from accounts.models import User
from customers.models import Customer
from infrastructure.models import Asset
from organizations.models import Membership, Organization
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Incident


class IncidentTenantTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="engineer",
            password="test-password",
        )
        self.organization_a = Organization.objects.create(name="TechCare")
        self.organization_b = Organization.objects.create(name="CloudCare")
        Membership.objects.create(
            user=self.user,
            organization=self.organization_a,
            role=Membership.Role.ENGINEER,
        )
        self.customer_a = Customer.objects.create(
            organization=self.organization_a,
            name="Cavendish University",
        )
        self.customer_b = Customer.objects.create(
            organization=self.organization_b,
            name="Example Hospital",
        )
        self.asset_a = Asset.objects.create(
            customer=self.customer_a,
            name="university-web-01",
            asset_type=Asset.AssetType.WEBSITE,
        )
        self.asset_b = Asset.objects.create(
            customer=self.customer_b,
            name="hospital-api-01",
            asset_type=Asset.AssetType.APPLICATION,
        )
        self.incident_a = Incident.objects.create(
            customer=self.customer_a,
            asset=self.asset_a,
            title="University website unavailable",
            severity=Incident.Severity.P1,
        )
        self.incident_b = Incident.objects.create(
            customer=self.customer_b,
            asset=self.asset_b,
            title="Hospital API unavailable",
            severity=Incident.Severity.P1,
        )
        self.client.force_authenticate(self.user)

    def headers(self, organization):
        return {"HTTP_X_ORGANIZATION_ID": str(organization.id)}

    def test_list_returns_only_active_organization_incidents(self):
        response = self.client.get(
            "/api/incidents/",
            **self.headers(self.organization_a),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data["results"]]
        self.assertEqual(ids, [str(self.incident_a.id)])

    def test_cannot_retrieve_another_organization_incident(self):
        response = self.client.get(
            f"/api/incidents/{self.incident_b.id}/",
            **self.headers(self.organization_a),
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_create_incident_for_another_organization_customer(self):
        response = self.client.post(
            "/api/incidents/",
            {
                "customer": str(self.customer_b.id),
                "title": "Rogue incident",
                "severity": Incident.Severity.P2,
            },
            format="json",
            **self.headers(self.organization_a),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_attach_asset_from_another_customer(self):
        response = self.client.post(
            "/api/incidents/",
            {
                "customer": str(self.customer_a.id),
                "asset": str(self.asset_b.id),
                "title": "Mismatched asset",
                "severity": Incident.Severity.P2,
            },
            format="json",
            **self.headers(self.organization_a),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_incident_defaults_to_new_status(self):
        response = self.client.post(
            "/api/incidents/",
            {
                "customer": str(self.customer_a.id),
                "asset": str(self.asset_a.id),
                "title": "Website returning 503",
                "severity": Incident.Severity.P1,
                "status": Incident.Status.CLOSED,
            },
            format="json",
            **self.headers(self.organization_a),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], Incident.Status.NEW)
        created = Incident.objects.get(id=response.data["id"])
        self.assertEqual(created.status, Incident.Status.NEW)
        self.assertIsNotNone(created.started_at)

    def test_status_cannot_be_changed_through_api(self):
        response = self.client.patch(
            f"/api/incidents/{self.incident_a.id}/",
            {"status": Incident.Status.CLOSED},
            format="json",
            **self.headers(self.organization_a),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.incident_a.refresh_from_db()
        self.assertEqual(self.incident_a.status, Incident.Status.NEW)

    def test_cannot_move_incident_to_another_organization_customer(self):
        response = self.client.patch(
            f"/api/incidents/{self.incident_a.id}/",
            {"customer": str(self.customer_b.id)},
            format="json",
            **self.headers(self.organization_a),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.incident_a.refresh_from_db()
        self.assertEqual(
            self.incident_a.customer_id,
            self.customer_a.id,
        )
