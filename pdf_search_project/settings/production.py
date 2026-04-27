"""
Django settings - PRODUCCIÓN (VPS + Cloudflare)

🎓 LECCIÓN: ¿Qué es crítico en producción?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
En producción queremos:
- DEBUG=False (NUNCA mostrar errores al público)
- SECRET_KEY desde variable de entorno (no hardcodeada)
- Solo dominios específicos en ALLOWED_HOSTS
- Todos los headers de seguridad activados
- HTTPS forzado en todo
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
from .base import *  # Importa toda la configuración base


def parse_env_list(raw_value: str) -> list[str]:
    if not raw_value:
        return []
    return [item.strip() for item in raw_value.split(',') if item.strip()]

# =============================================================================
# MODO PRODUCCIÓN
# =============================================================================
DEBUG = False

# 🔐 SECRET_KEY DEBE venir de variable de entorno
# 🎓 LECCIÓN: Si esta variable no existe, Django fallará al iniciar
#             Esto es INTENCIONAL - es mejor fallar que usar una clave insegura
SECRET_KEY = os.environ['DJANGO_SECRET_KEY']  # Falla si no existe

# Solo acepta tu dominio específico
DEFAULT_ALLOWED_HOSTS = [
    'search.liderman.net.pe',
    'www.search.liderman.net.pe',
    # IP del VPS (si accedes directo)
    os.getenv('VPS_IP', ''),
]

env_allowed_hosts = parse_env_list(os.getenv('DJANGO_ALLOWED_HOSTS', ''))
ALLOWED_HOSTS = env_allowed_hosts or DEFAULT_ALLOWED_HOSTS

# Filtrar valores vacíos
ALLOWED_HOSTS = [h for h in ALLOWED_HOSTS if h]


# =============================================================================
# CORS RESTRINGIDO
# =============================================================================
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    'https://search.liderman.net.pe',
]

CSRF_TRUSTED_ORIGINS = [
    'https://search.liderman.net.pe',
]

# Para que Django detecte HTTPS a través de Cloudflare/proxy
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True


# =============================================================================
# HSTS (HTTP Strict Transport Security)
# 🎓 LECCIÓN: Esto le dice al navegador "SIEMPRE usa HTTPS para este sitio"
# 
# max-age=31536000 = 1 año (tiempo que el navegador recordará)
# include_subdomains = También aplica a subdominios
# preload = Permite que Chrome, Firefox, etc. incluyan tu sitio en su lista
# =============================================================================
SECURE_HSTS_SECONDS = 31536000  # 1 año
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True


# =============================================================================
# COOKIES SEGURAS
# 🎓 LECCIÓN: Cada atributo protege contra un tipo diferente de ataque
# =============================================================================

# SECURE: Solo enviar cookies por HTTPS (nunca por HTTP plano)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_NAME = '__Host-sessionid'
CSRF_COOKIE_NAME = '__Host-csrftoken'

# HTTPONLY: JavaScript no puede leer estas cookies (previene XSS)
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False

# SAMESITE: El navegador solo envía cookies si la petición viene del mismo sitio
# 'Strict' = Máxima seguridad (puede romper algunos flujos de login con OAuth)
# 'Lax' = Buen balance (cookies se envían en navegación normal, no en peticiones cross-site)
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'


# =============================================================================
# HEADERS DE SEGURIDAD ADICIONALES
# 🎓 LECCIÓN: Django activa estos automáticamente cuando configuras los settings
# =============================================================================

# X-Content-Type-Options: nosniff
# Evita que el navegador "adivine" el tipo de archivo (MIME sniffing)
SECURE_CONTENT_TYPE_NOSNIFF = True

# X-Frame-Options: DENY (protección máxima contra clickjacking)
X_FRAME_OPTIONS = 'DENY'

# Redirige HTTP a HTTPS automáticamente
# NOTA: Si usas Cloudflare con "Always Use HTTPS", esto es redundante pero no daña
SECURE_SSL_REDIRECT = True


# =============================================================================
# WHITENOISE (producción)
# =============================================================================
WHITENOISE_AUTOREFRESH = False  # No buscar archivos nuevos constantemente
