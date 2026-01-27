# 🔍 Sistema de Búsqueda Inteligente de Planillas con MinIO

Sistema web completo para gestión, búsqueda y descarga masiva de documentos PDF (planillas de pago, boletas, etc.) usando almacenamiento MinIO, indexación PostgreSQL y extracción inteligente de texto con OCR.

---

## 📋 Tabla de Contenidos

- [Características Principales](#-características-principales)
- [Tecnologías Utilizadas](#-tecnologías-utilizadas)
- [Arquitectura del Sistema](#-arquitectura-del-sistema)
- [Instalación y Configuración](#-instalación-y-configuración)
- [Uso de la Aplicación](#-uso-de-la-aplicación)
- [Guía de Migración Django](docs/GUIA_MIGRACION_DJANGO.md)
- [Manual de Usuario](docs/MANUAL_USUARIO.md)
- [Reporte de Costos AWS](docs/COSTOS_AWS.md)
- [API Endpoints](#-api-endpoints)
- [Estructura del Proyecto](#-estructura-del-proyecto)
- [Optimizaciones Implementadas](#-optimizaciones-implementadas)

---

## 🚀 Características Principales

### 1. **Búsqueda Inteligente de Documentos**
- **Búsqueda Simple**: Por código de empleado/DNI con filtros adicionales
- **Búsqueda Masiva**: Procesa hasta 500 códigos simultáneamente
- **Filtros Avanzados**:
  - Año (2019 - presente)
  - Mes (Enero - Diciembre)
  - Banco (BBVA, BCP, Interbank, GENERAL)
  - Razón Social (RESGUARDO, ALARMAS, FACILITIES, LIDERMAN SERVICIOS)
  - Tipo de Documento (autocompletado inteligente: CUADRE, VACACIONES, REINTEGROS, etc.)
- **Velocidad**: ~20-50ms por búsqueda usando índice PostgreSQL

### 2. **Fusión de PDFs (Merge)**
- Combina múltiples resultados de búsqueda en un solo PDF
- Límite: 100 archivos por fusión
- Descarga automática del documento combinado
- Registro de auditoría de fusiones

### 3. **Gestión de Archivos (Admin)**
- **Explorador de Carpetas Visual**:
  - Navegación por carpetas usando PostgreSQL (instantáneo)
  - Breadcrumb de navegación
  - Creación de subcarpetas
  - Vista del contador de PDFs por carpeta
- **Carga Masiva de PDFs**:
  - Drag & Drop
  - Selección múltiple
  - Indexación automática con OCR (Tesseract)
  - Extracción de metadatos del path y contenido
- **Filtros y Búsqueda**:
  - Búsqueda por nombre de archivo
  - Filtros por año, mes, banco, razón social, tipo documento
  - Paginación (100 archivos por página)
  - Vista instantánea de 9,500+ archivos
- **Eliminación de Archivos**:
  - Borrado de MinIO y PostgreSQL
  - Confirmación de seguridad

### 4. **Indexación y OCR**
- **Indexación Completa**: Procesa todos los PDFs del bucket
- **Sincronización Rápida**: Solo indexa archivos nuevos o modificados
- **Extracción Inteligente**:
  - OCR con Tesseract para texto escaneado
  - Extracción nativa con PyMuPDF para PDFs digitales
  - Detección automática de códigos de empleado (4-10 dígitos)
  - Parsing de metadatos desde la ruta del archivo

### 5. **Sistema de Autenticación**
- Login con JWT (JSON Web Tokens)
- Roles: `admin` y `user`
- Usuarios:
  - **Admin**: `admin` / `admin123` (acceso completo)
  - **Usuario**: `ecabrera` / `password123` (solo búsqueda y descarga)
- Sesiones persistentes
- Protección de endpoints con decoradores de Django y DRF (`IsAuthenticated`)
- **Panel de Administración**: Acceso a `/admin` para gestión de base de datos

### 6. **Auditoría y Registro**
- Log de descargas (usuario, archivo, IP, timestamp)
- Log de fusiones de PDFs
- Registro de indexaciones y sincronizaciones

---

## 🛠️ Tecnologías Utilizadas

### Backend
- **Django 5.0.1** - Framework web robusto
- **Django REST Framework (DRF)** - Para la API REST
- **PostgreSQL 17** - Base de datos relacional
- **MinIO** - Almacenamiento de objetos S3-compatible
- **SimpleJWT** - Autenticación JWT para Django
- **PyMuPDF (fitz)** - Extracción y fusión de PDFs
- **Pytesseract** - OCR para texto escaneado
- **pdf2image** - Conversión PDF a imagen para OCR
- **Whitenoise** - Servido de archivos estáticos

### Frontend
- **Bootstrap 5.3.0** - Framework CSS
- **Vanilla JavaScript** - Sin frameworks adicionales
- **HTML5 Datalist** - Autocompletado nativo de tipo documento

### Infraestructura
- **Docker & Docker Compose** - Contenedorización
- **Gunicorn** - Servidor WSGI de producción

---

## 🏗️ Arquitectura del Sistema

```mermaid
graph TD
    subgraph "Nivel Usuario"
        Client["💻 Cliente (Browser)"]
    end

    subgraph "Nivel Aplicación (AWS EC2 / App Runner)"
        subgraph "Contenedor Django"
            API["🔥 Django API (Gunicorn)"]
            Auth["🔐 Auth (SimpleJWT)"]
            OCR["📄 Motor OCR (Tesseract/FitZ)"]
        end
    end

    subgraph "Nivel Persistencia"
        Postgres[("🐘 PostgreSQL 17 (RDS)")]
        MinIO[("📦 MinIO / AWS S3")]
    end

    Client -- "HTTP/JWT" --> API
    API -- "Django ORM" --> Postgres
    API -- "Stream PDF" --> MinIO
    API -- "Valida" --> Auth
    API -- "Procesa" --> OCR
```

### Flujo de Indexación
```mermaid
sequenceDiagram
    participant AD as Administrador
    participant DJ as Django API
    participant MN as MinIO (S3)
    participant DB as PostgreSQL
    participant OCR as Motor OCR

    AD->>DJ: Solicitar Sincronización / Reindex
    DJ->>MN: Listar objetos en Bucket
    loop Para cada archivo nuevo/modificado
        DJ->>MN: Descargar PDF temporal
        DJ->>OCR: Extraer texto y códigos de empleado
        OCR-->>DJ: Datos extraídos
        DJ->>DB: Guardar metadatos e índices
    end
    DJ-->>AD: Reporte de finalización
```

### Flujo de Búsqueda
```mermaid
graph LR
    U["👤 Usuario"] --> S["🔍 Input: Código + Filtros"]
    S --> API["🔥 Django API"]
    API --> DB["🐘 Query Django ORM (icontains)"]
    DB --> R["📄 Lista de Resultados"]
    R --> D["⬇️ Opción: Descarga / Fusionar"]
    D --> S3["📦 Stream desde MinIO/S3"]
    S3 --> PDF["📥 PDF Final"]
```

---

## 📦 Instalación y Configuración

### Prerrequisitos
- Docker Desktop
- Docker Compose
- Git

### 1. Clonar el Repositorio
```bash
git clone https://github.com/EstebanCabreraArbizu/PDF-search-with-minio.git
cd PDF-search-with-minio
```

### 2. Configurar Variables de Entorno
Editar `docker-compose.yaml` si es necesario:
```yaml
environment:
  - DATABASE_URL=postgresql://postgres:postgres@postgres:5432/pdf_search
  - MINIO_ENDPOINT=minio:9000
  - MINIO_ACCESS_KEY=minioadmin
  - MINIO_SECRET_KEY=minioadmin
  - SECRET_KEY=tu-clave-secreta-aqui
```

### 3. Levantar los Servicios
```bash
docker compose up -d
```

Esto iniciará:
- **Django App** → `http://localhost:8000`
- **MinIO Console** → `http://localhost:9001` (admin/password123)
- **PostgreSQL** → `localhost:5432`

### 4. Preparar la Base de Datos
```bash
docker exec -it django-api python manage.py migrate
docker exec -it django-api python manage.py createsuperuser
```

### 5. Acceder a la Aplicación
```
URL: http://localhost:8000

Credenciales Admin:
- Las creadas con createsuperuser o el admin por defecto configurado.
```

### 5. Indexar PDFs (Primera Vez)
Como admin:
1. Ir a pestaña **"🔧 Gestión de Archivos"**
2. Clic en **"🔄 Sincronizar Índice"** o **"📋 Re-indexar Todo"**
3. Esperar a que termine el proceso

---

## 📚 Documentación Adicional

- 📄 **[Guía de Migración Flask a Django](docs/GUIA_MIGRACION_DJANGO.md)**: Detalle del proceso de refactorización.
- 🛠️ **[Detalles Técnicos de Migración](docs/MIGRATION_DETAILS.md)**: Cambios en el modelo y lógica de sincronización.
- 📄 **[Manual de Usuario](docs/MANUAL_USUARIO.md)**: Guía detallada para usuarios y administradores.
- 💰 **[Reporte de Costos AWS](docs/COSTOS_AWS.md)**: Estimación de costos para despliegue en la nube.

---

## 💡 Uso de la Aplicación

### 🔍 Búsqueda Simple
1. Ingresar código de empleado/DNI (obligatorio)
2. Seleccionar filtros opcionales (año, mes, banco, etc.)
3. Escribir tipo de documento (ej: "CUADRE") para autocompletado
4. Clic en **"🔍 Buscar"**
5. Ver resultados con metadata
6. Descargar individualmente o fusionar todos

### 📋 Búsqueda Masiva
1. Ir a sub-pestaña **"📋 Búsqueda Masiva"**
2. Pegar códigos (uno por línea o separados por comas):
   ```
   12345678
   87654321
   11223344
   ```
3. Aplicar filtros opcionales
4. Clic en **"🔍 Buscar Masivamente"**
5. Ver resumen:
   - Códigos encontrados (verde)
   - Códigos no encontrados (rojo)
6. Opción de fusionar todos los resultados en un PDF

### 📂 Gestión de Archivos (Solo Admin)

#### Subir Archivos
1. Clic en **"📂 Explorar"** para seleccionar carpeta destino
2. Navegar por carpetas existentes o crear nueva
3. Arrastrar PDFs o clic en zona de carga
4. Clic en **"📤 Subir e Indexar"**
5. Los archivos se indexan automáticamente con OCR

#### Explorador de Carpetas
- **🏠 Raíz**: Ver carpetas principales
- **Clic en carpeta**: Navegar dentro
- **⬆️ Subir**: Ir a carpeta padre
- **🔄 Refrescar**: Actualizar lista
- **✓ Usar**: Seleccionar carpeta para subida
- **➕ Crear subcarpeta**: Nueva carpeta dentro de la actual

#### Buscar y Filtrar Archivos
1. Usar filtros: nombre, año, mes, banco, razón social, tipo
2. Paginación automática (100 por página)
3. Vista de 9,500+ archivos instantánea
4. Clic en **"🗑️"** para eliminar archivo

#### Reindexar
- **🔄 Sincronizar Índice**: Solo archivos nuevos (~1-5 seg)
- **📋 Re-indexar Todo**: Todos los PDFs (~5-30 min según cantidad)

---

## 🔌 API Endpoints

### Autenticación

#### `POST /api/token/`
Obtener tokens de acceso (JWT)
```json
Request:
{
  "username": "admin",
  "password": "password123"
}

Response:
{
  "refresh": "eyJ0eXAiOiJKV1...",
  "access": "eyJ0eXAiOiJKV1..."
}
```

#### `POST /api/token/refresh/`
Refrescar el token de acceso vencido.

### Búsqueda

#### `POST /api/search`
Búsqueda simple por código de empleado
```json
Request:
{
  "codigo_empleado": "12345678",
  "año": "2025",
  "mes": "01",
  "banco": "BCP",
  "razon_social": "RESGUARDO",
  "tipo_documento": "CUADRE"
}

Response:
{
  "total": 3,
  "results": [
    {
      "id": 1,
      "filename": "Planillas 2025/RESGUARDO/BCP/01 ENERO/CUADRE.pdf",
      "metadata": {
        "año": "2025",
        "mes": "01",
        "banco": "BCP",
        "razon_social": "RESGUARDO",
        "tipo_documento": "CUADRE"
      },
      "size_bytes": 245678,
      "size_kb": 239.9,
      "download_url": "/api/download/Planillas%202025/..."
    }
  ],
  "time_ms": 25.3
}
```

#### `POST /api/search/bulk`
Búsqueda masiva por múltiples códigos
```json
Request:
{
  "codigos": "12345678, 87654321, 11223344",
  "año": "2025",
  "mes": "01"
}

Response:
{
  "total": 45,
  "codigos_buscados": ["12345678", "87654321", "11223344"],
  "codigos_encontrados": ["12345678", "87654321"],
  "codigos_no_encontrados": ["11223344"],
  "results": [...],
  "can_merge": true
}
```

#### `POST /api/merge-pdfs`
Fusionar múltiples PDFs en uno solo
```json
Request:
{
  "paths": [
    "Planillas 2025/archivo1.pdf",
    "Planillas 2025/archivo2.pdf"
  ],
  "output_name": "documentos_combinados"
}

Response: Binary PDF file
Headers:
  Content-Type: application/pdf
  X-Files-Merged: 2
  X-Merge-Errors: 0
```

### Gestión de Archivos

#### `GET /api/files/list`
Listar archivos indexados con paginación
```
GET /api/files/list?page=1&per_page=100&año=2025&tipo_documento=CUADRE

Response:
{
  "files": [...],
  "total": 9562,
  "page": 1,
  "per_page": 100,
  "total_pages": 96
}
```

#### `GET /api/folders`
Listar carpetas disponibles
```
GET /api/folders?parent=Planillas%202025/

Response:
{
  "folders": [
    {
      "name": "RESGUARDO",
      "path": "Planillas 2025/RESGUARDO/",
      "count": 150
    }
  ],
  "current_path": "Planillas 2025/",
  "breadcrumb": [...],
  "time_ms": 15.2
}
```

#### `POST /api/files/upload`
Subir uno o varios PDFs
```
Multipart form-data:
  files[]: [archivo1.pdf, archivo2.pdf]
  folder: "Planillas 2025/"

Response:
{
  "success": true,
  "uploaded": [
    {
      "filename": "archivo1.pdf",
      "path": "Planillas 2025/archivo1.pdf",
      "indexed": true
    }
  ],
  "total_uploaded": 2
}
```

#### `DELETE /api/files/delete`
Eliminar archivo
```json
Request:
{
  "path": "Planillas 2025/archivo.pdf"
}

Response:
{
  "success": true,
  "message": "Archivo eliminado"
}
```

### Indexación

#### `POST /api/reindex` (Admin only)
Re-indexar todos los PDFs
```json
Response:
{
  "success": true,
  "total_processed": 9562,
  "new_files": 50,
  "updated_files": 100,
  "errors": 0,
  "time_seconds": 1234.5
}
```

#### `POST /api/index/sync` (Admin only)
Sincronización rápida (usa hashes MD5 para detectar cambios/movimientos)
```json
Response:
{
  "new_files": 5,
  "removed_orphans": 2,
  "time_seconds": 2.3
}
```

### Filtros

#### `GET /api/filter-options`
Obtener opciones para filtros
```json
Response:
{
  "años": ["2025", "2024", "2023"],
  "razones_sociales": ["RESGUARDO", "ALARMAS", "FACILITIES"],
  "bancos": ["BBVA", "BCP", "INTERBANK"],
  "tipos_documento": ["CUADRE", "VACACIONES", "REINTEGROS"],
  "meses": [
    {"value": "01", "label": "Enero"},
    {"value": "02", "label": "Febrero"}
  ]
}
```

---

## 📁 Estructura del Proyecto

```
PDF-search-with-minio/
├── pdf_search_project/      # Configuración central de Django
├── documents/               # Aplicación principal (Lógica, Modelos, Vistas)
│   ├── static/              # Archivos estáticos
│   ├── templates/           # Plantillas HTML
│   ├── migrations/          # Historial de base de datos
│   └── utils.py             # Funciones auxiliares (OCR, S3)
├── flask_project/ [LEGACY]  # Antigua versión en Flask (No funcional, histórica)
├── docs/                    # Documentación PDF y Markdown
├── docker-compose.yaml      # Orquestación de servicios (Django, Postgres, MinIO)
├── Dockerfile               # Imagen Docker para el proyecto Django
├── manage.py                # Utilidad de administración de Django
└── requirements.txt         # Dependencias de Python renovadas
```

### Modelos de Base de Datos

#### `CustomUser` (Capa de Django Auth)
```python
- id: Integer (PK)
- username: String UNIQUE
- password: PasswordHash
- full_name: String
- is_staff: Boolean (Define rol admin)
- is_active: Boolean
```

#### `PDFIndex`
```python
- id: Integer (PK)
- minio_object_name: String(500) UNIQUE INDEX
- razon_social: String(150) INDEX
- banco: String(100) INDEX
- mes: String(2) INDEX
- año: String(4) INDEX
- tipo_documento: String(300)
- size_bytes: BigInteger
- codigos_empleado: Text (CSV)
- md5_hash: String(32) INDEX (Nuevo para sync inteligente)
- indexed_at: DateTime
- last_modified: DateTime
- is_indexed: Boolean
```

#### `DownloadLog`
```python
- id: Integer (PK)
- user_id: Integer (FK → User)
- filename: String(500)
- downloaded_at: DateTime
- ip_address: String(50)
```

---

## ⚡ Optimizaciones Implementadas

### 1. **Índice PostgreSQL en lugar de MinIO**
- **Antes**: Listar 9,500 archivos tomaba 5-10 segundos
- **Ahora**: ~20-50ms usando consultas SQL indexadas
- **Mejora**: 100-200x más rápido

### 2. **Búsqueda Masiva con OR en SQL**
- **Antes**: 156 consultas separadas (una por código)
- **Ahora**: 1 consulta con `OR` de todos los códigos
- **Mejora**: 150x más rápido, sin perder códigos

### 3. **Explorador de Carpetas con PostgreSQL**
- **Antes**: Listar carpetas consultaba MinIO (lento)
- **Ahora**: Extrae carpetas del campo `minio_object_name`
- **Mejora**: Instantáneo (~10-30ms)

### 4. Búsqueda Parcial de Tipo Documento
- Usa `icontains` en Django QuerySet
- Encuentra variantes: CUADRE, CUADRE 2025, PRE-CUADRE, etc.
- Autocompletado con datalist HTML5

### 5. **Extracción OCR Inteligente**
- Detecta si el PDF tiene texto nativo o es escaneo
- Solo usa Tesseract cuando es necesario
- Reduce tiempo de indexación en ~60%

### 6. **Paginación Eficiente**
- 100 registros por página (configurable)
- Consultas SQL con `LIMIT` y `OFFSET`
- No carga todos los datos en memoria

---

## 🔐 Seguridad

- SimpleJWT con expiración configurable
- Contraseñas hasheadas nativamente por Django
- Validación de inputs con Serializers de DRF
- Protección contra inyección SQL (Django ORM)
- Middleware de Seguridad: CSP, X-Frame-Options, HSTS
- Separación de roles integrada (Staff vs Regular User)

---

## 📊 Casos de Uso

### Caso 1: Búsqueda de Boleta de Pago
```
Usuario: ecabrera
Acción: Buscar su boleta de enero 2025
1. Login con ecabrera/password123
2. Ingresar código: 12345678
3. Filtros: Año=2025, Mes=Enero
4. Descargar PDF
```

### Caso 2: Descarga Masiva de Planillas
```
Usuario: ecabrera
Acción: Descargar todas las boletas de un área para un mes
1. Búsqueda Masiva con 200 códigos
2. Filtro: Mes=Marzo, Razón Social=RESGUARDO
3. Fusionar todos en 1 PDF
4. Descargar documento combinado
```

### Caso 3: Carga de Nuevas Planillas
```
Usuario: admin
Acción: Subir planillas del mes actual
1. Ir a Gestión de Archivos
2. Explorar carpetas → Planillas 2025
3. Crear subcarpeta "FEBRERO"
4. Arrastrar 500 PDFs
5. Subir e indexar (automático con OCR)
```

---

## 🐛 Solución de Problemas

### PDFs no se encuentran en búsqueda
- Verificar que estén indexados: `POST /api/index/sync`
- Re-indexar si es necesario: `POST /api/reindex`

### Búsqueda muy lenta
- Revisar logs de Django: `docker compose logs django-app`

### Error al fusionar PDFs
- Verificar límite de 100 archivos
- Comprobar que los paths existan en MinIO

### No puedo subir archivos
- Verificar rol de usuario (debe ser admin)
- Comprobar permisos de MinIO

---

## 📝 Licencia

Este proyecto es de uso interno. Todos los derechos reservados.

---

## 👥 Autores

- **Esteban Cabrera Arbizu** - Desarrollo completo del sistema
- Repositorio: https://github.com/EstebanCabreraArbizu/PDF-search-with-minio

---

## 📞 Soporte

Para problemas o sugerencias, abrir un issue en GitHub o contactar al equipo de desarrollo.

---

**Versión**: 1.0.0  
**Última actualización**: Diciembre 2025
