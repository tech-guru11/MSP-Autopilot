from organizations.models import Membership, Organization
from rest_framework import status
from rest_framework.test import APITestCase

from .models import User


class MeEndpointTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="engineer",
            password="test-password",
            email="engineer@example.com",
        )
        self.organization = Organization.objects.create(name="TechCare")
        Membership.objects.create(
            user=self.user,
            organization=self.organization,
            role=Membership.Role.ENGINEER,
        )

    def test_me_returns_profile_and_memberships(self):
        self.client.force_authenticate(self.user)

        response = self.client.get("/api/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "engineer")
        self.assertEqual(
            response.data["memberships"][0]["role"],
            Membership.Role.ENGINEER,
        )
        self.assertNotIn("password", response.data)

    def test_me_requires_authentication(self):
        response = self.client.get("/api/me/")

        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
