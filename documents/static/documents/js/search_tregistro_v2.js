const API = {
  me: '/api/me',
  logout: '/api/auth/logout/',
  loginUi: '/ui/login/',
  filterOptions: '/api/v2/filter-options?domain=TREGISTRO',
  search: '/api/v2/search/tregistro',
  merge: '/api/merge-pdfs'
};

const TOKEN_KEY = 'docsearch_v2_access_token';
const REFRESH_TOKEN_KEY = 'docsearch_v2_refresh_token';
const USER_KEY = 'docsearch_v2_user';
let authToken = null;
let lastResults = [];

const DEFAULT_MESES = [
  { value: '01', label: 'Enero' },
  { value: '02', label: 'Febrero' },
  { value: '03', label: 'Marzo' },
  { value: '04', label: 'Abril' },
  { value: '05', label: 'Mayo' },
  { value: '06', label: 'Junio' },
  { value: '07', label: 'Julio' },
  { value: '08', label: 'Agosto' },
  { value: '09', label: 'Septiembre' },
  { value: '10', label: 'Octubre' },
  { value: '11', label: 'Noviembre' },
  { value: '12', label: 'Diciembre' }
];

const MESES_BY_VALUE = Object.fromEntries(DEFAULT_MESES.map(item => [item.value, item.label]));

const SHARED = window.DocSearchShared;
if (!SHARED) {
  throw new Error('DocSearchShared no disponible. Verifica la carga de scripts base.');
}

const form = document.getElementById('tregistroForm');
const tableBody = document.getElementById('tableBody');
const resultCount = document.getElementById('resultCount');
const stateEmpty = document.getElementById('stateEmpty');
const stateLoading = document.getElementById('stateLoading');
const stateTable = document.getElementById('stateTable');
const paginationControls = document.getElementById('paginationControls');
const prevPageBtn = document.getElementById('prevPageBtn');
const nextPageBtn = document.getElementById('nextPageBtn');
const paginationInfo = document.getElementById('paginationInfo');

const PAGE_SIZE = 12;
let currentPage = 1;

function setAuthState(connected) {
  SHARED.setAuthState(connected);
}

function renderSidebarUser() {
  SHARED.renderSidebarUser({ userKey: USER_KEY });
}

function clearSession() {
  authToken = null;
  SHARED.clearSession({
    tokenKey: TOKEN_KEY,
    refreshTokenKey: REFRESH_TOKEN_KEY,
    userKey: USER_KEY,
    updateUi: false
  });
  setAuthState(false);
  renderSidebarUser();
}

function redirectToLogin() {
  SHARED.redirectToLogin(API.loginUi);
}

function getAuthHeaders(withJsonBody = false) {
  const headers = {
    Authorization: `Bearer ${authToken}`
  };
  if (withJsonBody) {
    headers['Content-Type'] = 'application/json';
  }
  return headers;
}

async function fetchJson(url, options = {}) {
  return SHARED.fetchJson(url, options);
}

async function validateToken(token) {
  return SHARED.validateToken(API.me, token);
}

async function restoreSession() {
  const stored = localStorage.getItem(TOKEN_KEY);
  if (!stored) {
    setAuthState(false);
    renderSidebarUser();
    return false;
  }

  const isValid = await validateToken(stored);
  if (!isValid) {
    clearSession();
    return false;
  }

  authToken = stored;
  setAuthState(true);
  renderSidebarUser();
  return true;
}

async function ensureAuthToken() {
  if (authToken) {
    return true;
  }

  const restored = await restoreSession();
  if (restored) {
    return true;
  }

  redirectToLogin();
  return false;
}

async function logoutAndRedirect() {
  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);

  try {
    if (authToken && refreshToken) {
      await fetchJson(API.logout, {
        method: 'POST',
        headers: getAuthHeaders(true),
        body: JSON.stringify({ refresh: refreshToken })
      });
    }
  } catch (error) {
    // Best effort logout. We always clear local session.
    console.warn('No fue posible invalidar el token de refresh:', error);
  } finally {
    clearSession();
    redirectToLogin();
  }
}

function parseMasivo(raw) {
  return raw
    .split(/[\n,;\s]+/)
    .map(value => value.trim())
    .filter(Boolean);
}

function normalizeCode(code) {
  return String(code || '').trim();
}

function validateCodes(codes) {
  const normalized = [];
  for (const code of codes) {
    const clean = normalizeCode(code);
    if (!clean) {
      continue;
    }
    if (!/^\d{4,10}$/.test(clean)) {
      throw new Error(`Codigo invalido: ${clean}`);
    }
    normalized.push(clean);
  }
  return Array.from(new Set(normalized));
}

function safeText(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatPeriodo(metadata) {
  const year = metadata && metadata['a\u00f1o'] ? String(metadata['a\u00f1o']) : '';
  const month = metadata && metadata.mes ? String(metadata.mes).padStart(2, '0') : '';
  if (year && month) {
    const monthName = MESES_BY_VALUE[month] || month;
    return `${monthName.slice(0, 3)} ${year}`;
  }
  return '-';
}

function toRow(result) {
  const metadata = result.metadata || {};
  const filename = result.filename || '-';
  const empresa = metadata.razon_social || '-';
  const tipoMovimiento = metadata.tipo_movimiento || '-';
  const dni = metadata.dni || '-';
  const periodo = formatPeriodo(metadata);
  const estado = result.indexed ? 'Indexado' : 'Pendiente';
  const sizeText = `${Number(result.size_kb || 0).toFixed(2)} KB`;

  return {
    filename,
    empresa,
    tipoMovimiento,
    dni,
    periodo,
    estado,
    downloadUrl: result.download_url || '',
    sizeText
  };
}

function renderStatsFromResults(results) {
  const rows = results.map(toRow);
  const altas = rows.filter(item => item.tipoMovimiento.toUpperCase() === 'ALTA').length;
  const bajas = rows.filter(item => item.tipoMovimiento.toUpperCase() === 'BAJA').length;
  const empresas = new Set(rows.map(item => item.empresa).filter(Boolean)).size;

  document.getElementById('statsTRegistro').innerHTML = `
    <article class="stat-card acrylic-surface stat-border-1">
      <div class="label">Total</div>
      <div class="value">${rows.length}</div>
      <div class="hint">Documentos en resultado v2</div>
    </article>
    <article class="stat-card acrylic-surface stat-border-2">
      <div class="label">Altas</div>
      <div class="value">${altas}</div>
      <div class="hint">Movimientos de alta</div>
    </article>
    <article class="stat-card acrylic-surface stat-border-3">
      <div class="label">Bajas</div>
      <div class="value">${bajas}</div>
      <div class="hint">Movimientos de baja</div>
    </article>
    <article class="stat-card acrylic-surface stat-border-4">
      <div class="label">Empresas</div>
      <div class="value">${empresas}</div>
      <div class="hint">Con resultados</div>
    </article>
  `;
}

function getTotalPages(totalRows) {
  return Math.max(1, Math.ceil(totalRows / PAGE_SIZE));
}

function renderPagination(totalRows) {
  if (!paginationControls || !prevPageBtn || !nextPageBtn || !paginationInfo) {
    return;
  }

  if (totalRows <= PAGE_SIZE) {
    paginationControls.classList.add('hidden');
    return;
  }

  const totalPages = getTotalPages(totalRows);
  paginationControls.classList.remove('hidden');
  paginationInfo.textContent = `Pagina ${currentPage} de ${totalPages}`;
  prevPageBtn.disabled = currentPage <= 1;
  nextPageBtn.disabled = currentPage >= totalPages;
}

function renderRows(results) {
  const rows = results.map(toRow);
  resultCount.textContent = `${rows.length} documentos encontrados`;

  if (rows.length === 0) {
    stateEmpty.classList.remove('hidden');
    stateTable.classList.add('hidden');
    tableBody.innerHTML = '';
    currentPage = 1;
    if (paginationControls) {
      paginationControls.classList.add('hidden');
    }
    return;
  }

  const totalPages = getTotalPages(rows.length);
  if (currentPage > totalPages) {
    currentPage = totalPages;
  }

  const startIndex = (currentPage - 1) * PAGE_SIZE;
  const pageRows = rows.slice(startIndex, startIndex + PAGE_SIZE);

  stateEmpty.classList.add('hidden');
  stateTable.classList.remove('hidden');
  tableBody.innerHTML = pageRows
    .map(row => {
      const fileNameOnly = row.filename.split('/').pop() || row.filename;
      const isAlta = row.tipoMovimiento.toUpperCase() === 'ALTA';
      return `
        <tr>
          <td>
            <div class="fw-500">${safeText(fileNameOnly)}</div>
            <div class="doc-meta">${safeText(row.sizeText)} - ${safeText(row.estado)}</div>
          </td>
          <td>${safeText(row.empresa)}</td>
          <td>${isAlta ? '<span class="badge badge-green">ALTA</span>' : '<span class="badge badge-red">BAJA</span>'}</td>
          <td><span class="badge badge-blue">${safeText(row.dni)}</span></td>
          <td>${safeText(row.periodo)}</td>
          <td>${safeText(row.estado)}</td>
          <td>
            <div class="actions">
              <button
                type="button"
                class="btn btn-sm btn-success-soft js-download"
                data-url="${safeText(row.downloadUrl)}"
                data-name="${safeText(fileNameOnly)}"
                ${row.downloadUrl ? '' : 'disabled'}
              >
                <i class="ti ti-download"></i> Descargar
              </button>
            </div>
          </td>
        </tr>
      `;
    })
    .join('');

  renderPagination(rows.length);
}

async function downloadWithAuth(url, fallbackName) {
  const authed = await ensureAuthToken();
  if (!authed) {
    return;
  }

  const response = await fetch(url, {
    headers: getAuthHeaders(false)
  });

  if (response.status === 401) {
    clearSession();
    redirectToLogin();
    throw new Error('Sesion expirada. Redirigiendo al login.');
  }

  if (!response.ok) {
    throw new Error(`No se pudo descargar el archivo (HTTP ${response.status}).`);
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objectUrl;
  a.download = fallbackName || 'documento.pdf';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}

async function mergeAndDownloadCurrentResults() {
  if (lastResults.length === 0) {
    alert('No hay resultados para descargar.');
    return;
  }

  const authed = await ensureAuthToken();
  if (!authed) {
    return;
  }

  const paths = lastResults
    .map(item => item.filename)
    .filter(Boolean);

  if (paths.length === 0) {
    alert('No hay rutas validas para fusionar.');
    return;
  }

  const response = await fetch(API.merge, {
    method: 'POST',
    headers: getAuthHeaders(true),
    body: JSON.stringify({
      paths,
      output_name: `tregistro_${paths.length}_documentos.pdf`
    })
  });

  if (response.status === 401) {
    clearSession();
    redirectToLogin();
    throw new Error('Sesion expirada. Redirigiendo al login.');
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      detail = body.error || body.detail || detail;
    } catch (error) {
      // keep default detail
    }
    throw new Error(`No se pudo generar descarga consolidada: ${detail}`);
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objectUrl;
  a.download = `tregistro_${paths.length}_documentos.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}

function fillEmpresas(empresas) {
  const select = document.getElementById('empresaSelect');
  const unique = Array.from(new Set((empresas || []).filter(Boolean))).sort((a, b) => a.localeCompare(b));
  select.innerHTML =
    '<option value="">- Todas las empresas -</option>' +
    unique.map(item => `<option value="${safeText(item)}">${safeText(item)}</option>`).join('');
}

function fillPeriodos(anios, meses) {
  const select = document.getElementById('periodoSelect');
  if (!Array.isArray(anios) || anios.length === 0) {
    return;
  }

  const sortedYears = anios
    .map(value => String(value))
    .filter(Boolean)
    .sort((a, b) => Number(b) - Number(a));

  const monthSource = Array.isArray(meses) && meses.length > 0 ? meses : DEFAULT_MESES;
  const monthItems = monthSource
    .map(item => ({ value: String(item.value || '').padStart(2, '0'), label: String(item.label || item.value || '') }))
    .filter(item => item.value && item.label);

  let options = '<option value="">Todos</option>';
  for (const year of sortedYears) {
    for (const month of monthItems) {
      const shortLabel = month.label.slice(0, 3);
      const label = `${shortLabel} ${year}`;
      options += `<option value="${safeText(label)}">${safeText(label)}</option>`;
    }
  }
  select.innerHTML = options;
}

async function loadFilterOptionsIfAuthenticated() {
  if (!authToken) {
    const restored = await restoreSession();
    if (!restored) {
      return;
    }
  }

  try {
    const options = await fetchJson(API.filterOptions, {
      headers: getAuthHeaders(false)
    });
    fillEmpresas(options.razones_sociales || []);
    fillPeriodos(options['a\u00f1os'] || [], options.meses || []);
  } catch (error) {
    console.error('No se pudieron cargar filtros dinamicos:', error);
  }
}

function setMode(mode) {
  document.querySelectorAll('.mode-tab').forEach(btn => btn.classList.toggle('active', btn.dataset.mode === mode));
  document.getElementById('simpleMode').classList.toggle('hidden', mode !== 'simple');
  document.getElementById('masivaMode').classList.toggle('hidden', mode !== 'masiva');
}

function buildPayloadFromForm() {
  const mode = document.querySelector('.mode-tab.active').dataset.mode;
  const empresa = document.getElementById('empresaSelect').value.trim();
  const tipo = document.getElementById('tipoSelect').value.trim();
  const dni = document.getElementById('dniInput').value.trim();
  const periodo = document.getElementById('periodoSelect').value.trim();

  const payload = {};
  if (empresa) {
    payload.razon_social = empresa;
  }
  if (tipo) {
    payload.tipo = tipo;
  }
  if (periodo) {
    payload.periodo = periodo;
  }

  if (mode === 'masiva') {
    const massInput = document.getElementById('dniMasivo').value;
    const codes = validateCodes(parseMasivo(massInput));
    if (codes.length === 0) {
      throw new Error('Ingresa al menos un DNI para busqueda masiva.');
    }
    payload.codigos = codes;
  } else if (dni) {
    const codes = validateCodes([dni]);
    payload.codigo_empleado = codes[0];
  }

  return payload;
}

async function searchApi() {
  const authed = await ensureAuthToken();
  if (!authed) {
    const err = new Error('Redirigiendo al login...');
    err.authRedirect = true;
    throw err;
  }

  const payload = buildPayloadFromForm();
  return fetchJson(API.search, {
    method: 'POST',
    headers: getAuthHeaders(true),
    body: JSON.stringify(payload)
  });
}

function initTopbarControls() {
  SHARED.initTheme();
  const logoutBtn = document.getElementById('logoutBtn');

  if (logoutBtn) {
    logoutBtn.addEventListener('click', async () => {
      await logoutAndRedirect();
    });
  }
}

document.querySelectorAll('.mode-tab').forEach(btn => {
  btn.addEventListener('click', () => setMode(btn.dataset.mode));
});

if (prevPageBtn && nextPageBtn) {
  prevPageBtn.addEventListener('click', () => {
    if (currentPage <= 1) {
      return;
    }
    currentPage -= 1;
    renderRows(lastResults);
  });

  nextPageBtn.addEventListener('click', () => {
    const totalPages = getTotalPages(lastResults.length);
    if (currentPage >= totalPages) {
      return;
    }
    currentPage += 1;
    renderRows(lastResults);
  });
}

document.getElementById('limpiarBtn').addEventListener('click', () => {
  form.reset();
  lastResults = [];
  currentPage = 1;
  renderRows([]);
  renderStatsFromResults([]);
});

document.getElementById('downloadZipBtn').addEventListener('click', async () => {
  try {
    await mergeAndDownloadCurrentResults();
  } catch (error) {
    alert(error.message || 'No fue posible descargar los resultados.');
  }
});

tableBody.addEventListener('click', async event => {
  const button = event.target.closest('.js-download');
  if (!button) {
    return;
  }

  const url = button.dataset.url;
  const name = button.dataset.name || 'documento.pdf';
  if (!url) {
    alert('El documento no tiene URL de descarga.');
    return;
  }

  try {
    button.disabled = true;
    await downloadWithAuth(url, name);
  } catch (error) {
    alert(error.message || 'No se pudo descargar el documento.');
  } finally {
    button.disabled = false;
  }
});

form.addEventListener('submit', async event => {
  event.preventDefault();
  stateLoading.classList.remove('hidden');
  stateEmpty.classList.add('hidden');
  stateTable.classList.add('hidden');

  try {
    const data = await searchApi();
    const results = Array.isArray(data.results) ? data.results : [];
    lastResults = results;
    currentPage = 1;
    renderRows(results);
    renderStatsFromResults(results);

    if (data.comparison && typeof data.comparison.delta !== 'undefined') {
      resultCount.textContent = `${results.length} documentos encontrados | delta legacy: ${data.comparison.delta}`;
    }
  } catch (error) {
    if (error.authRedirect) {
      return;
    }

    if (error.status === 401) {
      clearSession();
      redirectToLogin();
      return;
    }

    alert(error.message || 'No se pudo completar la busqueda.');
    lastResults = [];
    currentPage = 1;
    renderRows([]);
    renderStatsFromResults([]);
  } finally {
    stateLoading.classList.add('hidden');
  }
});

initTopbarControls();
setAuthState(false);
renderSidebarUser();
renderStatsFromResults([]);
renderRows([]);

(async function initSessionAndFilters() {
  const authed = await ensureAuthToken();
  if (!authed) {
    return;
  }

  await loadFilterOptionsIfAuthenticated();
})();
