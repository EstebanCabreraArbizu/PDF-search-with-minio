# Guía de Despliegue en VPS

Esta guía detalla los pasos para actualizar tu entorno de VPS de Flask a Django.

## 1. Actualizar Script de Bash (`run`)

Tu script actual apunta a la carpeta de Flask. Debes actualizarlo para apuntar al proyecto Django.

### Configuración Nueva (Opción Recomendada: Gunicorn)
Gunicorn es un servidor de producción robusto. `runserver` es solo para desarrollo (es lento e inseguro).

```bash
RUN_DIR="/home/coder/scripts/run"

SERVICE_WWW_NAME="LiderSearch"
# CAMBIO IMPORTANTE: Apuntar a la raíz (donde está manage.py)
SERVICE_WWW_DIR="/home/coder/PDF-search-with-minio/" 
# COMANDO PRODUCCIÓN:
SERVICE_WWW_COMMAND="gunicorn pdf_search_project.wsgi:application --bind 0.0.0.0:5000 --workers 3"
SERVICE_WWW_PORT="5000" 
```

### ¿Por qué Gunicorn?
1.  **Rendimiento:** Maneja múltiples usuarios a la vez (multi-workers). `runserver` se traba si dos personas entran al mismo tiempo.
2.  **Seguridad:** Está diseñado para estar expuesto a internet.
3.  **Estabilidad:** Si falla un proceso, lo reinicia automáticamente.

## 2. Pasos de Actualización en VPS

El uso de Gunicorn **NO** afecta el uso de comandos de Django. Sigues teniendo acceso total a `manage.py`.

Ejecuta estos pasos en orden:

```bash
# 1. Activar entorno virtual
source venv/bin/activate

# 2. Instalar dependencias (incluyendo gunicorn)
pip install -r requirements.txt

# 3. Aplicar migraciones de base de datos
# ESTO FUNCIONA INDEPENDIENTE DEL SERVIDOR WEB
python manage.py makemigrations documents
python manage.py migrate

# 4. (Opcional) Recolectar archivos estáticos para nginx
python manage.py collectstatic --noinput
```

Una vez hechos estos pasos, tu script `run` levantará el servidor Gunicorn con la base de datos ya actualizada.

## 3. Verificar Variables de Entorno (.env)

Asegúrate de que tu `.env` en el VPS tenga las nuevas variables explicadas en la `S3_CONNECTION_GUIDE.md`:

```bash
MINIO_USE_SSL=False
MINIO_REGION=us-east-1 (o vacío si usas MinIO local simple)
```
