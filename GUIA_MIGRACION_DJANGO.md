# 🚀 Guía de Migración: Flask → Django

Esta guía te ayudará a migrar el "Sistema de Búsqueda Inteligente" de Flask a Django, aprovechando sus ventajas en seguridad y gestión de usuarios.

---

## 📋 Tabla de Contenidos
1. [¿Por qué Django?](#-por-qué-django)
2. [Preparación del Entorno](#-preparación-del-entorno)
3. [Estructura del Proyecto Django](#-estructura-del-proyecto-django)
4. [Migración de Modelos](#-migración-de-modelos)
5. [Migración de Vistas (Endpoints)](#-migración-de-vistas-endpoints)
6. [Sistema de Autenticación](#-sistema-de-autenticación)
7. [Integración con MinIO/S3](#-integración-con-minios3)
8. [Configuración de Docker](#-configuración-de-docker)
9. [Checklist de Migración](#-checklist-de-migración)

---

## 🎯 ¿Por qué Django?

| Característica | Flask | Django |
| :--- | :--- | :--- |
| **Autenticación** | Manual (Flask-JWT) | Incluida (`django.contrib.auth`) |
| **Admin Panel** | No incluido | Incluido (`/admin`) |
| **ORM** | SQLAlchemy (externo) | Django ORM (integrado) |
| **Migraciones** | Alembic (externo) | Incluidas (`makemigrations`) |
| **Seguridad** | Manual | CSRF, XSS, SQL Injection protegidos |
| **Permisos** | Manual | Sistema de permisos y grupos |

---

## 🛠️ Preparación del Entorno

### 1. Crear el Proyecto Django
```bash
# Crear entorno virtual
python -m venv venv
venv\Scripts\activate  # Windows

# Instalar Django y dependencias
pip install django djangorestframework django-cors-headers psycopg2-binary boto3 PyMuPDF pytesseract Pillow pdf2image djangorestframework-simplejwt

# Crear proyecto
django-admin startproject pdf_search_project .

# Crear app principal
python manage.py startapp documents
```

### 2. Estructura de Carpetas Resultante
```
PDF-search-with-minio/
├── pdf_search_project/      # Configuración del proyecto
│   ├── settings.py          # Configuraciones principales
│   ├── urls.py               # Rutas principales
│   └── wsgi.py
├── documents/               # Tu app principal
│   ├── models.py            # Modelos (PDFIndex, DownloadLog)
│   ├── views.py             # Vistas/Endpoints
│   ├── serializers.py       # Serializadores DRF
│   ├── urls.py               # Rutas de la app
│   └── admin.py             # Registro en Admin Panel
├── templates/               # HTML templates
├── manage.py
└── requirements.txt
```

---

## 📦 Migración de Modelos

### Archivo: `documents/models.py`

```python
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
```

### Configurar Usuario en `settings.py`
```python
AUTH_USER_MODEL = 'documents.CustomUser'
```

### Ejecutar Migraciones
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser  # Crear admin
```

---

## 🔌 Migración de Vistas (Endpoints)

### Archivo: `documents/views.py` (usando Django REST Framework)

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import status
from django.db.models import Q
from .models import PDFIndex
from .serializers import PDFIndexSerializer

class SearchView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        codigo = request.data.get('codigo_empleado', '')
        año = request.data.get('año')
        mes = request.data.get('mes')
        
        query = Q(codigos_empleado__icontains=codigo)
        if año:
            query &= Q(año=año)
        if mes:
            query &= Q(mes=mes)
        
        results = PDFIndex.objects.filter(query)[:100]
        serializer = PDFIndexSerializer(results, many=True)
        return Response({'total': len(results), 'results': serializer.data})

class ReindexView(APIView):
    permission_classes = [IsAdminUser]  # Solo admins

    def post(self, request):
        # Tu lógica de reindexación aquí
        return Response({'success': True, 'message': 'Reindexación iniciada'})
```

### Archivo: `documents/serializers.py`
```python
from rest_framework import serializers
from .models import PDFIndex

class PDFIndexSerializer(serializers.ModelSerializer):
    class Meta:
        model = PDFIndex
        fields = '__all__'
```

### Archivo: `documents/urls.py`
```python
from django.urls import path
from .views import SearchView, ReindexView

urlpatterns = [
    path('api/search/', SearchView.as_view(), name='search'),
    path('api/reindex/', ReindexView.as_view(), name='reindex'),
    # Añade más endpoints aquí...
]
```

### Archivo: `pdf_search_project/urls.py`
```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('documents.urls')),
]
```

---

## 🔐 Sistema de Autenticación

### Opción 1: JWT con `djangorestframework-simplejwt`
```python
# settings.py
INSTALLED_APPS = [
    # ...
    'rest_framework',
    'rest_framework_simplejwt',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
}

# urls.py
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
```

### Opción 2: Sesiones (más simple para apps web)
```python
# settings.py
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
}
```

---

## ☁️ Integración con MinIO/S3

### Archivo: `documents/storage.py`
```python
import boto3
from django.conf import settings

def get_minio_client():
    return boto3.client(
        's3',
        endpoint_url=f"http://{settings.MINIO_ENDPOINT}",
        aws_access_key_id=settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=settings.MINIO_SECRET_KEY,
    )

def download_pdf(object_name):
    client = get_minio_client()
    response = client.get_object(Bucket=settings.MINIO_BUCKET, Key=object_name)
    return response['Body'].read()
```

### Añadir a `settings.py`
```python
# MinIO / S3
MINIO_ENDPOINT = os.environ.get('MINIO_ENDPOINT', 'minio:9000')
MINIO_ACCESS_KEY = os.environ.get('MINIO_ACCESS_KEY', 'admin')
MINIO_SECRET_KEY = os.environ.get('MINIO_SECRET_KEY', 'password123')
MINIO_BUCKET = 'planillas-pdfs'
```

---

## 🐳 Configuración de Docker

### Nuevo `Dockerfile` para Django
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema para OCR
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-spa \
    poppler-utils \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Recolectar archivos estáticos
RUN python manage.py collectstatic --noinput

# Usar Gunicorn para producción
CMD ["gunicorn", "pdf_search_project.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
```

### Actualizar `docker-compose.yaml`
```yaml
services:
  django-app:
    build: ./django-app
    container_name: django-api
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://admin:password123@postgres:5432/pdf_search
      - MINIO_ENDPOINT=minio:9000
      - MINIO_ACCESS_KEY=admin
      - MINIO_SECRET_KEY=password123
      - DJANGO_SECRET_KEY=tu-clave-secreta-aqui
      - DEBUG=False
    depends_on:
      postgres:
        condition: service_healthy
      minio:
        condition: service_healthy
    volumes:
      - ./django-app:/app
```

---

## ✅ Checklist de Migración

```
[ ] 1. Crear proyecto Django y app "documents"
[ ] 2. Configurar settings.py (DB, CORS, REST Framework)
[ ] 3. Migrar modelos de SQLAlchemy a Django ORM
[ ] 4. Ejecutar makemigrations y migrate
[ ] 5. Crear serializers para cada modelo
[ ] 6. Migrar cada endpoint de Flask a una APIView
[ ] 7. Configurar autenticación JWT o Session
[ ] 8. Migrar lógica de MinIO a storage.py
[ ] 9. Migrar lógica de OCR
[ ] 10. Registrar modelos en admin.py
[ ] 11. Actualizar Dockerfile y docker-compose.yaml
[ ] 12. Migrar templates HTML (si aplica)
[ ] 13. Probar todos los endpoints
[ ] 14. Actualizar documentación (README.md)
```

---

## 📚 Recursos Adicionales

- [Django REST Framework - Guía Oficial](https://www.django-rest-framework.org/)
- [Simple JWT - Documentación](https://django-rest-framework-simplejwt.readthedocs.io/)
- [Django Admin Cookbook](https://books.agiliq.com/projects/django-admin-cookbook/)
- [Boto3 (AWS S3/MinIO)](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)

---

> [!TIP]
> **Consejo**: Migra endpoint por endpoint. No intentes hacerlo todo de una vez. Comienza con `/api/login` y `/api/search`, y ve añadiendo los demás gradualmente.

**¿Dudas?** Si te atoras en algún paso, puedo darte más detalles o ejemplos de código específicos.
