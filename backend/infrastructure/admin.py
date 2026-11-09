from django.contrib import admin

from .models import Asset


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "customer",
        "asset_type",
        "status",
        "created_at",
    )
    list_filter = ("asset_type", "status")
    search_fields = ("name", "external_identifier", "customer__name")
