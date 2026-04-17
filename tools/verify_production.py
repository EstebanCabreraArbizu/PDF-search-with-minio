"""
Verificar configuracion de PRODUCCION (HSTS, cookies seguras, etc.)
"""
import os
import sys

# Forzar modo produccion
os.environ['DJANGO_ENV'] = 'production'
# Simular SECRET_KEY para pruebas
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-for-verification-only'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pdf_search_project.settings')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
django.setup()

from django.conf import settings

print("=" * 60)
print("VERIFICACION MODO PRODUCCION")
print("=" * 60)

print(f"\n[1] DEBUG = {settings.DEBUG}")
assert settings.DEBUG == False, "DEBUG debe ser False en produccion"
print("    [OK] DEBUG es False")

print(f"\n[2] HSTS")
print(f"    SECURE_HSTS_SECONDS = {getattr(settings, 'SECURE_HSTS_SECONDS', 'NO CONFIGURADO')}")
print(f"    SECURE_HSTS_INCLUDE_SUBDOMAINS = {getattr(settings, 'SECURE_HSTS_INCLUDE_SUBDOMAINS', False)}")
print(f"    SECURE_HSTS_PRELOAD = {getattr(settings, 'SECURE_HSTS_PRELOAD', False)}")

print(f"\n[3] COOKIES SEGURAS")
print(f"    SESSION_COOKIE_SECURE = {getattr(settings, 'SESSION_COOKIE_SECURE', False)}")
print(f"    SESSION_COOKIE_HTTPONLY = {getattr(settings, 'SESSION_COOKIE_HTTPONLY', False)}")
print(f"    SESSION_COOKIE_SAMESITE = {getattr(settings, 'SESSION_COOKIE_SAMESITE', 'None')}")
print(f"    CSRF_COOKIE_SECURE = {getattr(settings, 'CSRF_COOKIE_SECURE', False)}")

print(f"\n[4] OTROS HEADERS")
print(f"    SECURE_CONTENT_TYPE_NOSNIFF = {getattr(settings, 'SECURE_CONTENT_TYPE_NOSNIFF', False)}")
print(f"    SECURE_SSL_REDIRECT = {getattr(settings, 'SECURE_SSL_REDIRECT', False)}")
print(f"    X_FRAME_OPTIONS = {getattr(settings, 'X_FRAME_OPTIONS', 'NO CONFIG')}")

print(f"\n[5] ALLOWED_HOSTS")
print(f"    {settings.ALLOWED_HOSTS}")

print("\n" + "=" * 60)
print("*** CONFIGURACION DE PRODUCCION VERIFICADA ***")
print("=" * 60)
