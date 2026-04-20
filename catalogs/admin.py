from django.contrib import admin

from .models import (
    CatalogBank,
    CatalogCompany,
    CatalogDocumentStatus,
    CatalogDomain,
    CatalogInsuranceSubtype,
    CatalogInsuranceType,
    CatalogPeriod,
    CatalogTRegistroType,
)


@admin.register(CatalogDomain)
class CatalogDomainAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    search_fields = ("code", "name")
    list_filter = ("is_active",)


@admin.register(CatalogCompany)
class CatalogCompanyAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    search_fields = ("code", "name")
    list_filter = ("is_active",)


@admin.register(CatalogPeriod)
class CatalogPeriodAdmin(admin.ModelAdmin):
    list_display = ("year", "month")
    list_filter = ("year", "month")
    search_fields = ("=year", "=month")


@admin.register(CatalogBank)
class CatalogBankAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    search_fields = ("code", "name")
    list_filter = ("is_active",)


@admin.register(CatalogDocumentStatus)
class CatalogDocumentStatusAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_terminal")
    search_fields = ("code", "name")
    list_filter = ("is_terminal",)


@admin.register(CatalogTRegistroType)
class CatalogTRegistroTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    search_fields = ("code", "name")
    list_filter = ("is_active",)


@admin.register(CatalogInsuranceType)
class CatalogInsuranceTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "allows_subtype", "is_active")
    search_fields = ("code", "name")
    list_filter = ("allows_subtype", "is_active")


@admin.register(CatalogInsuranceSubtype)
class CatalogInsuranceSubtypeAdmin(admin.ModelAdmin):
    list_display = ("insurance_type", "code", "name", "is_active")
    search_fields = ("insurance_type__name", "code", "name")
    list_filter = ("insurance_type", "is_active")
