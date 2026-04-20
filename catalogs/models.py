from django.db import models
from django.db.models import Q

from core.models import TimestampedModel


class CatalogDomain(TimestampedModel):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "catalog_domain"
        ordering = ["name"]

    def __str__(self):
        return self.name


class CatalogCompany(TimestampedModel):
    code = models.CharField(max_length=60, unique=True)
    name = models.CharField(max_length=180, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "catalog_company"
        ordering = ["name"]

    def __str__(self):
        return self.name


class CatalogPeriod(TimestampedModel):
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()

    class Meta:
        db_table = "catalog_period"
        ordering = ["-year", "-month"]
        constraints = [
            models.UniqueConstraint(fields=["year", "month"], name="catalog_period_year_month_uniq"),
            models.CheckConstraint(check=Q(month__gte=1) & Q(month__lte=12), name="catalog_period_month_range_chk"),
        ]

    def __str__(self):
        return f"{self.year}-{self.month:02d}"


class CatalogBank(TimestampedModel):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=120, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "catalog_bank"
        ordering = ["name"]

    def __str__(self):
        return self.name


class CatalogDocumentStatus(TimestampedModel):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=80, unique=True)
    is_terminal = models.BooleanField(default=False)

    class Meta:
        db_table = "catalog_document_status"
        ordering = ["name"]

    def __str__(self):
        return self.name


class CatalogTRegistroType(TimestampedModel):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=60, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "catalog_tregistro_type"
        ordering = ["name"]

    def __str__(self):
        return self.name


class CatalogInsuranceType(TimestampedModel):
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=80, unique=True)
    allows_subtype = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "catalog_insurance_type"
        ordering = ["name"]

    def __str__(self):
        return self.name


class CatalogInsuranceSubtype(TimestampedModel):
    insurance_type = models.ForeignKey(CatalogInsuranceType, on_delete=models.CASCADE, related_name="subtypes")
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "catalog_insurance_subtype"
        ordering = ["insurance_type__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["insurance_type", "code"],
                name="catalog_insurance_subtype_type_code_uniq",
            )
        ]

    def __str__(self):
        return f"{self.insurance_type.code} - {self.name}"
