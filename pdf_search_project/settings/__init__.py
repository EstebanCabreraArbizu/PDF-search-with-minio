"""
Selector de configuración de Django

LECCION: Como selecciona Django que configuracion usar?
Este archivo lee la variable de entorno DJANGO_ENV y decide:
- Si DJANGO_ENV = 'production' -> usa production.py
- Cualquier otro valor (o si no existe) -> usa development.py

Ejemplo de uso:
- En tu VPS: export DJANGO_ENV=production
- En tu PC local: no necesitas hacer nada (usa development por defecto)
"""

import os

# Lee la variable de entorno DJANGO_ENV
# Si no existe, usa 'development' como valor por defecto
environment = os.getenv('DJANGO_ENV', 'development')

if environment == 'production':
    from .production import *
    print("[PRODUCCION] Django iniciando en modo PRODUCCION")
else:
    from .development import *
    print("[DESARROLLO] Django iniciando en modo DESARROLLO")
