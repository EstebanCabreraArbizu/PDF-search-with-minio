const API = {
  login: '/api/auth/login/',
  me: '/api/me'
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

const DEFAULT_NEXT = '/ui/seguros/';

const form = document.getElementById('loginForm');
const usernameInput = document.getElementById('usernameInput');
const passwordInput = document.getElementById('passwordInput');
const submitBtn = document.getElementById('loginSubmitBtn');
const errorNode = document.getElementById('loginError');
const nextHintNode = document.getElementById('loginNextHint');

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

function parseNextPath() {
  const params = new URLSearchParams(window.location.search);
  const raw = String(params.get('next') || '').trim();
  if (!raw.startsWith('/')) {
    return DEFAULT_NEXT;
  }
  if (raw.startsWith('//') || raw.includes('://') || raw.startsWith('/ui/login/')) {
    return DEFAULT_NEXT;
  }
  return raw;
}

function setError(message) {
  if (!errorNode) {
    return;
  }
  if (!message) {
    errorNode.textContent = '';
    errorNode.classList.add('hidden');
    return;
  }
  errorNode.textContent = message;
  errorNode.classList.remove('hidden');
}

function setLoadingState(loading) {
  if (!submitBtn) {
    return;
  }
  submitBtn.disabled = loading;
  submitBtn.innerHTML = loading
    ? '<i class="ti ti-loader-2"></i> Validando...'
    : '<i class="ti ti-login-2"></i> Entrar al sistema';
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
  if (!token) {
    return false;
  }
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

function clearStoredSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

function persistSession(payload) {
  localStorage.setItem(TOKEN_KEY, payload.access);
  if (payload.refresh) {
    localStorage.setItem(REFRESH_TOKEN_KEY, payload.refresh);
  } else {
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  }

  if (payload.user) {
    localStorage.setItem(USER_KEY, JSON.stringify(payload.user));
  } else {
    localStorage.removeItem(USER_KEY);
  }
}

async function tryAutoRedirect(nextPath) {
  const storedToken = localStorage.getItem(TOKEN_KEY);
  if (!storedToken) {
    return;
  }

  const isValid = await validateToken(storedToken);
  if (!isValid) {
    clearStoredSession();
    return;
  }

  window.location.replace(nextPath);
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  setError('');

  const username = String(usernameInput.value || '').trim();
  const password = String(passwordInput.value || '');

  if (!username || !password) {
    setError('Ingresa usuario y password para continuar.');
    return;
  }

  setLoadingState(true);
  const nextPath = parseNextPath();

  try {
    const auth = await fetchJson(API.login, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ username, password })
    });

    if (!auth.access) {
      throw new Error('No se recibio token de acceso.');
    }

    persistSession(auth);
    window.location.replace(nextPath);
  } catch (error) {
    setError(error.message || 'No fue posible iniciar sesion.');
  } finally {
    setLoadingState(false);
  }
});

(async function init() {
  initTheme();
  const nextPath = parseNextPath();
  if (nextHintNode) {
    nextHintNode.textContent = 'Ingresa tus credenciales para continuar.';
  }

  await tryAutoRedirect(nextPath);

  if (usernameInput) {
    usernameInput.focus();
  }
})();
