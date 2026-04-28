/**
 * DocSearch v2 - Search Constancias
 * Powered by UI Core Framework
 */

// Ensure DocSearchCore is available, or wait for it
if (typeof window.DocSearchCore === 'undefined') {
    console.warn('DocSearchCore not loaded yet, waiting...');
    document.addEventListener('DOMContentLoaded', initializeConstanciasSearch);
} else {
    // DocSearchCore is already loaded, initialize immediately
    initializeConstanciasSearch();
}

function initializeConstanciasSearch() {
    const { createSearchApp, safeText, formatPeriodo, API_PATHS, loadFilterOptions, populateSelect } = window.DocSearchCore;
    
    // Initialize theme system - call as methods to preserve 'this' context
    window.DocSearchCore.initTheme();
    window.DocSearchCore.initGlobalUI();  // 🎨 Wire up theme toggle button and other global UI elements
    window.DocSearchCore.syncThemeToggle();

    // Load dynamic filters
    loadFilterOptions('CONSTANCIA_ABONO').then(filters => {
        if (filters) {
            if (filters.razon_social) populateSelect('empresaSelect', filters.razon_social);
            if (filters.banco) populateSelect('bancoSelect', filters.banco);
            if (filters.tipo_documento) populateSelect('planillaSelect', filters.tipo_documento);
        }
    });

    // Setup filter change listeners for fresh data fetch
    const bancoSelect = document.getElementById('bancoSelect');
    if (bancoSelect) {
        bancoSelect.addEventListener('change', () => {
            sessionStorage.removeItem('filter_options_CONSTANCIA_ABONO');
        });
    }

    const mesesMap = {
        '01': 'Enero', '02': 'Febrero', '03': 'Marzo', '04': 'Abril',
        '05': 'Mayo', '06': 'Junio', '07': 'Julio', '08': 'Agosto',
        '09': 'Septiembre', '10': 'Octubre', '11': 'Noviembre', '12': 'Diciembre'
    };

    const app = createSearchApp({
        type: 'constancias',
        apiPaths: API_PATHS,
        formId: 'constanciasForm',
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
                    const name = doc.filename.split('/').pop();
                    return `<div class="font-medium">${safeText(name)}</div>
                            <div class="text-xs text-muted">${safeText(doc.employee_codes.join(', ') || '—')}</div>`;
                }
            },
            { 
                label: 'Razón Social', 
                render: doc => `<div class="truncate max-w-xs" title="${safeText(doc.metadata.razon_social)}">${safeText(doc.metadata.razon_social)}</div>` 
            },
            { 
                label: 'Banco', 
                render: doc => `<span class="text-sm">${safeText(doc.metadata.banco || '—')}</span>` 
            },
            { 
                label: 'Tipo Planilla', 
                render: doc => `<span class="badge badge-info">${safeText(doc.metadata.tipo_planilla || 'Constancia')}</span>` 
            },
            { 
                label: 'Periodo', 
                render: doc => formatPeriodo(doc.metadata, mesesMap) 
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

            const empresa = document.getElementById('empresaSelect')?.value;
            const banco = document.getElementById('bancoSelect')?.value;
            const planilla = document.getElementById('planillaSelect')?.value;
            const periodo = document.getElementById('periodoSelect')?.value;

            if (empresa) payload.razon_social = empresa;
            if (banco) payload.banco = banco;
            if (planilla) payload.payroll_type = planilla;
            if (periodo) payload.periodo = periodo;

            if (isMasivo) {
                const massInput = document.getElementById('dniMasivo')?.value || '';
                const codes = massInput.split(/[\s,;\n]+/).map(c => c.trim()).filter(c => c.length >= 4);
                if (codes.length === 0) {
                    window.DocSearchCore.showToast('Ingresa al menos un codigo para busqueda masiva.', 'warning');
                    return null;
                }
                payload.codigos = codes;
            } else {
                const codigoSimple = document.getElementById('dniInput')?.value;
                if (codigoSimple) payload.codigo_empleado = codigoSimple.trim();
            }

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

    app.init();

    // Reset filters listener
    const limpiarBtn = document.getElementById('limpiarBtn');
    if (limpiarBtn) {
        limpiarBtn.addEventListener('click', () => {
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
        });
    }
}
