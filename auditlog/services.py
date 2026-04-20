import logging
import uuid
from typing import Any

from auditlog.models import AuditEvent


logger = logging.getLogger(__name__)


def _request_ip(request: Any) -> str | None:
    if request is None:
        return None

    cf_ip = request.META.get("HTTP_CF_CONNECTING_IP")
    if cf_ip:
        return str(cf_ip).strip()

    real_ip = request.META.get("HTTP_X_REAL_IP")
    if real_ip:
        return str(real_ip).strip()

    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return str(x_forwarded_for).split(",")[0].strip()

    remote_addr = request.META.get("REMOTE_ADDR")
    if remote_addr:
        return str(remote_addr).strip()

    return None


def _coerce_correlation_id(value: Any) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value

    if value:
        try:
            return uuid.UUID(str(value))
        except (ValueError, TypeError, AttributeError):
            pass

    return uuid.uuid4()


def record_audit_event(
    *,
    action: str,
    resource_type: str,
    resource_id: str = "",
    request: Any | None = None,
    actor: Any | None = None,
    document: Any | None = None,
    metadata: dict[str, Any] | None = None,
    correlation_id: Any | None = None,
) -> AuditEvent | None:
    """Best-effort audit event persistence that never breaks request flow."""
    try:
        resolved_actor = None
        if actor is not None and getattr(actor, "is_authenticated", False):
            resolved_actor = actor
        elif request is not None:
            request_user = getattr(request, "user", None)
            if request_user is not None and getattr(request_user, "is_authenticated", False):
                resolved_actor = request_user

        request_correlation = getattr(request, "correlation_id", None) if request is not None else None
        resolved_correlation_id = _coerce_correlation_id(correlation_id or request_correlation)

        clean_resource_id = (resource_id or "").strip()[:64]
        clean_metadata = metadata if isinstance(metadata, dict) else {}

        user_agent = ""
        if request is not None:
            user_agent = str(request.META.get("HTTP_USER_AGENT") or "")[:300]

        event = AuditEvent.objects.create(
            actor=resolved_actor,
            action=(action or "").strip()[:64],
            resource_type=(resource_type or "").strip()[:80],
            resource_id=clean_resource_id,
            document=document,
            ip_address=_request_ip(request),
            user_agent=user_agent,
            correlation_id=resolved_correlation_id,
            metadata=clean_metadata,
        )
        return event
    except Exception:
        logger.exception("audit_event_persist_failed")
        return None
