/**
 * DocSearch V2 - T-Registro Logic
 */
(function(DS) {
    'use strict';

    document.addEventListener('DOMContentLoaded', async () => {
        // 1. Auth check
        const token = await DS.ensureAuthToken();
        if (!token) return;

        // 2. Initialize UI
        DS.initTheme();
        DS.initTopbarControls();
        DS.renderSidebarUser();

        // 3. Setup Masivo Toggle
        const cbMasivo = document.getElementById('checkMasivo');
        const containerMasivo = document.getElementById('masivoContainer');
        if (cbMasivo && containerMasivo) {
            cbMasivo.onchange = () => containerMasivo.classList.toggle('d-none', !cbMasivo.checked);
        }

        // 4. Initialize Search App
        const app = DS.createSearchApp({
            endpoint: DS.API_PATHS.search.tregistro,
            formId: 'searchForm',
            resultsContainerId: 'resultsTableBody',
            paginationContainerId: 'paginationContainer',
            renderRow: (doc) => {
                return `
                    <tr>
                        <td>
                            <div class="d-flex align-items-center">
                                <div class="file-icon-sm me-3">
                                    <i class="ti ti-file-text"></i>
                                </div>
                                <div>
                                    <div class="fw-bold text-dark">${DS.safeText(doc.documento_identidad)}</div>
                                    <small class="text-muted">${DS.safeText(doc.tipo_trabajador || 'Trabajador')}</small>
                                </div>
                            </div>
                        </td>
                        <td>${DS.safeText(doc.nombre_completo || '-')}</td>
                        <td>
                            <span class="badge bg-soft-primary text-primary">
                                ${DS.safeText(doc.tipo_documento)}
                            </span>
                        </td>
                        <td>
                            <div class="d-flex flex-column">
                                <span class="fw-medium">${DS.safeText(doc.anio || doc.periodo_anio)}</span>
                                <small class="text-muted">${DS.safeText(doc.mes || doc.periodo_mes)}</small>
                            </div>
                        </td>
                        <td>
                            <div class="d-flex gap-2">
                                <button class="btn btn-icon btn-light-primary btn-sm btn-download" 
                                        data-url="${doc.file_url}" 
                                        data-name="TREG_${doc.documento_identidad}.pdf"
                                        title="Descargar">
                                    <i class="ti ti-download"></i>
                                </button>
                                <button class="btn btn-icon btn-light-info btn-sm btn-view" 
                                        data-url="${doc.file_url}"
                                        title="Ver">
                                    <i class="ti ti-eye"></i>
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
            },
            onBeforeSearch: () => {
                const formData = new FormData(document.getElementById('searchForm'));
                const params = {
                    documento: formData.get('documento'),
                    anio: formData.get('anio'),
                    mes: formData.get('mes'),
                    tipo_trabajador: formData.get('tipo_trabajador')
                };

                if (formData.get('is_masivo') === 'on') {
                    const raw = formData.get('documentos_masivos');
                    const codes = DS.parseMasivo(raw);
                    const valid = DS.validateCodes(codes);
                    if (valid.length > 0) {
                        params.documentos_masivos = valid;
                    } else if (raw.trim()) {
                        DS.showToast('Ingrese documentos válidos (8-11 dígitos)', 'warning');
                        return false;
                    }
                }
                return params;
            }
        });

        // 5. Global Event Delegation for Downloads/View
        document.addEventListener('click', async (e) => {
            const btnDownload = e.target.closest('.btn-download');
            if (btnDownload) {
                const url = btnDownload.dataset.url;
                const name = btnDownload.dataset.name;
                DS.setLoading(btnDownload, true, '');
                try {
                    await DS.downloadWithAuth(url, { authToken: token, fallbackName: name });
                } catch (err) {
                    DS.showToast(err.message, 'error');
                } finally {
                    DS.setLoading(btnDownload, false);
                }
            }

            const btnView = e.target.closest('.btn-view');
            if (btnView) {
                window.open(btnView.dataset.url, '_blank');
            }
        });

        // Initial empty state or default load
        // app.performSearch(1); 
    });

})(window.DocSearchShared);
