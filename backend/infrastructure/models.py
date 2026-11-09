import uuid

from django.db import models


class Asset(models.Model):
    class AssetType(models.TextChoices):
        SERVER = "server", "Server"
        DATABASE = "database", "Database"
        WEBSITE = "website", "Website"
        NETWORK = "network", "Network Device"
        APPLICATION = "application", "Application"

    class Status(models.TextChoices):
        HEALTHY = "healthy", "Healthy"
        DEGRADED = "degraded", "Degraded"
        UNHEALTHY = "unhealthy", "Unhealthy"
        UNKNOWN = "unknown", "Unknown"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="assets",
    )
    name = models.CharField(max_length=255)
    asset_type = models.CharField(
        max_length=30,
        choices=AssetType.choices,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UNKNOWN,
    )
    external_identifier = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["customer", "asset_type"]),
        ]

    def __str__(self):
        return self.name
