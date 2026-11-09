from accounts.models import User
from customers.models import Customer
from infrastructure.models import Asset
from organizations.models import Membership, Organization
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import Alert, Incident


class IncidentAPITestCase(APITestCase):
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
        self.client.force_authenticate(self.user)

    def headers(self):
        return {
            "HTTP_X_ORGANIZATION_ID": str(self.organization.id),
        }


class AlertIngestionAPITests(IncidentAPITestCase):
    def ingest(self, **overrides):
        payload = {
            "customer": str(self.customer.id),
            "asset": str(self.asset.id),
            "title": "University website unavailable",
            "description": "Website returns HTTP 503.",
            "severity": Alert.Severity.CRITICAL,
            "condition": "website-down",
        }
        payload.update(overrides)
        return self.client.post(
            "/api/alerts/",
            payload,
            format="json",
            **self.headers(),
        )

    def test_first_alert_creates_alert_and_incident(self):
        response = self.ingest()

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(Alert.objects.count(), 1)
        self.assertEqual(Incident.objects.count(), 1)
        self.assertIsNotNone(response.data["incident"])

    def test_repeated_alert_is_deduplicated(self):
        first = self.ingest()
        second = self.ingest()

        self.assertEqual(
            first.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(
            second.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(Alert.objects.count(), 1)
        self.assertEqual(Incident.objects.count(), 1)
        self.assertEqual(second.data["occurrence_count"], 2)

    def test_cannot_ingest_for_another_organization_customer(self):
        response = self.ingest(customer=str(self.other_customer.id))

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_viewer_cannot_ingest(self):
        viewer = User.objects.create_user(
            username="viewer",
            password="test-password",
        )
        Membership.objects.create(
            user=viewer,
            organization=self.organization,
            role=Membership.Role.VIEWER,
        )
        self.client.force_authenticate(viewer)

        response = self.ingest()

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )


class IncidentTransitionAPITests(IncidentAPITestCase):
    def setUp(self):
        super().setUp()
        self.incident = Incident.objects.create(
            customer=self.customer,
            asset=self.asset,
            title="University website unavailable",
            severity=Incident.Severity.P1,
        )

    def test_valid_transition(self):
        response = self.client.post(
            f"/api/incidents/{self.incident.id}/transition/",
            {"status": Incident.Status.TRIAGING},
            format="json",
            **self.headers(),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.incident.refresh_from_db()
        self.assertEqual(
            self.incident.status,
            Incident.Status.TRIAGING,
        )

    def test_invalid_transition_is_rejected(self):
        response = self.client.post(
            f"/api/incidents/{self.incident.id}/transition/",
            {"status": Incident.Status.CLOSED},
            format="json",
            **self.headers(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_events_endpoint_returns_timeline(self):
        self.client.post(
            f"/api/incidents/{self.incident.id}/transition/",
            {"status": Incident.Status.TRIAGING},
            format="json",
            **self.headers(),
        )

        response = self.client.get(
            f"/api/incidents/{self.incident.id}/events/",
            **self.headers(),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["event_type"], "status_changed")

    def test_viewer_cannot_transition(self):
        viewer = User.objects.create_user(
            username="viewer",
            password="test-password",
        )
        Membership.objects.create(
            user=viewer,
            organization=self.organization,
            role=Membership.Role.VIEWER,
        )
        self.client.force_authenticate(viewer)

        response = self.client.post(
            f"/api/incidents/{self.incident.id}/transition/",
            {"status": Incident.Status.TRIAGING},
            format="json",
            **self.headers(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )


class AccountAndHealthAPITests(IncidentAPITestCase):
    def test_me_returns_memberships(self):
        response = self.client.get("/api/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "engineer")
        self.assertEqual(len(response.data["memberships"]), 1)

    def test_token_authentication_works(self):
        self.client.force_authenticate(user=None)
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = self.client.get("/api/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_health_endpoint(self):
        response = self.client.get("/health/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"], "ok")
