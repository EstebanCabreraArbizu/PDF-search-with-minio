# Guía de Ejecución: UX Interactivity Plan

> **Prerequisito**: Leer `implementation_plan.md` (artifact de Antigravity) antes de ejecutar.

---

## 1. Configuración de Modelos Gratuitos por Servicio

### Cline (VS Code Extension)

```
Settings → Cline → API Provider → Ollama
  Base URL: http://localhost:11434
  Model ID: deepseek-v3.1:671b-cloud
```

Modelos a usar en Cline:
- **Fases 1, 3**: `deepseek-v3.1:671b-cloud` (principal)
- **Fallback**: `deepseek-v3.2:cloud` o `qwen3.5:397b-cloud`

### Kilocode (VS Code Extension)

```
Settings → Kilocode → API Configuration → Ollama
  Base URL: http://localhost:11434
  Model: qwen3.5:397b-cloud
```

Modelos a usar en Kilocode:
- **Fases 0, 2**: `qwen3.5:397b-cloud` (principal)
- **Fallback**: `deepseek-v3.1:671b-cloud`

### OpenCode (Terminal)

```bash
# En .opencode.yaml o variable de entorno:
export OPENCODE_PROVIDER=ollama
export OPENCODE_MODEL=gpt-oss:120b-cloud
# Alternativamente:
opencode --provider ollama --model gpt-oss:120b-cloud
```

Modelos a usar en OpenCode:
- **Fase 4**: `gpt-oss:120b-cloud`
- **Fase 5**: `gemma4:31b-cloud`

### Codex (OpenAI CLI)

```bash
# Codex usa GPT-5.5 directamente (trial)
codex --model gpt-5.5
# Solo para Fase 6
```

### OpenRouter (Fallback si Ollama cae)

```
# En Cline/Kilocode: API Provider → OpenRouter
# API Key: tu key de OpenRouter
# Model: deepseek/deepseek-v3 (free tier)
# O: qwen/qwen-2.5-coder-32b-instruct (free tier)
```

---

## 2. Modos de Agente: Cuándo Usar Cada Uno

### Cline — 4 Modos

| Modo | Cuándo | En este plan |
|------|--------|-------------|
| **Code** | Escribir/editar código con aprobación paso a paso | Fases 1, 3 (edición principal) |
| **Plan** | Analizar antes de editar, genera plan primero | NO usar — ya tenemos plan |
| **Debug** | Cuando algo falla post-ejecución | Si Fase 1 o 3 rompe algo |
| **Architect** | Diseñar estructura sin tocar código | NO usar — ya diseñado |

→ **Para este plan: usar siempre modo `Code`**. Si falla, cambiar a `Debug`.

### Kilocode — 6 Modos

| Modo | Cuándo | En este plan |
|------|--------|-------------|
| **Code** | Escribir/editar código | Fases 0, 2 (edición principal) |
| **Architect** | Diseñar sin implementar | NO usar |
| **Ask** | Preguntas sobre el codebase | Si necesitas entender algo antes de editar |
| **Debug** | Diagnosticar errores | Si Fase 0 o 2 falla |
| **Orchestrator** | Dividir tarea compleja en subtareas | NO usar (fases ya son atómicas) |
| **Boomerang** | Delegar a otro modo y volver | NO usar |

→ **Para este plan: usar siempre modo `Code`**. Si falla, `Debug`. Si no entiendes algo, `Ask`.

### OpenCode — Modo único

Terminal interactiva. Ejecutar comando y pegar prompt.

### Codex — Modo único

Sandbox autónomo. Un solo prompt completo → ejecuta → devuelve resultado.

---

## 3. Ejecución Paso a Paso

### Paso 0: Preparar Rama

```powershell
# En terminal (ya estás en fix/02-buscador-temas)
git checkout -b feature/ux-interactivity-improvements
```

---

### BLOQUE A — Gratis, Sin Riesgo

#### Fase 0: Componentes Compartidos
**Agente**: Kilocode → Modo `Code`
**Modelo**: `qwen3.5:397b-cloud`

Prompt para Kilocode:
```
Add the following utility functions to window.DocSearchCore in
c:\Proyecto - búsqueda inteligente con minio\documents\static\documents\js\ui_core_v2.js

Do NOT modify any existing functions. Only ADD new ones.

1. renderCodesBadge(codes) - Always returns a badge HTML string showing
   "👤 N códigos" with a click handler that opens a popover with the full
   list and a "Copiar todos" button. Never show codes inline.

2. renderSkeletonRows(count) - Returns HTML string of `count` table rows
   with .skeleton-row class and shimmer animation placeholder cells.

3. renderErrorState(message) - Returns HTML for an error card with icon,
   message text, and a "Reintentar" button.

4. renderMetaSummary(metadata, domain) - Returns HTML showing domain-specific
   metadata fields as small badges/chips.

Add corresponding CSS classes to:
c:\Proyecto - búsqueda inteligente con minio\documents\static\documents\css\search-document.css

Classes needed: .skeleton-row, .shimmer, .codes-badge, .codes-popover,
.error-state, .meta-chip

Files to modify (ONLY these two):
- documents/static/documents/js/ui_core_v2.js
- documents/static/documents/css/search-document.css
```

**Después**: Verificar en consola del navegador que `DocSearchCore.renderCodesBadge` existe.

```powershell
git add -A; git commit -m "feat(ui): add shared component helpers to DocSearchCore"
```

---

#### Fase 4: Periodos Dinámicos + Limpiar
**Agente**: OpenCode
**Modelo**: `gpt-oss:120b-cloud`

Prompt para OpenCode:
```
Fix two issues in the search modules. Files to modify:

1. documents/templates/documents/search_seguros.html - Remove hardcoded
   <option> tags from #periodoSelect (lines 58-62) and #tipoSelect options
   except the first default option. Keep only <option value="">- Todos -</option>.

2. documents/templates/documents/search_tregistro.html - Remove hardcoded
   <option> tags from #periodoSelect (lines 49-54). Keep only
   <option value="">Todos</option>.

3. In search_constancias_v2.js, search_seguros_v2.js, search_tregistro_v2.js:
   Add event listener for #limpiarBtn that:
   - Resets all select elements to value=""
   - Clears #dniInput and #dniMasivo
   - Hides results (#stateTable → hidden, #stateEmpty → visible)
   - Resets #resultCount to "0 documentos encontrados"

Do NOT modify any other logic. Only add the limpiarBtn listener and remove
hardcoded options.
```

```powershell
git add -A; git commit -m "fix(ux): dynamic periods and clear button functionality"
```

---

#### Fase 5: Auditoría Paths
**Agente**: OpenCode
**Modelo**: `gemma4:31b-cloud`

Prompt para OpenCode:
```
Create a Django management command at:
documents/management/commands/audit_storage_paths.py

The command should:
1. Query all StorageObject.object_key values
2. Classify each into: matches "Planillas 20XX/...", matches "20XX/..." (no Planillas prefix), or other pattern
3. Print a summary report with counts per category
4. For paths matching "20XX/..." without "Planillas" prefix:
   - Rename the object in MinIO using copy+delete (minio_client from documents.utils)
   - Update StorageObject.object_key in database
   - New key: "Planillas " + original key
5. Add --dry-run flag (default True) that only reports without renaming
6. Add --execute flag to actually perform renames

Use documents.utils.minio_client and django.conf.settings.MINIO_BUCKET.
```

```powershell
git add -A; git commit -m "chore(tools): add storage path audit and rename command"
```

---

#### Fase 2: Badge DNI Compacto
**Agente**: Kilocode → Modo `Code`
**Modelo**: `qwen3.5:397b-cloud`

Prompt para Kilocode:
```
Replace the employee_codes rendering in all 3 search modules to use the
renderCodesBadge() helper created in Fase 0.

1. In search_constancias_v2.js line 64: replace
   doc.employee_codes.join(', ') with DocSearchCore.renderCodesBadge(doc.employee_codes)

2. In search_seguros_v2.js: add a "Códigos" cell in each result row using
   DocSearchCore.renderCodesBadge(doc.employee_codes)

3. In search_tregistro_v2.js: add a "Códigos" cell in each result row using
   DocSearchCore.renderCodesBadge(doc.employee_codes)

4. Update the <thead> in search_seguros.html and search_tregistro.html to
   include a "Códigos" column header.

Do NOT change any other rendering logic. Only replace/add the codes cell.
```

```powershell
git add -A; git commit -m "feat(ux): compact employee codes badge with popover"
```

---

### BLOQUE B — Gratis, Complejidad Media

#### Fase 1: Skeleton Loaders
**Agente**: Cline → Modo `Code`
**Modelo**: `deepseek-v3.1:671b-cloud`

Prompt para Cline:
```
Modify the search flow in ui_core_v2.js to show skeleton loaders immediately
when a search is submitted, instead of the current delayed spinner.

Current behavior (broken):
- User clicks search → spinner shows AFTER fetch starts → data replaces spinner

Desired behavior:
- User clicks search → skeleton rows show IMMEDIATELY (before fetch) →
  data replaces skeleton → on error, show error state

Changes needed:

1. In ui_core_v2.js search() function: before the fetch call, call
   renderSkeletonRows(5) and inject into #tableBody. Show #stateTable,
   hide #stateEmpty and #stateLoading.

2. On fetch success: replace skeleton with real rows (existing logic).

3. On fetch error: call renderErrorState(errorMessage) and inject into
   the results area. Add a "Reintentar" button that re-triggers the search.

4. Disable the submit button during search (add disabled attribute, restore after).

5. In search-document.css: add shimmer animation keyframes for .skeleton-row

Files: ui_core_v2.js, search-document.css
Do NOT modify the 3 search module files.
```

```powershell
git add -A; git commit -m "feat(ux): add skeleton loaders and error states"
```

---

#### Fase 3: Unificar Stats + Columnas
**Agente**: Cline → Modo `Code`
**Modelo**: `deepseek-v3.1:671b-cloud`

Prompt para Cline:
```
Unify the visual structure across all 3 search modules. Reference how
search_seguros_v2.js and search_tregistro_v2.js already implement renderStats().

1. search_constancias_v2.js: Add renderStats() function that populates
   #statsConstancias with stat cards showing:
   - Total documentos encontrados
   - Desglose por banco (count per unique metadata.banco)
   - Desglose por tipo de constancia (count per unique metadata.tipo_planilla)
   Use the same stat-card HTML pattern as search_seguros_v2.js.

2. Normalize column order in all 3 modules to match:
   Documento | Empresa | Tipo | Detalle | Códigos | Periodo | Acciones

   - Constancias "Tipo" = metadata.tipo_planilla, "Detalle" = metadata.banco
   - Seguros "Tipo" = metadata.tipo_seguro/subtipo, "Detalle" = personas detectadas
   - TRegistro "Tipo" = metadata.tipo_movimiento (as badge), "Detalle" = DNI trabajador

3. Update the <thead> in all 3 HTML templates to match the new column order.

4. Normalize "Documento" cell in all 3: show filename (last segment of path)
   + size_kb in a small muted span.

Files: search_constancias_v2.js, search_seguros_v2.js, search_tregistro_v2.js,
search_constancias.html, search_seguros.html, search_tregistro.html
```

```powershell
git add -A; git commit -m "feat(ux): unify column structure and stats across modules"
```

---

### BLOQUE C — Gasto Pagado (Solo Fase 6)

#### Fase 6: Modal Fallback + Migración
**Agente**: Codex (OpenAI CLI)
**Modelo**: `gpt-5.5` (trial)

```bash
codex "
In the Django project at c:\Proyecto - búsqueda inteligente con minio:

1. Add a CharField 'correction_reason' (max_length=500, blank=True) to
   the Document model in docrepo/models.py. Create and apply the migration.

2. In the file management JS (search_files_v2.js or equivalent), when the
   upload classify-preview API returns status 'REQUIRES_CONFIRMATION':
   - Show a modal dialog with:
     a) Suggested folder path
     b) Visual confidence bar (percentage from API response)
     c) Highlighted missing/uncertain fields
     d) Dropdown to select alternative folder
     e) Text input for correction reason
     f) Confirm and Cancel buttons
   - On confirm: proceed with upload using selected path, save correction_reason

3. When status is 'DUPLICATE': show a warning banner with link to existing doc.

4. Add CSS for the modal in search-document.css: .classify-modal, .confidence-bar

Create the migration, update the model, JS, and CSS.
"
```

```powershell
git add -A; git commit -m "feat(ux): guided fallback for document auto-classification"
```

---

#### Fase 7: Testing Integral
**Agente**: Antigravity (esta sesión o nueva)
**Modelo**: `deepseek-v3.1:671b-cloud` (o Gemini 2.5 Pro si es necesario)

Acciones en Antigravity:
1. Crear `tests/e2e/search-ux.spec.js` con Playwright specs
2. Ejecutar TestSprite: bootstrap → test plan → execute
3. Validar ZIP download: PDFs planos sin estructura de carpetas
4. Generar walkthrough con screenshots

```powershell
git add -A; git commit -m "test(e2e): add UX interactivity test suite"
```

---

## 4. Post-Ejecución

```powershell
# Verificar todo
npx playwright test

# Crear PR
gh pr create --base main --title "feat: improve document search interactivity and UX consistency" --body-file docs/PR_BODY.md
```

---

## 5. Troubleshooting Rápido

| Problema | Solución |
|----------|----------|
| Ollama cloud timeout | Cambiar a OpenRouter free tier en Cline/Kilocode settings |
| DeepSeek genera código roto | Cambiar a `deepseek-v3.2:cloud` y reintentar |
| Cline no encuentra Ollama | Verificar `ollama serve` corriendo, URL `http://localhost:11434` |
| Kilocode no muestra modelo | Settings → Provider → Ollama → Refresh Models |
| Fase rompe funcionalidad | `git stash` → abrir Cline en modo `Debug` → pegar error |
| Copilot rate limit | Esperar reset o cambiar a Ollama via Cline/Kilocode |
