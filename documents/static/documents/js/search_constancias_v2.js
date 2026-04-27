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
            if (isMasivo) {
                // Core handles masivoInput validation/parsing if configured, 
                // but we can add extra logic here if needed.
            }
            return params;
        }
    });

    app.init();
}
