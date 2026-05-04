/* =====================================================================
 * search_files_v2.js — Módulo de Gestión de Archivos
 * Página: /ui/files/
 * ===================================================================== */


let rutaActiva = [];
const API = {
  me: '/api/me',
  logout: '/api/auth/logout/',
  loginUi: '/ui/login/',
  stats: '/api/index/stats',
  filesList: '/api/files/list',
  filesDelete: '/api/files/delete',
  filesUpload: '/api/files/upload',
  classifyPreview: '/api/files/classify-preview',
  createFolder: '/api/files/create-folder',
  sync: '/api/index/sync',
  mergePdfs: '/api/merge-pdfs',
  filterOptions: '/api/filter-options',
  foldersList: '/api/folders/list'
};

const SHARED = window.DocSearchShared;

const TOKEN_KEY = SHARED?.STORAGE_KEYS?.AUTH_TOKEN || 'docsearch_v2_access_token';
const REFRESH_TOKEN_KEY = SHARED?.STORAGE_KEYS?.REFRESH_TOKEN || 'docsearch_v2_refresh_token';
const USER_KEY = SHARED?.STORAGE_KEYS?.USER_DATA || 'docsearch_v2_user';

/* ── Estado global ──────────────────────────────────────────────────── */
let authToken = null;
let currentUser = null;
let isAdmin = false;
let filesPage = 1;
const FILES_PER_PAGE = 50;
let filesTotal = 0;
let filesTotalPages = 1;
let searchDebounce = null;
let selectedPaths = new Set();
let pendingUploadMap = new Map(); // filename → { file, previewItem }
let syncRunning = false;
let syncShouldStop = false;
let uploadMode = 'auto';
let selectedManualFolder = '';

/* ── Helpers de autenticación ───────────────────────────────────────── */
function getAuthHeaders(includeContentType = true) {
  return SHARED.getAuthHeaders(includeContentType);
}

function safeText(v) {
  return String(v || '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function updateURLFromPath() {
  const fullPath = rutaActiva.join('/');
  const hash = fullPath ? `#files/${encodeURI(fullPath)}` : '#files';
  history.pushState({ ruta: [...rutaActiva] }, '', hash);
}

function formatPathLabel(rawPath) {
  return window.DocSearchCore ? window.DocSearchCore.formatPathLabel(rawPath) : rawPath;
}

function restorePathFromHash() {
  const hash = window.location.hash || '';
  const match = hash.match(/^#files\/(.+)$/);
  if (match) {
    try {
      const decoded = decodeURIComponent(match[1]);
      rutaActiva = decoded.split('/').filter(Boolean);
    } catch (_) {
      rutaActiva = [];
    }
  } else {
    rutaActiva = [];
  }
}

function entrarACarpeta(nombreCarpeta) {
  const nombreLimpio = nombreCarpeta.replace(/\/+$/, '');
  if (!nombreLimpio) return;
  rutaActiva.push(nombreLimpio);
  updateURLFromPath();
  loadFiles(1);
}

function salirDeCarpeta(){
  if (rutaActiva.length === 0) return;
  rutaActiva.pop();
  updateURLFromPath();
  loadFiles(1);
}

function renderBreadcrumbs() {
  const container = document.getElementById('filesBreadcrumb');
  if (!container) return;
  const ol = container.querySelector('.breadcrumb-list');
  if (!ol) return;

  let html = `<li class="breadcrumb-item">
    <a href="#" onclick="window._filesGoHome(); return false;" class="breadcrumb-link">
      <i class="ti ti-home"></i> Inicio
    </a>
  </li>`;

  for (let idx = 0; idx < rutaActiva.length; idx++) {
    const folder = rutaActiva[idx];
    const isLast = idx === rutaActiva.length - 1;
    const label = formatPathLabel(folder);
    if (isLast) {
      html += `<li class="breadcrumb-item active" aria-current="page" title="${safeText(label)}">${safeText(label)}</li>`;
    } else {
      html += `<li class="breadcrumb-item">
        <a href="#" onclick="window._filesGoTo(${idx}); return false;" class="breadcrumb-link" title="${safeText(label)}">${safeText(label)}</a>
      </li>`;
    }
  }

  ol.innerHTML = html;
}

window._filesGoHome = function() {
  rutaActiva = [];
  updateURLFromPath();
  loadFiles(1);
};

window._filesGoTo = function(index) {
  rutaActiva = rutaActiva.slice(0, index + 1);
  updateURLFromPath();
  loadFiles(1);
};

function setAuthState(connected) { SHARED.setAuthState(connected); }
function renderSidebarUser() { SHARED.renderSidebarUser({ userKey: USER_KEY }); }
function redirectToLogin() { SHARED.redirectToLogin(API.loginUi, { includeHash: true }); }

function clearSession() {
  authToken = null;
  SHARED.clearSession({ tokenKey: TOKEN_KEY, refreshTokenKey: REFRESH_TOKEN_KEY, userKey: USER_KEY, updateUi: false });
  setAuthState(false);
  renderSidebarUser();
}

async function fetchJson(url, options = {}) { return SHARED.fetchJson(url, options); }
async function validateToken(token) { return SHARED.validateToken(API.me, token); }

async function restoreSession() {
  const stored = SHARED.getAuthToken();
  if (!stored) return false;
  
  const isValid = await validateToken(stored);
  if (!isValid) { clearSession(); return false; }
  
  authToken = stored;
  setAuthState(true);
  renderSidebarUser();

  try {
    const raw = localStorage.getItem(USER_KEY);
    if (raw) {
      currentUser = JSON.parse(raw);
      isAdmin = currentUser?.can_manage_files === true || currentUser?.role === 'admin' || currentUser?.is_staff === true;
    }
  } catch (_) { }

  return true;
}

async function logout() {
  await SHARED.logoutAndRedirect({
    apiUrl: API.logout,
    authToken,
    tokenKey: TOKEN_KEY,
    refreshTokenKey: REFRESH_TOKEN_KEY,
    userKey: USER_KEY,
    loginUiUrl: API.loginUi,
    includeHash: true
  });
  authToken = null;
}

/* ── Utilidades ─────────────────────────────────────────────────────── */
function show(el) { if (el) el.classList.remove('hidden'); }
function hide(el) { if (el) el.classList.add('hidden'); }

function formatSize(bytes) {
  if (!bytes) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

function formatDate(isoStr) {
  if (!isoStr) return '—';
  try { return new Date(isoStr).toLocaleDateString('es-PE', { day: '2-digit', month: 'short', year: 'numeric' }); }
  catch (_) { return isoStr.slice(0, 10); }
}

function addLogEntry(container, msg, type = 'info') {
  if (!container) return;
  const entry = document.createElement('div');
  entry.className = `sync-log-entry ${type}`;
  const now = new Date().toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  entry.innerHTML = `<span class="sync-log-time">${now}</span><span>${safeText(msg)}</span>`;
  container.appendChild(entry);
  container.scrollTop = container.scrollHeight;
}

/* ── STATS ──────────────────────────────────────────────────────────── */
async function loadStats() {
  try {
    const data = await fetchJson(API.stats, { headers: getAuthHeaders() });
    const total = data.total_indexed ?? 0;
    const sizeGb = data.total_size_gb ?? 0;
    const indexed = data.indexed_successfully ?? 0;
    const errors = data.with_errors ?? 0;

    document.getElementById('statTotalValue').textContent = total.toLocaleString('es-PE');
    document.getElementById('statSizeValue').textContent = `${sizeGb} GB`;
    document.getElementById('statOkValue').textContent = indexed.toLocaleString('es-PE');
    document.getElementById('statErrValue').textContent = errors.toLocaleString('es-PE');

    const hint = data.last_indexed
      ? `Último: ${formatDate(data.last_indexed)}`
      : 'Sin registros';
    document.getElementById('statTotalHint').textContent = hint;
  } catch (e) {
    console.warn('Error cargando stats:', e);
  }
}

/* ── FILTROS ────────────────────────────────────────────────────────── */
async function loadFilterOptions() {
  try {
    const data = await fetchJson(API.filterOptions, { headers: getAuthHeaders() });
    const yearSel = document.getElementById('filesYearFilter');
    const razonSel = document.getElementById('filesRazonFilter');

    const years = (data.years || data.años || []).sort((a, b) => b - a);
    for (const y of years) {
      const opt = document.createElement('option');
      opt.value = y;
      opt.textContent = y;
      yearSel.appendChild(opt);
    }

    const razones = (data.razones_sociales || data.companies || []).sort();
    for (const r of razones) {
      const opt = document.createElement('option');
      opt.value = r;
      opt.textContent = r;
      razonSel.appendChild(opt);
    }

  } catch (e) {
    console.warn('Error cargando filtros:', e);
  }
}

function getActiveFilters() {
  return {
    search: document.getElementById('filesSearchInput')?.value.trim() || '',
    año: document.getElementById('filesYearFilter')?.value || '',
    mes: document.getElementById('filesMonthFilter')?.value || '',
    razon_social: document.getElementById('filesRazonFilter')?.value || '',
  };
}

/* ── TABLA DE ARCHIVOS ──────────────────────────────────────────────── */
async function loadFiles(page = 1) {
  console.log("🚀 Iniciando loadFiles para la página:", page);
  filesPage = page;
  
  const folderPrefix = rutaActiva.length > 0 ? rutaActiva.join('/') + '/' : '';
  const filters = getActiveFilters();
  const params = new URLSearchParams({
    page,
    per_page: FILES_PER_PAGE,
    folder: folderPrefix,
    ...filters
  });
  
  for (const [k, v] of [...params.entries()]) { if (!v) params.delete(k); }

  const loadingEl = document.getElementById('filesStateLoading');
  const emptyEl = document.getElementById('filesStateEmpty');
  const tableEl = document.getElementById('filesStateTable');
  const pagEl = document.getElementById('filesPagination');

  // 1. APAGAMOS TODO POR DEFECTO PARA LIMPIAR LA PANTALLA
  hide(emptyEl); 
  hide(tableEl); 
  hide(pagEl);
  show(loadingEl);

  try {
    const [filesData, foldersData] = await Promise.all([
      fetchJson(`${API.filesList}?${params}`, { headers: getAuthHeaders() }),
      fetchJson(`${API.foldersList}?${params}`, { headers: getAuthHeaders() })
    ]);
    
    hide(loadingEl);

    filesTotal = filesData.total ?? 0;
    filesTotalPages = filesData.total_pages ?? 1;

    const safeFiles = Array.isArray(filesData.files) ? filesData.files : [];
    const safeFolders = Array.isArray(foldersData.folders) ? foldersData.folders : [];

    console.log(`📦 PDFs recibidos: ${safeFiles.length}`);
    console.log(`📁 Carpetas recibidas: ${safeFolders.length}`);

    // 2. LA CONDICIÓN DE HIERRO: Solo es "vacío" si AMBOS son cero
    if (safeFiles.length === 0 && safeFolders.length === 0) {
      console.warn("⚠️ Todo está vacío. Mostrando pantalla de 'Sin archivos'.");
      show(emptyEl);
      return;
    }

    console.log("✅ Hay datos. Ordenando carpetas arriba...");
    const combinedData = [...safeFolders, ...safeFiles];
    
    combinedData.sort((a, b) => {
      const aIsFolder = a.is_folder === true || (!a.download_url && a.path && a.path.endsWith('/'));
      const bIsFolder = b.is_folder === true || (!b.download_url && b.path && b.path.endsWith('/'));
      
      if (aIsFolder && !bIsFolder) return -1;
      if (!aIsFolder && bIsFolder) return 1;
      return 0;
    });

    console.log(`🎨 Dibujando tabla con ${combinedData.length} filas.`);
    renderFilesTable(combinedData);
    updatePagination(filesData);
    renderBreadcrumbs();
    
    // 3. ENCENDEMOS LA TABLA AL FINAL
    show(tableEl);
    show(pagEl);
    
  } catch (e) {
    hide(loadingEl);
    show(emptyEl);
    console.error('❌ Error fatal en loadFiles:', e);
    // Mostrar feedback en el UI si es posible
    const emptyTitle = emptyEl.querySelector('h3');
    if (emptyTitle) emptyTitle.textContent = "Error al cargar datos";
    const emptyMsg = emptyEl.querySelector('p');
    if (emptyMsg) emptyMsg.textContent = e.message || "No se pudo conectar con el servidor.";
  }
}

function renderFilesTable(files) {
  const tbody = document.getElementById('filesTableBody');
  tbody.innerHTML = '';
  selectedPaths.clear();
  updateBatchBar();

  if (rutaActiva.length > 0) {
    const trBack = document.createElement('tr');
    trBack.style.cursor = 'pointer';
    trBack.style.backgroundColor = 'var(--bg-surface-secondary, #f8f9fa)'; // Fondo sutil
    
    trBack.innerHTML = `
      <td></td>
      <td class="files-filename-cell" colspan="2">
        <i class="ti ti-arrow-back-up" style="color: #6c757d; font-size: 1.3rem; margin-right: 8px;"></i>
        <span style="font-weight: 700; color: #495057;">.. / Volver al nivel anterior</span>
      </td>
      <td colspan="6"></td>
    `;
    trBack.addEventListener('click', salirDeCarpeta);
    tbody.appendChild(trBack);
  }

  files.forEach(file => {
    const tr = document.createElement('tr');
    tr.dataset.path = file.path;

    // Detectamos si es carpeta
    const isFolder = file.is_folder === true || (!file.download_url && file.path && file.path.endsWith('/'));

    if (isFolder) {
      // 📂 DIBUJAMOS LA CARPETA
      tr.style.cursor = 'pointer';
      tr.classList.add('folder-row');

      tr.innerHTML = `
        <td></td>
        <td class="files-filename-cell">
          <i class="ti ti-folder" style="color: #f6c23e; font-size: 1.3rem; margin-right: 8px;"></i>
          <span class="files-name" style="font-weight: 600;" title="${safeText(file.name)}">${safeText(formatPathLabel(file.name))}</span>
        </td>
        <td class="files-folder-cell"><span class="files-folder-path" title="${safeText(file.path)}">${safeText(formatPathLabel(file.path))}</span></td>
        <td colspan="5" style="color: var(--text-muted); font-size: 0.9em; text-align: left;">
          Carpeta de archivos (${file.count || 0} elementos)
        </td>
        <td></td>
      `;

      tr.addEventListener('click', () => { entrarACarpeta(file.name); });

    } else {
      // 📄 DIBUJAMOS EL PDF
      const isChecked = selectedPaths.has(file.path);
      const periodo = (file.año && file.mes) ? `${file.mes}/${file.año}` : file.año || '—';
      const razon = safeText(file.razon_social || '—');
      const banco = safeText(file.banco || '—');
      const statusBadge = file.indexed
        ? `<span class="status-badge indexed">✓ Indexado</span>`
        : `<span class="status-badge not-indexed">⚠ Sin texto</span>`;
      
      const deleteBtn = isAdmin
        ? `<button class="btn-icon-danger delete-btn" data-path="${safeText(file.path)}" title="Eliminar archivo">
            <i class="ti ti-trash"></i>
           </button>`
        : '';

      tr.innerHTML = `
        <td>
          <input type="checkbox" class="row-checkbox" data-path="${safeText(file.path)}" ${isChecked ? 'checked' : ''}>
        </td>
        <td class="files-filename-cell">
          <i class="ti ti-file-type-pdf file-icon-pdf"></i>
          <span class="files-name" title="${safeText(file.path)}">${safeText(file.name)}</span>
        </td>
        <td class="files-folder-cell">
          <span class="files-folder-path" title="${safeText(formatPathLabel(file.folder || '/'))}">${safeText(formatPathLabel(file.folder || '/'))}</span>
        </td>
        <td>${safeText(periodo)}</td>
        <td>${razon}</td>
        <td>${banco}</td>
        <td>${safeText(formatSize(file.size_bytes))}</td>
        <td>${statusBadge}</td>
        <td class="files-actions-cell">
          <button type="button" class="btn-icon download-link" data-url="${safeText(file.download_url)}" data-name="${safeText(file.name)}" title="Descargar PDF">
            <i class="ti ti-download"></i>
          </button>
          ${deleteBtn}
        </td>
      `;
    }

    // 🚀 ESTA ES LA LÍNEA MÁGICA (Fuera del if/else)
    tbody.appendChild(tr);
  });

  // Re-vincular eventos de los checkboxes y botones de eliminar
  tbody.querySelectorAll('.row-checkbox').forEach(cb => {
    cb.addEventListener('change', () => {
      const path = cb.dataset.path;
      if (cb.checked) selectedPaths.add(path);
      else selectedPaths.delete(path);
      updateBatchBar();
      syncSelectAllState();
    });
  });

  tbody.querySelectorAll('.delete-btn').forEach(btn => {
    btn.addEventListener('click', () => openDeleteModal(btn.dataset.path));
  });

  tbody.querySelectorAll('.download-link').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const url = btn.getAttribute('data-url');
      const name = btn.getAttribute('data-name');
      try {
        await SHARED.downloadWithAuth(url, { fallbackName: name });
      } catch (err) {
        alert(err.message || 'Error al descargar');
      }
    });
  });
}

function updatePagination(data) {
  const infoEl = document.getElementById('filesPaginationInfo');
  const totalEl = document.getElementById('filesTotalInfo');
  const prevBtn = document.getElementById('filesPrevBtn');
  const nextBtn = document.getElementById('filesNextBtn');

  infoEl.textContent = `Página ${data.page} de ${data.total_pages || 1}`;
  totalEl.textContent = `${(data.total || 0).toLocaleString('es-PE')} archivos`;
  prevBtn.disabled = !data.has_prev;
  nextBtn.disabled = !data.has_next;
}

/* ── SELECT ALL ─────────────────────────────────────────────────────── */
function syncSelectAllState() {
  const allCbs = document.querySelectorAll('#filesTableBody .row-checkbox');
  const selectAll = document.getElementById('selectAllCheckbox');
  if (!selectAll || allCbs.length === 0) return;
  const checkedCount = [...allCbs].filter(c => c.checked).length;
  selectAll.indeterminate = checkedCount > 0 && checkedCount < allCbs.length;
  selectAll.checked = checkedCount === allCbs.length;
}

function updateBatchBar() {
  const bar = document.getElementById('batchActionsBar');
  const countEl = document.getElementById('batchCount');
  const n = selectedPaths.size;
  if (n > 0) {
    show(bar);
    countEl.textContent = `${n} seleccionado${n !== 1 ? 's' : ''}`;
  } else {
    hide(bar);
  }
}

/* ── DELETE ─────────────────────────────────────────────────────────── */
let pendingDeletePath = null;

function openDeleteModal(path) {
  pendingDeletePath = path;
  document.getElementById('deleteModalPath').textContent = path;
  show(document.getElementById('deleteModal'));
}

function closeDeleteModal() {
  pendingDeletePath = null;
  hide(document.getElementById('deleteModal'));
}

async function executeDelete() {
  if (!pendingDeletePath) return;
  const path = pendingDeletePath;
  closeDeleteModal();

  try {
    await fetchJson(API.filesDelete, {
      method: 'DELETE',
      headers: getAuthHeaders(true),
      body: JSON.stringify({ path })
    });
    // Recargar tabla y stats
    await Promise.all([loadFiles(filesPage), loadStats()]);
  } catch (e) {
    alert(`Error al eliminar: ${e.message || e}`);
    console.error('Error delete:', e);
  }
}

/* ── MERGE / BATCH DOWNLOAD ─────────────────────────────────────────── */
async function handleBatchDownload() {
  const paths = [...selectedPaths];
  if (paths.length === 0) return;

  const btn = document.getElementById('batchDownloadBtn');
  btn.disabled = true;
  btn.innerHTML = '<i class="ti ti-loader"></i> Generando PDF...';

  try {
    const resp = await fetch(API.mergePdfs, {
      method: 'POST',
      headers: getAuthHeaders(true),
      body: JSON.stringify({ paths, output_name: 'documentos_seleccionados', output_format: 'pdf' })
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${resp.status}`);
    }

    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'documentos_seleccionados.pdf';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert(`Error al generar PDF combinado: ${e.message || e}`);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="ti ti-files"></i> Combinar PDF';
  }
}

async function handleBatchZipDownload() {
  const paths = [...selectedPaths];
  if (paths.length === 0) return;

  const btn = document.getElementById('batchZipBtn');
  btn.disabled = true;
  btn.innerHTML = '<i class="ti ti-loader"></i> Generando ZIP...';

  try {
    const resp = await fetch(API.mergePdfs, {
      method: 'POST',
      headers: getAuthHeaders(true),
      body: JSON.stringify({ paths, output_name: 'documentos_seleccionados', output_format: 'zip' })
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${resp.status}`);
    }

    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'documentos_seleccionados.zip';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert(`Error al generar ZIP: ${e.message || e}`);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="ti ti-file-zip"></i> Descargar ZIP';
  }
}

/* ── DRAG & DROP + CLASSIFY PREVIEW ────────────────────────────────── */
function initDropZone() {
  const zone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fileInput');
  if (!zone || !fileInput) return;

  zone.addEventListener('click', () => fileInput.click());
  zone.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') fileInput.click(); });

  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drop-zone-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drop-zone-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drop-zone-over');
    const files = [...(e.dataTransfer.files || [])].filter(f => f.name.toLowerCase().endsWith('.pdf'));
    if (files.length) triggerClassifyPreview(files);
  });

fileInput.addEventListener('change', () => {
    const files = [...fileInput.files];
    if (files.length) triggerClassifyPreview(files);
    fileInput.value = '';
  });
}

function initUploadModeToggle() {
  const autoOpt = document.getElementById('uploadModeAuto');
  const manualOpt = document.getElementById('uploadModeManual');
  const manualControls = document.getElementById('uploadManualControls');
  const useCurrentBtn = document.getElementById('useCurrentFolderBtn');
  const browseBtn = document.getElementById('browseFoldersBtn');
  const manualInput = document.getElementById('manualFolderInput');
  const folderBrowserResult = document.getElementById('folderBrowserResult');
  const selectedFolderPath = document.getElementById('selectedFolderPath');

  if (!autoOpt || !manualOpt) return;

  function setUploadMode(mode) {
    uploadMode = mode;
    if (mode === 'auto') {
      autoOpt.checked = true;
      manualOpt.closest('.auto-option')?.classList.add('active');
      manualOpt.closest('.manual-option')?.classList.remove('active');
      manualControls?.classList.add('hidden');
      selectedManualFolder = '';
    } else {
      manualOpt.checked = true;
      manualOpt.closest('.manual-option')?.classList.add('active');
      autoOpt.closest('.auto-option')?.classList.remove('active');
      manualControls?.classList.remove('hidden');
      if (rutaActiva.length > 0) {
        selectedManualFolder = rutaActiva.join('/');
      } else {
        selectedManualFolder = normalizeFolderValue(manualInput?.value || '');
      }
    }
  }

  autoOpt.addEventListener('change', () => setUploadMode('auto'));
  manualOpt.addEventListener('change', () => setUploadMode('manual'));

  useCurrentBtn?.addEventListener('click', () => {
    if (rutaActiva.length > 0) {
      selectedManualFolder = rutaActiva.join('/');
      manualInput.value = selectedManualFolder;
      if (folderBrowserResult) {
        folderBrowserResult.classList.remove('hidden');
        if (selectedFolderPath) selectedFolderPath.textContent = selectedManualFolder;
      }
    } else {
      alert('No hay una carpeta activa en el explorador.');
    }
  });

  browseBtn?.addEventListener('click', async () => {
    const existingBackdrop = document.querySelector('.folder-browser-backdrop');
    if (existingBackdrop) existingBackdrop.remove();

    let currentPath = rutaActiva.length > 0 ? rutaActiva.join('/') + '/' : '';

    function buildBreadcrumb(path) {
      const parts = path ? path.rstrip('/').split('/') : [];
      const crumbs = [];
      let accumulated = '';
      for (const part of parts) {
        accumulated += part + '/';
        crumbs.push({ name: part, path: accumulated });
      }
      return crumbs;
    }

    function closeBrowser() {
      document.querySelector('.folder-browser-backdrop')?.remove();
    }

    function renderFolderBrowser(path, folders, breadcrumb) {
      const backdrop = document.querySelector('.folder-browser-backdrop') || (() => {
        const el = document.createElement('div');
        el.className = 'modal-backdrop folder-browser-backdrop';
        el.setAttribute('role', 'dialog');
        el.setAttribute('aria-modal', 'true');
        el.addEventListener('click', e => { if (e.target === el) closeBrowser(); });
        document.body.appendChild(el);
        return el;
      })();

      const crumbs = buildBreadcrumb(path);
      backdrop.innerHTML = `
        <div class="modal-card folder-browser-modal acrylic-surface">
          <div class="modal-header">
            <span class="modal-title"><i class="ti ti-folder"></i> Examinar carpetas</span>
            <button type="button" class="btn btn-ghost btn-sm folder-browser-close" aria-label="Cerrar">&times;</button>
          </div>
          <div class="modal-body" style="padding:0;overflow:hidden;">
            ${crumbs.length > 0 ? `
              <div class="folder-browser-breadcrumb">
                <button type="button" class="btn btn-ghost btn-sm crumb-home" data-path="">Raíz</button>
                ${crumbs.map((c, i) => `
                  <span class="crumb-sep">/</span>
                  <button type="button" class="btn btn-ghost btn-sm crumb-btn" data-path="${c.path}">${safeText(c.name)}</button>
                `).join('')}
              </div>
            ` : ''}
            <div class="folder-browser-list">
              ${folders.length === 0 ? `
                <div class="folder-browser-empty">No hay subcarpetas en esta ubicación.</div>
              ` : folders.map(f => `
                <div class="folder-browser-item">
                  <span class="folder-browser-item-name"><i class="ti ti-folder"></i> ${safeText(f.name)}</span>
                  <div class="folder-browser-item-actions">
                    <button type="button" class="btn btn-ghost btn-sm folder-browser-open" data-path="${f.path}" title="Entrar">
                      <i class="ti ti-arrow-right"></i> Entrar
                    </button>
                    <button type="button" class="btn btn-sm folder-browser-pick" data-path="${f.path.replace(/\/$/, '')}" title="Seleccionar esta carpeta">
                      <i class="ti ti-check"></i> Seleccionar
                    </button>
                  </div>
                </div>
              `).join('')}
            </div>
          </div>
          <div class="modal-footer">
            <span class="folder-browser-hint">Usa <strong>Entrar</strong> para navegar o <strong>Seleccionar</strong> para usar esta carpeta</span>
            <button type="button" class="btn btn-ghost folder-browser-cancel">Cancelar</button>
          </div>
        </div>
      `;

      backdrop.querySelector('.folder-browser-close')?.addEventListener('click', closeBrowser);
      backdrop.querySelector('.folder-browser-cancel')?.addEventListener('click', closeBrowser);
      backdrop.querySelectorAll('.crumb-btn').forEach(btn => {
        btn.addEventListener('click', () => loadFolderLevel(btn.dataset.path));
      });
      backdrop.querySelector('.crumb-home')?.addEventListener('click', () => loadFolderLevel(''));
      backdrop.querySelectorAll('.folder-browser-open').forEach(btn => {
        btn.addEventListener('click', () => loadFolderLevel(btn.dataset.path));
      });
      backdrop.querySelectorAll('.folder-browser-pick').forEach(btn => {
        btn.addEventListener('click', () => {
          const chosen = btn.dataset.path;
          selectedManualFolder = chosen;
          manualInput.value = chosen;
          if (folderBrowserResult) {
            folderBrowserResult.classList.remove('hidden');
            if (selectedFolderPath) selectedFolderPath.textContent = chosen;
          }
          closeBrowser();
        });
      });
    }

    async function loadFolderLevel(path) {
      currentPath = path;
      const params = new URLSearchParams();
      if (path) params.set('folder', path);
      try {
        const data = await fetchJson(`${API.foldersList}?${params}`, { headers: getAuthHeaders() });
        renderFolderBrowser(path, data.folders || [], data.breadcrumb || []);
      } catch (e) {
        alert('Error al cargar carpetas: ' + (e.message || e));
        closeBrowser();
      }
    }

    await loadFolderLevel(currentPath);
  });

  manualInput?.addEventListener('input', () => {
    selectedManualFolder = normalizeFolderValue(manualInput.value);
    if (folderBrowserResult) {
      if (selectedManualFolder) {
        folderBrowserResult.classList.remove('hidden');
        if (selectedFolderPath) selectedFolderPath.textContent = selectedManualFolder;
      } else {
        folderBrowserResult.classList.add('hidden');
      }
    }
  });

  setUploadMode('auto');
}

function getSuggestedFolder(item) {
  const prefix = String(item?.logical_prefix || '').trim();
  if (prefix) return prefix.replace(/^\/+|\/+$/g, '');

  const logicalPath = String(item?.logical_path || '').trim();
  if (!logicalPath || !logicalPath.includes('/')) return '';
  return logicalPath.split('/').slice(0, -1).join('/');
}

function normalizeFolderValue(path) {
  return String(path || '').trim().replace(/^\/+|\/+$/g, '');
}

function folderLabel(path) {
  const normalized = normalizeFolderValue(path);
  return normalized ? formatPathLabel(normalized) : 'Raiz del repositorio';
}

async function loadFolderOptions(suggestedFolder) {
  const options = [];
  const seen = new Set();

  const addOption = (path, labelPrefix = '') => {
    const normalized = normalizeFolderValue(path);
    if (seen.has(normalized)) return;
    seen.add(normalized);
    options.push({
      value: normalized,
      label: `${labelPrefix}${folderLabel(normalized)}`,
    });
  };

  addOption(suggestedFolder, 'Sugerida: ');
  addOption(rutaActiva.join('/'), 'Actual: ');
  addOption('', 'Alternativa: ');

  try {
    const params = new URLSearchParams();
    if (rutaActiva.length > 0) params.set('folder', `${rutaActiva.join('/')}/`);
    const data = await fetchJson(`${API.foldersList}?${params}`, { headers: getAuthHeaders() });
    (data.folders || []).forEach(folder => addOption(folder.path, 'Alternativa: '));
  } catch (e) {
    console.warn('No se pudieron cargar carpetas alternativas:', e);
  }

  return options;
}

function renderDuplicateBanner(items) {
  const previewArea = document.getElementById('uploadPreviewArea');
  if (!previewArea) return;

  previewArea.querySelector('.duplicate-warning-banner')?.remove();
  const duplicates = items.filter(item => item.status === 'DUPLICATE' && item.duplicate);
  if (!duplicates.length) return;

  const banner = document.createElement('div');
  banner.className = 'duplicate-warning-banner';
  const canOverride = isAdmin;

  duplicates.forEach(item => {
    const objectKey = item.duplicate?.object_key || '';
    const existingPath = objectKey;
    const existingFolder = existingPath.split('/').slice(0, -1).join('/') || '';

    const itemDiv = document.createElement('div');
    itemDiv.style.marginBottom = duplicates.length > 1 ? '10px' : '0';
    itemDiv.style.width = '100%';

    const fileLink = objectKey
      ? `<a href="${safeText(encodeURI(`/api/download/${objectKey}`))}" class="duplicate-doc-link" data-download-url="${safeText(encodeURI(`/api/download/${objectKey}`))}">${safeText(item.filename)}</a>`
      : safeText(item.filename);

    itemDiv.innerHTML = `
      <div class="banner-text">
        <i class="ti ti-alert-triangle"></i>
        <span><strong>${safeText(item.filename)}</strong> es duplicado. Ya existe en:</span>
      </div>
      <code class="duplicate-existing-path">${safeText(existingPath)}</code>
      <div class="duplicate-banner-actions">
        <button type="button" class="btn-duplicate-use-folder" data-folder="${safeText(existingFolder)}" title="Usar la carpeta del archivo existente">
          <i class="ti ti-folder"></i> Usar esta carpeta
        </button>
        ${canOverride ? `
          <button type="button" class="btn-duplicate-override" data-duplicate-filename="${safeText(item.filename)}" title="Sobrescribir el archivo existente">
            <i class="ti ti-upload"></i> Subir de todos modos
          </button>
        ` : `<span style="font-size:11px;color:var(--muted);">Solo admin puede forzar re-ingreso</span>`}
      </div>
    `;
    banner.appendChild(itemDiv);
  });

  previewArea.prepend(banner);
  bindDuplicateDownloadLinks(banner);

  banner.querySelectorAll('.btn-duplicate-use-folder').forEach(btn => {
    btn.addEventListener('click', () => {
      const folder = btn.getAttribute('data-folder');
      if (folder) {
        uploadMode = 'manual';
        selectedManualFolder = folder;
        const manualOpt = document.getElementById('uploadModeManual');
        const manualControls = document.getElementById('uploadManualControls');
        const manualInput = document.getElementById('manualFolderInput');
        const folderBrowserResult = document.getElementById('folderBrowserResult');
        const selectedFolderPath = document.getElementById('selectedFolderPath');
        if (manualOpt) manualOpt.checked = true;
        document.querySelector('.manual-option')?.classList.add('active');
        document.querySelector('.auto-option')?.classList.remove('active');
        if (manualControls) manualControls.classList.remove('hidden');
        if (manualInput) manualInput.value = folder;
        if (folderBrowserResult) folderBrowserResult.classList.remove('hidden');
        if (selectedFolderPath) selectedFolderPath.textContent = folder;

        const duplicateItem = duplicates.find(d => {
          const existingPath = d.duplicate?.object_key || '';
          const existingFolder = existingPath.split('/').slice(0, -1).join('/') || '';
          return existingFolder === folder;
        });
        if (duplicateItem) {
          const entry = pendingUploadMap.get(duplicateItem.filename);
          if (entry) {
            entry.allowDuplicate = true;
            entry.isDuplicate = true;
          }
          const row = document.querySelector(`tr[data-preview-filename="${CSS.escape(duplicateItem.filename)}"]`);
          if (row) row.classList.add('is-confirmed');
          const checkbox = document.querySelector(`.preview-checkbox[data-filename="${CSS.escape(duplicateItem.filename)}"]`);
          if (checkbox) checkbox.checked = true;
        }
      }
    });
  });

  banner.querySelectorAll('.btn-duplicate-override').forEach(btn => {
    btn.addEventListener('click', () => {
      const filename = btn.getAttribute('data-duplicate-filename');
      const entry = pendingUploadMap.get(filename);
      if (entry) {
        entry.allowDuplicate = true;
        entry.isDuplicate = true;
      }
      const row = document.querySelector(`tr[data-preview-filename="${CSS.escape(filename)}"]`);
      if (row) row.classList.add('is-confirmed');
      const checkbox = document.querySelector(`.preview-checkbox[data-filename="${CSS.escape(filename)}"]`);
      if (checkbox) checkbox.checked = true;
      btn.disabled = true;
      btn.textContent = '✓ Re-ingreso permitido';
    });
  });
}

function bindDuplicateDownloadLinks(root) {
  root.querySelectorAll('.duplicate-doc-link').forEach(link => {
    link.addEventListener('click', async e => {
      e.preventDefault();
      const url = link.getAttribute('data-download-url') || link.getAttribute('href');
      if (!url || url === '#') return;
      try {
        await SHARED.downloadWithAuth(url, { fallbackName: link.textContent.trim() || 'documento.pdf' });
      } catch (err) {
        alert(err.message || 'Error al descargar duplicado');
      }
    });
  });
}

async function openClassifyConfirmationModal(filename) {
  const entry = pendingUploadMap.get(filename);
  if (!entry) return false;

  const item = entry.previewItem || {};
  const meta = item.metadata || {};
  const suggestedFolder = getSuggestedFolder(item);
  const folderOptions = await loadFolderOptions(suggestedFolder);
  const conf = item.confidence != null ? Math.round(item.confidence * 100) : 0;
  const missing = new Set(item.missing_fields || []);
  if (missing.has('aÃ±o')) missing.add('año');
  const warnings = item.warnings || [];
  const fieldLabels = [
    ['año', 'Año', meta.año || meta.anio],
    ['mes', 'Mes', meta.mes],
    ['razon_social', 'Razon social', meta.razon_social],
    ['banco', 'Banco', meta.banco],
    ['tipo_documento', 'Tipo documento', meta.tipo_documento],
    ['tipo_movimiento', 'Movimiento', meta.tipo_documento],
    ['tipo_seguro', 'Tipo seguro', meta.tipo_documento],
  ];

  return new Promise(resolve => {
    document.querySelector('.classify-modal-backdrop')?.remove();

    const backdrop = document.createElement('div');
    backdrop.className = 'modal-backdrop classify-modal-backdrop';
    backdrop.setAttribute('role', 'dialog');
    backdrop.setAttribute('aria-modal', 'true');
    backdrop.innerHTML = `
      <div class="modal-card acrylic-surface classify-modal">
        <div class="modal-header">
          <span class="modal-title"><i class="ti ti-adjustments-check"></i> Confirmar clasificacion</span>
        </div>
        <div class="modal-body">
          <div class="classify-modal-file" title="${safeText(filename)}">${safeText(filename)}</div>
          <label class="classify-modal-label">Ruta sugerida</label>
          <code class="classify-modal-path">${safeText(item.logical_path || `${suggestedFolder}/${filename}`)}</code>

          <div class="classify-confidence-row">
            <span>Confianza</span>
            <div class="confidence-bar-wrap">
              <div class="confidence-bar" style="width:${conf}%"></div>
              <span class="confidence-label">${conf}%</span>
            </div>
          </div>

          <div class="classify-field-grid">
            ${fieldLabels.map(([key, label, value]) => `
              <div class="classify-field ${missing.has(key) ? 'is-missing' : ''}">
                <span>${safeText(label)}</span>
                <strong>${safeText(value || 'Pendiente')}</strong>
              </div>
            `).join('')}
          </div>

          <div class="classify-warning-list">
            ${(warnings.length ? warnings : ['revision_manual']).map(warning => `
              <span class="classify-warning-chip">${safeText(warning)}</span>
            `).join('')}
          </div>

          <label class="classify-modal-label" for="classifyFolderSelect">Carpeta alternativa</label>
          <select id="classifyFolderSelect" class="form-select classify-modal-select">
            ${folderOptions.map(option => `
              <option value="${safeText(option.value)}">${safeText(option.label)}</option>
            `).join('')}
          </select>

          <label class="classify-modal-label" for="classifyCorrectionReason">Motivo de correccion</label>
          <input id="classifyCorrectionReason" class="form-control classify-modal-input"
                 type="text" maxlength="500" placeholder="Ej. Ruta corregida por revision manual"
                 value="${safeText(entry.confirmation?.correctionReason || '')}">
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-ghost classify-cancel-btn">Cancelar</button>
          <button type="button" class="btn btn-primary classify-confirm-btn">
            <i class="ti ti-check"></i> Confirmar
          </button>
        </div>
      </div>
    `;

    const close = confirmed => {
      backdrop.remove();
      resolve(confirmed);
    };

    backdrop.querySelector('.classify-cancel-btn').addEventListener('click', () => close(false));
    backdrop.querySelector('.classify-confirm-btn').addEventListener('click', () => {
      const selectedFolder = normalizeFolderValue(backdrop.querySelector('#classifyFolderSelect')?.value || suggestedFolder);
      const correctionReason = String(backdrop.querySelector('#classifyCorrectionReason')?.value || '').trim().slice(0, 500);
      entry.confirmation = { folder: selectedFolder, correctionReason };
      const checkbox = document.querySelector(`.preview-checkbox[data-filename="${CSS.escape(filename)}"]`);
      if (checkbox) checkbox.checked = true;
      const row = document.querySelector(`tr[data-preview-filename="${CSS.escape(filename)}"]`);
      if (row) row.classList.add('is-confirmed');
      close(true);
    });
    backdrop.addEventListener('click', e => {
      if (e.target === backdrop) close(false);
    });

    document.body.appendChild(backdrop);
    backdrop.querySelector('#classifyCorrectionReason')?.focus();
  });
}

async function triggerClassifyPreview(files) {
  const previewArea = document.getElementById('uploadPreviewArea');
  const tbody = document.getElementById('classifyPreviewBody');
  const summaryEl = document.getElementById('previewSummary');
  const zone = document.getElementById('dropZone');

  zone.classList.add('drop-zone-loading');
  zone.querySelector('.drop-zone-title').textContent = 'Clasificando archivos...';

  pendingUploadMap.clear();
  tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:1.5rem;">
    <div class="spinner" style="margin:0 auto;"></div></td></tr>`;
  show(previewArea);
  hide(document.getElementById('uploadProgressArea'));

  const formData = new FormData();
  files.forEach(f => formData.append('files[]', f));
  formData.append('upload_mode', uploadMode);
  if (uploadMode === 'manual' && selectedManualFolder) {
    formData.append('folder', selectedManualFolder);
  }

  try {
    const data = await fetchJson(API.classifyPreview, {
      method: 'POST',
      headers: getAuthHeaders(false), // sin Content-Type (multipart)
      body: formData
    });

    const items = data.files || [];
    items.forEach((item, i) => {
      if (item.status !== 'INVALID_FILE') {
        pendingUploadMap.set(item.filename, { file: files[i], previewItem: item, allowDuplicate: false, isDuplicate: false });
      }
    });

    renderClassifyPreview(items);
    renderDuplicateBanner(items);

    const ready = items.filter(i => i.status === 'READY').length;
    const confirm = items.filter(i => i.status === 'REQUIRES_CONFIRMATION').length;
    const dup = items.filter(i => i.status === 'DUPLICATE').length;
    summaryEl.innerHTML =
      `<span class="preview-badge ready">${ready} listos</span>` +
      `<span class="preview-badge warn">${confirm} requieren confirmación</span>` +
      `<span class="preview-badge dup">${dup} duplicados</span>`;

    const firstRequiresConfirmation = items.find(i => i.status === 'REQUIRES_CONFIRMATION');
    if (firstRequiresConfirmation) {
      setTimeout(() => openClassifyConfirmationModal(firstRequiresConfirmation.filename), 80);
    }
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="8" class="preview-error">Error clasificando: ${safeText(e.message)}</td></tr>`;
  } finally {
    zone.classList.remove('drop-zone-loading');
    zone.querySelector('.drop-zone-title').textContent = 'Arrastra PDFs aquí o haz clic para seleccionar';
  }
}

function renderClassifyPreview(items) {
  const tbody = document.getElementById('classifyPreviewBody');
  tbody.innerHTML = '';

  items.forEach(item => {
    const tr = document.createElement('tr');
    tr.dataset.previewFilename = item.filename;
    const conf = item.confidence != null ? Math.round(item.confidence * 100) : null;
    const confBar = conf != null
      ? `<div class="confidence-bar-wrap"><div class="confidence-bar" style="width:${conf}%"></div>
         <span class="confidence-label">${conf}%</span></div>`
      : '—';

    const statusMap = {
      'READY': ['status-badge ready', '✓ Listo'],
      'REQUIRES_CONFIRMATION': ['status-badge requires-confirmation', '⚠ Revisión'],
      'DUPLICATE': ['status-badge duplicate', '⋈ Duplicado'],
      'INVALID_FILE': ['status-badge invalid', '✗ Inválido'],
    };
    const [cls, label] = statusMap[item.status] || ['status-badge', item.status];

    const meta = item.metadata || {};
    const warns = (item.warnings || []).join(', ') || '—';
    const periodo = [meta.año, meta.mes ? String(meta.mes).padStart(2, '0') : ''].filter(Boolean).join('/') || '—';

    const missingChips = (item.missing_fields || []).map(field =>
      `<span class="missing-field-chip">${safeText(field)}</span>`
    ).join('');

    // Checkbox para incluir en upload (solo no-duplicados, no-inválidos)
    const canUpload = item.status === 'READY' || item.status === 'REQUIRES_CONFIRMATION';
    const checkbox = canUpload
      ? `<input type="checkbox" class="preview-checkbox" data-filename="${safeText(item.filename)}"
               ${item.status === 'READY' ? 'checked' : ''}>`
      : '';
    const reviewBtn = item.status === 'REQUIRES_CONFIRMATION'
      ? `<button type="button" class="btn btn-ghost btn-sm classify-review-btn" data-filename="${safeText(item.filename)}">
           <i class="ti ti-adjustments"></i> Revisar
         </button>`
      : '';
    const duplicateLink = item.status === 'DUPLICATE' && item.duplicate?.object_key
      ? `<a class="duplicate-doc-link" href="${safeText(encodeURI(`/api/download/${item.duplicate.object_key}`))}" data-download-url="${safeText(encodeURI(`/api/download/${item.duplicate.object_key}`))}">Ver existente</a>`
      : '';

    tr.innerHTML = `
      <td>
        ${checkbox}
        <span class="preview-filename" title="${safeText(item.filename)}">${safeText(item.filename)}</span>
        ${reviewBtn}
      </td>
      <td><span class="${cls}">${label}</span></td>
      <td>${confBar}</td>
      <td><code class="domain-code">${safeText(item.domain || '—')}</code></td>
      <td>${safeText(periodo)}</td>
      <td>${safeText(meta.razon_social || '—')}</td>
      <td class="logical-path-cell" title="${safeText(item.logical_path || '')}">
        ${safeText(item.logical_path || '—')}
      </td>
      <td class="warns-cell">${safeText(warns)} ${missingChips} ${duplicateLink}</td>
    `;
    tbody.appendChild(tr);
  });

  tbody.querySelectorAll('.classify-review-btn').forEach(btn => {
    btn.addEventListener('click', () => openClassifyConfirmationModal(btn.dataset.filename));
  });

  bindDuplicateDownloadLinks(tbody);

  tbody.querySelectorAll('.preview-checkbox').forEach(cb => {
    cb.addEventListener('change', async () => {
      const entry = pendingUploadMap.get(cb.dataset.filename);
      if (!cb.checked || entry?.previewItem?.status !== 'REQUIRES_CONFIRMATION' || entry.confirmation) return;
      const confirmed = await openClassifyConfirmationModal(cb.dataset.filename);
      if (!confirmed) cb.checked = false;
    });
  });
}

/* ── UPLOAD ─────────────────────────────────────────────────────────── */
async function handleUpload() {
  // Recoger checkboxes marcados en preview
  const checkedFilenames = [...document.querySelectorAll('.preview-checkbox:checked')]
    .map(cb => cb.dataset.filename);

  if (checkedFilenames.length === 0) {
    alert('No hay archivos seleccionados para subir.');
    return;
  }

  const progressArea = document.getElementById('uploadProgressArea');
  const progressBar = document.getElementById('uploadProgressBar');
  const progressText = document.getElementById('uploadProgressText');
  const countEl = document.getElementById('uploadProgressCount');
  const logEl = document.getElementById('uploadLog');

  show(progressArea);
  logEl.innerHTML = '';
  progressBar.style.width = '0%';

  const total = checkedFilenames.length;
  let done = 0;

  const uploadBtn = document.getElementById('uploadApprovedBtn');
  uploadBtn.disabled = true;

  for (const filename of checkedFilenames) {
    const entry = pendingUploadMap.get(filename);
    if (!entry) continue;

    if (entry.previewItem?.status === 'REQUIRES_CONFIRMATION' && !entry.confirmation) {
      const confirmed = await openClassifyConfirmationModal(filename);
      if (!confirmed) {
        done++;
        const pct = Math.round((done / total) * 100);
        progressBar.style.width = `${pct}%`;
        addLogEntry(logEl, `${filename} - subida cancelada por falta de confirmacion`, 'warn');
        continue;
      }
    }

    progressText.textContent = `Subiendo ${filename}...`;
    countEl.textContent = `${done}/${total}`;

const formData = new FormData();
    formData.append('files[]', entry.file);

    // Incluir hints del preview si están disponibles
    const meta = entry.previewItem?.metadata || {};
    if (meta.año) formData.append('año', meta.año);
    if (meta.mes) formData.append('mes', meta.mes);
    if (meta.razon_social) formData.append('razon_social', meta.razon_social);
    if (meta.banco) formData.append('banco', meta.banco);
    if (meta.tipo_documento) formData.append('tipo_documento', meta.tipo_documento);
    if (entry.confirmation?.folder) {
      formData.append('folder', entry.confirmation.folder);
    } else if (uploadMode === 'manual' && selectedManualFolder) {
      formData.append('folder', selectedManualFolder);
    }
    if (entry.confirmation?.correctionReason) {
      formData.append('correction_reason', entry.confirmation.correctionReason);
    }
    formData.append('upload_mode', uploadMode);
    if (entry.isDuplicate && entry.allowDuplicate) {
      formData.append('allow_duplicate', 'true');
    }

    try {
      const resp = await fetchJson(API.filesUpload, {
        method: 'POST',
        headers: getAuthHeaders(false),
        body: formData
      });
      done++;
      const pct = Math.round((done / total) * 100);
      progressBar.style.width = `${pct}%`;
      addLogEntry(logEl, `✓ ${filename} — subido correctamente`, 'success');
    } catch (e) {
      done++;
      const pct = Math.round((done / total) * 100);
      progressBar.style.width = `${pct}%`;
      addLogEntry(logEl, `✗ ${filename} — error: ${e.message || e}`, 'error');
    }
  }

  progressText.textContent = `Subida completada: ${done} de ${total} archivos`;
  countEl.textContent = `${done}/${total}`;
  uploadBtn.disabled = false;

  // Refrescar tabla y stats
  await Promise.all([loadFiles(1), loadStats()]);
}

/* ── SINCRONIZACION ─────────────────────────────────────────────────── */
async function runSync() {
  if (syncRunning) return;
  syncRunning = true;
  syncShouldStop = false;

  const progressArea = document.getElementById('syncProgressArea');
  const progressBar = document.getElementById('syncProgressBar');
  const progressText = document.getElementById('syncProgressText');
  const progressPct = document.getElementById('syncProgressPercent');
  const statsRow = document.getElementById('syncStatsRow');
  const logEl = document.getElementById('syncLog');
  const runBtn = document.getElementById('runSyncBtn');
  const stopBtn = document.getElementById('stopSyncBtn');

  const batchSize = parseInt(document.getElementById('syncBatchSize')?.value || '12', 10);
  const skipNew = document.getElementById('syncSkipNew')?.checked || false;

  show(progressArea);
  show(stopBtn);
  hide(runBtn);
  statsRow.style.display = 'none';
  logEl.innerHTML = '';
  progressBar.style.width = '0%';
  progressText.textContent = 'Iniciando sincronización...';
  progressPct.textContent = '0%';

  let cumulativeNew = 0;
  let cumulativeMoved = 0;
  let cumulativeRemoved = 0;
  let cumulativeErrors = 0;

  addLogEntry(logEl, `Iniciando sincronización (lote: ${batchSize}, skip_new: ${skipNew})...`);

  try {
    let hasMore = true;
    let attempts = 0;
    const MAX_ATTEMPTS = 200;

    while (hasMore && !syncShouldStop && attempts < MAX_ATTEMPTS) {
      attempts++;
      const data = await fetchJson(API.sync, {
        method: 'POST',
        headers: getAuthHeaders(true),
        body: JSON.stringify({ batch_size: batchSize, skip_new: skipNew })
      });

      cumulativeNew += data.new_files || 0;
      cumulativeMoved += data.moved_files || 0;
      cumulativeRemoved += data.removed_orphans || 0;
      cumulativeErrors += data.errors || 0;

      const pct = data.progress_percent ?? 100;
      progressBar.style.width = `${pct}%`;
      progressPct.textContent = `${pct}%`;
      progressText.textContent = data.message || 'Procesando...';

      statsRow.style.display = 'flex';
      document.getElementById('syncNewCount').textContent = cumulativeNew;
      document.getElementById('syncMovedCount').textContent = cumulativeMoved;
      document.getElementById('syncRemovedCount').textContent = cumulativeRemoved;
      document.getElementById('syncErrorCount').textContent = cumulativeErrors;

      const logMsg = data.has_more
        ? `Lote ${attempts}: +${data.new_files || 0} nuevos, ${data.moved_files || 0} movidos, ${data.pending_new || 0} pendientes`
        : `Completado: ${cumulativeNew} nuevos, ${cumulativeMoved} movidos, ${cumulativeRemoved} desactivados`;
      addLogEntry(logEl, logMsg, data.errors ? 'error' : 'info');

      hasMore = data.has_more === true;

      if (hasMore && !syncShouldStop) {
        await new Promise(r => setTimeout(r, 400)); // Pequeña pausa entre lotes
      }
    }

    if (syncShouldStop) {
      addLogEntry(logEl, '⏹ Sincronización detenida manualmente.', 'warn');
      progressText.textContent = 'Detenida manualmente';
    } else {
      progressBar.style.width = '100%';
      progressPct.textContent = '100%';
      progressText.textContent = 'Sincronización completada';
      addLogEntry(logEl, '✓ Sincronización completada correctamente.', 'success');
    }
  } catch (e) {
    progressText.textContent = 'Error en sincronización';
    addLogEntry(logEl, `✗ Error: ${e.message || e}`, 'error');
    console.error('Sync error:', e);
  } finally {
    syncRunning = false;
    hide(stopBtn);
    show(runBtn);
    // Refrescar stats y tabla después de sync
    await Promise.all([loadStats(), loadFiles(1)]);
  }
}

/* ── BIND EVENTS ────────────────────────────────────────────────────── */
function bindAllEvents() {
  /* Popstate para navegación del browser */
  window.addEventListener('popstate', () => {
    restorePathFromHash();
    loadFiles(1);
  });

  /* Logout */
  document.getElementById('btnLogout')?.addEventListener('click', logout);

  /* Paginación */
  document.getElementById('filesPrevBtn')?.addEventListener('click', () => {
    if (filesPage > 1) loadFiles(filesPage - 1);
  });
  document.getElementById('filesNextBtn')?.addEventListener('click', () => {
    if (filesPage < filesTotalPages) loadFiles(filesPage + 1);
  });

  /* Select all */
  document.getElementById('selectAllCheckbox')?.addEventListener('change', (e) => {
    const allCbs = document.querySelectorAll('#filesTableBody .row-checkbox');
    allCbs.forEach(cb => {
      cb.checked = e.target.checked;
      const path = cb.dataset.path;
      if (e.target.checked) selectedPaths.add(path);
      else selectedPaths.delete(path);
    });
    updateBatchBar();
  });

  /* Batch actions */
  document.getElementById('batchZipBtn')?.addEventListener('click', handleBatchZipDownload);
  document.getElementById('batchDownloadBtn')?.addEventListener('click', handleBatchDownload);
  document.getElementById('batchClearBtn')?.addEventListener('click', () => {
    selectedPaths.clear();
    document.querySelectorAll('#filesTableBody .row-checkbox').forEach(cb => cb.checked = false);
    document.getElementById('selectAllCheckbox').checked = false;
    updateBatchBar();
  });

  /* Filtros con debounce */
  document.getElementById('filesSearchInput')?.addEventListener('input', () => {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => loadFiles(1), 400);
  });
  ['filesYearFilter', 'filesMonthFilter', 'filesRazonFilter'].forEach(id => {
    document.getElementById(id)?.addEventListener('change', () => loadFiles(1));
  });
  document.getElementById('filesClearFilters')?.addEventListener('click', () => {
    document.getElementById('filesSearchInput').value = '';
    document.getElementById('filesYearFilter').value = '';
    document.getElementById('filesMonthFilter').value = '';
    document.getElementById('filesRazonFilter').value = '';
    rutaActiva = [];
    updateURLFromPath();
    loadFiles(1);
  });

  /* Delete modal */
  document.getElementById('deleteModalCancel')?.addEventListener('click', closeDeleteModal);
  document.getElementById('deleteModalConfirm')?.addEventListener('click', executeDelete);
  document.getElementById('deleteModal')?.addEventListener('click', e => {
    if (e.target === document.getElementById('deleteModal')) closeDeleteModal();
  });

  /* Upload */
  document.getElementById('uploadApprovedBtn')?.addEventListener('click', handleUpload);
  document.getElementById('classifyAgainBtn')?.addEventListener('click', () => {
    document.getElementById('fileInput').click();
  });

  /* Sync */
  document.getElementById('runSyncBtn')?.addEventListener('click', runSync);
  document.getElementById('stopSyncBtn')?.addEventListener('click', () => { syncShouldStop = true; });
}

/* ── ADMIN UI ──────────────────────────────────────────────────────── */
function applyAdminVisibility() {
  // Si no es admin ocultar secciones restringidas
  if (!isAdmin) {
    const uploadSection = document.getElementById('upload-section');
    const syncSection = document.getElementById('sync-section');
    if (uploadSection) {
      uploadSection.innerHTML = `<div style="padding:2rem 1.5rem;text-align:center;color:var(--muted);">
        <i class="ti ti-lock" style="font-size:1.5rem;display:block;margin-bottom:.5rem;"></i>
        Acceso restringido a administradores</div>`;
    }
    if (syncSection) {
      syncSection.innerHTML = `<div style="padding:2rem 1.5rem;text-align:center;color:var(--muted);">
        <i class="ti ti-lock" style="font-size:1.5rem;display:block;margin-bottom:.5rem;"></i>
        Acceso restringido a administradores</div>`;
    }
  }
}

function focusSectionFromQuery() {
  const params = new URLSearchParams(window.location.search);
  const section = String(params.get('section') || '').toLowerCase();
  if (section) {
    const el = document.getElementById(`${section}-section`);
    if (el) setTimeout(() => el.scrollIntoView({ behavior: 'smooth', block: 'start' }), 200);
  }
}

/* ── BOOTSTRAP ──────────────────────────────────────────────────────── */
async function bootstrap() {
  if (!SHARED) {
    console.error('DocSearchShared no disponible. Verifica la carga de scripts base.');
    const container = document.getElementById('filesStateLoading');
    if (container) {
      container.innerHTML = `
        <div style="text-align: center; padding: 2rem; color: #dc3545;">
          <i class="ti ti-alert-circle" style="font-size: 2rem; margin-bottom: 1rem; display: block;"></i>
          <h3>Error de carga</h3>
          <p>No se pudo cargar el módulo de búsqueda. Por favor recarga la página o contacta al administrador.</p>
        </div>
      `;
    }
    return;
  }
  SHARED.initTheme();
  SHARED.initGlobalUI();  // 🎨 Wire up theme toggle button and other global UI elements
  renderSidebarUser();

  const hasSession = await restoreSession();
  if (!hasSession) { redirectToLogin(); return; }

  applyAdminVisibility();
  bindAllEvents();
  initUploadModeToggle();
  initDropZone();

  // Restaurar ruta desde la URL si existe
  restorePathFromHash();

  // Carga inicial en paralelo
  await Promise.all([loadStats(), loadFilterOptions()]);
  await loadFiles(1);

  focusSectionFromQuery();
}

bootstrap();
