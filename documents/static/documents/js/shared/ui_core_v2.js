(function initDocSearchShared(global) {
  if (!global || global.DocSearchShared) {
    return;
  }

  const DEFAULT_THEME_KEY = 'docsearch-theme';
  const DEFAULT_THEME = 'corp';
  const DEFAULT_THEMES = [DEFAULT_THEME, 'corp-dark', 'dark', 'light'];
  const DEFAULT_THEME_META = {
    corp: { label: 'Tema Corporativo', icon: 'ti ti-adjustments' },
    'corp-dark': { label: 'Tema Corporativo Oscuro', icon: 'ti ti-adjustments-horizontal' },
    dark: { label: 'Tema Oscuro', icon: 'ti ti-moon' },
    light: { label: 'Tema Claro', icon: 'ti ti-sun' }
  };

  const DEFAULT_TOKEN_KEY = 'docsearch_v2_access_token';
  const DEFAULT_REFRESH_TOKEN_KEY = 'docsearch_v2_refresh_token';
  const DEFAULT_USER_KEY = 'docsearch_v2_user';

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

  function resolveThemeConfig(options) {
    const config = options || {};
    return {
      themeKey: config.themeKey || DEFAULT_THEME_KEY,
      defaultTheme: config.defaultTheme || DEFAULT_THEME,
      themes: Array.isArray(config.themes) && config.themes.length > 0 ? config.themes : DEFAULT_THEMES,
      themeMeta: config.themeMeta || DEFAULT_THEME_META,
      toggleButtonId: config.toggleButtonId || 'themeToggleBtn',
      toggleIconId: config.toggleIconId || 'themeToggleIcon'
    };
  }

  function applyTheme(theme, options) {
    const config = resolveThemeConfig(options);
    const safeTheme = config.themes.includes(theme) ? theme : config.defaultTheme;
    document.documentElement.setAttribute('data-theme', safeTheme);
    return safeTheme;
  }

  function syncThemeToggle(theme, options) {
    const config = resolveThemeConfig(options);
    const themeToggleBtn = document.getElementById(config.toggleButtonId);
    const themeToggleIcon = document.getElementById(config.toggleIconId);
    if (!themeToggleBtn || !themeToggleIcon) {
      return;
    }

    const fallbackMeta = { label: 'Tema', icon: 'ti ti-adjustments' };
    const meta = config.themeMeta[theme] || config.themeMeta[config.defaultTheme] || fallbackMeta;
    themeToggleIcon.className = meta.icon;
    themeToggleBtn.title = `${meta.label} (clic para cambiar)`;
    themeToggleBtn.setAttribute('aria-label', `Tema actual: ${meta.label}. Clic para cambiar.`);
  }

  function initTheme(options) {
    const config = resolveThemeConfig(options);
    const themeToggleBtn = document.getElementById(config.toggleButtonId);

    let storedTheme = config.defaultTheme;
    try {
      const themeFromStorage = localStorage.getItem(config.themeKey);
      storedTheme = themeFromStorage || config.defaultTheme;
      if (!themeFromStorage) {
        localStorage.setItem(config.themeKey, config.defaultTheme);
      }
    } catch (error) {
      storedTheme = config.defaultTheme;
    }

    const activeTheme = applyTheme(storedTheme, config);
    syncThemeToggle(activeTheme, config);

    if (!themeToggleBtn) {
      return activeTheme;
    }

    themeToggleBtn.addEventListener('click', () => {
      const currentTheme = document.documentElement.getAttribute('data-theme') || config.defaultTheme;
      const currentIndex = config.themes.indexOf(currentTheme);
      const safeIndex = currentIndex === -1 ? 0 : currentIndex;
      const nextTheme = config.themes[(safeIndex + 1) % config.themes.length];
      const selectedTheme = applyTheme(nextTheme, config);
      syncThemeToggle(selectedTheme, config);
      try {
        localStorage.setItem(config.themeKey, selectedTheme);
      } catch (error) {
        // localStorage can be blocked by browser policies.
      }
    });

    return activeTheme;
  }

  function parseStoredUser(userKey) {
    const safeUserKey = userKey || DEFAULT_USER_KEY;
    try {
      return JSON.parse(localStorage.getItem(safeUserKey) || 'null');
    } catch (error) {
      return null;
    }
  }

  function renderSidebarUser(options) {
    const config = options || {};
    const user = parseStoredUser(config.userKey || DEFAULT_USER_KEY);
    const fallbackName = config.fallbackName || 'admin';
    const fallbackRole = config.fallbackRole || 'admin';
    const nameNode = document.getElementById(config.nameId || 'sidebarUserName');
    const roleNode = document.getElementById(config.roleId || 'sidebarUserRole');

    if (nameNode) {
      nameNode.textContent = user && user.username ? user.username : fallbackName;
    }

    if (roleNode) {
      const role = user && user.role ? user.role : fallbackRole;
      roleNode.textContent = String(role).toUpperCase();
    }
  }

  function setAuthState(connected, options) {
    const config = options || {};
    const logoutBtn = document.getElementById(config.logoutButtonId || 'logoutBtn');
    if (!logoutBtn) {
      return;
    }

    const connectedLabel = config.connectedLabel || 'Cerrar sesion API';
    const disconnectedLabel = config.disconnectedLabel || 'Sin sesion API';
    const label = connected ? connectedLabel : disconnectedLabel;
    logoutBtn.title = label;
    logoutBtn.setAttribute('aria-label', label);
  }

  function clearSession(options) {
    const config = options || {};
    const tokenKey = config.tokenKey || DEFAULT_TOKEN_KEY;
    const refreshTokenKey = config.refreshTokenKey || DEFAULT_REFRESH_TOKEN_KEY;
    const userKey = config.userKey || DEFAULT_USER_KEY;

    localStorage.removeItem(tokenKey);
    localStorage.removeItem(refreshTokenKey);
    localStorage.removeItem(userKey);

    if (config.updateUi !== false) {
      setAuthState(false, config);
      renderSidebarUser({
        userKey,
        fallbackName: config.fallbackName,
        fallbackRole: config.fallbackRole,
        nameId: config.nameId,
        roleId: config.roleId
      });
    }
  }

  function redirectToLogin(loginUiUrl, options) {
    const config = options || {};
    const loginUrl = loginUiUrl || '/ui/login/';
    const hash = config.includeHash ? window.location.hash : '';
    const next = `${window.location.pathname}${window.location.search}${hash}`;
    window.location.href = `${loginUrl}?next=${encodeURIComponent(next)}`;
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options || {});
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

  async function validateToken(meUrl, token) {
    if (!meUrl || !token) {
      return false;
    }

    try {
      await fetchJson(meUrl, {
        headers: {
          Authorization: `Bearer ${token}`
        }
      });
      return true;
    } catch (error) {
      return false;
    }
  }

  function getAuthHeaders(token, withJsonBody = false) {
    const headers = { Authorization: `Bearer ${token}` };
    if (withJsonBody) {
      headers['Content-Type'] = 'application/json';
    }
    return headers;
  }

  async function logoutAndRedirect(options) {
    const config = options || {};
    const apiUrl = config.apiUrl;
    const token = config.authToken;

    if (apiUrl && token) {
      try {
        await fetchJson(apiUrl, {
          method: 'POST',
          headers: getAuthHeaders(token)
        });
      } catch (error) {
        console.warn('Logout API call failed:', error);
      }
    }

    clearSession({
      tokenKey: config.tokenKey,
      refreshTokenKey: config.refreshTokenKey,
      userKey: config.userKey,
      updateUi: false
    });
    setAuthState(false, config);
    redirectToLogin(config.loginUiUrl, config);
  }

  async function restoreSession(options) {
    const config = options || {};
    const tokenKey = config.tokenKey || DEFAULT_TOKEN_KEY;
    const userKey = config.userKey || DEFAULT_USER_KEY;
    const apiMe = config.apiMe || '/api/me';

    const token = localStorage.getItem(tokenKey);
    if (!token) return null;

    const isValid = await validateToken(apiMe, token);
    if (!isValid) return null;

    const user = parseStoredUser(userKey);
    if (!user) return null;

    return token;
  }

  async function ensureAuthToken(options) {
    const config = options || {};
    if (config.currentToken) return true;

    const token = await restoreSession(config);
    if (token) {
      if (config.onSuccess) config.onSuccess(token);
      return true;
    }

    if (config.onFailure) config.onFailure();
    return false;
  }

  async function downloadWithAuth(url, options) {
    const config = options || {};
    const fallbackName = config.fallbackName || 'documento.pdf';

    const hasToken = await ensureAuthToken(config);
    if (!hasToken) return;

    const token = config.currentToken || localStorage.getItem(config.tokenKey || DEFAULT_TOKEN_KEY);

    const response = await fetch(url, {
      headers: getAuthHeaders(token, false)
    });

    if (response.status === 401) {
      if (config.onFailure) config.onFailure();
      throw new Error('Sesion expirada. Redirigiendo al login.');
    }

    if (!response.ok) {
      throw new Error(`No se pudo descargar el archivo (HTTP ${response.status}).`);
    }

    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = objectUrl;
    a.download = fallbackName;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(objectUrl);
  }

  function safeText(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function parseMasivo(raw) {
    return String(raw || '')
      .split(/[\n,;\s]+/)
      .map(value => value.trim())
      .filter(Boolean);
  }

  function normalizeCode(code) {
    return String(code || '').trim();
  }

  function validateCodes(codes, pattern = /^\d{4,10}$/) {
    const normalized = [];
    for (const code of codes) {
      const clean = normalizeCode(code);
      if (!clean) continue;
      if (!pattern.test(clean)) {
        throw new Error(`Codigo invalido: ${clean}`);
      }
      normalized.push(clean);
    }
    return Array.from(new Set(normalized));
  }

  function getTotalPages(totalRows, pageSize) {
    return Math.max(1, Math.ceil(totalRows / (pageSize || 12)));
  }

  function formatPeriodo(metadata) {
    if (!metadata) return 'N/A';
    const mes = metadata.mes ? (MESES_BY_VALUE[metadata.mes] || metadata.mes) : '';
    const anio = metadata.anio || '';
    if (mes && anio) return `${mes} ${anio}`;
    return mes || anio || 'N/A';
  }

  function fillSelect(el, items, placeholder = '- Seleccionar -') {
    if (!el) return;
    el.innerHTML = `<option value="">${placeholder}</option>` +
      items.map(item => {
        const val = typeof item === 'object' ? item.value : item;
        const label = typeof item === 'object' ? item.label : item;
        return `<option value="${val}">${label}</option>`;
      }).join('');
  }

  function showLoader(el, show) {
    if (!el) return;
    el.classList.toggle('active', show);
  }

  function initTopbarControls(options) {
    const config = options || {};
    const logoutBtn = document.getElementById(config.logoutButtonId || 'logoutBtn');
    if (logoutBtn && config.onLogout) {
      logoutBtn.addEventListener('click', config.onLogout);
    }
  }

  function renderPagination(container, totalPages, currentPage, onPageChange) {
    if (!container) return;
    container.innerHTML = '';
    if (totalPages <= 1) return;

    const nav = document.createElement('nav');
    nav.setAttribute('aria-label', 'Navegacion de resultados');
    const ul = document.createElement('ul');
    ul.className = 'pagination';

    // Previous
    const prevLi = document.createElement('li');
    prevLi.className = `page-item ${currentPage === 1 ? 'disabled' : ''}`;
    const prevA = document.createElement('a');
    prevA.className = 'page-link';
    prevA.href = '#';
    prevA.innerHTML = '<i class="ti ti-chevron-left"></i>';
    prevA.addEventListener('click', (e) => {
      e.preventDefault();
      if (currentPage > 1) onPageChange(currentPage - 1);
    });
    prevLi.appendChild(prevA);
    ul.appendChild(prevLi);

    // Dynamic Pages (simplified)
    const maxVisible = 5;
    let startPage = Math.max(1, currentPage - Math.floor(maxVisible / 2));
    let endPage = Math.min(totalPages, startPage + maxVisible - 1);
    
    if (endPage - startPage + 1 < maxVisible) {
      startPage = Math.max(1, endPage - maxVisible + 1);
    }

    if (startPage > 1) {
      const firstLi = document.createElement('li');
      firstLi.className = 'page-item';
      const firstA = document.createElement('a');
      firstA.className = 'page-link';
      firstA.textContent = '1';
      firstA.addEventListener('click', (e) => { e.preventDefault(); onPageChange(1); });
      firstLi.appendChild(firstA);
      ul.appendChild(firstLi);
      if (startPage > 2) {
        const dots = document.createElement('li');
        dots.className = 'page-item disabled';
        dots.innerHTML = '<span class="page-link">...</span>';
        ul.appendChild(dots);
      }
    }

    for (let i = startPage; i <= endPage; i++) {
      const li = document.createElement('li');
      li.className = `page-item ${i === currentPage ? 'active' : ''}`;
      const a = document.createElement('a');
      a.className = 'page-link';
      a.href = '#';
      a.textContent = i;
      a.addEventListener('click', (e) => {
        e.preventDefault();
        onPageChange(i);
      });
      li.appendChild(a);
      ul.appendChild(li);
    }

    if (endPage < totalPages) {
      if (endPage < totalPages - 1) {
        const dots = document.createElement('li');
        dots.className = 'page-item disabled';
        dots.innerHTML = '<span class="page-link">...</span>';
        ul.appendChild(dots);
      }
      const lastLi = document.createElement('li');
      lastLi.className = 'page-item';
      const lastA = document.createElement('a');
      lastA.className = 'page-link';
      lastA.textContent = totalPages;
      lastA.addEventListener('click', (e) => { e.preventDefault(); onPageChange(totalPages); });
      lastLi.appendChild(lastA);
      ul.appendChild(lastLi);
    }

    // Next
    const nextLi = document.createElement('li');
    nextLi.className = `page-item ${currentPage === totalPages ? 'disabled' : ''}`;
    const nextA = document.createElement('a');
    nextA.className = 'page-link';
    nextA.href = '#';
    nextA.innerHTML = '<i class="ti ti-chevron-right"></i>';
    nextA.addEventListener('click', (e) => {
      e.preventDefault();
      if (currentPage < totalPages) onPageChange(currentPage + 1);
    });
    nextLi.appendChild(nextA);
    ul.appendChild(nextLi);

    nav.appendChild(ul);
    container.appendChild(nav);
  }

  const API_PATHS = {
    auth: {
      me: '/api/me/',
      login: '/api/token/',
      refresh: '/api/token/refresh/',
      logout: '/api/logout/'
    },
    search: {
      files: '/api/documents/search_files/',
      constancias: '/api/documents/search_constancias/',
      seguros: '/api/documents/search_seguros/',
      tregistro: '/api/documents/search_tregistro/'
    },
    download: '/api/documents/download/'
  };

  function setupMasivoToggle(toggleId, singleGroupId, masivoGroupId, masivoInputId) {
    const toggle = document.getElementById(toggleId);
    const singleGroup = document.getElementById(singleGroupId);
    const masivoGroup = document.getElementById(masivoGroupId);
    const masivoInput = document.getElementById(masivoInputId);

    if (!toggle || !singleGroup || !masivoGroup) return;

    toggle.addEventListener('change', () => {
      const isMasivo = toggle.checked;
      singleGroup.style.display = isMasivo ? 'none' : 'block';
      masivoGroup.style.display = isMasivo ? 'block' : 'none';
      if (!isMasivo && masivoInput) masivoInput.value = '';
    });
  }

  global.DocSearchShared = {
    API_PATHS,
    DEFAULT_MESES,
    MESES_BY_VALUE,
    applyTheme,
    syncThemeToggle,
    initTheme,
    parseStoredUser,
    renderSidebarUser,
    setAuthState,
    clearSession,
    redirectToLogin,
    fetchJson,
    validateToken,
    getAuthHeaders,
    logoutAndRedirect,
    restoreSession,
    ensureAuthToken,
    downloadWithAuth,
    safeText,
    parseMasivo,
    normalizeCode,
    validateCodes,
    getTotalPages,
    formatPeriodo,
    initTopbarControls,
    renderPagination,
    fillSelect,
    showLoader,
    setupMasivoToggle
  };
})(window);
