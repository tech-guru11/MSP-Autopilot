from accounts.models import User
from customers.models import Customer
from django.core.management.base import BaseCommand
from infrastructure.models import Asset
from organizations.models import Membership, Organization

from incidents.models import Alert, Incident, RemediationAction
from incidents.services.alerts import ingest_alert
from incidents.services.correlation import create_incident_for_alert
from incidents.services.investigation import run_investigation
from incidents.services.remediation import propose_remediation_action
from incidents.services.state_machine import transition_incident

DEMO_EVIDENCE = {
    "observations": {
        "http_status": 503,
        "db_connection_usage": 98,
        "cpu_usage": 35,
        "recent_deployment": True,
        "log_errors": True,
    }
}


class Command(BaseCommand):
    help = "Create demo users, organization, customer, asset and incident."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="demo-password",
            help="Password for newly created demo users.",
        )

    def handle(self, *args, **options):
        password = options["password"]

        organization, _ = Organization.objects.get_or_create(
            name="TechCare MSP",
        )

        users = {}
        for username, role, is_staff, is_superuser in [
            ("admin", Membership.Role.ADMIN, True, True),
            ("engineer", Membership.Role.ENGINEER, False, False),
            ("viewer", Membership.Role.VIEWER, False, False),
        ]:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@example.com",
                    "is_staff": is_staff,
                    "is_superuser": is_superuser,
                },
            )

            if created:
                user.set_password(password)
                user.save(update_fields=["password"])

            Membership.objects.get_or_create(
                organization=organization,
                user=user,
                defaults={"role": role},
            )
            users[username] = user

        customer, _ = Customer.objects.get_or_create(
            organization=organization,
            name="Cavendish University",
            defaults={"contact_email": "it@cavendish.example"},
        )
        asset, _ = Asset.objects.get_or_create(
            customer=customer,
            name="university-web-01",
            defaults={
                "asset_type": Asset.AssetType.WEBSITE,
                "external_identifier": "university-website",
            },
        )

        alert, _ = ingest_alert(
            customer=customer,
            asset=asset,
            fingerprint="demo-university-website-down",
            title="University website unavailable",
            description="Website returns HTTP 503.",
            severity=Alert.Severity.CRITICAL,
            condition="website-down",
        )
        incident, incident_created = create_incident_for_alert(alert)

        if incident_created:
            transition_incident(
                incident.id,
                Incident.Status.TRIAGING,
                actor=users["engineer"],
            )
            transition_incident(
                incident.id,
                Incident.Status.INVESTIGATING,
                actor=users["engineer"],
            )
            investigation = run_investigation(
                incident,
                DEMO_EVIDENCE,
                actor=users["engineer"],
            )
            propose_remediation_action(
                incident=incident,
                action_type=(RemediationAction.ActionType.RESTART_SERVICE),
                parameters={
                    "asset_id": str(asset.id),
                    "service_name": "university-website",
                },
                actor=users["engineer"],
                investigation=investigation,
                idempotency_key="demo-restart-university-website",
            )

        self.stdout.write(self.style.SUCCESS("Demo data is ready."))
        self.stdout.write(f"Organization: {organization.id}")
        self.stdout.write(f"Customer: {customer.id}")
        self.stdout.write(f"Incident: {incident.id}")
        self.stdout.write("Users (newly created only):")
        self.stdout.write(f"  admin / {password}")
        self.stdout.write(f"  engineer / {password}")
        self.stdout.write(f"  viewer / {password}")
