const API = {
  login: '/api/auth/login/',
  me: '/api/me'
};

const TOKEN_KEY = 'docsearch_v2_access_token';
const REFRESH_TOKEN_KEY = 'docsearch_v2_refresh_token';
const USER_KEY = 'docsearch_v2_user';

const SHARED = window.DocSearchShared;
if (!SHARED) {
  throw new Error('DocSearchShared no disponible. Verifica la carga de scripts base.');
}

const DEFAULT_NEXT = '/ui/constancias/';

const form = document.getElementById('loginForm');
const usernameInput = document.getElementById('usernameInput');
const passwordInput = document.getElementById('passwordInput');
const submitBtn = document.getElementById('loginSubmitBtn');
const errorNode = document.getElementById('loginError');
const nextHintNode = document.getElementById('loginNextHint');

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

  const isValid = await SHARED.validateToken(API.me, storedToken);
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
    const auth = await SHARED.fetchJson(API.login, {
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
  SHARED.initTheme();
  SHARED.initGlobalUI();  // 🎨 Setup theme toggle button and other global UI elements
  const nextPath = parseNextPath();
  if (nextHintNode) {
    nextHintNode.textContent = 'Ingresa tus credenciales para continuar.';
  }

  await tryAutoRedirect(nextPath);

  if (usernameInput) {
    usernameInput.focus();
  }
})();
