from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from catalogs.models import (
    CatalogBank,
    CatalogCompany,
    CatalogDocumentStatus,
    CatalogDomain,
    CatalogInsuranceSubtype,
    CatalogInsuranceType,
    CatalogPeriod,
    CatalogTRegistroType,
)

from .domain_inference import infer_domain_code
from .models import (
    ConstanciaAbonoDocument,
    Document,
    EmployeeCode,
    IndexState,
    InsuranceDocument,
    StorageObject,
    TRegistroDocument,
)


@dataclass
class UploadIngestionResult:
    document: Document
    domain_code: str
    created_document: bool
    indexed: bool
    employee_codes: list[str]


def _safe_text(value: Any, max_len: int) -> str:
    return str(value or "").strip()[:max_len]


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _normalize_search_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).upper()


def _extract_filename(object_key: str) -> str:
    if not object_key:
        return ""
    return object_key.rsplit("/", 1)[-1][:500]


def _parse_employee_codes(codes: list[str] | None) -> list[str]:
    if not codes:
        return []

    valid_codes: list[str] = []
    for code in codes:
        normalized = str(code).strip()
        if re.fullmatch(r"\d{4,10}", normalized):
            valid_codes.append(normalized)

    return list(dict.fromkeys(valid_codes))


def _domain(code: str, name: str):
    obj, _ = CatalogDomain.objects.get_or_create(code=code, defaults={"name": name})
    if obj.name != name:
        obj.name = name
        obj.save(update_fields=["name", "updated_at"])
    return obj


def _status(code: str, name: str, is_terminal: bool = False):
    obj, _ = CatalogDocumentStatus.objects.get_or_create(
        code=code,
        defaults={"name": name, "is_terminal": is_terminal},
    )

    updated_fields: list[str] = []
    if obj.name != name:
        obj.name = name
        updated_fields.append("name")
    if obj.is_terminal != is_terminal:
        obj.is_terminal = is_terminal
        updated_fields.append("is_terminal")
    if updated_fields:
        updated_fields.append("updated_at")
        obj.save(update_fields=updated_fields)

    return obj


def _company(raw_name: str):
    normalized_name = _safe_text(raw_name or "DESCONOCIDO", 180) or "DESCONOCIDO"
    code = slugify(normalized_name).replace("-", "_").upper()[:60] or "DESCONOCIDO"

    obj, _ = CatalogCompany.objects.get_or_create(code=code, defaults={"name": normalized_name})
    if obj.name != normalized_name:
        obj.name = normalized_name
        obj.save(update_fields=["name", "updated_at"])

    return obj


def _period(year_raw: Any, month_raw: Any):
    year = _safe_int(year_raw, timezone.now().year)
    month = _safe_int(month_raw, 1)

    if year < 2000 or year > 2100:
        year = timezone.now().year
    if month < 1 or month > 12:
        month = 1

    obj, _ = CatalogPeriod.objects.get_or_create(year=year, month=month)
    return obj


def _bank(raw_name: str):
    normalized_name = _safe_text(raw_name or "GENERAL", 120) or "GENERAL"
    code = slugify(normalized_name).replace("-", "_").upper()[:40] or "GENERAL"

    obj, _ = CatalogBank.objects.get_or_create(code=code, defaults={"name": normalized_name})
    if obj.name != normalized_name:
        obj.name = normalized_name
        obj.save(update_fields=["name", "updated_at"])

    return obj


def _tregistro_type(is_baja: bool):
    code = "BAJA" if is_baja else "ALTA"
    name = "Baja" if is_baja else "Alta"

    obj, _ = CatalogTRegistroType.objects.get_or_create(code=code, defaults={"name": name})
    if obj.name != name:
        obj.name = name
        obj.save(update_fields=["name", "updated_at"])

    return obj


def _insurance_type(joined_text: str):
    if "sctr" in joined_text:
        code, name, allows_subtype = "SCTR", "SCTR", True
    elif "vida ley" in joined_text or re.search(r"\bvida\b", joined_text):
        code, name, allows_subtype = "VIDA_LEY", "Vida Ley", False
    else:
        code, name, allows_subtype = "OTRO", "Otro", False

    obj, _ = CatalogInsuranceType.objects.get_or_create(
        code=code,
        defaults={"name": name, "allows_subtype": allows_subtype},
    )

    updated_fields: list[str] = []
    if obj.name != name:
        obj.name = name
        updated_fields.append("name")
    if obj.allows_subtype != allows_subtype:
        obj.allows_subtype = allows_subtype
        updated_fields.append("allows_subtype")
    if updated_fields:
        updated_fields.append("updated_at")
        obj.save(update_fields=updated_fields)

    return obj


def _insurance_subtype(joined_text: str, insurance_type: CatalogInsuranceType):
    if not insurance_type.allows_subtype:
        return None

    tokens = set(re.findall(r"\b\w+\b", _normalize_search_text(joined_text)))

    if "SALUD" in tokens:
        code, name = "SALUD", "Salud"
    elif "PENSION" in tokens:
        code, name = "PENSION", "Pension"
    else:
        return None

    obj, _ = CatalogInsuranceSubtype.objects.get_or_create(
        insurance_type=insurance_type,
        code=code,
        defaults={"name": name},
    )
    if obj.name != name:
        obj.name = name
        obj.save(update_fields=["name", "updated_at"])

    return obj


def _clear_non_domain_details(document: Document, domain_code: str):
    if domain_code != "TREGISTRO":
        TRegistroDocument.objects.filter(document=document).delete()
    if domain_code != "SEGUROS":
        InsuranceDocument.objects.filter(document=document).delete()
    if domain_code != "CONSTANCIA_ABONO":
        ConstanciaAbonoDocument.objects.filter(document=document).delete()


@transaction.atomic
def upsert_document_from_upload(
    *,
    object_key: str,
    metadata: dict[str, Any],
    size_bytes: int,
    etag: str | None,
    last_modified: Any,
    employee_codes: list[str] | None,
    is_indexed: bool,
    actor: Any | None = None,
    correction_reason: str = "",
) -> UploadIngestionResult:
    object_key = _safe_text(object_key, 800)
    tipo_documento = _safe_text(metadata.get("tipo_documento") or "GENERAL", 300) or "GENERAL"

    domain_code = infer_domain_code(object_key, tipo_documento)
    domain = _domain(domain_code, domain_code.replace("_", " ").title())
    company = _company(str(metadata.get("razon_social") or "DESCONOCIDO"))
    period = _period(metadata.get("año"), metadata.get("mes"))
    doc_status = _status("INDEXED", "Indexed") if is_indexed else _status("ERROR", "Error")

    storage = StorageObject.objects.select_related("document").filter(
        bucket_name=settings.MINIO_BUCKET,
        object_key=object_key,
    ).first()

    created_document = storage is None
    document = storage.document if storage else Document()

    now = timezone.now()
    document.domain = domain
    document.company = company
    document.period = period
    document.original_filename = _extract_filename(object_key)
    document.source_path_legacy = object_key
    document.source_hash_md5 = _safe_text(etag, 64) or None
    document.correction_reason = _safe_text(correction_reason, 500)
    document.status = doc_status
    document.indexed_at = now if is_indexed else None
    document.is_active = True

    if actor is not None and getattr(actor, "is_authenticated", False):
        if created_document and document.created_by_id is None:
            document.created_by = actor
        document.updated_by = actor

    document.save()

    StorageObject.objects.update_or_create(
        document=document,
        defaults={
            "bucket_name": settings.MINIO_BUCKET,
            "object_key": object_key,
            "etag": _safe_text(etag, 255),
            "size_bytes": max(int(size_bytes or 0), 0),
            "last_modified": last_modified,
            "content_type": "application/pdf",
        },
    )

    normalized_codes = _parse_employee_codes(employee_codes)

    IndexState.objects.update_or_create(
        document=document,
        defaults={
            "is_indexed": is_indexed,
            "index_version": "v2-upload-api",
            "indexed_at": now if is_indexed else None,
            "last_error_code": "" if is_indexed else "UPLOAD_INDEX_EMPTY",
            "last_error_detail": "" if is_indexed else "Text extraction returned empty content",
            "extracted_codes_count": len(normalized_codes),
        },
    )

    existing_extracted = set(
        EmployeeCode.objects.filter(
            document=document,
            source=EmployeeCode.SourceChoices.EXTRACTED,
        ).values_list("employee_code", flat=True)
    )

    stale_codes = existing_extracted - set(normalized_codes)
    if stale_codes:
        EmployeeCode.objects.filter(
            document=document,
            source=EmployeeCode.SourceChoices.EXTRACTED,
            employee_code__in=stale_codes,
        ).delete()

    missing_codes = [code for code in normalized_codes if code not in existing_extracted]
    if missing_codes:
        EmployeeCode.objects.bulk_create(
            [
                EmployeeCode(
                    document=document,
                    employee_code=code,
                    source=EmployeeCode.SourceChoices.EXTRACTED,
                )
                for code in missing_codes
            ],
            ignore_conflicts=True,
            batch_size=1000,
        )

    _clear_non_domain_details(document, domain_code)

    joined_text = f"{object_key} {tipo_documento}".lower()
    if domain_code == "TREGISTRO":
        movement_type = _tregistro_type(is_baja=("baja" in joined_text))
        TRegistroDocument.objects.update_or_create(
            document=document,
            defaults={
                "movement_type": movement_type,
                "worker_document_type": "DNI",
                "worker_document_number": normalized_codes[0] if normalized_codes else "",
            },
        )
    elif domain_code == "SEGUROS":
        ins_type = _insurance_type(joined_text)
        ins_subtype = _insurance_subtype(joined_text, ins_type)
        InsuranceDocument.objects.update_or_create(
            document=document,
            defaults={
                "insurance_type": ins_type,
                "insurance_subtype": ins_subtype,
                "insured_count": len(normalized_codes),
            },
        )
    else:
        bank = _bank(str(metadata.get("banco") or "GENERAL"))
        ConstanciaAbonoDocument.objects.update_or_create(
            document=document,
            defaults={
                "bank": bank,
                "payroll_type": _safe_text(tipo_documento, 80),
                "source_period_text": f"{period.year}-{period.month:02d}" if period else "",
                "ingestion_channel": "upload_api",
                "legacy_tipo_documento": _safe_text(tipo_documento, 300),
                "employee_count": len(normalized_codes) if normalized_codes else None,
            },
        )

    return UploadIngestionResult(
        document=document,
        domain_code=domain_code,
        created_document=created_document,
        indexed=is_indexed,
        employee_codes=normalized_codes,
    )


@transaction.atomic
def deactivate_document_by_storage_key(
    *,
    object_key: str,
    actor: Any | None = None,
) -> Document | None:
    object_key = _safe_text(object_key, 800)
    if not object_key:
        return None

    storage = StorageObject.objects.select_related("document").filter(
        bucket_name=settings.MINIO_BUCKET,
        object_key=object_key,
    ).first()

    document = storage.document if storage else None
    if document is None:
        document = Document.objects.filter(source_path_legacy=object_key).first()

    if document is None:
        return None

    archived_status = _status("ARCHIVED", "Archived", is_terminal=True)
    document.is_active = False
    document.status = archived_status

    if actor is not None and getattr(actor, "is_authenticated", False):
        document.updated_by = actor

    document.save(update_fields=["is_active", "status", "updated_by", "updated_at"])

    IndexState.objects.filter(document=document).update(
        is_indexed=False,
        indexed_at=timezone.now(),
        last_error_code="STORAGE_OBJECT_DELETED",
        last_error_detail="Storage object removed via API",
        updated_at=timezone.now(),
    )

    return document
