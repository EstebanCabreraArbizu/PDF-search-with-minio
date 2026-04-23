/**
 * DocSearch V2 - Boletas Logic
 */
(function(DS) {
    'use strict';

    document.addEventListener('DOMContentLoaded', async () => {
        const token = await DS.ensureAuthToken();
        if (!token) return;

        DS.initTheme();
        DS.initTopbarControls();
        DS.renderSidebarUser();

        const cbMasivo = document.getElementById('checkMasivo');
        const containerMasivo = document.getElementById('masivoContainer');
        if (cbMasivo && containerMasivo) {
            cbMasivo.onchange = () => containerMasivo.classList.toggle('d-none', !cbMasivo.checked);
        }

        const app = DS.createSearchApp({
            endpoint: DS.API_PATHS.search.boletas,
            formId: 'searchForm',
            resultsContainerId: 'resultsTableBody',
            paginationContainerId: 'paginationContainer',
            renderRow: (doc) => {
                return `
                    <tr>
                        <td>
                            <div class="d-flex align-items-center">
                                <div class="file-icon-sm me-3">
                                    <i class="ti ti-file-dollar"></i>
                                </div>
                                <div>
                                    <div class="fw-bold text-dark">${DS.safeText(doc.dni)}</div>
                                    <small class="text-muted">${DS.safeText(doc.tipo_boleta || 'Mensual')}</small>
                                </div>
                            </div>
                        </td>
                        <td>${DS.safeText(doc.nombres || '-')}</td>
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
                                        data-name="BOL_${doc.dni}_${doc.anio}.pdf"
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
                    tipo_boleta: formData.get('tipo_boleta')
                };

                if (formData.get('is_masivo') === 'on') {
                    const raw = formData.get('documentos_masivos');
                    const codes = DS.parseMasivo(raw);
                    const valid = DS.validateCodes(codes);
                    if (valid.length > 0) {
                        params.documentos_masivos = valid;
                    } else if (raw.trim()) {
                        DS.showToast('Ingrese documentos válidos', 'warning');
                        return false;
                    }
                }
                return params;
            }
        });

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
            if (btnView) window.open(btnView.dataset.url, '_blank');
        });
    });

})(window.DocSearchShared);
