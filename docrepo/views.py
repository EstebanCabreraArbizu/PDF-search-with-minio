import re
import time
from typing import Any

from django.conf import settings
from django.http import StreamingHttpResponse
from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from auditlog.services import record_audit_event
from documents.models import DownloadLog, PDFIndex
from documents.utils import minio_client

from .domain_inference import infer_domain_code
from .models import Document


MONTH_MAP = {
    "ene": 1,
    "enero": 1,
    "feb": 2,
    "febrero": 2,
    "mar": 3,
    "marzo": 3,
    "abr": 4,
    "abril": 4,
    "may": 5,
    "mayo": 5,
    "jun": 6,
    "junio": 6,
    "jul": 7,
    "julio": 7,
    "ago": 8,
    "agosto": 8,
    "set": 9,
    "sept": 9,
    "septiembre": 9,
    "setiembre": 9,
    "oct": 10,
    "octubre": 10,
    "nov": 11,
    "noviembre": 11,
    "dic": 12,
    "diciembre": 12,
}

MONTH_OPTIONS = [
    {"value": "01", "label": "Enero"},
    {"value": "02", "label": "Febrero"},
    {"value": "03", "label": "Marzo"},
    {"value": "04", "label": "Abril"},
    {"value": "05", "label": "Mayo"},
    {"value": "06", "label": "Junio"},
    {"value": "07", "label": "Julio"},
    {"value": "08", "label": "Agosto"},
    {"value": "09", "label": "Septiembre"},
    {"value": "10", "label": "Octubre"},
    {"value": "11", "label": "Noviembre"},
    {"value": "12", "label": "Diciembre"},
]


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "si", "on"}


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _safe_month(value: Any) -> int | None:
    month = _safe_int(value)
    if month is None:
        return None
    if 1 <= month <= 12:
        return month
    return None


def _parse_period(period_value: Any) -> tuple[int | None, int | None]:
    if not period_value:
        return None, None

    text = str(period_value).strip().lower()
    year_match = re.search(r"(20\d{2})", text)
    year = int(year_match.group(1)) if year_match else None

    month = None
    for token, numeric_month in MONTH_MAP.items():
        if re.search(rf"\b{re.escape(token)}\b", text):
            month = numeric_month
            break

    if month is None:
        month_match = re.search(r"\b(0?[1-9]|1[0-2])\b", text)
        if month_match:
            month = int(month_match.group(1))

    return year, month


def _parse_employee_codes(payload: dict[str, Any]) -> list[str]:
    codes: list[str] = []

    single = str(payload.get("codigo_empleado") or payload.get("dni") or payload.get("cuit") or "").strip()
    if single:
        codes.append(single)

    bulk = payload.get("codigos") or payload.get("dni_list") or []
    if isinstance(bulk, str):
        codes.extend([c.strip() for c in re.split(r"[,;\s\n]+", bulk) if c.strip()])
    elif isinstance(bulk, list):
        codes.extend([str(c).strip() for c in bulk if str(c).strip()])

    unique_codes = list(dict.fromkeys(codes))
    for code in unique_codes:
        if not re.fullmatch(r"\d{4,10}", code):
            raise ValueError(f"Codigo invalido: {code}")

    return unique_codes


class BaseV2SearchView(APIView):
    permission_classes = [IsAuthenticated]
    domain_code: str = ""
    detail_select_related: tuple[str, ...] = ()

    def get(self, request):
        return self.post(request)

    def post(self, request):
        start_time = time.time()
        payload = request.data if request.method == "POST" else request.query_params

        try:
            employee_codes = _parse_employee_codes(payload)
        except ValueError as exc:
            return Response(
                {
                    "error": str(exc),
                    "hint": "Cada codigo debe tener entre 4 y 10 digitos.",
                    "total": 0,
                    "results": [],
                },
                status=400,
            )

        # Validate that at least one search filter is provided (excluding pagination)
        if not any([
            payload.get("razon_social") or payload.get("company"),
            payload.get("periodo"),
            payload.get("año") or payload.get("anio") or payload.get("year"),
            payload.get("mes") or payload.get("month"),
            payload.get("banco") or payload.get("bank"),
            payload.get("payroll_type") or payload.get("tipo_documento") or payload.get("tipo"),
            payload.get("tipo") or payload.get("insurance_type"),
            payload.get("subtipo") or payload.get("insurance_subtype"),
            payload.get("movement_type") or payload.get("tipo_documento"),
            payload.get("dni") or payload.get("cuit") or payload.get("certificado"),
            employee_codes,
        ]):
            return Response({
                "error": "Debe proporcionar al menos un filtro de búsqueda.",
                "hint": "Puede buscar por Empresa, Periodo o Tipo de documento. El DNI es opcional.",
                "total": 0,
                "results": [],
            }, status=400)

        queryset = self._build_v2_queryset(payload, employee_codes)
        max_results = int(getattr(settings, "DOCREPO_MAX_RESULTS", 500))
        documents = list(queryset[:max_results])

        response_data = {
            "total": len(documents),
            "results": [self._serialize_document(doc) for doc in documents],
            "source": "docrepo_v2",
            "search_time_ms": round((time.time() - start_time) * 1000, 2),
            "domain": self.domain_code,
        }

        comparison = self._build_dual_read_comparison(payload, employee_codes, documents)
        if comparison is not None:
            response_data["comparison"] = comparison

        return Response(response_data)

    def _build_v2_queryset(self, payload: dict[str, Any], employee_codes: list[str]):
        queryset = Document.objects.filter(
            is_active=True,
            domain__code=self.domain_code,
        ).select_related(
            "domain",
            "company",
            "period",
            "storage_object",
            "index_state",
            *self.detail_select_related,
        ).prefetch_related("employee_codes")

        period_year = _safe_int(payload.get("año") or payload.get("anio") or payload.get("year"))
        period_month = _safe_month(payload.get("mes") or payload.get("month"))

        if period_year is None and period_month is None and payload.get("periodo"):
            parsed_year, parsed_month = _parse_period(payload.get("periodo"))
            period_year = parsed_year or period_year
            period_month = parsed_month or period_month

        query = Q()

        company_value = str(payload.get("razon_social") or payload.get("company") or "").strip()
        if company_value:
            query &= Q(company__name__iexact=company_value) | Q(company__code__iexact=company_value)

        if period_year is not None:
            query &= Q(period__year=period_year)

        if period_month is not None:
            query &= Q(period__month=period_month)

        if employee_codes:
            query &= Q(employee_codes__employee_code__in=employee_codes)

        query &= self._domain_query(payload)

        return queryset.filter(query).distinct().order_by("-indexed_at", "-created_at")

    def _serialize_document(self, document: Document):
        storage = getattr(document, "storage_object", None)
        index_state = getattr(document, "index_state", None)

        object_key = ""
        size_bytes = 0
        if storage is not None:
            object_key = storage.object_key
            size_bytes = storage.size_bytes or 0
        elif document.source_path_legacy:
            object_key = document.source_path_legacy

        result = {
            "id": str(document.id),
            "filename": object_key,
            "metadata": {
                "domain": document.domain.code,
                "razon_social": document.company.name,
                "año": document.period.year if document.period else None,
                "mes": f"{document.period.month:02d}" if document.period else None,
                **self._domain_metadata(document),
            },
            "download_url": f"/api/v2/documents/{document.id}/download",
            "download_legacy_url": f"/api/download/{object_key}" if object_key else None,
            "size_kb": round(size_bytes / 1024, 2) if size_bytes else 0,
            "indexed": index_state.is_indexed if index_state else False,
            "employee_codes": [code.employee_code for code in document.employee_codes.all()],
        }
        return result

    def _build_dual_read_comparison(self, payload: dict[str, Any], employee_codes: list[str], v2_documents: list[Document]):
        if not getattr(settings, "DOCREPO_DUAL_READ_ENABLED", False):
            return None

        if not _as_bool(payload.get("compare_with_legacy")):
            return None

        legacy_queryset = PDFIndex.objects.filter(self._legacy_query(payload, employee_codes)).only(
            "minio_object_name",
            "tipo_documento",
        )

        legacy_sample: list[str] = []
        legacy_count = 0
        for row in legacy_queryset.iterator(chunk_size=500):
            if infer_domain_code(row.minio_object_name, row.tipo_documento) != self.domain_code:
                continue
            legacy_count += 1
            if len(legacy_sample) < 10:
                legacy_sample.append(row.minio_object_name)

        v2_sample = []
        for doc in v2_documents[:10]:
            storage = getattr(doc, "storage_object", None)
            v2_sample.append(storage.object_key if storage else doc.source_path_legacy)

        return {
            "enabled": True,
            "method": "approximate_legacy_filter_plus_domain_inference",
            "legacy_total": legacy_count,
            "v2_total": len(v2_documents),
            "delta": len(v2_documents) - legacy_count,
            "legacy_sample": legacy_sample,
            "v2_sample": v2_sample,
        }

    def _legacy_query(self, payload: dict[str, Any], employee_codes: list[str]):
        query = Q(is_indexed=True)

        company_value = str(payload.get("razon_social") or payload.get("company") or "").strip()
        if company_value:
            query &= Q(razon_social__iexact=company_value)

        period_year = _safe_int(payload.get("año") or payload.get("anio") or payload.get("year"))
        period_month = _safe_month(payload.get("mes") or payload.get("month"))

        if period_year is None and period_month is None and payload.get("periodo"):
            parsed_year, parsed_month = _parse_period(payload.get("periodo"))
            period_year = parsed_year or period_year
            period_month = parsed_month or period_month

        if period_year is not None:
            query &= Q(año=str(period_year))

        if period_month is not None:
            query &= Q(mes=f"{period_month:02d}")

        if employee_codes:
            code_query = Q()
            for code in employee_codes:
                code_query |= Q(codigos_empleado__icontains=code)
            query &= code_query

        query &= self._legacy_domain_query(payload)
        return query

    def _domain_query(self, payload: dict[str, Any]):
        return Q()

    def _legacy_domain_query(self, payload: dict[str, Any]):
        return Q()

    def _domain_metadata(self, document: Document):
        return {}


class FilterOptionsV2View(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        domain_filter = str(request.query_params.get("domain") or "").strip().upper()
        valid_domains = {"SEGUROS", "TREGISTRO", "CONSTANCIA_ABONO"}

        queryset = Document.objects.filter(is_active=True)
        if domain_filter in valid_domains:
            queryset = queryset.filter(domain__code=domain_filter)

        years = [
            str(year)
            for year in queryset.exclude(period__isnull=True)
            .values_list("period__year", flat=True)
            .distinct()
            .order_by("-period__year")
            if year
        ]

        razones_sociales = [
            name
            for name in queryset.values_list("company__name", flat=True)
            .distinct()
            .order_by("company__name")
            if name
        ]

        bancos = [
            bank_name
            for bank_name in queryset.values_list("constancia_detail__bank__name", flat=True)
            .distinct()
            .order_by("constancia_detail__bank__name")
            if bank_name
        ]

        tipos_documento_values = set()
        for value in queryset.values_list("constancia_detail__payroll_type", flat=True).distinct():
            if value:
                tipos_documento_values.add(value.strip())

        for value in queryset.values_list("constancia_detail__legacy_tipo_documento", flat=True).distinct():
            if value:
                tipos_documento_values.add(value.strip())

        for value in queryset.values_list("insurance_detail__insurance_type__name", flat=True).distinct():
            if value:
                tipos_documento_values.add(value.strip())

        for value in queryset.values_list("tregistro_detail__movement_type__name", flat=True).distinct():
            if value:
                tipos_documento_values.add(value.strip())

        tipos_documento = sorted(tipos_documento_values, key=str.casefold)

        return Response(
            {
                "años": years,
                "razones_sociales": razones_sociales,
                "bancos": bancos,
                "tipos_documento": tipos_documento,
                "meses": MONTH_OPTIONS,
                "source": "docrepo_v2",
                "domain": domain_filter if domain_filter in valid_domains else "ALL",
            }
        )


class DocumentDownloadV2View(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, document_id):
        document = Document.objects.select_related("storage_object").filter(id=document_id, is_active=True).first()
        if document is None:
            record_audit_event(
                action="DOC_DOWNLOAD_FAILED",
                resource_type="document",
                resource_id=str(document_id),
                request=request,
                metadata={"reason": "document_not_found", "status_code": 404},
            )
            return Response({"error": "Documento no encontrado."}, status=404)

        storage = getattr(document, "storage_object", None)
        object_key = ""
        if storage is not None and storage.object_key:
            object_key = storage.object_key
        elif document.source_path_legacy:
            object_key = document.source_path_legacy

        if not object_key:
            record_audit_event(
                action="DOC_DOWNLOAD_FAILED",
                resource_type="document",
                resource_id=str(document.id),
                request=request,
                document=document,
                metadata={"reason": "storage_reference_missing", "status_code": 404},
            )
            return Response({"error": "Documento sin referencia de storage."}, status=404)

        try:
            response = minio_client.get_object(settings.MINIO_BUCKET, object_key)
        except Exception:
            record_audit_event(
                action="DOC_DOWNLOAD_FAILED",
                resource_type="document",
                resource_id=str(document.id),
                request=request,
                document=document,
                metadata={"reason": "storage_object_not_found", "status_code": 404, "object_key": object_key},
            )
            return Response({"error": "Archivo no encontrado en storage."}, status=404)

        DownloadLog.objects.create(
            user=request.user,
            filename=object_key,
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        record_audit_event(
            action="DOC_DOWNLOAD_SUCCEEDED",
            resource_type="document",
            resource_id=str(document.id),
            request=request,
            actor=request.user,
            document=document,
            metadata={
                "status_code": 200,
                "object_key": object_key,
                "domain": document.domain.code,
            },
        )

        safe_filename = object_key.split("/")[-1] or f"{document.id}.pdf"
        return StreamingHttpResponse(
            response.stream(amt=8192),
            content_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
        )


class SegurosV2SearchView(BaseV2SearchView):
    domain_code = "SEGUROS"
    detail_select_related = (
        "insurance_detail",
        "insurance_detail__insurance_type",
        "insurance_detail__insurance_subtype",
    )

    def _domain_query(self, payload: dict[str, Any]):
        query = Q()

        insurance_type = str(payload.get("tipo") or payload.get("insurance_type") or "").strip()
        if insurance_type:
            query &= Q(insurance_detail__insurance_type__name__iexact=insurance_type) | Q(
                insurance_detail__insurance_type__code__iexact=insurance_type
            )

        insurance_subtype = str(payload.get("subtipo") or payload.get("insurance_subtype") or "").strip()
        if insurance_subtype:
            query &= Q(insurance_detail__insurance_subtype__name__iexact=insurance_subtype) | Q(
                insurance_detail__insurance_subtype__code__iexact=insurance_subtype
            )

        return query

    def _legacy_domain_query(self, payload: dict[str, Any]):
        query = Q()

        insurance_type = str(payload.get("tipo") or payload.get("insurance_type") or "").strip()
        if insurance_type:
            query &= Q(tipo_documento__icontains=insurance_type) | Q(minio_object_name__icontains=insurance_type)

        insurance_subtype = str(payload.get("subtipo") or payload.get("insurance_subtype") or "").strip()
        if insurance_subtype:
            query &= Q(tipo_documento__icontains=insurance_subtype) | Q(minio_object_name__icontains=insurance_subtype)

        return query

    def _domain_metadata(self, document: Document):
        detail = getattr(document, "insurance_detail", None)
        if detail is None:
            return {
                "tipo_seguro": None,
                "subtipo_seguro": None,
                "asegurados": 0,
            }

        return {
            "tipo_seguro": detail.insurance_type.name,
            "subtipo_seguro": detail.insurance_subtype.name if detail.insurance_subtype else None,
            "asegurados": detail.insured_count,
        }


class TRegistroV2SearchView(BaseV2SearchView):
    domain_code = "TREGISTRO"
    detail_select_related = (
        "tregistro_detail",
        "tregistro_detail__movement_type",
    )

    def _domain_query(self, payload: dict[str, Any]):
        query = Q()

        movement_type = str(
            payload.get("tipo")
            or payload.get("tipo_documento")
            or payload.get("movement_type")
            or ""
        ).strip()
        if movement_type:
            query &= Q(tregistro_detail__movement_type__name__iexact=movement_type) | Q(
                tregistro_detail__movement_type__code__iexact=movement_type
            )

        return query

    def _legacy_domain_query(self, payload: dict[str, Any]):
        movement_type = str(
            payload.get("tipo")
            or payload.get("tipo_documento")
            or payload.get("movement_type")
            or ""
        ).strip()
        if not movement_type:
            return Q()
        return Q(tipo_documento__icontains=movement_type) | Q(minio_object_name__icontains=movement_type)

    def _domain_metadata(self, document: Document):
        detail = getattr(document, "tregistro_detail", None)
        if detail is None:
            return {
                "tipo_movimiento": None,
                "dni": None,
            }

        return {
            "tipo_movimiento": detail.movement_type.name,
            "dni": detail.worker_document_number or None,
        }


class ConstanciasV2SearchView(BaseV2SearchView):
    domain_code = "CONSTANCIA_ABONO"
    detail_select_related = (
        "constancia_detail",
        "constancia_detail__bank",
    )

    def _domain_query(self, payload: dict[str, Any]):
        query = Q()

        # New contract parameter: banco (supports legacy bank alias)
        bank = str(payload.get("banco") or payload.get("bank") or "").strip()
        if bank:
            query &= Q(constancia_detail__bank__name__iexact=bank) | Q(constancia_detail__bank__code__iexact=bank)

        # New contract parameter: payroll_type (supports legacy tipo_documento/tipo aliases)
        payroll_type = str(payload.get("payroll_type") or payload.get("tipo_documento") or payload.get("tipo") or "").strip()
        if payroll_type:
            query &= Q(constancia_detail__payroll_type__icontains=payroll_type) | Q(
                constancia_detail__legacy_tipo_documento__icontains=payroll_type
            )

        return query

    def _legacy_domain_query(self, payload: dict[str, Any]):
        query = Q()

        bank = str(payload.get("banco") or payload.get("bank") or "").strip()
        if bank:
            query &= Q(banco__iexact=bank)

        payroll_type = str(payload.get("payroll_type") or payload.get("tipo_documento") or "").strip()
        if payroll_type:
            query &= Q(tipo_documento__icontains=payroll_type)

        return query

    def _domain_metadata(self, document: Document):
        detail = getattr(document, "constancia_detail", None)
        if detail is None:
            return {
                "banco": None,
                "tipo_planilla": None,
                "lote": None,
                "estado_indexacion": None,
            }

        index_state = getattr(document, "index_state", None)
        return {
            "banco": detail.bank.name if detail.bank else None,
            "tipo_planilla": detail.payroll_type or None,
            "lote": detail.payment_batch_ref or None,
            "estado_indexacion": "INDEXED" if index_state and index_state.is_indexed else "PENDING",
        }
