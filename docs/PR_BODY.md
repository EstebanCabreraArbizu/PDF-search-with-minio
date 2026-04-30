## Cambios
- [x] Skeleton loaders inmediatos en búsqueda
- [x] Badge compacto para códigos de empleado (siempre contador → popover)
- [x] Stats cards unificadas en Constancias/Seguros/T-Registro
- [x] Periodos dinámicos y botón "Limpiar" funcional
- [x] Descarga ZIP de resultados (PDFs planos, sin estructura de carpetas)
- [x] Flujo guiado de autoorganización con fallback manual
- [x] Suite de tests e2e (14 Playwright + 4 TestSprite)

## Testing
- **Playwright local**: 15 passed ✅ (`npx playwright test`)
- **TestSprite MCP**: 1/4 passed (3 blocked por dev server single-thread — requiere Gunicorn para 100%)
- Spec file: `tests/e2e/search-ux-interactivity.spec.js`

## Notas de Despliegue
- Requiere 1 migración menor (`python manage.py migrate` — campo `correction_reason` en Document)
- Requiere `docker compose build django-app` para incluir cambios en `docrepo/`, `ui_core_v2.js`, y CSS
- No requiere cambios en variables de entorno
- Compatible con Gunicorn existente (3 workers, timeout 300)
