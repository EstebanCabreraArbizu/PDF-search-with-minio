import os
import django
from django.conf import settings
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pdf_search_project.settings')
django.setup()

def check_static():
    print("🔍 Diagnosticando Estáticos...")
    
    base_dir = settings.BASE_DIR
    static_root = settings.STATIC_ROOT
    static_url = settings.STATIC_URL
    debug = settings.DEBUG
    
    print(f"   BASE_DIR: {base_dir}")
    print(f"   STATIC_ROOT: {static_root}")
    print(f"   STATIC_URL: {static_url}")
    print(f"   DEBUG: {debug}")
    print(f"   Middleware installed: {'whitenoise.middleware.WhiteNoiseMiddleware' in settings.MIDDLEWARE}")

    # Chequear si existe la carpeta root
    if not os.path.exists(static_root):
        print("❌ ERROR CRÍTICO: La carpeta STATIC_ROOT no existe.")
        print("   Debes ejecutar: python manage.py collectstatic --noinput")
        return

    # Chequear un archivo específico (admin/css/base.css)
    admin_css = Path(static_root) / 'admin' / 'css' / 'base.css'
    if admin_css.exists():
        print(f"✅ Archivo encontrado: {admin_css}")
        print(f"   Tamaño: {admin_css.stat().st_size} bytes")
    else:
        print(f"❌ ERROR: No se encuentra 'admin/css/base.css' en {static_root}")
        print("   Esto significa que collectstatic no corrió bien o se borró la carpeta.")
    
    # Chequear permisos (básico)
    try:
        with open(admin_css, 'r') as f:
            pass
        print("✅ Permisos de lectura OK.")
    except Exception as e:
        print(f"❌ Error de permisos: {e}")

if __name__ == "__main__":
    check_static()
