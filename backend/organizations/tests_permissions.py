from accounts.models import User
from customers.models import Customer
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Membership, Organization


class RolePermissionTests(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="TechCare")
        self.admin = User.objects.create_user(
            username="admin",
            password="test-password",
        )
        self.engineer = User.objects.create_user(
            username="engineer",
            password="test-password",
        )
        self.viewer = User.objects.create_user(
            username="viewer",
            password="test-password",
        )
        Membership.objects.create(
            user=self.admin,
            organization=self.organization,
            role=Membership.Role.ADMIN,
        )
        Membership.objects.create(
            user=self.engineer,
            organization=self.organization,
            role=Membership.Role.ENGINEER,
        )
        self.viewer_membership = Membership.objects.create(
            user=self.viewer,
            organization=self.organization,
            role=Membership.Role.VIEWER,
        )
        self.customer = Customer.objects.create(
            organization=self.organization,
            name="Cavendish University",
        )

    def headers(self):
        return {
            "HTTP_X_ORGANIZATION_ID": str(self.organization.id),
        }

    def test_viewer_can_read_customers(self):
        self.client.force_authenticate(self.viewer)
        response = self.client.get(
            "/api/customers/",
            **self.headers(),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_create_customers(self):
        self.client.force_authenticate(self.viewer)
        response = self.client.post(
            "/api/customers/",
            {"name": "New Customer"},
            format="json",
            **self.headers(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_engineer_can_create_customers(self):
        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            "/api/customers/",
            {"name": "New Customer"},
            format="json",
            **self.headers(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

    def test_only_admin_can_list_memberships(self):
        self.client.force_authenticate(self.viewer)
        forbidden = self.client.get(
            "/api/memberships/",
            **self.headers(),
        )
        self.assertEqual(
            forbidden.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.client.force_authenticate(self.admin)
        allowed = self.client.get(
            "/api/memberships/",
            **self.headers(),
        )
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)

    def test_admin_can_add_membership(self):
        new_user = User.objects.create_user(
            username="new-user",
            password="test-password",
        )
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            "/api/memberships/",
            {
                "user": str(new_user.id),
                "role": Membership.Role.ENGINEER,
            },
            format="json",
            **self.headers(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertTrue(
            Membership.objects.filter(
                organization=self.organization,
                user=new_user,
                role=Membership.Role.ENGINEER,
            ).exists()
        )

    def test_last_admin_cannot_be_demoted(self):
        self.client.force_authenticate(self.admin)
        admin_membership = Membership.objects.get(
            organization=self.organization,
            user=self.admin,
        )

        response = self.client.patch(
            f"/api/memberships/{admin_membership.id}/",
            {"role": Membership.Role.ENGINEER},
            format="json",
            **self.headers(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        admin_membership.refresh_from_db()
        self.assertEqual(
            admin_membership.role,
            Membership.Role.ADMIN,
        )

    def test_last_admin_cannot_be_removed(self):
        self.client.force_authenticate(self.admin)
        admin_membership = Membership.objects.get(
            organization=self.organization,
            user=self.admin,
        )

        response = self.client.delete(
            f"/api/memberships/{admin_membership.id}/",
            **self.headers(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertTrue(
            Membership.objects.filter(id=admin_membership.id).exists()
        )
