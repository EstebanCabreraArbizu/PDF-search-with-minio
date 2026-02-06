"""
Script de Verificacion de Configuraciones de Seguridad

Ejecutar con: py tools/verify_security.py
"""
import os
import sys

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pdf_search_project.settings')

# Agregar el directorio raiz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
django.setup()

from django.conf import settings

def check_security_settings():
    print("=" * 60)
    print("VERIFICACION DE PROTOCOLOS DE SEGURIDAD")
    print("=" * 60)
    
    results = []
    
    # 1. Verificar modo (DEBUG)
    print(f"\n[1] MODO: {'DESARROLLO' if settings.DEBUG else 'PRODUCCION'}")
    print(f"    DEBUG = {settings.DEBUG}")
    
    # 2. Verificar Rate Limiting
    print("\n[2] RATE LIMITING (Proteccion DoS)")
    if 'DEFAULT_THROTTLE_CLASSES' in settings.REST_FRAMEWORK:
        print("    [OK] Throttle classes configuradas")
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        for scope, rate in rates.items():
            print(f"    - {scope}: {rate}")
        results.append(("Rate Limiting", True))
    else:
        print("    [FALTA] No hay throttle configurado")
        results.append(("Rate Limiting", False))
    
    # 3. Verificar Middleware de seguridad
    print("\n[3] MIDDLEWARE DE SEGURIDAD")
    middlewares_security = [
        ('SecurityMiddleware', 'django.middleware.security.SecurityMiddleware'),
        ('CSP', 'csp.middleware.CSPMiddleware'),
        ('Clickjacking', 'django.middleware.clickjacking.XFrameOptionsMiddleware'),
        ('Headers Custom', 'documents.middleware.SecurityHeadersMiddleware'),
    ]
    
    for name, middleware in middlewares_security:
        if middleware in settings.MIDDLEWARE:
            print(f"    [OK] {name}")
            results.append((name, True))
        else:
            print(f"    [FALTA] {name}")
            results.append((name, False))
    
    # 4. Verificar CSP
    print("\n[4] CONTENT SECURITY POLICY")
    if hasattr(settings, 'CONTENT_SECURITY_POLICY'):
        print("    [OK] CSP configurado")
        results.append(("CSP", True))
    else:
        print("    [FALTA] CSP no configurado")
        results.append(("CSP", False))
    
    # 5. Verificar Password Validators
    print("\n[5] VALIDADORES DE CONTRASENAS")
    validators = settings.AUTH_PASSWORD_VALIDATORS
    print(f"    {len(validators)} validadores configurados")
    for v in validators:
        name = v['NAME'].split('.')[-1]
        opts = v.get('OPTIONS', {})
        print(f"    - {name} {opts if opts else ''}")
    results.append(("Password Validators", len(validators) >= 4))
    
    # Resumen
    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)
    
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    
    for name, ok in results:
        status = "[OK]" if ok else "[X]"
        print(f"  {status} {name}")
    
    print(f"\nResultado: {passed}/{total} verificaciones pasadas")
    
    if passed == total:
        print("\n*** TODAS LAS VERIFICACIONES PASARON ***")
    else:
        print("\n*** HAY CONFIGURACIONES PENDIENTES ***")

if __name__ == '__main__':
    check_security_settings()
