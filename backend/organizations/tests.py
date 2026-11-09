from accounts.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Membership, Organization


class OrganizationListTests(APITestCase):
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
        self.client.force_authenticate(self.user)

    def test_list_returns_only_member_organizations(self):
        response = self.client.get("/api/organizations/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data["results"]]
        self.assertEqual(ids, [str(self.organization_a.id)])

    def test_unauthenticated_request_is_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/organizations/")

        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
