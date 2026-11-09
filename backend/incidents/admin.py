from django.contrib import admin

from .models import (
    Alert,
    Evidence,
    Incident,
    IncidentEvent,
    Investigation,
    RemediationAction,
)


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "customer",
        "severity",
        "status",
        "started_at",
    )
    list_filter = ("severity", "status")
    search_fields = ("title", "customer__name")


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "customer",
        "severity",
        "status",
        "occurrence_count",
        "last_seen_at",
    )
    list_filter = ("severity", "status")
    search_fields = ("title", "fingerprint", "customer__name")


class EvidenceInline(admin.TabularInline):
    model = Evidence
    extra = 0
    readonly_fields = (
        "source",
        "observation",
        "supports",
        "metadata",
        "created_at",
    )


@admin.register(Investigation)
class InvestigationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "incident",
        "status",
        "severity_assessment",
        "requested_by",
        "created_at",
    )
    list_filter = ("status", "severity_assessment")
    search_fields = ("incident__title", "summary")
    inlines = [EvidenceInline]


@admin.register(IncidentEvent)
class IncidentEventAdmin(admin.ModelAdmin):
    list_display = (
        "incident",
        "event_type",
        "actor",
        "created_at",
    )
    list_filter = ("event_type",)
    search_fields = ("incident__title", "event_type", "description")


@admin.register(RemediationAction)
class RemediationActionAdmin(admin.ModelAdmin):
    list_display = (
        "action_type",
        "incident",
        "risk",
        "status",
        "requires_approval",
        "requested_by",
        "created_at",
    )
    list_filter = ("risk", "status", "action_type")
    search_fields = (
        "incident__title",
        "action_type",
        "idempotency_key",
    )
