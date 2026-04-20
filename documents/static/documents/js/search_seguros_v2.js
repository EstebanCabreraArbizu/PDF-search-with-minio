const API = {
      me: '/api/me',
      logout: '/api/auth/logout/',
      loginUi: '/ui/login/',
  filterOptions: '/api/v2/filter-options?domain=SEGUROS',
      search: '/api/v2/search/seguros'
    };

    const TOKEN_KEY = 'docsearch_v2_access_token';
    const REFRESH_TOKEN_KEY = 'docsearch_v2_refresh_token';
    const USER_KEY = 'docsearch_v2_user';
    let authToken = null;
    let lastResults = [];

    const SUBTIPOS = {
      Vida: ['Alta', 'Baja', 'Renovacion'],
      EPS: ['Renovacion', 'Afiliacion', 'Exclusion'],
      SCTR: ['Ingreso', 'Cese', 'Rectificacion'],
      Vehicular: ['Reemision', 'Endoso', 'Anulacion']
    };

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

    const THEME_KEY = 'docsearch-theme';
    const DEFAULT_THEME = 'corp';
    const THEMES = [DEFAULT_THEME, 'corp-dark', 'dark', 'light'];
    const THEME_META = {
      corp: { label: 'Tema Corporativo', icon: 'ti ti-adjustments' },
      'corp-dark': { label: 'Tema Corporativo Oscuro', icon: 'ti ti-adjustments-horizontal' },
      dark: { label: 'Tema Oscuro', icon: 'ti ti-moon' },
      light: { label: 'Tema Claro', icon: 'ti ti-sun' }
    };

    const form = document.getElementById('segurosForm');
    const simpleMode = document.getElementById('simpleMode');
    const masivaMode = document.getElementById('masivaMode');
    const tableBody = document.getElementById('tableBody');
    const resultCount = document.getElementById('resultCount');
    const chipDni = document.getElementById('chipDni');
    const stateEmpty = document.getElementById('stateEmpty');
    const stateLoading = document.getElementById('stateLoading');
    const stateTable = document.getElementById('stateTable');
    const paginationControls = document.getElementById('paginationControls');
    const prevPageBtn = document.getElementById('prevPageBtn');
    const nextPageBtn = document.getElementById('nextPageBtn');
    const paginationInfo = document.getElementById('paginationInfo');

    const PAGE_SIZE = 12;
    let currentPage = 1;

    function applyTheme(theme) {
      const safeTheme = THEMES.includes(theme) ? theme : DEFAULT_THEME;
      document.documentElement.setAttribute('data-theme', safeTheme);
      return safeTheme;
    }

    function syncThemeToggle(theme) {
      const themeToggleBtn = document.getElementById('themeToggleBtn');
      const themeToggleIcon = document.getElementById('themeToggleIcon');
      if (!themeToggleBtn || !themeToggleIcon) {
        return;
      }

      const meta = THEME_META[theme] || THEME_META[DEFAULT_THEME];
      themeToggleIcon.className = meta.icon;
      themeToggleBtn.title = `${meta.label} (clic para cambiar)`;
      themeToggleBtn.setAttribute('aria-label', `Tema actual: ${meta.label}. Clic para cambiar.`);
    }

    function setAuthState(connected) {
      const logoutBtn = document.getElementById('logoutBtn');
      if (!logoutBtn) {
        return;
      }
      logoutBtn.title = connected ? 'Cerrar sesion API' : 'Sin sesion API';
      logoutBtn.setAttribute('aria-label', connected ? 'Cerrar sesion API' : 'Sin sesion API');
    }

    function parseStoredUser() {
      try {
        return JSON.parse(localStorage.getItem(USER_KEY) || 'null');
      } catch (error) {
        return null;
      }
    }

    function renderSidebarUser() {
      const user = parseStoredUser();
      const nameNode = document.getElementById('sidebarUserName');
      const roleNode = document.getElementById('sidebarUserRole');

      if (nameNode) {
        nameNode.textContent = user && user.username ? user.username : 'admin';
      }

      if (roleNode) {
        const role = user && user.role ? user.role : 'admin';
        roleNode.textContent = String(role).toUpperCase();
      }
    }

    function clearSession() {
      authToken = null;
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(REFRESH_TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
      setAuthState(false);
      renderSidebarUser();
    }

    function redirectToLogin() {
      const next = `${window.location.pathname}${window.location.search}`;
      window.location.href = `${API.loginUi}?next=${encodeURIComponent(next)}`;
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
      const response = await fetch(url, options);
      const rawText = await response.text();

      let payload = {};
      if (rawText) {
        try {
          payload = JSON.parse(rawText);
        } catch (error) {
          payload = { raw: rawText };
        }
      }

      if (!response.ok) {
        const message = payload.error || payload.detail || payload.message || `HTTP ${response.status}`;
        const err = new Error(message);
        err.status = response.status;
        err.payload = payload;
        throw err;
      }

      return payload;
    }

    async function validateToken(token) {
      try {
        await fetchJson(API.me, {
          headers: {
            Authorization: `Bearer ${token}`
          }
        });
        return true;
      } catch (error) {
        return false;
      }
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
      const empresas = metadata.razon_social || '-';
      const tipo = metadata.tipo_seguro || '-';
      const personas = Number(metadata.asegurados || 0);
      const periodo = formatPeriodo(metadata);
      const estado = result.indexed ? 'Indexado' : 'Pendiente';
      const sizeText = `${Number(result.size_kb || 0).toFixed(2)} KB`;

      return {
        filename,
        empresa: empresas,
        tipo,
        personas,
        periodo,
        estado,
        downloadUrl: result.download_url || '',
        sizeText
      };
    }

    function renderStatsFromResults(results) {
      const rows = results.map(toRow);
      const empresasCount = new Set(rows.map(item => item.empresa).filter(Boolean)).size;
      const tiposCount = new Set(rows.map(item => item.tipo).filter(Boolean)).size;
      const totalAsegurados = rows.reduce((sum, item) => sum + item.personas, 0);

      document.getElementById('statsSeguros').innerHTML = `
        <article class="stat-card acrylic-surface">
          <div class="label">Total Documentos</div>
          <div class="value">${rows.length}</div>
          <div class="hint">Resultado de busqueda v2</div>
        </article>
        <article class="stat-card acrylic-surface">
          <div class="label">Empresas</div>
          <div class="value">${empresasCount}</div>
          <div class="hint">Razones sociales en resultado</div>
        </article>
        <article class="stat-card acrylic-surface">
          <div class="label">Asegurados</div>
          <div class="value">${totalAsegurados}</div>
          <div class="hint">Suma reportada en metadata</div>
        </article>
      `;

      if (rows.length > 0 && tiposCount > 0) {
        const stats = document.getElementById('statsSeguros');
        stats.insertAdjacentHTML(
          'beforeend',
          `
          <article class="stat-card acrylic-surface">
            <div class="label">Tipos de Seguro</div>
            <div class="value">${tiposCount}</div>
            <div class="hint">Diversidad de tipos en resultado</div>
          </article>
        `
        );
      }
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
          return `
            <tr>
              <td>
                <div class="fw-500">${safeText(fileNameOnly)}</div>
                <div class="doc-meta">${safeText(row.sizeText)} - ${safeText(row.estado)}</div>
              </td>
              <td>${safeText(row.empresa)}</td>
              <td><span class="badge badge-blue">${safeText(row.tipo)}</span></td>
              <td><span class="badge badge-blue">${safeText(String(row.personas))} personas</span></td>
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

      let options = '<option value="">- Todos -</option>';
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
      simpleMode.classList.toggle('hidden', mode !== 'simple');
      masivaMode.classList.toggle('hidden', mode !== 'masiva');
      chipDni.classList.add('hidden');
    }

    function resetSubtipoSelect() {
      document.getElementById('subtipoSelect').innerHTML = '<option value="">- Seleccione Tipo primero -</option>';
    }

    function buildPayloadFromForm() {
      const mode = document.querySelector('.mode-tab.active').dataset.mode;
      const empresa = document.getElementById('empresaSelect').value.trim();
      const dni = document.getElementById('dniInput').value.trim();
      const tipo = document.getElementById('tipoSelect').value.trim();
      const subtipo = document.getElementById('subtipoSelect').value.trim();
      const periodo = document.getElementById('periodoSelect').value.trim();

      const payload = {};
      if (empresa) {
        payload.razon_social = empresa;
      }
      if (tipo) {
        payload.tipo = tipo;
      }
      if (subtipo) {
        payload.subtipo = subtipo;
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
        chipDni.textContent = `DNI: ${codes.join(', ')}`;
        chipDni.classList.remove('hidden');
      } else {
        chipDni.classList.add('hidden');
        if (dni) {
          const codes = validateCodes([dni]);
          payload.codigo_empleado = codes[0];
          chipDni.textContent = `DNI: ${payload.codigo_empleado}`;
          chipDni.classList.remove('hidden');
        }
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
      const themeToggleBtn = document.getElementById('themeToggleBtn');
      const logoutBtn = document.getElementById('logoutBtn');

      let storedTheme = DEFAULT_THEME;
      try {
        const themeFromStorage = localStorage.getItem(THEME_KEY);
        storedTheme = themeFromStorage || DEFAULT_THEME;
        if (!themeFromStorage) {
          localStorage.setItem(THEME_KEY, DEFAULT_THEME);
        }
      } catch (error) {
        storedTheme = DEFAULT_THEME;
      }

      const activeTheme = applyTheme(storedTheme);
      syncThemeToggle(activeTheme);

      if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', () => {
          const currentTheme = document.documentElement.getAttribute('data-theme') || DEFAULT_THEME;
          const currentIndex = THEMES.indexOf(currentTheme);
          const nextTheme = THEMES[(currentIndex + 1) % THEMES.length];
          const selectedTheme = applyTheme(nextTheme);
          syncThemeToggle(selectedTheme);
          try {
            localStorage.setItem(THEME_KEY, selectedTheme);
          } catch (error) {
            // localStorage can be blocked by browser policies.
          }
        });
      }

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

    document.getElementById('tipoSelect').addEventListener('change', event => {
      const list = SUBTIPOS[event.target.value] || [];
      document.getElementById('subtipoSelect').innerHTML =
        '<option value="">- Seleccione Tipo primero -</option>' +
        list.map(item => `<option value="${safeText(item)}">${safeText(item)}</option>`).join('');
    });

    document.getElementById('limpiarBtn').addEventListener('click', () => {
      form.reset();
      resetSubtipoSelect();
      chipDni.classList.add('hidden');
      lastResults = [];
      currentPage = 1;
      renderRows([]);
      renderStatsFromResults([]);
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
    resetSubtipoSelect();

    (async function initSessionAndFilters() {
      const authed = await ensureAuthToken();
      if (!authed) {
        return;
      }

      await loadFilterOptionsIfAuthenticated();
    })();
