/**
 * T-REGISTRO v2 Search - Refactored to use DocSearchCore App Factory
 */
document.addEventListener('DOMContentLoaded', () => {
    const { createSearchApp, safeText, formatPeriodo, API_PATHS } = window.DocSearchCore;

    const app = createSearchApp({
        type: 'tregistro',
        apiPaths: API_PATHS,
        formId: 'tregistroForm',
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
                    const fileNameOnly = doc.filename.split('/').pop() || doc.filename;
                    const sizeText = `${Number(doc.size_kb || 0).toFixed(2)} KB`;
                    const estado = doc.indexed ? 'Indexado' : 'Pendiente';
                    return `
                        <div class="fw-500">${safeText(fileNameOnly)}</div>
                        <div class="doc-meta">${safeText(sizeText)} - ${safeText(estado)}</div>
                    `;
                }
            },
            {
                label: 'Razon Social',
                render: doc => safeText(doc.metadata.razon_social || '—')
            },
            {
                label: 'Movimiento',
                render: doc => {
                    const mov = (doc.metadata.tipo_movimiento || '—').toUpperCase();
                    const badge = mov === 'ALTA' ? 'badge-green' : (mov === 'BAJA' ? 'badge-red' : 'badge-blue');
                    return `<span class="badge ${badge}">${safeText(mov)}</span>`;
                }
            },
            {
                label: 'Persona',
                render: doc => {
                    const detail = doc.metadata || {};
                    const titular = detail.nombre_trabajador || detail.titular || '—';
                    const dni = detail.dni || '—';
                    return `
                        <div class="fw-500">${safeText(titular)}</div>
                        <div class="doc-meta">DNI: <span class="badge badge-blue">${safeText(dni)}</span></div>
                    `;
                }
            },
            {
                label: 'Periodo',
                render: doc => formatPeriodo(doc.metadata)
            },
            {
                label: 'Acciones',
                render: doc => {
                    const fileNameOnly = doc.filename.split('/').pop() || doc.filename;
                    return `
                        <div class="actions">
                            <button
                                type="button"
                                class="btn btn-sm btn-success-soft js-download"
                                data-url="${safeText(doc.download_url)}"
                                data-name="${safeText(fileNameOnly)}"
                                ${doc.download_url ? '' : 'disabled'}
                            >
                                <i class="ti ti-download"></i> Descargar
                            </button>
                        </div>
                    `;
                }
            }
        ],

        onBeforeSearch: (params, isMasivo) => {
            const payload = {};
            
            const empresa = document.getElementById('empresaSelect')?.value;
            const tipo = document.getElementById('tipoSelect')?.value;
            const periodo = document.getElementById('periodoSelect')?.value;

            if (empresa) payload.razon_social = empresa;
            if (tipo) payload.tipo = tipo;
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

    // Custom Stats for T-Registro
    const originalRenderResults = app.renderResults;
    app.renderResults = (results, page) => {
        originalRenderResults(results, page);
        renderStats(results);
    };

    function renderStats(results) {
        const altas = results.filter(r => (r.metadata.tipo_movimiento || '').toUpperCase() === 'ALTA').length;
        const bajas = results.filter(r => (r.metadata.tipo_movimiento || '').toUpperCase() === 'BAJA').length;
        const empresas = new Set(results.map(r => r.metadata.razon_social).filter(Boolean)).size;

        const html = `
            <article class="stat-card acrylic-surface stat-border-1">
                <div class="label">Total</div>
                <div class="value">${results.length}</div>
                <div class="hint">Documentos encontrados</div>
            </article>
            <article class="stat-card acrylic-surface stat-border-2">
                <div class="label">Altas</div>
                <div class="value">${altas}</div>
                <div class="hint">Movimientos de alta</div>
            </article>
            <article class="stat-card acrylic-surface stat-border-3">
                <div class="label">Bajas</div>
                <div class="value">${bajas}</div>
                <div class="hint">Movimientos de baja</div>
            </article>
            <article class="stat-card acrylic-surface stat-border-4">
                <div class="label">Empresas</div>
                <div class="value">${empresas}</div>
                <div class="hint">Con resultados</div>
            </article>
        `;
        
        const statsContainer = document.getElementById('statsTRegistro');
        if (statsContainer) statsContainer.innerHTML = html;
    }

    app.init();
});
