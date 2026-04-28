/**
 * SEGUROS v2 Search - Refactored to use DocSearchCore App Factory
 */

// Ensure DocSearchCore is available, or wait for it
console.log('[search_seguros] Script loaded, checking DocSearchCore availability...');
if (typeof window.DocSearchCore === 'undefined') {
    console.warn('[search_seguros] DocSearchCore not loaded yet, waiting for DOMContentLoaded...');
    document.addEventListener('DOMContentLoaded', initializeSegurosSearch);
} else {
    // DocSearchCore is already loaded, initialize immediately
    console.log('[search_seguros] DocSearchCore is available, initializing immediately...');
    initializeSegurosSearch();
}

function initializeSegurosSearch() {
    // Get destructured functions from DocSearchCore
    const { createSearchApp, safeText, formatPeriodo, API_PATHS, loadFilterOptions, populateSelect } = window.DocSearchCore;
    
    try {
        console.log('[search_seguros] Initializing theme system...');
        // Initialize theme system - call as methods to preserve 'this' context
        window.DocSearchCore.initTheme();
        window.DocSearchCore.initGlobalUI();  // 🎨 Wire up theme toggle button and other global UI elements
        window.DocSearchCore.syncThemeToggle();
        console.log('[search_seguros] Theme initialization complete');
    } catch (error) {
        console.error('[search_seguros] Error initializing theme:', error);
    }

    // Load dynamic filters
    loadFilterOptions('SEGUROS').then(filters => {
        if (filters) {
            if (filters.razon_social) populateSelect('empresaSelect', filters.razon_social);
            if (filters.tipo_documento) populateSelect('tipoSelect', filters.tipo_documento);
        }
    });

    // Setup filter change listeners for fresh data fetch (re-fetch when user changes filters)
    const tipoSelect = document.getElementById('tipoSelect');
    if (tipoSelect) {
        tipoSelect.addEventListener('change', () => {
            // User changed filter - fresh data could be needed on next search
            sessionStorage.removeItem('filter_options_SEGUROS');
        });
    }

    const app = createSearchApp({
        type: 'seguros',
        apiPaths: API_PATHS,
        formId: 'segurosForm',
        resultsTableId: 'stateTable',
        resultsTableBodyId: 'tableBody',
        paginationContainerId: 'paginationControls',
        emptyStateId: 'stateEmpty',
        loaderId: 'stateLoading',
        simpleFiltersId: 'simpleMode',
        masivoFiltersId: 'masivaMode',
        masivoInputId: 'dniMasivo',
        
        columns: [
            {
                label: 'Documento',
                render: doc => {
                    const name = window.DocSearchCore.formatPathLabel(doc.filename);
                    const sizeText = `${Number(doc.size_kb || 0).toFixed(2)} KB`;
                    return `
                        <div class="fw-500">${safeText(name)}</div>
                        <div class="doc-meta text-xs opacity-70">${safeText(sizeText)}</div>
                    `;
                }
            },
            {
                label: 'Razon Social',
                render: doc => safeText(doc.metadata.razon_social || '—')
            },
            {
                label: 'Tipo',
                render: doc => {
                    const detail = doc.metadata || {};
                    return `
                        <div class="text-sm font-medium">${safeText(detail.tipo_seguro || '—')}</div>
                        <div class="text-xs opacity-70">${safeText(detail.subtipo_seguro || '')}</div>
                    `;
                }
            },
            {
                label: 'Titular',
                render: doc => {
                    const detail = doc.metadata || {};
                    const titular = detail.titular || '—';
                    const dni = detail.dni || '—';
                    return `
                        <div class="text-sm font-medium">${safeText(titular)}</div>
                        <div class="text-xs opacity-70">DNI: ${safeText(dni)}</div>
                    `;
                }
            },
            {
                label: 'Periodo',
                render: doc => formatPeriodo(doc.metadata)
            },
            {
                label: 'Estado',
                render: doc => doc.indexed 
                    ? `<span class="badge badge-success">✓ Indexado</span>` 
                    : `<span class="badge badge-warning">⚠ Pendiente</span>`
            }
        ],

        onBeforeSearch: (params, isMasivo) => {
            const payload = {};
            
            // Collect common filters
            const empresa = document.getElementById('empresaSelect')?.value;
            const tipo = document.getElementById('tipoSelect')?.value;
            const subtipo = document.getElementById('subtipoSelect')?.value;
            const periodo = document.getElementById('periodoSelect')?.value;

            if (empresa) payload.razon_social = empresa;
            if (tipo) payload.tipo = tipo;
            if (subtipo) payload.subtipo = subtipo;
            if (periodo) payload.periodo = periodo;

            if (isMasivo) {
                const massInput = document.getElementById('dniMasivo')?.value || '';
                const codes = massInput.split(/[\s,;\n]+/).map(c => c.trim()).filter(c => c.length >= 4);
                if (codes.length === 0) {
                    window.DocSearchCore.showToast('Ingresa al menos un DNI para busqueda masiva.', 'warning');
                    return null;
                }
                payload.codigos = codes;
            } else {
                const dniSimple = document.getElementById('dniInput')?.value;
                if (dniSimple) payload.codigo_empleado = dniSimple.trim();
            }

            // Convert payload to search params
            Object.keys(payload).forEach(key => {
                if (Array.isArray(payload[key])) {
                    payload[key].forEach(val => params.append(key, val));
                } else {
                    params.append(key, payload[key]);
                }
            });

            return params;
        }
    });

    // Custom Stats for Seguros
    const originalRenderResults = app.renderResults;
    app.renderResults = (results, page) => {
        originalRenderResults(results, page);
        renderStats(results);
    };

    function renderStats(results) {
        const dnis = new Set(results.map(r => r.metadata.dni).filter(Boolean)).size;
        const empresas = new Set(results.map(r => r.metadata.razon_social).filter(Boolean)).size;

        const html = `
            <article class="stat-card acrylic-surface stat-border-1">
                <div class="label">Total</div>
                <div class="value">${results.length}</div>
                <div class="hint">Documentos encontrados</div>
            </article>
            <article class="stat-card acrylic-surface stat-border-2">
                <div class="label">Diferentes DNI</div>
                <div class="value">${dnis}</div>
                <div class="hint">En los resultados</div>
            </article>
            <article class="stat-card acrylic-surface stat-border-3">
                <div class="label">Empresas</div>
                <div class="value">${empresas}</div>
                <div class="hint">Representadas</div>
            </article>
        `;
        
        const statsContainer = document.getElementById('statsSeguros');
        if (statsContainer) statsContainer.innerHTML = html;
    }

    app.init();

    // Reset filters listener
    const limpiarBtn = document.getElementById('limpiarBtn');
    if (limpiarBtn) {
        limpiarBtn.addEventListener('click', () =>
            document.querySelectorAll('select').forEach(s => s.value = '');
            const dniInput = document.getElementById('dniInput');
            if (dniInput) dniInput.value = '';
            const dniMasivo = document.getElementById('dniMasivo');
            if (dniMasivo) dniMasivo.value = '';
            const resultCount = document.getElementById('resultCount');
            if (resultCount) resultCount.textContent = '0 documentos encontrados';
            const stateTable = document.getElementById('stateTable');
            if (stateTable) stateTable.classList.add('hidden');
            const stateEmpty = document.getElementById('stateEmpty');
            if (stateEmpty) stateEmpty.classList.remove('hidden');
            const pagination = document.getElementById('paginationControls');
            if (pagination) pagination.classList.add('hidden');
            const tableBody = document.getElementById('tableBody');
            if (tableBody) tableBody.innerHTML = '';
        );
    }
}
