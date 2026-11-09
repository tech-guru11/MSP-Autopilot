from accounts.models import User
from customers.models import Customer
from organizations.models import Membership, Organization
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Asset


class AssetTenantTests(APITestCase):
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
            asset_type=Asset.AssetType.SERVER,
        )
        self.asset_b = Asset.objects.create(
            customer=self.customer_b,
            name="hospital-api-01",
            asset_type=Asset.AssetType.SERVER,
        )
        self.client.force_authenticate(self.user)

    def headers(self, organization):
        return {"HTTP_X_ORGANIZATION_ID": str(organization.id)}

    def test_list_returns_only_active_organization_assets(self):
        response = self.client.get(
            "/api/assets/",
            **self.headers(self.organization_a),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data["results"]]
        self.assertEqual(ids, [str(self.asset_a.id)])

    def test_cannot_retrieve_another_organization_asset(self):
        response = self.client.get(
            f"/api/assets/{self.asset_b.id}/",
            **self.headers(self.organization_a),
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_create_asset_for_another_organization_customer(self):
        response = self.client.post(
            "/api/assets/",
            {
                "customer": str(self.customer_b.id),
                "name": "rogue-asset",
                "asset_type": Asset.AssetType.SERVER,
            },
            format="json",
            **self.headers(self.organization_a),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_move_asset_to_another_organization_customer(self):
        response = self.client.patch(
            f"/api/assets/{self.asset_a.id}/",
            {"customer": str(self.customer_b.id)},
            format="json",
            **self.headers(self.organization_a),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.asset_a.refresh_from_db()
        self.assertEqual(self.asset_a.customer_id, self.customer_a.id)

    def test_create_asset_in_active_organization(self):
        response = self.client.post(
            "/api/assets/",
            {
                "customer": str(self.customer_a.id),
                "name": "university-db-01",
                "asset_type": Asset.AssetType.DATABASE,
            },
            format="json",
            **self.headers(self.organization_a),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Asset.objects.get(id=response.data["id"])
        self.assertEqual(created.customer_id, self.customer_a.id)
