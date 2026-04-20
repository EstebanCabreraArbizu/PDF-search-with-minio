import re
from dataclasses import dataclass

from django.conf import settings
from django.core.management.base import BaseCommand
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
from documents.models import PDFIndex
from docrepo.models import (
    ConstanciaAbonoDocument,
    Document,
    EmployeeCode,
    IndexState,
    InsuranceDocument,
    StorageObject,
    TRegistroDocument,
)


@dataclass
class BackfillStats:
    processed: int = 0
    created_documents: int = 0
    updated_documents: int = 0
    created_codes: int = 0
    tregistro_docs: int = 0
    insurance_docs: int = 0
    constancia_docs: int = 0


class Command(BaseCommand):
    help = "Backfill V2 document architecture from legacy documents.PDFIndex"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0, help="Max rows to process")
        parser.add_argument("--offset", type=int, default=0, help="Rows to skip from start")
        parser.add_argument("--dry-run", action="store_true", help="Analyze only without writes")

    def handle(self, *args, **options):
        limit = options["limit"]
        offset = options["offset"]
        dry_run = options["dry_run"]

        queryset = PDFIndex.objects.all().order_by("id")
        if offset > 0:
            queryset = queryset[offset:]
        if limit > 0:
            queryset = queryset[:limit]

        self.stdout.write(self.style.NOTICE("Starting V2 backfill from legacy pdf_index"))
        self.stdout.write(f"Dry run: {dry_run}")

        if not dry_run:
            self._ensure_seed_catalogs()

        stats = BackfillStats()
        for legacy in queryset.iterator(chunk_size=500):
            stats.processed += 1
            if dry_run:
                domain_code = self._infer_domain_code(legacy)
                if domain_code == "TREGISTRO":
                    stats.tregistro_docs += 1
                elif domain_code == "SEGUROS":
                    stats.insurance_docs += 1
                else:
                    stats.constancia_docs += 1
                continue

            with transaction.atomic():
                created_document, codes_created, domain_code = self._migrate_legacy_row(legacy)
                if created_document:
                    stats.created_documents += 1
                else:
                    stats.updated_documents += 1
                stats.created_codes += codes_created

                if domain_code == "TREGISTRO":
                    stats.tregistro_docs += 1
                elif domain_code == "SEGUROS":
                    stats.insurance_docs += 1
                else:
                    stats.constancia_docs += 1

        self.stdout.write(self.style.SUCCESS("Backfill completed"))
        self.stdout.write(f"Processed: {stats.processed}")
        self.stdout.write(f"Documents created: {stats.created_documents}")
        self.stdout.write(f"Documents updated: {stats.updated_documents}")
        self.stdout.write(f"Employee codes created: {stats.created_codes}")
        self.stdout.write(f"T-registro docs: {stats.tregistro_docs}")
        self.stdout.write(f"Insurance docs: {stats.insurance_docs}")
        self.stdout.write(f"Constancia docs: {stats.constancia_docs}")

    def _ensure_seed_catalogs(self):
        self._domain("CONSTANCIA_ABONO", "Constancia de abono")
        self._domain("TREGISTRO", "T-registro")
        self._domain("SEGUROS", "Seguros")

        self._status("NEW", "New")
        self._status("INDEXING", "Indexing")
        self._status("INDEXED", "Indexed")
        self._status("ERROR", "Error")
        self._status("ARCHIVED", "Archived", is_terminal=True)

        self._tregistro_type("ALTA", "Alta")
        self._tregistro_type("BAJA", "Baja")

        sctr = self._insurance_type("SCTR", "SCTR", allows_subtype=True)
        self._insurance_type("VIDA_LEY", "Vida Ley", allows_subtype=False)
        self._insurance_type("OTRO", "Otro", allows_subtype=False)

        self._insurance_subtype(sctr, "SALUD", "Salud")
        self._insurance_subtype(sctr, "PENSION", "Pension")

        self._bank("GENERAL", "General")

    def _migrate_legacy_row(self, legacy):
        domain_code = self._infer_domain_code(legacy)
        company = self._company_from_legacy(legacy.razon_social)
        period = self._period_from_legacy(legacy.año, legacy.mes)
        status = self._status("INDEXED", "Indexed") if legacy.is_indexed else self._status("ERROR", "Error")

        storage = StorageObject.objects.select_related("document").filter(
            bucket_name=settings.MINIO_BUCKET,
            object_key=legacy.minio_object_name,
        ).first()

        created_document = storage is None
        if storage:
            document = storage.document
        else:
            document = Document()

        document.domain = self._domain_from_code(domain_code)
        document.company = company
        document.period = period
        document.original_filename = self._extract_filename(legacy.minio_object_name)
        document.source_path_legacy = legacy.minio_object_name
        document.content_hash_sha256 = document.content_hash_sha256 or None
        document.source_hash_md5 = legacy.md5_hash or None
        document.status = status
        document.indexed_at = legacy.indexed_at
        document.is_active = True
        document.save()

        StorageObject.objects.update_or_create(
            document=document,
            defaults={
                "bucket_name": settings.MINIO_BUCKET,
                "object_key": legacy.minio_object_name,
                "etag": legacy.md5_hash or "",
                "size_bytes": legacy.size_bytes or 0,
                "last_modified": legacy.last_modified,
                "content_type": "application/pdf",
            },
        )

        IndexState.objects.update_or_create(
            document=document,
            defaults={
                "is_indexed": legacy.is_indexed,
                "index_version": "legacy-v1",
                "indexed_at": legacy.indexed_at,
                "last_error_code": "" if legacy.is_indexed else "LEGACY_NOT_INDEXED",
                "last_error_detail": "" if legacy.is_indexed else "Legacy row marked as not indexed",
            },
        )

        codes = self._parse_employee_codes(legacy.codigos_empleado)
        created_codes = 0
        if codes:
            # Bulk insert with conflict ignore avoids O(n) per-code roundtrips.
            EmployeeCode.objects.bulk_create(
                [EmployeeCode(document=document, employee_code=code) for code in codes],
                ignore_conflicts=True,
                batch_size=1000,
            )
            created_codes = len(codes)

        if domain_code == "TREGISTRO":
            movement = self._tregistro_movement_from_legacy(legacy)
            TRegistroDocument.objects.update_or_create(
                document=document,
                defaults={
                    "movement_type": movement,
                    "worker_document_type": "DNI",
                    "worker_document_number": codes[0] if codes else "",
                },
            )
        elif domain_code == "SEGUROS":
            insurance_type = self._insurance_type_from_legacy(legacy)
            insurance_subtype = self._insurance_subtype_from_legacy(legacy, insurance_type)
            InsuranceDocument.objects.update_or_create(
                document=document,
                defaults={
                    "insurance_type": insurance_type,
                    "insurance_subtype": insurance_subtype,
                    "insured_count": len(codes),
                },
            )
        else:
            bank = self._bank_from_legacy(legacy.banco)
            ConstanciaAbonoDocument.objects.update_or_create(
                document=document,
                defaults={
                    "bank": bank,
                    "payroll_type": self._safe_text(legacy.tipo_documento, max_len=80),
                    "source_period_text": f"{legacy.año}-{legacy.mes}",
                    "ingestion_channel": "legacy_migration",
                    "legacy_tipo_documento": self._safe_text(legacy.tipo_documento, max_len=300),
                    "employee_count": len(codes) if codes else None,
                },
            )

        return created_document, created_codes, domain_code

    def _infer_domain_code(self, legacy):
        joined = f"{legacy.minio_object_name} {legacy.tipo_documento}".lower()
        if "tregistro" in joined or "t-registro" in joined:
            return "TREGISTRO"
        if "sctr" in joined or "vida ley" in joined or "seguros" in joined or "poliza" in joined:
            return "SEGUROS"
        return "CONSTANCIA_ABONO"

    def _tregistro_movement_from_legacy(self, legacy):
        joined = f"{legacy.minio_object_name} {legacy.tipo_documento}".lower()
        if "baja" in joined:
            return self._tregistro_type("BAJA", "Baja")
        return self._tregistro_type("ALTA", "Alta")

    def _insurance_type_from_legacy(self, legacy):
        joined = f"{legacy.minio_object_name} {legacy.tipo_documento}".lower()
        if "sctr" in joined:
            return self._insurance_type("SCTR", "SCTR", allows_subtype=True)
        if "vida ley" in joined or re.search(r"\bvida\b", joined):
            return self._insurance_type("VIDA_LEY", "Vida Ley", allows_subtype=False)
        return self._insurance_type("OTRO", "Otro", allows_subtype=False)

    def _insurance_subtype_from_legacy(self, legacy, insurance_type):
        if not insurance_type.allows_subtype:
            return None

        joined = f"{legacy.minio_object_name} {legacy.tipo_documento}".lower()
        if "salud" in joined:
            return self._insurance_subtype(insurance_type, "SALUD", "Salud")
        if "pension" in joined:
            return self._insurance_subtype(insurance_type, "PENSION", "Pension")
        return None

    def _parse_employee_codes(self, raw_codes):
        if not raw_codes:
            return []
        chunks = [chunk.strip() for chunk in raw_codes.split(",") if chunk.strip()]
        valid = []
        for value in chunks:
            if re.fullmatch(r"\d{4,10}", value):
                valid.append(value)
        return list(dict.fromkeys(valid))

    def _company_from_legacy(self, raw_name):
        name = self._safe_text(raw_name or "DESCONOCIDO", max_len=180)
        code = slugify(name).replace("-", "_").upper()[:60] or "DESCONOCIDO"
        company, _ = CatalogCompany.objects.get_or_create(code=code, defaults={"name": name})
        if company.name != name:
            company.name = name
            company.save(update_fields=["name", "updated_at"])
        return company

    def _period_from_legacy(self, year_raw, month_raw):
        year = self._safe_int(year_raw, default=timezone.now().year)
        month = self._safe_int(month_raw, default=1)
        if year < 2000 or year > 2100:
            year = timezone.now().year
        if month < 1 or month > 12:
            month = 1
        period, _ = CatalogPeriod.objects.get_or_create(year=year, month=month)
        return period

    def _bank_from_legacy(self, bank_raw):
        bank_name = self._safe_text(bank_raw or "GENERAL", max_len=120)
        code = slugify(bank_name).replace("-", "_").upper()[:40] or "GENERAL"
        return self._bank(code, bank_name)

    def _domain_from_code(self, code):
        return self._domain(code, code.replace("_", " ").title())

    def _domain(self, code, name):
        obj, _ = CatalogDomain.objects.get_or_create(code=code, defaults={"name": name})
        if obj.name != name:
            obj.name = name
            obj.save(update_fields=["name", "updated_at"])
        return obj

    def _status(self, code, name, is_terminal=False):
        obj, _ = CatalogDocumentStatus.objects.get_or_create(
            code=code,
            defaults={"name": name, "is_terminal": is_terminal},
        )
        updated_fields = []
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

    def _tregistro_type(self, code, name):
        obj, _ = CatalogTRegistroType.objects.get_or_create(code=code, defaults={"name": name})
        if obj.name != name:
            obj.name = name
            obj.save(update_fields=["name", "updated_at"])
        return obj

    def _insurance_type(self, code, name, allows_subtype=False):
        obj, _ = CatalogInsuranceType.objects.get_or_create(
            code=code,
            defaults={"name": name, "allows_subtype": allows_subtype},
        )
        updated_fields = []
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

    def _insurance_subtype(self, insurance_type, code, name):
        obj, _ = CatalogInsuranceSubtype.objects.get_or_create(
            insurance_type=insurance_type,
            code=code,
            defaults={"name": name},
        )
        if obj.name != name:
            obj.name = name
            obj.save(update_fields=["name", "updated_at"])
        return obj

    def _bank(self, code, name):
        obj, _ = CatalogBank.objects.get_or_create(code=code, defaults={"name": name})
        if obj.name != name:
            obj.name = name
            obj.save(update_fields=["name", "updated_at"])
        return obj

    def _extract_filename(self, object_key):
        if not object_key:
            return ""
        return object_key.rsplit("/", 1)[-1][:500]

    def _safe_int(self, value, default=0):
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return default

    def _safe_text(self, value, max_len):
        text = (value or "").strip()
        return text[:max_len]
