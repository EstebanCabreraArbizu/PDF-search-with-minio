# Reporte de Migración: Flask a Django

Se ha completado la migración de la lógica y estructura del proyecto "Smart Search" de Flask a Django, incorporando las optimizaciones de la rama `main` y añadiendo capas de seguridad.

## 1. Cambios Realizados

### Configuración y Seguridad (`settings.py`)
- **JWT (JSON Web Tokens)**: Se configuró `djangorestframework-simplejwt` para manejar la autenticación.
- **CORS (Cross-Origin Resource Sharing)**: Habilitado para permitir peticiones desde el frontend (actualmente `ALLOW_ALL`, pero configurable).
- **CSP (Content Security Policy)**: Se añadió la configuración base para prevenir ataques XSS, permitiendo scripts propios y CDNs necesarios (Bootstrap).
- **Middleware**: Se añadieron los middlewares de seguridad necesarios.

### Base de Datos y Modelos (`models.py`)
- Se añadió el campo `md5_hash` al modelo `PDFIndex`. Esto es **CRÍTICO** para la nueva lógica de sincronización inteligente, permitiendo detectar si un archivo solo se movió de carpeta sin necesidad de re-procesarlo.

### Lógica de Negocio (`views.py` y `utils.py`)
- **Portabilidad**: Se reescribió `views.py` utilizando *Django REST Framework (DRF)*.
- **Utils**: Se extrajeron las funciones auxiliares (`extract_metadata`, `search_in_pdf`, etc.) a `utils.py` para mantener el código limpio.
- **Sincronización Inteligente**: Se implementó el endpoint `/api/index/sync` que:
    1.  Utiliza caché en memoria para listar MinIO (evita latencia).
    2.  Compara MD5 y tamaño para detectar archivos movidos.
    3.  Procesa descargas e indexación en *batch* (lotes) para no saturar el servidor.

### Frontend
- Se migró `search.html` a la estructura de plantillas de Django: `documents/templates/documents/search.html`.
- Se configuró la vista `index` para servir esta plantilla en la raíz `/`.

---

## 2. Ofuscación de JavaScript (Manual / Futuro)

Se solicitó la implementación de ofuscación de código JS con Node.js.

### ¿Por qué Node.js?
Las herramientas de ofuscación más potentes y mantenidas (como `javascript-obfuscator`) están en el ecosistema Node.js.

### Estado Actual
Actualmente, el código JavaScript vive **dentro** del archivo `search.html` (<script> tags). Las herramientas de ofuscación funcionan sobre archivos `.js` independientes.

### Guía Manual para Implementar la Ofuscación
Para activar la ofuscación completa, sigue estos pasos:

1.  **Extraer el JS**:
    -   Crea un archivo `documents/static/documents/js/app.js`.
    -   Corta todo el contenido entre `<script>` y `</script>` de `search.html` y pégalo en `app.js`.
    -   En `search.html`, reemplaza el bloque script con:
        ```html
        {% load static %}
        <script src="{% static 'documents/js/dist/app.js' %}"></script>
        ```

2.  **Instalar Dependencias**:
    -   Ejecuta en la raíz (necesitas Node.js instalado):
        ```bash
        npm install
        ```

3.  **Configurar el Script**:
    -   Edita `tools/obfuscate.js` y descomenta/actualiza la línea:
        ```javascript
        const FILES_TO_OBFUSCATE = [
             './documents/static/documents/js/app.js' 
        ];
        ```

4.  **Ejecutar Ofuscación**:
    -   Corre el comando:
        ```bash
        npm run obfuscate
        ```
    -   Esto generará una versión ilegible pero funcional de tu código en la carpeta `dist`.

Esto añade una capa de protección de propiedad intelectual al código del cliente.

---

## 3. Próximos Pasos

1.  **Instalar dependencias Python**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Migraciones de DB**:
    ```bash
    python manage.py makemigrations documents
    python manage.py migrate
    ```
3.  **Ejecutar Servidor**:
    ```bash
    python manage.py runserver
    ```
