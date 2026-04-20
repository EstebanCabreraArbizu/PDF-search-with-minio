from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = (
        "occurred_at",
        "action",
        "resource_type",
        "resource_id",
        "actor",
        "ip_address",
        "correlation_id",
    )
    list_filter = ("action", "resource_type", "occurred_at")
    search_fields = ("resource_id", "actor__username", "actor__full_name", "correlation_id")
    autocomplete_fields = ("actor", "document")
