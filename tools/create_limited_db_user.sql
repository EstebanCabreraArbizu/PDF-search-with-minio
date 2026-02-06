-- ═══════════════════════════════════════════════════════════════════════════
-- SCRIPT: Creación de Usuario PostgreSQL con Privilegio Mínimo
-- ═══════════════════════════════════════════════════════════════════════════
-- 
-- 🎓 LECCIÓN: ¿Qué es el Principio de Privilegio Mínimo?
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- Es un principio de seguridad que dice:
-- "Cada componente debe tener SOLO los permisos estrictamente necesarios"
-- 
-- ❌ PROBLEMA ACTUAL:
-- Tu aplicación Django se conecta como 'admin' con permisos de superusuario.
-- Si un atacante compromete la app, podría:
--   - DROP DATABASE (borrar toda la base de datos)
--   - CREATE USER (crear usuarios maliciosos)
--   - Acceder a otras bases de datos
-- 
-- ✅ SOLUCIÓN:
-- Crear un usuario 'app_django' que SOLO pueda:
--   - SELECT, INSERT, UPDATE, DELETE en las tablas de la app
--   - Usar secuencias (para IDs automáticos)
--   - NADA MÁS (no puede CREATE TABLE, DROP, ni acceder al sistema)
-- ═══════════════════════════════════════════════════════════════════════════

-- ┌─────────────────────────────────────────────────────────────────────────┐
-- │ PASO 1: Conectarse como superusuario (admin)                           │
-- │ Ejecuta este script conectándote al servidor PostgreSQL como admin     │
-- │ Ejemplo: psql -h localhost -U admin -d pdf_search                      │
-- └─────────────────────────────────────────────────────────────────────────┘

-- ┌─────────────────────────────────────────────────────────────────────────┐
-- │ PASO 2: Crear el usuario con contraseña segura                         │
-- └─────────────────────────────────────────────────────────────────────────┘

-- ⚠️ IMPORTANTE: Reemplaza 'TU_CONTRASEÑA_SEGURA_AQUI' con una contraseña
-- generada de forma segura. Puedes usar:
-- openssl rand -base64 32

CREATE USER app_django WITH PASSWORD 'TU_CONTRASEÑA_SEGURA_AQUI';

-- 🎓 LECCIÓN: ¿Por qué NO usamos SUPERUSER ni CREATEDB?
-- Queremos que este usuario NO pueda hacer nada fuera de lo normal.

-- ┌─────────────────────────────────────────────────────────────────────────┐
-- │ PASO 3: Dar permisos de conexión a la base de datos                    │
-- └─────────────────────────────────────────────────────────────────────────┘

GRANT CONNECT ON DATABASE pdf_search TO app_django;

-- 🎓 LECCIÓN: CONNECT solo permite conectarse, no hacer nada más.

-- ┌─────────────────────────────────────────────────────────────────────────┐
-- │ PASO 4: Dar permisos en el schema public                               │
-- └─────────────────────────────────────────────────────────────────────────┘

GRANT USAGE ON SCHEMA public TO app_django;

-- 🎓 LECCIÓN: USAGE permite usar el schema, pero no crear objetos en él.

-- ┌─────────────────────────────────────────────────────────────────────────┐
-- │ PASO 5: Dar permisos CRUD en TODAS las tablas existentes               │
-- └─────────────────────────────────────────────────────────────────────────┘

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_django;

-- 🎓 LECCIÓN: Estos 4 permisos son los básicos de CRUD:
--   - SELECT: Leer datos
--   - INSERT: Crear registros nuevos
--   - UPDATE: Modificar registros existentes
--   - DELETE: Eliminar registros
-- 
-- NO incluimos:
--   - CREATE: No puede crear tablas nuevas
--   - DROP: No puede eliminar tablas
--   - ALTER: No puede modificar estructura de tablas
--   - TRUNCATE: No puede vaciar tablas de golpe

-- ┌─────────────────────────────────────────────────────────────────────────┐
-- │ PASO 6: Dar permisos en secuencias (para IDs automáticos)              │
-- └─────────────────────────────────────────────────────────────────────────┘

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_django;

-- 🎓 LECCIÓN: Las secuencias generan los IDs automáticos (SERIAL, BIGSERIAL).
-- Sin este permiso, Django no podría crear registros nuevos.

-- ┌─────────────────────────────────────────────────────────────────────────┐
-- │ PASO 7: Configurar permisos para FUTURAS tablas (migraciones)          │
-- └─────────────────────────────────────────────────────────────────────────┘

-- Cuando ejecutes migraciones de Django, se crean tablas nuevas.
-- Estas líneas aseguran que app_django tenga permisos automáticamente.

ALTER DEFAULT PRIVILEGES IN SCHEMA public 
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_django;

ALTER DEFAULT PRIVILEGES IN SCHEMA public 
GRANT USAGE, SELECT ON SEQUENCES TO app_django;

-- 🎓 LECCIÓN: DEFAULT PRIVILEGES aplica a objetos creados EN EL FUTURO
-- por el usuario que ejecuta este comando (admin).

-- ┌─────────────────────────────────────────────────────────────────────────┐
-- │ PASO 8: Verificar permisos                                             │
-- └─────────────────────────────────────────────────────────────────────────┘

-- Ejecuta esto para ver los permisos del usuario:
-- \du app_django

-- Y esto para ver permisos en tablas:
-- \dp

-- ═══════════════════════════════════════════════════════════════════════════
-- ✅ DESPUÉS DE EJECUTAR ESTE SCRIPT:
-- 
-- 1. Actualiza docker-compose.yaml:
--    - POSTGRES_USER=app_django
--    - POSTGRES_PASSWORD=<la contraseña que usaste arriba>
-- 
-- 2. O mejor aún, actualiza las variables de entorno en tu VPS:
--    export POSTGRES_USER=app_django
--    export POSTGRES_PASSWORD=<contraseña>
-- 
-- 3. Reinicia Django:
--    docker compose restart django-app
-- ═══════════════════════════════════════════════════════════════════════════
