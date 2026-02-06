# Guía de Conexión: MinIO (VPS) vs AWS S3

Este documento explica las diferencias clave y cómo configurar el sistema para ambos entornos.

## 1. Variables de Entorno (.env)

Agrega estas nuevas variables a tu archivo `.env`:

```bash
# === Opción A: MinIO en VPS (Actual) ===
MINIO_ENDPOINT=192.168.1.100:9000  # O tu dominio: minio.midominio.com
MINIO_ACCESS_KEY=admin
MINIO_SECRET_KEY=password123
MINIO_BUCKET=planillas-pdfs
MINIO_USE_SSL=False                # True si tienes HTTPS configurado (Certbot/Nginx)
# MINIO_REGION=                    # Generalmente no es necesario para MinIO standalone

# === Opción B: AWS S3 (Futuro) ===
# MINIO_ENDPOINT=s3.amazonaws.com  # O s3.us-east-1.amazonaws.com
# MINIO_ACCESS_KEY=TU_AWS_ACCESS_KEY
# MINIO_SECRET_KEY=TU_AWS_SECRET_KEY
# MINIO_BUCKET=nombre-unico-del-bucket
# MINIO_USE_SSL=True               # AWS S3 SIEMPRE requiere SSL (True)
# MINIO_REGION=us-east-1           # REQUERIDO para AWS S3
```

## 2. Diferencias Técnicas

### A. MinIO en VPS (Self-Hosted)
Es lo que estás usando ahora. Tú controlas el servidor.

*   **Endpoint:** Es la IP o dominio de TU servidor.
*   **SSL (Secure):**
    *   **False:** Si conectas por IP directa (ej: `http://192.168.1.5:9000`).
    *   **True:** Si has configurado un dominio con certificado SSL (ej: `https://minio.miempresa.com`). **Recomendado para producción**.
*   **Región:** MinIO por defecto usa `us-east-1`, pero no suele validar esto estrictamente en modo standalone.

### B. AWS S3 (Cloud)
Al migrar a la nube de Amazon.

*   **Endpoint:**
    *   Global: `s3.amazonaws.com`
    *   Regional: `s3.{region}.amazonaws.com` (ej: `s3.us-east-1.amazonaws.com`).
*   **SSL (Secure):** **Siempre `True`**. AWS rechaza conexiones inseguras por defecto en buckets modernos.
*   **Región:** **Obligatorio**. Debes especificar la región donde creaste el bucket (ej: `us-east-1`, `sa-east-1` para Sao Paulo). Si no coincide, obtendrás errores de redirección 301 o 400 Bad Request.
*   **Costos:** S3 cobra por almacenamiento Y por solicitudes (GET/LIST).
    *   *Nota:* Nuestra lógica de sincronización (`sync_index`) es eficiente, pero un `list_objects(recursive=True)` completo puede ser costoso si tienes millones de archivos. MinIO en VPS no tiene este costo por solicitud.

## 3. Cambios en el Código (Ya realizados)

Se actualizó `settings.py` y `utils.py` para leer `MINIO_USE_SSL` y `MINIO_REGION`.

### Verificación

Cuando cambies a S3 o actives HTTPS en tu VPS:

1.  Actualiza `.env`.
2.  Reinicia el servidor Django.
3.  Revisa los logs. Si ves errores de `SSL: CERTIFICATE_VERIFY_FAILED`, asegúrate que tu servidor tenga los certificados raíz de CA actualizados (en VPS Linux: `update-ca-certificates`).
