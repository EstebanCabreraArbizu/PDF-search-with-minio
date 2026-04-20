from django.contrib import admin

from .models import (
    ConstanciaAbonoDocument,
    Document,
    EmployeeCode,
    IndexState,
    InsuranceDocument,
    StorageObject,
    TRegistroDocument,
)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "domain", "company", "period", "status", "indexed_at", "is_active")
    list_filter = ("domain", "company", "status", "is_active")
    search_fields = ("original_filename", "source_path_legacy", "content_hash_sha256", "source_hash_md5")
    autocomplete_fields = ("company", "domain", "period", "status")


@admin.register(StorageObject)
class StorageObjectAdmin(admin.ModelAdmin):
    list_display = ("document", "bucket_name", "object_key", "size_bytes", "last_modified")
    list_filter = ("bucket_name",)
    search_fields = ("object_key", "etag")


@admin.register(IndexState)
class IndexStateAdmin(admin.ModelAdmin):
    list_display = ("document", "is_indexed", "index_version", "indexed_at", "last_error_code")
    list_filter = ("is_indexed", "index_version")
    search_fields = ("document__original_filename", "last_error_code")


@admin.register(EmployeeCode)
class EmployeeCodeAdmin(admin.ModelAdmin):
    list_display = ("employee_code", "document", "source", "created_at")
    list_filter = ("source",)
    search_fields = ("employee_code", "document__original_filename")


@admin.register(TRegistroDocument)
class TRegistroDocumentAdmin(admin.ModelAdmin):
    list_display = ("document", "movement_type", "worker_document_type", "worker_document_number", "effective_date")
    list_filter = ("movement_type", "worker_document_type")
    search_fields = ("worker_document_number", "document__original_filename")


@admin.register(InsuranceDocument)
class InsuranceDocumentAdmin(admin.ModelAdmin):
    list_display = ("document", "insurance_type", "insurance_subtype", "policy_number", "insured_count")
    list_filter = ("insurance_type", "insurance_subtype")
    search_fields = ("policy_number", "document__original_filename")


@admin.register(ConstanciaAbonoDocument)
class ConstanciaAbonoDocumentAdmin(admin.ModelAdmin):
    list_display = ("document", "bank", "payroll_type", "payment_batch_ref", "employee_count")
    list_filter = ("bank", "payroll_type")
    search_fields = ("payment_batch_ref", "document__original_filename")
