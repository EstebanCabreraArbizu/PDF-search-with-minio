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

  global.DocSearchShared = {
    applyTheme,
    syncThemeToggle,
    initTheme,
    parseStoredUser,
    renderSidebarUser,
    setAuthState,
    clearSession,
    redirectToLogin,
    fetchJson,
    validateToken
  };
})(window);
