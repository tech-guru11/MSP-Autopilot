from accounts.models import User
from customers.models import Customer
from django.core.exceptions import ValidationError
from django.test import TestCase
from infrastructure.models import Asset
from organizations.models import Membership, Organization
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Incident, RemediationAction
from .services.policy import evaluate_action
from .services.remediation import (
    approve_remediation_action,
    execute_remediation_action,
    propose_remediation_action,
    reject_remediation_action,
    rollback_remediation_action,
)


class RemediationBaseMixin:
    def setUp(self):
        self.organization = Organization.objects.create(name="TechCare")
        self.other_organization = Organization.objects.create(name="CloudCare")
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
        Membership.objects.create(
            user=self.viewer,
            organization=self.organization,
            role=Membership.Role.VIEWER,
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
        self.other_asset = Asset.objects.create(
            customer=self.other_customer,
            name="hospital-web-01",
            asset_type=Asset.AssetType.WEBSITE,
        )
        self.incident = Incident.objects.create(
            customer=self.customer,
            asset=self.asset,
            title="University website unavailable",
            severity=Incident.Severity.P1,
            status=Incident.Status.INVESTIGATING,
        )


class PolicyEngineTests(RemediationBaseMixin, TestCase):
    def test_medium_risk_action_requires_approval(self):
        decision = evaluate_action(
            RemediationAction.ActionType.RESTART_SERVICE,
            {"asset_id": str(self.asset.id)},
            self.engineer,
            self.incident,
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.risk, RemediationAction.Risk.MEDIUM)
        self.assertTrue(decision.requires_approval)

    def test_low_risk_action_does_not_require_approval(self):
        decision = evaluate_action(
            RemediationAction.ActionType.INSPECT_CONNECTION_POOL,
            {},
            self.engineer,
            self.incident,
        )

        self.assertTrue(decision.allowed)
        self.assertFalse(decision.requires_approval)

    def test_critical_action_is_prohibited(self):
        decision = evaluate_action(
            RemediationAction.ActionType.DELETE_DATABASE,
            {},
            self.admin,
            self.incident,
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.risk, RemediationAction.Risk.CRITICAL)

    def test_asset_from_another_customer_is_rejected(self):
        decision = evaluate_action(
            RemediationAction.ActionType.RESTART_SERVICE,
            {"asset_id": str(self.other_asset.id)},
            self.engineer,
            self.incident,
        )

        self.assertFalse(decision.allowed)

    def test_viewer_cannot_propose(self):
        decision = evaluate_action(
            RemediationAction.ActionType.INSPECT_CONNECTION_POOL,
            {},
            self.viewer,
            self.incident,
        )

        self.assertFalse(decision.allowed)


class RemediationWorkflowTests(RemediationBaseMixin, TestCase):
    def propose_restart(self, key="restart-1"):
        return propose_remediation_action(
            incident=self.incident,
            action_type=RemediationAction.ActionType.RESTART_SERVICE,
            parameters={"asset_id": str(self.asset.id)},
            actor=self.engineer,
            idempotency_key=key,
        )

    def test_proposal_requires_approval_and_moves_incident(self):
        action, created = self.propose_restart()

        self.assertTrue(created)
        self.assertEqual(
            action.status,
            RemediationAction.Status.PENDING_APPROVAL,
        )
        self.assertTrue(action.requires_approval)
        self.incident.refresh_from_db()
        self.assertEqual(
            self.incident.status,
            Incident.Status.AWAITING_APPROVAL,
        )
        self.assertTrue(
            self.incident.events.filter(
                event_type="remediation_proposed",
            ).exists()
        )

    def test_low_risk_proposal_is_approved_immediately(self):
        action, created = propose_remediation_action(
            incident=self.incident,
            action_type=(RemediationAction.ActionType.INSPECT_CONNECTION_POOL),
            parameters={},
            actor=self.engineer,
        )

        self.assertTrue(created)
        self.assertEqual(
            action.status,
            RemediationAction.Status.APPROVED,
        )
        self.incident.refresh_from_db()
        self.assertEqual(
            self.incident.status,
            Incident.Status.INVESTIGATING,
        )

    def test_idempotency_returns_existing_action(self):
        first, first_created = self.propose_restart()
        second, second_created = self.propose_restart()

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first.id, second.id)
        self.assertEqual(RemediationAction.objects.count(), 1)

    def test_proposal_rejected_when_incident_not_investigable(self):
        self.incident.status = Incident.Status.NEW
        self.incident.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            self.propose_restart()

    def test_admin_approves_pending_action(self):
        action, _ = self.propose_restart()

        action = approve_remediation_action(
            action.id,
            self.admin,
            self.organization,
        )

        self.assertEqual(
            action.status,
            RemediationAction.Status.APPROVED,
        )
        self.assertEqual(action.approved_by_id, self.admin.id)
        self.assertIsNotNone(action.approved_at)

    def test_engineer_cannot_approve(self):
        action, _ = self.propose_restart()

        with self.assertRaises(ValidationError):
            approve_remediation_action(
                action.id,
                self.engineer,
                self.organization,
            )

    def test_admin_rejects_pending_action(self):
        action, _ = self.propose_restart()

        action = reject_remediation_action(
            action.id,
            self.admin,
            self.organization,
            reason="Use the runbook first.",
        )

        self.assertEqual(
            action.status,
            RemediationAction.Status.REJECTED,
        )
        self.assertEqual(
            action.rejection_reason,
            "Use the runbook first.",
        )
        self.incident.refresh_from_db()
        self.assertEqual(
            self.incident.status,
            Incident.Status.INVESTIGATING,
        )

    def test_unapproved_action_cannot_execute(self):
        action, _ = self.propose_restart()

        with self.assertRaises(ValidationError):
            execute_remediation_action(
                action.id,
                self.engineer,
                self.organization,
            )

    def test_approved_action_executes_and_moves_to_verifying(self):
        action, _ = self.propose_restart()
        approve_remediation_action(
            action.id,
            self.admin,
            self.organization,
        )

        action = execute_remediation_action(
            action.id,
            self.engineer,
            self.organization,
        )

        self.assertEqual(
            action.status,
            RemediationAction.Status.SUCCEEDED,
        )
        self.assertTrue(action.result["simulated"])
        self.assertIsNotNone(action.executed_at)
        self.incident.refresh_from_db()
        self.assertEqual(
            self.incident.status,
            Incident.Status.VERIFYING,
        )

    def test_execute_is_idempotent(self):
        action, _ = self.propose_restart()
        approve_remediation_action(
            action.id,
            self.admin,
            self.organization,
        )
        execute_remediation_action(
            action.id,
            self.engineer,
            self.organization,
        )
        second = execute_remediation_action(
            action.id,
            self.engineer,
            self.organization,
        )

        self.assertEqual(
            second.status,
            RemediationAction.Status.SUCCEEDED,
        )
        self.assertEqual(
            self.incident.events.filter(
                event_type="remediation_executed",
            ).count(),
            1,
        )

    def test_successful_action_can_be_rolled_back(self):
        action, _ = self.propose_restart()
        approve_remediation_action(
            action.id,
            self.admin,
            self.organization,
        )
        execute_remediation_action(
            action.id,
            self.engineer,
            self.organization,
        )

        action = rollback_remediation_action(
            action.id,
            self.engineer,
            self.organization,
        )

        self.assertEqual(
            action.status,
            RemediationAction.Status.ROLLED_BACK,
        )
        self.assertIn("rollback", action.result)
        self.incident.refresh_from_db()
        self.assertEqual(
            self.incident.status,
            Incident.Status.INVESTIGATING,
        )


class RemediationAPITests(RemediationBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.engineer)

    def headers(self):
        return {
            "HTTP_X_ORGANIZATION_ID": str(self.organization.id),
        }

    def propose_via_api(self):
        return self.client.post(
            "/api/remediation-actions/",
            {
                "incident": str(self.incident.id),
                "action_type": (RemediationAction.ActionType.RESTART_SERVICE),
                "parameters": {"asset_id": str(self.asset.id)},
                "idempotency_key": "api-restart-1",
            },
            format="json",
            **self.headers(),
        )

    def test_engineer_can_propose_action(self):
        response = self.propose_via_api()

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(
            response.data["status"],
            RemediationAction.Status.PENDING_APPROVAL,
        )

    def test_viewer_cannot_propose_action(self):
        self.client.force_authenticate(self.viewer)
        response = self.propose_via_api()

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_engineer_cannot_approve(self):
        action, _ = propose_remediation_action(
            incident=self.incident,
            action_type=RemediationAction.ActionType.RESTART_SERVICE,
            parameters={"asset_id": str(self.asset.id)},
            actor=self.engineer,
        )

        response = self.client.post(
            f"/api/remediation-actions/{action.id}/approve/",
            {},
            format="json",
            **self.headers(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_admin_approves_and_engineer_executes(self):
        action, _ = propose_remediation_action(
            incident=self.incident,
            action_type=RemediationAction.ActionType.RESTART_SERVICE,
            parameters={"asset_id": str(self.asset.id)},
            actor=self.engineer,
        )
        self.client.force_authenticate(self.admin)
        approve_response = self.client.post(
            f"/api/remediation-actions/{action.id}/approve/",
            {},
            format="json",
            **self.headers(),
        )
        self.assertEqual(
            approve_response.status_code,
            status.HTTP_200_OK,
        )

        self.client.force_authenticate(self.engineer)
        execute_response = self.client.post(
            f"/api/remediation-actions/{action.id}/execute/",
            {},
            format="json",
            **self.headers(),
        )

        self.assertEqual(
            execute_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            execute_response.data["status"],
            RemediationAction.Status.SUCCEEDED,
        )

    def test_cross_tenant_action_is_hidden(self):
        other_incident = Incident.objects.create(
            customer=self.other_customer,
            title="Other incident",
            severity=Incident.Severity.P1,
            status=Incident.Status.INVESTIGATING,
        )
        action = RemediationAction.objects.create(
            incident=other_incident,
            action_type=(RemediationAction.ActionType.RESTART_SERVICE),
            parameters={},
            risk=RemediationAction.Risk.MEDIUM,
            status=RemediationAction.Status.PENDING_APPROVAL,
            requires_approval=True,
            idempotency_key="cross-tenant",
        )

        response = self.client.get(
            f"/api/remediation-actions/{action.id}/",
            **self.headers(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
