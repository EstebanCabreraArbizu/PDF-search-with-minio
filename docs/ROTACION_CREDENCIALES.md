# 🔐 Guía de Rotación de Credenciales

> **Objetivo**: Cambiar periódicamente las contraseñas y claves de acceso para minimizar el riesgo de compromiso.

---

## 🎓 ¿Por qué rotar credenciales?

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ESCENARIO DE ATAQUE                                   │
│                                                                          │
│  Día 1: Atacante obtiene acceso a una contraseña antigua                │
│  Día 30: Atacante intenta usarla                                        │
│                                                                          │
│  SIN ROTACIÓN: ✅ Contraseña sigue válida → Acceso exitoso              │
│  CON ROTACIÓN: ❌ Contraseña ya cambió → Acceso denegado                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 📋 Calendario de Rotación Recomendado

| Credencial | Frecuencia | Responsable |
|------------|------------|-------------|
| DJANGO_SECRET_KEY | 6 meses | DevOps |
| POSTGRES_PASSWORD | 3 meses | DBA/DevOps |
| MINIO_SECRET_KEY | 3 meses | DevOps |
| JWT tokens | Auto-expiran | Sistema |

---

## 🔄 Procedimientos de Rotación

### 1. Rotar DJANGO_SECRET_KEY

```bash
# Generar nueva clave
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# Actualizar en el VPS (variable de entorno)
export DJANGO_SECRET_KEY='nueva-clave-aqui'

# Reiniciar Django
docker compose restart django-app
```

> ⚠️ **Efecto**: Invalida todas las sesiones activas. Los usuarios deberán hacer login nuevamente.

---

### 2. Rotar POSTGRES_PASSWORD

```bash
# 1. Conectarse a PostgreSQL como superusuario
docker exec -it postgres-db psql -U admin -d pdf_search

# 2. Cambiar contraseña del usuario app_django
ALTER USER app_django WITH PASSWORD 'nueva-contraseña-segura';

# 3. Salir de psql
\q

# 4. Actualizar variable de entorno
export POSTGRES_PASSWORD='nueva-contraseña-segura'

# 5. Reiniciar Django
docker compose restart django-app
```

---

### 3. Rotar MINIO_SECRET_KEY

```bash
# 1. Acceder a MinIO Console (puerto 9001)
# 2. Ir a Settings > Access Keys
# 3. Crear nueva Access Key
# 4. Actualizar variables de entorno:
export MINIO_ACCESS_KEY='nuevo-access-key'
export MINIO_SECRET_KEY='nuevo-secret-key'

# 5. Reiniciar Django
docker compose restart django-app
```

---

## 📝 Registro de Rotaciones

Mantén un log de cuándo se rotaron las credenciales:

| Fecha | Credencial | Rotado Por | Notas |
|-------|------------|------------|-------|
| 2026-02-06 | Inicial | Setup | Primera configuración |
| | | | |

---

## 🔐 Generadores de Contraseñas Seguras

```bash
# Opción 1: OpenSSL (recomendado)
openssl rand -base64 32

# Opción 2: Python
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Opción 3: /dev/urandom (Linux)
head -c 32 /dev/urandom | base64
```
