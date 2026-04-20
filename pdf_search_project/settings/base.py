"""
Django settings - CONFIGURACIÓN BASE (común para todos los entornos)

🎓 LECCIÓN: ¿Por qué separar settings?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Este archivo contiene configuración que es IGUAL en desarrollo y producción.
Las diferencias (DEBUG, SECRET_KEY, etc.) van en development.py o production.py

Beneficios:
1. No puedes accidentalmente desplegar con DEBUG=True
2. Las credenciales sensibles NO están en el código
3. Es fácil ver qué es diferente entre entornos
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from pathlib import Path
import os
import json
from datetime import timedelta
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# NOTA: Subimos un nivel extra porque ahora estamos en settings/base.py
BASE_DIR = Path(__file__).resolve().parent.parent.parent


# =============================================================================
# APLICACIONES INSTALADAS
# =============================================================================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
    'catalogs',
    'docrepo',
    'auditlog',
    'documents',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
]


# =============================================================================
# MIDDLEWARE
# =============================================================================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'documents.middleware.IPRateLimitMiddleware',
    'documents.middleware.RequestSanitizationMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'documents.middleware.AdminIPRestrictionMiddleware',
    'documents.middleware.AuditLoggingMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'documents.middleware.SecurityHeadersMiddleware',
]


# =============================================================================
# LOGGING
# =============================================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
    },
}


# =============================================================================
# REST FRAMEWORK + JWT
# =============================================================================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    # 🆕 RATE LIMITING (Protección DoS)
    # 🎓 LECCIÓN: Esto limita cuántas peticiones puede hacer cada usuario
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '30/minute',      # Usuarios no autenticados: 30 req/min
        'user': '120/minute',     # Usuarios autenticados: 120 req/min
        'login': '5/minute',      # Intentos de login: 5/min (CRÍTICO)
        'search': '60/minute',    # Búsquedas: 60/min
        'bulk_search': '10/minute',  # Búsquedas masivas: 10/min (más pesado)
    }
}


# =============================================================================
# SIMPLE JWT
# =============================================================================
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'AUTH_HEADER_TYPES': ('Bearer',),
}


# =============================================================================
# MINIO / S3 CONFIGURATION
# =============================================================================
MINIO_ENDPOINT = os.environ.get('MINIO_ENDPOINT', 'minio:9000')
MINIO_ACCESS_KEY = os.environ.get('MINIO_ACCESS_KEY', 'admin')
MINIO_SECRET_KEY = os.environ.get('MINIO_SECRET_KEY', 'password123')
MINIO_BUCKET = os.environ.get('MINIO_BUCKET', 'planillas-pdfs')
MINIO_USE_SSL = os.environ.get('MINIO_USE_SSL', 'False').lower() == 'true'
MINIO_REGION = os.environ.get('MINIO_REGION', None)


# =============================================================================
# DOCREPO V2 FEATURES
# =============================================================================
DOCREPO_DUAL_READ_ENABLED = os.environ.get('DOCREPO_DUAL_READ_ENABLED', 'False').lower() == 'true'
DOCREPO_DUAL_WRITE_LEGACY_ENABLED = os.environ.get('DOCREPO_DUAL_WRITE_LEGACY_ENABLED', 'True').lower() == 'true'
DOCREPO_MAX_RESULTS = int(os.environ.get('DOCREPO_MAX_RESULTS', '500'))


# =============================================================================
# ROUTING & TEMPLATES
# =============================================================================
ROOT_URLCONF = 'pdf_search_project.urls'
DJANGO_ADMIN_URL = os.getenv('DJANGO_ADMIN_URL', 'panel-gestion').strip('/')


def parse_admin_allowed_ips(raw_value):
    raw_value = (raw_value or '').strip()
    if not raw_value:
        return []

    normalized = raw_value.lower()
    if normalized in {'[]', 'none', 'null'}:
        return []

    if raw_value.startswith('[') and raw_value.endswith(']'):
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, list):
                return [str(ip).strip() for ip in parsed if str(ip).strip()]
        except json.JSONDecodeError:
            pass

    return [ip.strip() for ip in raw_value.split(',') if ip.strip()]


ADMIN_ALLOWED_IPS = parse_admin_allowed_ips(os.getenv('ADMIN_ALLOWED_IPS', ''))

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'documents' / 'templates' / 'documents'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'pdf_search_project.wsgi.application'


# =============================================================================
# AUTH & DATABASE
# =============================================================================
AUTH_USER_MODEL = 'documents.CustomUser'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "pdf_search"),
        "USER": os.getenv("POSTGRES_USER", "admin"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "password123"),
        "HOST": os.getenv("POSTGRES_HOST", "postgres"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }
}


# =============================================================================
# PASSWORD VALIDATION
# 🎓 LECCIÓN: Estas reglas aseguran contraseñas fuertes
# =============================================================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 10}},  # 🆕 Aumentado de 8 a 10
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# =============================================================================
# INTERNATIONALIZATION
# =============================================================================
LANGUAGE_CODE = 'es-pe'  # 🆕 Cambiado a español Perú
TIME_ZONE = 'America/Lima'  # 🆕 Zona horaria correcta
USE_I18N = True
USE_TZ = True


# =============================================================================
# STATIC FILES
# =============================================================================
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
WHITENOISE_USE_FINDERS = True
