# Create your models here. 
from django.db import models

from django.contrib.auth.models import AbstractUser

# Usuario personalizado (opcional, pero recomendado)
class CustomUser(AbstractUser):
    full_name = models.CharField(max_length=120, blank=True)
    # El campo 'role' se maneja con 'is_staff' y 'groups' en Django

    class Meta:
        db_table = 'users'

# Índice de PDFs
class PDFIndex(models.Model):
    minio_object_name = models.CharField(max_length=500, unique=True, db_index=True)
    razon_social = models.CharField(max_length=150, db_index=True, blank=True)
    banco = models.CharField(max_length=100, db_index=True, blank=True)
    mes = models.CharField(max_length=2, db_index=True, blank=True)
    año = models.CharField(max_length=4, db_index=True, blank=True)
    tipo_documento = models.CharField(max_length=300, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    md5_hash = models.CharField(max_length=64, blank=True, null=True) # Hash MD5 for sync
    codigos_empleado = models.TextField(blank=True)  # CSV de códigos
    indexed_at = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)
    is_indexed = models.BooleanField(default=True)

    class Meta:
        db_table = 'pdf_index'

# Log de descargas
class DownloadLog(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    filename = models.CharField(max_length=500)
    downloaded_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True)

    class Meta:
        db_table = 'download_log'