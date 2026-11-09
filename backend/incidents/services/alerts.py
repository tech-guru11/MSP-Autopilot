import hashlib
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from incidents.models import Alert

DEDUPLICATION_WINDOW = timedelta(minutes=10)


def generate_fingerprint(customer_id, asset_id=None, condition=""):
    raw_value = ":".join(
        [
            str(customer_id),
            str(asset_id or ""),
            str(condition).strip().lower(),
        ]
    )
    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()


@transaction.atomic
def ingest_alert(
    customer,
    asset,
    fingerprint=None,
    title="",
    severity=Alert.Severity.MEDIUM,
    description="",
    condition=None,
):
    if asset is not None and asset.customer_id != customer.id:
        raise ValidationError(
            "The asset does not belong to the selected customer."
        )

    if severity not in Alert.Severity.values:
        raise ValidationError(f"Unknown alert severity: {severity}.")

    if not fingerprint:
        fingerprint = generate_fingerprint(
            customer.id,
            getattr(asset, "id", None),
            condition or title,
        )

    now = timezone.now()

    alert = (
        Alert.objects.select_for_update()
        .filter(
            customer=customer,
            fingerprint=fingerprint,
        )
        .order_by("-last_seen_at")
        .first()
    )

    if alert is not None and alert.last_seen_at >= (
        now - DEDUPLICATION_WINDOW
    ):
        alert.occurrence_count += 1
        alert.last_seen_at = now
        alert.title = title or alert.title
        alert.description = description or alert.description
        alert.severity = severity
        alert.save(
            update_fields=[
                "occurrence_count",
                "last_seen_at",
                "title",
                "description",
                "severity",
            ]
        )
        return alert, False

    alert = Alert.objects.create(
        customer=customer,
        asset=asset,
        fingerprint=fingerprint,
        title=title,
        description=description,
        severity=severity,
        occurrence_count=1,
    )

    return alert, True
