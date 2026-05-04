import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

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
from core.models import TimestampedModel


class Document(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    domain = models.ForeignKey(CatalogDomain, on_delete=models.PROTECT, related_name="documents")
    company = models.ForeignKey(CatalogCompany, on_delete=models.PROTECT, related_name="documents")
    period = models.ForeignKey(CatalogPeriod, on_delete=models.PROTECT, null=True, blank=True, related_name="documents")
    original_filename = models.CharField(max_length=500)
    source_path_legacy = models.CharField(max_length=700, blank=True, db_index=True)
    content_hash_sha256 = models.CharField(max_length=64, blank=True, null=True, db_index=True)
    source_hash_md5 = models.CharField(max_length=64, blank=True, null=True, db_index=True)
    correction_reason = models.CharField(max_length=500, blank=True)
    status = models.ForeignKey(
        CatalogDocumentStatus,
        on_delete=models.PROTECT,
        related_name="documents",
        null=True,
        blank=True,
    )
    indexed_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="docrepo_documents_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="docrepo_documents_updated",
    )

    class Meta:
        db_table = "docrepo_document"
        indexes = [
            models.Index(fields=["domain", "company", "period"], name="docrepo_doc_dom_comp_per_idx"),
            models.Index(fields=["is_active", "indexed_at"], name="docrepo_doc_active_idx"),
            models.Index(fields=["is_active", "domain", "company", "period"], name="docrepo_doc_active_scope_idx"),
            models.Index(fields=["indexed_at"], name="docrepo_doc_indexed_at_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["domain", "company", "period", "content_hash_sha256"],
                condition=Q(content_hash_sha256__isnull=False) & ~Q(content_hash_sha256=""),
                name="docrepo_doc_hash_scope_uniq",
            )
        ]

    def __str__(self):
        return f"{self.domain.code} - {self.original_filename}"


class StorageObject(TimestampedModel):
    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name="storage_object")
    bucket_name = models.CharField(max_length=120)
    object_key = models.CharField(max_length=800)
    object_version = models.CharField(max_length=255, blank=True)
    etag = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=120, default="application/pdf")
    size_bytes = models.BigIntegerField(default=0)
    last_modified = models.DateTimeField(null=True, blank=True)
    checksum_sha256 = models.CharField(max_length=64, null=True, blank=True)
    is_encrypted = models.BooleanField(default=False)

    class Meta:
        db_table = "docrepo_storage_object"
        constraints = [
            models.UniqueConstraint(fields=["bucket_name", "object_key"], name="docrepo_storage_bucket_key_uniq")
        ]
        indexes = [
            models.Index(fields=["bucket_name", "object_key"], name="docrepo_storage_bucket_key_idx"),
            models.Index(fields=["object_key"], name="docrepo_storage_obj_key_idx"),
            models.Index(fields=["bucket_name"], name="docrepo_storage_bucket_idx"),
            models.Index(fields=["etag"], name="docrepo_storage_etag_idx"),
            models.Index(fields=["size_bytes"], name="docrepo_storage_size_idx"),
            models.Index(fields=["bucket_name", "etag", "size_bytes"], name="docrepo_storage_dup_idx"),
        ]

    def __str__(self):
        return f"{self.bucket_name}/{self.object_key}"


class IndexState(TimestampedModel):
    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name="index_state")
    is_indexed = models.BooleanField(default=False)
    index_version = models.CharField(max_length=40, default="v1")
    indexed_at = models.DateTimeField(null=True, blank=True)
    indexed_by_job_id = models.UUIDField(null=True, blank=True)
    last_error_code = models.CharField(max_length=80, blank=True)
    last_error_detail = models.TextField(blank=True)
    extracted_codes_count = models.PositiveIntegerField(default=0)
    total_pages = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = "docrepo_index_state"
        indexes = [models.Index(fields=["is_indexed", "indexed_at"], name="docrepo_index_state_idx")]

    def __str__(self):
        return f"{self.document_id} - {'indexed' if self.is_indexed else 'pending'}"


class EmployeeCode(TimestampedModel):
    class SourceChoices(models.TextChoices):
        EXTRACTED = "EXTRACTED", "Extracted"
        MANUAL = "MANUAL", "Manual"
        IMPORTED = "IMPORTED", "Imported"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="employee_codes")
    employee_code = models.CharField(max_length=20)
    source = models.CharField(max_length=20, choices=SourceChoices.choices, default=SourceChoices.EXTRACTED)

    class Meta:
        db_table = "docrepo_employee_code"
        constraints = [
            models.UniqueConstraint(fields=["document", "employee_code"], name="docrepo_emp_code_doc_code_uniq")
        ]
        indexes = [models.Index(fields=["employee_code"], name="docrepo_emp_code_idx")]

    def __str__(self):
        return self.employee_code


class TRegistroDocument(TimestampedModel):
    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name="tregistro_detail")
    movement_type = models.ForeignKey(CatalogTRegistroType, on_delete=models.PROTECT, related_name="tregistro_documents")
    worker_document_type = models.CharField(max_length=20, default="DNI")
    worker_document_number = models.CharField(max_length=20, blank=True, db_index=True)
    effective_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "docrepo_tregistro_document"
        indexes = [
            models.Index(fields=["movement_type", "effective_date"], name="docrepo_treg_move_date_idx")
        ]

    def __str__(self):
        return f"{self.movement_type.code} - {self.document_id}"


class InsuranceDocument(TimestampedModel):
    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name="insurance_detail")
    insurance_type = models.ForeignKey(CatalogInsuranceType, on_delete=models.PROTECT, related_name="documents")
    insurance_subtype = models.ForeignKey(
        CatalogInsuranceSubtype,
        on_delete=models.PROTECT,
        related_name="documents",
        null=True,
        blank=True,
    )
    policy_number = models.CharField(max_length=80, blank=True)
    coverage_start = models.DateField(null=True, blank=True)
    coverage_end = models.DateField(null=True, blank=True)
    insured_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "docrepo_insurance_document"
        indexes = [
            models.Index(fields=["insurance_type", "insurance_subtype"], name="docrepo_ins_type_sub_idx")
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(coverage_start__isnull=True)
                | Q(coverage_end__isnull=True)
                | Q(coverage_end__gte=F("coverage_start")),
                name="docrepo_ins_coverage_range_chk",
            )
        ]

    def clean(self):
        if self.insurance_subtype and self.insurance_subtype.insurance_type_id != self.insurance_type_id:
            raise ValidationError("Insurance subtype must belong to insurance type.")
        if self.insurance_subtype and not self.insurance_type.allows_subtype:
            raise ValidationError("Insurance type does not allow subtypes.")

    def __str__(self):
        return f"{self.insurance_type.code} - {self.document_id}"


class ConstanciaAbonoDocument(TimestampedModel):
    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name="constancia_detail")
    bank = models.ForeignKey(CatalogBank, on_delete=models.PROTECT, related_name="constancia_documents", null=True, blank=True)
    payroll_type = models.CharField(max_length=80, blank=True)
    payment_batch_ref = models.CharField(max_length=120, blank=True)
    employee_count = models.PositiveIntegerField(null=True, blank=True)
    source_period_text = models.CharField(max_length=80, blank=True)
    ingestion_channel = models.CharField(max_length=50, blank=True)
    legacy_tipo_documento = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "docrepo_constancia_abono_document"
        indexes = [models.Index(fields=["bank", "payroll_type"], name="docrepo_const_bank_pay_idx")]

    def __str__(self):
        return f"CONSTANCIA - {self.document_id}"
