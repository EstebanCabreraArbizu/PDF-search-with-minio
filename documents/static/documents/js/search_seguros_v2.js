/**
 * SEGUROS v2 Search - Refactored to use DocSearchCore App Factory
 */
document.addEventListener('DOMContentLoaded', () => {
    const { createSearchApp, safeText, formatPeriodo, API_PATHS } = window.DocSearchCore;

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
                    const decodedPath = decodeURIComponent(doc.filename || '');
                    const fileNameOnly = decodedPath.split('/').pop() || decodedPath;
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
                label: 'Tipo',
                render: doc => {
                    const detail = doc.metadata || {};
                    return `
                        <div class="fw-500">${safeText(detail.tipo_seguro || '—')}</div>
                        <div class="doc-meta">${safeText(detail.subtipo_seguro || '')}</div>
                    `;
                }
            },
            {
                label: 'PERSONAS DETECTADAS',
                render: doc => {
                    const detail = doc.metadata || {};
                    const titular = detail.titular || '—';
                    const dni = detail.dni || '—';
                    return `
                        <div class="fw-500">${safeText(titular)}</div>
                        <div class="doc-meta">DNI: ${safeText(dni)}</div>
                    `;
                }
            },
            {
                label: 'Periodo',
                render: doc => formatPeriodo(doc.metadata)
            },
            {
                label: 'Fecha Carga',
                render: doc => doc.created_at ? new Date(doc.created_at).toLocaleDateString() : '—'
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
});
