import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimestampedModel


class AuditEvent(TimestampedModel):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    action = models.CharField(max_length=64)
    resource_type = models.CharField(max_length=80)
    resource_id = models.CharField(max_length=64, blank=True)
    document = models.ForeignKey(
        "docrepo.Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    correlation_id = models.UUIDField(default=uuid.uuid4, null=True, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "audit_event"
        indexes = [
            models.Index(fields=["action", "occurred_at"], name="audit_action_time_idx"),
            models.Index(fields=["resource_type", "resource_id"], name="audit_resource_idx"),
        ]

    def __str__(self):
        return f"{self.action} - {self.resource_type}"
