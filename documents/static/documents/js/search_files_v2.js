const API = {
  me: '/api/me',
  logout: '/api/auth/logout/',
  loginUi: '/ui/login/'
};

const TOKEN_KEY = 'docsearch_v2_access_token';
const REFRESH_TOKEN_KEY = 'docsearch_v2_refresh_token';
const USER_KEY = 'docsearch_v2_user';

const THEME_KEY = 'docsearch-theme';
const DEFAULT_THEME = 'corp';
const THEMES = [DEFAULT_THEME, 'corp-dark', 'dark', 'light'];
const THEME_META = {
  corp: { label: 'Tema Corporativo', icon: 'ti ti-adjustments' },
  'corp-dark': { label: 'Tema Corporativo Oscuro', icon: 'ti ti-adjustments-horizontal' },
  dark: { label: 'Tema Oscuro', icon: 'ti ti-moon' },
  light: { label: 'Tema Claro', icon: 'ti ti-sun' }
};

let authToken = null;

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

function initTheme() {
  const themeToggleBtn = document.getElementById('themeToggleBtn');

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

  if (!themeToggleBtn) {
    return;
  }

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

function setAuthState(connected) {
  const logoutBtn = document.getElementById('logoutBtn');
  if (!logoutBtn) {
    return;
  }
  logoutBtn.title = connected ? 'Cerrar sesion API' : 'Sin sesion API';
  logoutBtn.setAttribute('aria-label', connected ? 'Cerrar sesion API' : 'Sin sesion API');
}

function clearSession() {
  authToken = null;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  setAuthState(false);
}

function redirectToLogin() {
  const next = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  window.location.href = `${API.loginUi}?next=${encodeURIComponent(next)}`;
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
      headers: { Authorization: `Bearer ${token}` }
    });
    return true;
  } catch (error) {
    return false;
  }
}

async function restoreSession() {
  const stored = localStorage.getItem(TOKEN_KEY);
  if (!stored) {
    return false;
  }

  authToken = stored;
  const isValid = await validateToken(stored);
  if (!isValid) {
    clearSession();
    return false;
  }

  setAuthState(true);
  return true;
}

async function logout() {
  const token = authToken;
  clearSession();

  if (token) {
    try {
      await fetchJson(API.logout, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` }
      });
    } catch (error) {
      // Ignore backend logout errors and force local logout.
    }
  }

  redirectToLogin();
}

function bindActions() {
  const logoutBtn = document.getElementById('logoutBtn');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', logout);
  }
}

function focusSectionFromQuery() {
  const params = new URLSearchParams(window.location.search);
  const section = String(params.get('section') || '').toLowerCase();

  if (section === 'sync') {
    const syncSection = document.getElementById('sync-section');
    if (syncSection) {
      syncSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }
}

async function bootstrap() {
  initTheme();
  renderSidebarUser();

  const hasSession = await restoreSession();
  if (!hasSession) {
    redirectToLogin();
    return;
  }

  bindActions();
  focusSectionFromQuery();
}

bootstrap();
