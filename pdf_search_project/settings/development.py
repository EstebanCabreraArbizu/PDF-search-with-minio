"""
Django settings - DESARROLLO LOCAL

🎓 LECCIÓN: ¿Qué es diferente en desarrollo?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
En desarrollo queremos:
- DEBUG=True para ver errores detallados
- Aceptar localhost como host
- CORS permisivo (para desarrollo frontend)
- Menos restricciones de seguridad (para iterar rápido)

⚠️ NUNCA uses esta configuración en producción!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from .base import *  # Importa toda la configuración base

# =============================================================================
# MODO DESARROLLO
# =============================================================================
DEBUG = True

# SECRET_KEY para desarrollo (está bien que sea insegura aquí)
SECRET_KEY = 'django-insecure-dev-key-solo-para-desarrollo-local-12345'

# Acepta cualquier host en desarrollo
ALLOWED_HOSTS = ['*']


# =============================================================================
# CORS PERMISIVO (solo desarrollo)
# =============================================================================
CORS_ALLOW_ALL_ORIGINS = True
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://localhost:3000',  # Si usas React/Vue en otro puerto
]


# =============================================================================
# WHITENOISE (recarga automática en desarrollo)
# =============================================================================
WHITENOISE_AUTOREFRESH = True


# =============================================================================
# SEGURIDAD RELAJADA (solo desarrollo)
# 🎓 LECCIÓN: Estas configuraciones hacen que el desarrollo sea más fácil
#             pero NO son seguras para producción
# =============================================================================

# No forzar HTTPS en desarrollo
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Permitir cookies sin SameSite estricto
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'


# CSP se gestiona dinámicamente en documents.middleware.SecurityHeadersMiddleware
