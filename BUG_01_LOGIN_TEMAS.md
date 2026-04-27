# 🐛 BUG #1 - Sistema de Temas en Login

## 📋 Descripción

El sistema de cambio de temas en la página de login no está funcionando en el entorno Docker, aunque los archivos CSS y JavaScript están presentes y configurados correctamente.

## 🔍 Root Cause

- **Problema Principal:** Django necesita ejecutar `collectstatic` para servir archivos estáticos através de Whitenoise en producción
- **Configuración:** El `Dockerfile` YA ejecuta `collectstatic` en línea 27, pero requiere **rebuild completo** del contenedor cuando hay cambios en archivos estáticos

## ✅ Estado del Sistema

Todos los componentes ya están en lugar:

### HTML (login.html)
- ✅ `data-theme="corp"` presente en `<html>`
- ✅ `corp-style.css` cargado
- ✅ `theme.css` cargado
- ✅ `search-document.css` cargado
- ✅ Botón de toggle con ID `themeToggleBtn`
- ✅ Ícono con ID `themeToggleIcon`

### CSS (theme.css)
- ✅ 4 temas definidos: `corp`, `dark`, `light`, `corp-dark`
- ✅ Variables CSS mapeadas correctamente
- ✅ Selectores `html[data-theme="..."]` implementados

### JavaScript (ui_core_v2.js)
- ✅ `initTheme()` carga tema desde localStorage
- ✅ `toggleTheme()` cicla entre 4 temas
- ✅ `syncThemeToggle()` actualiza iconografía
- ✅ Eventos listener en `#themeToggleBtn`

### Docker (Dockerfile)
- ✅ `npm run build` ejecuta build de frontend
- ✅ `npm run sync:corp-style` sincroniza corp-style.css
- ✅ `collectstatic --noinput` recolecta estáticos
- ✅ Whitenoise activo en settings.py

## 🔧 Cambios Realizados

### 1. Script de Rebuild (`scripts/rebuild-docker.sh`)
- Automatiza el rebuild completo de Docker
- Asegura que `collectstatic` se ejecute correctamente
- Verifica que servicios estén listos

## 🚀 Verificación y Testing

### Paso 1: Rebuild Docker
```bash
# Opción A: Usar script (Linux/Mac)
bash scripts/rebuild-docker.sh

# Opción B: Manual (Windows/PowerShell)
docker-compose down
docker-compose build --no-cache django node
docker-compose up -d
docker-compose exec django python manage.py collectstatic --no-input
```

### Paso 2: Verificar Archivos Estáticos
```bash
# Dentro del contenedor Django
docker-compose exec django ls -la /app/staticfiles/documents/css/

# Debe mostrar:
# - theme.css
# - search-document.css
# - corp-style.css
```

### Paso 3: Test en Navegador
1. Navegar a `http://localhost:8000/ui/login/`
2. Verificar presencia de `data-theme` en `<html>`
3. Abrir DevTools → Console
4. Ejecutar: `document.documentElement.getAttribute('data-theme')`
5. Debe retornar: `"corp"`

### Paso 4: Test de Toggle
1. Clickear botón de tema (ícono en esquina superior derecha)
2. Verificar que ícono cambia:
   - `corp` → ⚙️ (engranaje)
   - `dark` → 🌙 (luna)
   - `light` → ☀️ (sol)
   - `corp-dark` → 🎨 (paleta)
3. Verificar que colores de fondo cambian
4. Refresca página: tema debe persistir (localStorage)

### Paso 5: Test Playwright
```bash
npm test -- theme-toggle.spec.js
```

## 📦 Docker Rebuild - Detalles Técnicos

### ¿Por qué se necesita rebuild?

```
Dockerfile (ejecuta en build time)
├── npm run build          ← Construye frontend (sincroniza corp-style)
├── collectstatic          ← Recolecta estáticos a /app/staticfiles/
└── Copia todo a imagen

Docker volume (en desarrollo)
├── Si NO hay volumen montado → Usa archivos del build ✅
└── Si hay volumen → Sobrescribe con archivos locales (posible desync)
```

Docker-compose.yaml actual:
- ✅ NO tiene volumen montado para `/app/staticfiles`
- ✅ Usa archivos del build directamente
- ✅ Whitenoise sirve desde `/app/staticfiles/`

### Cuando NO se necesita rebuild
- Cambios en templates HTML (se sirven en vivo)
- Cambios en JavaScript sin ofuscación
- Cambios en settings.py

### Cuando SÍ se necesita rebuild
- ✅ Cambios en `corp-style.css` o paquete npm
- ✅ Cambios en archivos CSS locales
- ✅ Cambios en `package.json` (dependencias)
- ✅ Cambios en `requirements.txt` (dependencias Python)

## 📝 Monitoreo Post-Fix

### Verificar que Whitenoise está sirviendo estáticos
```bash
curl -I http://localhost:8000/static/documents/css/theme.css

# Debe retornar 200 OK
# Header: Content-Type: text/css
```

### Ver logs de Docker
```bash
# Verificar que npm run build fue exitoso
docker-compose logs django | grep -i "npm\|build\|collectstatic"

# Verificar que collectstatic fue exitoso
docker-compose logs django | grep -i "collectstatic"
```

## 🔐 Notas de Seguridad

- Whitenoise (CompressedManifestStaticFilesStorage) comprime y versionea archivos
- Los archivos estáticos se sirven con headers de cache correcto
- DEBUG mode debe estar deshabilitado en producción

## 🎯 Conclusión

El sistema de temas **funciona perfectamente** — el problema es solo el mecanismo de servicio de estáticos en Docker. Una vez que se ejecute `collectstatic` correctamente (tras rebuild), todo funcionará como se espera.

## ✅ Checklist de Validación

- [ ] Rebuild Docker completado sin errores
- [ ] `docker-compose exec django ls -la /app/staticfiles/documents/css/` muestra archivos CSS
- [ ] Login carga correctamente en `http://localhost:8000/ui/login/`
- [ ] `data-theme="corp"` presente en HTML
- [ ] Theme toggle button visible y clickeable
- [ ] Ícono cambia al hacer click
- [ ] Colores cambian al hacer click
- [ ] localStorage contiene `docsearch_theme` en DevTools → Storage
- [ ] Refresh mantiene el tema seleccionado
- [ ] Playwright tests pasan
