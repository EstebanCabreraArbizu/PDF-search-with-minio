/**
 * DocSearch V2 - Shared Utilities & Design System Core
 * Provides common functionality and the Search App Factory.
 */
(function(global) {
    'use strict';

    const STORAGE_KEYS = {
        AUTH_TOKEN: 'docsearch_v2_access_token',
        USER_DATA: 'docsearch_v2_user',
        THEME: 'docsearch_theme'
    };

    const API_PATHS = {
        login: '/api/auth/login/',
        logout: '/api/auth/logout/',
        me: '/api/me',
        search: {
            seguros: '/api/v2/seguros/search/',
            constancias: '/api/v2/constancias/search/',
            tregistro: '/api/v2/tregistro/search/'
        },
        download: '/api/v2/documents/',
        filters: '/api/v2/filter-options'
    };

    const MESES_MAP = {
        '01': 'Enero', '02': 'Febrero', '03': 'Marzo', '04': 'Abril',
        '05': 'Mayo', '06': 'Junio', '07': 'Julio', '08': 'Agosto',
        '09': 'Septiembre', '10': 'Octubre', '11': 'Noviembre', '12': 'Diciembre'
    };

    const DocSearchCore = {
        API_PATHS,
        MESES_MAP,

        // --- Auth & Session ---
        getAuthToken() {
            return localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN);
        },

        getAuthHeaders() {
            const token = this.getAuthToken();
            return {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            };
        },

        async ensureAuth() {
            const token = this.getAuthToken();
            if (!token) {
                this.redirectToLogin();
                return null;
            }
            return token;
        },

        redirectToLogin() {
            const current = window.location.pathname;
            if (current !== '/ui/login/') {
                window.location.href = `/ui/login/?next=${encodeURIComponent(current)}`;
            }
        },

        logout() {
            localStorage.removeItem(STORAGE_KEYS.AUTH_TOKEN);
            localStorage.removeItem(STORAGE_KEYS.USER_DATA);
            this.redirectToLogin();
        },

        // --- HTTP ---
        async fetchJson(url, options = {}) {
            const headers = { ...this.getAuthHeaders(), ...(options.headers || {}) };
            const response = await fetch(url, { ...options, headers });
            
            if (response.status === 401 || response.status === 403) {
                this.logout();
                throw new Error('Sesión expirada');
            }
            
            if (!response.ok) {
                const err = await response.json().catch(() => ({ detail: 'Error en la petición' }));
                throw new Error(err.detail || err.error || `HTTP ${response.status}`);
            }
            return response.json();
        },

        async validateToken(meUrl, token) {
            try {
                const response = await fetch(meUrl, {
                    headers: { 'Authorization': `Token ${token}` }
                });
                return response.ok;
            } catch (e) {
                return false;
            }
        },

        // --- UI Helpers ---
        safeText(text) {
            if (text === null || text === undefined) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },

        formatPeriodo(m, map = MESES_MAP) {
            if (!m) return '-';
            const mes = m.mes || m.periodo_mes || '';
            const anio = m.anio || m.año || m.periodo_anio || '';
            const mesName = map[mes] || mes;
            if (!mes && !anio) return '-';
            return `${mesName} ${anio}`.trim();
        },

        showToast(message, type = 'info') {
            let container = document.getElementById('toastContainer');
            if (!container) {
                container = document.createElement('div');
                container.id = 'toastContainer';
                container.className = 'toast-container';
                document.body.appendChild(container);
            }

            const toast = document.createElement('div');
            toast.className = `toast toast-${type} show fade-in`;
            const icon = type === 'success' ? 'check' : type === 'error' ? 'alert-circle' : 'info-circle';
            
            toast.innerHTML = `
                <div class="toast-content">
                    <i class="ti ti-${icon}"></i>
                    <span>${message}</span>
                </div>
                <button class="toast-close">&times;</button>
            `;
            
            container.appendChild(toast);
            const remove = () => {
                toast.classList.replace('fade-in', 'fade-out');
                setTimeout(() => toast.remove(), 300);
            };
            toast.querySelector('.toast-close').onclick = remove;
            setTimeout(remove, 5000);
        },

        initTheme() {
            const current = localStorage.getItem(STORAGE_KEYS.THEME) || 'corp';
            document.documentElement.setAttribute('data-theme', current);
            this.syncThemeToggle();
            return current;
        },

        syncThemeToggle() {
            const icon = document.getElementById('themeToggleIcon');
            if (!icon) return;
            const current = document.documentElement.getAttribute('data-theme');
            icon.className = current === 'dark' ? 'ti ti-moon' : 'ti ti-adjustments';
        },

        setLoading(btn, isLoading, text = 'Cargando...') {
            const el = typeof btn === 'string' ? document.getElementById(btn) : btn;
            if (!el) return;
            el.disabled = isLoading;
            if (isLoading) {
                el.dataset.original = el.innerHTML;
                el.innerHTML = `<span class="spinner-border spinner-border-sm"></span> ${text}`;
            } else if (el.dataset.original) {
                el.innerHTML = el.dataset.original;
            }
        },

        // --- App Factory ---
        createSearchApp(config) {
            const {
                type,
                baseUrl,
                resultsPerPage = 15,
                columns = [],
                // Custom overrides
                renderResults: customRenderResults,
                onBeforeSearch,
                // ID Overrides
                formId = 'searchForm',
                resultsTableId = 'resultsTable',
                resultsTableBodyId = 'resultsTableBody',
                paginationContainerId = 'paginationContainer',
                emptyStateId = 'emptyState',
                loaderId = 'loader',
                tabSimpleId = 'tabSimple',
                tabMasivoId = 'tabMasivo',
                masivoInputId = 'masivoInput',
                simpleFiltersId = 'simpleFilters',
                masivoFiltersId = 'masivoFilters'
            } = config;

            const state = {
                results: [],
                count: 0,
                currentPage: 1,
                isMasivo: false,
                loading: false
            };

            // DOM Elements
            // DOM Elements with fallbacks
            const form = document.getElementById(formId) || document.querySelector('.search-form');
            const resultsTable = document.getElementById(resultsTableId) || document.querySelector('.table');
            const resultsTableBody = document.getElementById(resultsTableBodyId) || document.getElementById('tableBody');
            const paginationContainer = document.getElementById(paginationContainerId) || document.getElementById('paginationControls');
            const emptyState = document.getElementById(emptyStateId) || document.getElementById('stateEmpty');
            const loader = document.getElementById(loaderId) || document.getElementById('stateLoading');
            const tabSimple = document.getElementById(tabSimpleId) || document.querySelector('.mode-tab[data-mode="simple"]');
            const tabMasivo = document.getElementById(tabMasivoId) || document.querySelector('.mode-tab[data-mode="masiva"]');
            const masivoInput = document.getElementById(masivoInputId) || document.getElementById('dniMasivo');

            const init = async () => {
                await DocSearchCore.ensureAuth();
                setupListeners();
                DocSearchCore.initTheme();
                renderUser();
            };

            const setupListeners = () => {
                if (form) {
                    form.onsubmit = (e) => {
                        e.preventDefault();
                        search(1);
                    };
                }

                if (tabSimple) tabSimple.onclick = () => setMode(false);
                if (tabMasivo) tabMasivo.onclick = () => setMode(true);

                // Delegation for downloads
                if (resultsTableBody) {
                    resultsTableBody.onclick = async (e) => {
                        const btn = e.target.closest('.js-download');
                        if (btn) {
                            const id = btn.dataset.id;
                            const url = btn.dataset.url;
                            const name = btn.dataset.name;
                            try {
                                DocSearchCore.showToast('Iniciando descarga...', 'info');
                                if (url) {
                                    if (window.DocSearchShared && window.DocSearchShared.downloadWithAuth) {
                                        await window.DocSearchShared.downloadWithAuth(url, { fallbackName: name });
                                    } else {
                                        const response = await fetch(url, { headers: DocSearchCore.getAuthHeaders() });
                                        if (!response.ok) throw new Error('Error al descargar');
                                        const blob = await response.blob();
                                        const dlUrl = window.URL.createObjectURL(blob);
                                        const a = document.createElement('a');
                                        a.href = dlUrl;
                                        a.download = name;
                                        document.body.appendChild(a);
                                        a.click();
                                        window.URL.revokeObjectURL(dlUrl);
                                        a.remove();
                                    }
                                } else {
                                    await DocSearchCore.downloadFile(id, name);
                                }
                            } catch (err) {
                                DocSearchCore.showToast(err.message, 'error');
                            }
                        }
                    };
                }

                // Global components
                DocSearchCore.initGlobalUI();
            };

            const setMode = (masivo) => {
                state.isMasivo = masivo;
                tabSimple?.classList.toggle('active', !masivo);
                tabMasivo?.classList.toggle('active', masivo);
                
                // Flexible container toggling
                const simpleCont = document.getElementById(simpleFiltersId) || document.getElementById('simpleMode');
                const masivoCont = document.getElementById(masivoFiltersId) || document.getElementById('masivaMode');
                
                simpleCont?.classList.toggle('hidden', masivo);
                masivoCont?.classList.toggle('hidden', !masivo);
            };

            const search = async (page = 1) => {
                if (state.loading) return;
                state.loading = true;
                state.currentPage = page;

                if (loader) loader.classList.remove('hidden');
                DocSearchCore.setLoading('btnSubmit', true);

                try {
                    const params = new URLSearchParams({
                        page,
                        page_size: resultsPerPage
                    });

                    // Add simple filters
                    if (!state.isMasivo && form) {
                        const formData = new FormData(form);
                        for (let [key, value] of formData.entries()) {
                            if (value && key !== 'masivo_input') params.append(key, value);
                        }
                    } else if (state.isMasivo && masivoInput) {
                        const lines = masivoInput.value.split(/[\n,;]/).map(s => s.trim()).filter(Boolean);
                        lines.forEach(l => params.append('q_masivo', l));
                    }

                    let finalParams = params;
                    if (onBeforeSearch) {
                        finalParams = onBeforeSearch(params, state.isMasivo);
                    }

                    const url = `${DocSearchCore.API_PATHS.search[type]}?${finalParams.toString()}`;
                    const data = await DocSearchCore.fetchJson(url);

                    state.results = data.results || [];
                    state.count = data.total !== undefined ? data.total : (data.count || 0);
                    
                    if (!Array.isArray(state.results)) {
                        console.error('API results is not an array:', data);
                        state.results = [];
                    }
                    
                    app.renderResults(state.results, state.currentPage);
                } catch (err) {
                    DocSearchCore.showToast(err.message, 'error');
                } finally {
                    state.loading = false;
                    if (loader) loader.classList.add('hidden');
                    DocSearchCore.setLoading('btnSubmit', false);
                }
            };

            const renderResults = (customResults) => {
                if (!resultsTableBody) return;
                
                const results = customResults || state.results || [];

                if (results.length === 0) {
                    resultsTable?.classList.add('hidden');
                    emptyState?.classList.remove('hidden');
                    if (paginationContainer) paginationContainer.innerHTML = '';
                    return;
                }

                resultsTable?.classList.remove('hidden');
                emptyState?.classList.add('hidden');

                resultsTableBody.innerHTML = results.map(doc => {
                    const decodedPath = decodeURIComponent(doc.filename || '');
                    const name = decodedPath.split('/').pop() || 'documento.pdf';
                    return `
                        <tr>
                            <td>
                                <div class="doc-title" title="${DocSearchCore.safeText(decodedPath)}">${DocSearchCore.safeText(name)}</div>
                                <div class="doc-sub">${DocSearchCore.safeText(doc.size_human || '')}</div>
                            </td>
                            ${columns.map(col => `<td>${col.render(doc)}</td>`).join('')}
                            <td>
                                <button class="btn btn-icon btn-primary js-download" data-id="${doc.id}" data-name="${name}">
                                    <i class="ti ti-download"></i>
                                </button>
                            </td>
                        </tr>
                    `;
                }).join('');

                renderPagination();
            };

            const renderPagination = () => {
                if (!paginationContainer) return;
                const totalPages = Math.ceil(state.count / resultsPerPage);
                if (totalPages <= 1) {
                    paginationContainer.innerHTML = '';
                    return;
                }

                let html = '<ul class="pagination">';
                
                // Prev
                html += `<li class="page-item ${state.currentPage === 1 ? 'disabled' : ''}">
                    <button class="page-link" onclick="window._currentApp.search(${state.currentPage - 1})"><i class="ti ti-chevron-left"></i></button>
                </li>`;

                // Pages (simple)
                for (let i = 1; i <= totalPages; i++) {
                    if (i === 1 || i === totalPages || (i >= state.currentPage - 2 && i <= state.currentPage + 2)) {
                        html += `<li class="page-item ${state.currentPage === i ? 'active' : ''}">
                            <button class="page-link" onclick="window._currentApp.search(${i})">${i}</button>
                        </li>`;
                    } else if (i === state.currentPage - 3 || i === state.currentPage + 3) {
                        html += '<li class="page-item disabled"><span class="page-link">...</span></li>';
                    }
                }

                // Next
                html += `<li class="page-item ${state.currentPage === totalPages ? 'disabled' : ''}">
                    <button class="page-link" onclick="window._currentApp.search(${state.currentPage + 1})"><i class="ti ti-chevron-right"></i></button>
                </li>`;

                html += '</ul>';
                paginationContainer.innerHTML = html;
            };


            const renderUser = () => {
                const user = JSON.parse(localStorage.getItem(STORAGE_KEYS.USER_DATA) || '{}');
                const el = document.getElementById('sidebarUser');
                if (el && user.username) {
                    el.innerHTML = `
                        <div class="user-info">
                            <div class="user-avatar">${user.username[0].toUpperCase()}</div>
                            <div class="user-details">
                                <span class="user-name">${DocSearchCore.safeText(user.username)}</span>
                                <span class="user-role text-xs opacity-60">Usuario</span>
                            </div>
                        </div>
                    `;
                }
            };

            const app = { init, search, state, renderResults, renderPagination };
            window._currentApp = app; // For pagination callbacks
            return app;
        },

        async downloadFile(id, filename) {
            const url = `${this.API_PATHS.download}${id}/download`;
            const response = await fetch(url, { headers: this.getAuthHeaders() });
            if (!response.ok) throw new Error('Error al descargar');
            
            const blob = await response.blob();
            const dlUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = dlUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(dlUrl);
            a.remove();
        },

        initGlobalUI() {
            // Check for both possible IDs for compatibility
            const btnTheme = document.getElementById('themeToggleBtn') || document.getElementById('btnThemeToggle');
            if (btnTheme) {
                btnTheme.onclick = () => {
                    const current = document.documentElement.getAttribute('data-theme');
                    const next = current === 'dark' ? 'corp' : 'dark';
                    document.documentElement.setAttribute('data-theme', next);
                    localStorage.setItem(STORAGE_KEYS.THEME, next);
                    this.syncThemeToggle();
                };
            }

            const btnLogout = document.getElementById('btnLogout');
            if (btnLogout) {
                btnLogout.onclick = () => this.logout();
            }
        }
    };

    global.DocSearchCore = DocSearchCore;
    global.DocSearchShared = DocSearchCore; // Compatibility alias

})(window);


