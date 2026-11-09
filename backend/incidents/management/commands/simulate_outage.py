from customers.models import Customer
from django.core.management.base import BaseCommand, CommandError
from infrastructure.models import Asset

from incidents.models import Alert
from incidents.services.alerts import generate_fingerprint, ingest_alert
from incidents.services.correlation import create_incident_for_alert
from incidents.services.events import record_incident_event


class Command(BaseCommand):
    help = "Simulate a university website outage"

    def add_arguments(self, parser):
        parser.add_argument(
            "--customer",
            default="Cavendish University",
            help="Customer name.",
        )
        parser.add_argument(
            "--asset",
            default="university-web-01",
            help="Asset name.",
        )
        parser.add_argument(
            "--condition",
            default="website-down",
            help="Alert condition used for the fingerprint.",
        )

    def handle(self, *args, **options):
        try:
            customer = Customer.objects.get(name=options["customer"])
        except Customer.DoesNotExist as exc:
            raise CommandError(
                f"Customer '{options['customer']}' does not exist. "
                "Create it first or pass --customer."
            ) from exc

        try:
            asset = Asset.objects.get(
                customer=customer,
                name=options["asset"],
            )
        except Asset.DoesNotExist as exc:
            raise CommandError(
                f"Asset '{options['asset']}' does not exist for "
                f"customer '{customer.name}'. Create it first or "
                "pass --asset."
            ) from exc

        fingerprint = generate_fingerprint(
            customer.id,
            asset.id,
            options["condition"],
        )

        alert, alert_created = ingest_alert(
            customer=customer,
            asset=asset,
            fingerprint=fingerprint,
            title="University website unavailable",
            severity=Alert.Severity.CRITICAL,
            description="Website health check failed.",
        )

        incident, incident_created = create_incident_for_alert(alert)

        record_incident_event(
            incident=incident,
            event_type="outage_simulated",
            description="Simulated website outage alert ingested.",
            metadata={
                "alert_id": str(alert.id),
                "alert_created": alert_created,
                "incident_created": incident_created,
            },
        )

        alert_state = "created" if alert_created else "updated"
        incident_state = "created" if incident_created else "reused"

        self.stdout.write(
            self.style.SUCCESS(
                f"Alert {alert_state}: {alert.id} "
                f"(occurrences={alert.occurrence_count})"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Incident {incident_state}: {incident.id} "
                f"({incident.severity}, {incident.status})"
            )
        )
