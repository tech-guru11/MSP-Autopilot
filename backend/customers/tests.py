from accounts.models import User
from organizations.models import Membership, Organization
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Customer


class CustomerIsolationTests(APITestCase):
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
        self.client.force_authenticate(self.user)

    def headers(self, organization):
        return {"HTTP_X_ORGANIZATION_ID": str(organization.id)}

    def test_list_returns_only_active_organization_customers(self):
        response = self.client.get(
            "/api/customers/",
            **self.headers(self.organization_a),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data["results"]]
        self.assertEqual(ids, [str(self.customer_a.id)])

    def test_cannot_retrieve_another_organization_customer(self):
        response = self.client.get(
            f"/api/customers/{self.customer_b.id}/",
            **self.headers(self.organization_a),
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_assigns_organization_from_membership(self):
        response = self.client.post(
            "/api/customers/",
            {
                "name": "New Customer",
                "contact_email": "ops@example.com",
                "status": "active",
                "organization": str(self.organization_b.id),
            },
            format="json",
            **self.headers(self.organization_a),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Customer.objects.get(id=response.data["id"])
        self.assertEqual(created.organization_id, self.organization_a.id)

    def test_missing_organization_header_is_rejected(self):
        response = self.client.get("/api/customers/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_organization_header_is_rejected(self):
        response = self.client.get(
            "/api/customers/",
            HTTP_X_ORGANIZATION_ID="not-a-uuid",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_member_organization_is_forbidden(self):
        response = self.client.get(
            "/api/customers/",
            **self.headers(self.organization_b),
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_request_is_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(
            "/api/customers/",
            **self.headers(self.organization_a),
        )

        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_empty_customer_name_is_rejected(self):
        response = self.client.post(
            "/api/customers/",
            {"name": "   ", "status": "active"},
            format="json",
            **self.headers(self.organization_a),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
