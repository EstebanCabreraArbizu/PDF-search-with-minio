// Token JWT almacenado en memoria (más seguro que localStorage)
let authToken = null;
let currentUser = null;
let filterOptions = null;

// ========================================
// LOGIN
// ========================================
document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const formData = new FormData(e.target);
    const credentials = {
        username: formData.get('username'),
        password: formData.get('password')
    };

    try {
        const response = await fetch('/api/token/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username: credentials.username,
                password: credentials.password
            })
        });

        const data = await response.json();

        if (response.ok) {
            authToken = data.access;
            // Since Django JWT doesn't return user info by default, we'll simulate it or wait for user to add it.
            // For now, let's assume a basic user object if not present.
            currentUser = data.user || { username: credentials.username, role: 'admin' };

            // console.log('✓ Token recibido:', authToken ? authToken.substring(0, 10) + '...' : 'NULL');
            // console.log('✓ Usuario:', currentUser);

            // Mostrar pantalla de búsqueda
            document.getElementById('loginScreen').classList.add('d-none');
            document.getElementById('searchScreen').classList.remove('d-none');
            document.getElementById('username').textContent = `👤 ${currentUser.full_name || currentUser.username}`;

            // Mostrar sección de upload, sincronización y hashes solo para admin
            if (currentUser.role === 'admin') {
                document.getElementById('uploadSection').classList.remove('d-none');
                document.getElementById('syncSection').classList.remove('d-none');
                document.getElementById('hashSection').classList.remove('d-none');
            }

            // Poblar filtros de archivos con las mismas opciones
            populateFileFilters();

            // Cargar opciones de filtros después del login
            await loadFilterOptions();
        } else {
            document.getElementById('loginError').textContent = data.error;
            document.getElementById('loginError').classList.remove('d-none');
        }
    } catch (error) {
        alert('Error de conexión: ' + error);
    }
});

// ========================================
// CARGAR OPCIONES DE FILTROS
// ========================================
async function loadFilterOptions() {
    try {
        const response = await fetch('/api/filter-options', {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (!response.ok) {
            console.error('Error cargando opciones de filtros');
            return;
        }

        filterOptions = await response.json();

        // ---- BÚSQUEDA SIMPLE ----
        // Poblar selector de Años
        const selectAño = document.getElementById('selectAño');
        if (selectAño) {
            let añosHtml = '<option value="">Todos</option>';
            filterOptions.años.forEach(año => {
                añosHtml += `<option value="${año}">${año}</option>`;
            });
            selectAño.innerHTML = añosHtml;
        }

        // Poblar selector de Meses
        const selectMes = document.getElementById('selectMes');
        if (selectMes) {
            let mesesHtml = '<option value="">Todos</option>';
            filterOptions.meses.forEach(mes => {
                mesesHtml += `<option value="${mes.value}">${mes.label}</option>`;
            });
            selectMes.innerHTML = mesesHtml;
        }

        // Poblar selector de Bancos
        const selectBanco = document.getElementById('selectBanco');
        if (selectBanco) {
            let bancosHtml = '<option value="">Todos</option>';
            filterOptions.bancos.forEach(banco => {
                bancosHtml += `<option value="${banco}">${banco}</option>`;
            });
            selectBanco.innerHTML = bancosHtml;
        }

        // Poblar selector de Razones Sociales
        const selectRazonSocial = document.getElementById('selectRazonSocial');
        if (selectRazonSocial) {
            let razonesHtml = '<option value="">Todas</option>';
            filterOptions.razones_sociales.forEach(rs => {
                razonesHtml += `<option value="${rs}">${rs}</option>`;
            });
            selectRazonSocial.innerHTML = razonesHtml;
        }

        // Poblar datalist de Tipos de Documento (autocompletado)
        const tiposDocumentoList = document.getElementById('tiposDocumentoList');
        if (tiposDocumentoList && filterOptions.tipos_documento) {
            let tiposHtml = '';
            filterOptions.tipos_documento.forEach(tipo => {
                tiposHtml += `<option value="${tipo}">`;
            });
            tiposDocumentoList.innerHTML = tiposHtml;
        }

        // ---- BÚSQUEDA MASIVA ----
        const bulkAño = document.getElementById('bulkAño');
        if (bulkAño) {
            let bulkAñosHtml = '<option value="">Todos</option>';
            filterOptions.años.forEach(año => {
                bulkAñosHtml += `<option value="${año}">${año}</option>`;
            });
            bulkAño.innerHTML = bulkAñosHtml;
        }

        const bulkMes = document.getElementById('bulkMes');
        if (bulkMes) {
            let bulkMesesHtml = '<option value="">Todos</option>';
            filterOptions.meses.forEach(mes => {
                bulkMesesHtml += `<option value="${mes.value}">${mes.label}</option>`;
            });
            bulkMes.innerHTML = bulkMesesHtml;
        }

        const bulkBanco = document.getElementById('bulkBanco');
        if (bulkBanco) {
            let bulkBancosHtml = '<option value="">Todos</option>';
            filterOptions.bancos.forEach(banco => {
                bulkBancosHtml += `<option value="${banco}">${banco}</option>`;
            });
            bulkBanco.innerHTML = bulkBancosHtml;
        }

        const bulkRazonSocial = document.getElementById('bulkRazonSocial');
        if (bulkRazonSocial) {
            let bulkRazonesHtml = '<option value="">Todas</option>';
            filterOptions.razones_sociales.forEach(rs => {
                bulkRazonesHtml += `<option value="${rs}">${rs}</option>`;
            });
            bulkRazonSocial.innerHTML = bulkRazonesHtml;
        }

        // Poblar datalist de Tipos de Documento (Masiva - autocompletado)
        const bulkTiposDocumentoList = document.getElementById('bulkTiposDocumentoList');
        if (bulkTiposDocumentoList && filterOptions.tipos_documento) {
            let bulkTiposHtml = '';
            filterOptions.tipos_documento.forEach(tipo => {
                bulkTiposHtml += `<option value="${tipo}">`;
            });
            bulkTiposDocumentoList.innerHTML = bulkTiposHtml;
        }

        // Configurar autocompletado dinámico para tipos de documento
        setupTipoDocumentoAutocomplete();

        // ---- GESTIÓN DE ARCHIVOS ----
        populateFileFilters();

        // console.log('✓ Opciones de filtros cargadas');
    } catch (error) {
        console.error('Error cargando opciones:', error);
    }
}

// ========================================
// AUTOCOMPLETADO TIPO DOCUMENTO (estilo Google)
// ========================================
function setupTipoDocumentoAutocomplete() {
    const inputs = [
        { input: 'inputTipoDocumento', datalist: 'tiposDocumentoList' },
        { input: 'bulkTipoDocumento', datalist: 'bulkTiposDocumentoList' }
    ];

    inputs.forEach(({ input, datalist }) => {
        const inputEl = document.getElementById(input);
        const datalistEl = document.getElementById(datalist);

        if (!inputEl || !datalistEl || !filterOptions?.tipos_documento) return;

        inputEl.addEventListener('input', function () {
            const searchTerm = this.value.toLowerCase().trim();

            // Limpiar datalist
            datalistEl.innerHTML = '';

            if (!searchTerm) {
                // Si está vacío, mostrar máximo 50
                const initial = filterOptions.tipos_documento.slice(0, 50);
                let html = '';
                initial.forEach(tipo => {
                    html += `<option value="${tipo}">`;
                });
                datalistEl.innerHTML = html;
            } else {
                // Filtrar tipos que contengan el término de búsqueda
                const matches = filterOptions.tipos_documento.filter(tipo =>
                    tipo.toLowerCase().includes(searchTerm)
                );

                // Ordenar: primero los que empiezan con el término, luego el resto
                matches.sort((a, b) => {
                    const aStarts = a.toLowerCase().startsWith(searchTerm);
                    const bStarts = b.toLowerCase().startsWith(searchTerm);
                    if (aStarts && !bStarts) return -1;
                    if (!aStarts && bStarts) return 1;
                    return a.localeCompare(b);
                });

                // Mostrar máximo 15 sugerencias
                let html = '';
                matches.slice(0, 15).forEach(tipo => {
                    html += `<option value="${tipo}">`;
                });
                datalistEl.innerHTML = html;
            }
        });
    });
}

// ========================================
// LOGOUT
// ========================================
function logout() {
    authToken = null;
    currentUser = null;
    filterOptions = null;
    currentSearchResults = [];
    document.getElementById('loginScreen').classList.remove('d-none');
    document.getElementById('searchScreen').classList.add('d-none');
    document.getElementById('loginForm').reset();
    document.getElementById('resultsContainer').classList.add('d-none');
}

// ========================================
// LIMPIAR FILTROS
// ========================================
function clearFilters() {
    document.getElementById('searchForm').reset();
    document.getElementById('resultsContainer').classList.add('d-none');
    document.getElementById('bulkSearchSummary').classList.add('d-none');
    document.getElementById('mergeButtonContainer').classList.add('d-none');
    currentSearchResults = [];
}

// Variable global para almacenar resultados (para merge)
let currentSearchResults = [];

// ========================================
// BÚSQUEDA SIMPLE
// ========================================
document.getElementById('searchForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    document.getElementById('searchBtn').classList.add('d-none');
    document.getElementById('loadingBtn').classList.remove('d-none');
    document.getElementById('bulkSearchSummary').classList.add('d-none');

    const formData = new FormData(e.target);
    const filters = {};
    const activeFiltersList = [];

    for (let [key, value] of formData.entries()) {
        if (value) {
            filters[key] = value;
            // Crear lista de filtros activos para mostrar
            activeFiltersList.push(`${key}: ${value}`);
        }
    }

    try {
        // console.log('Enviando búsqueda con filtros:', filters);

        const response = await fetch('/api/search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify(filters)
        });

        // console.log('Respuesta del servidor:', response.status);

        if (response.status === 401) {
            alert('Sesión expirada. Por favor inicia sesión nuevamente.');
            logout();
            return;
        }

        const data = await response.json();

        if (data.error) {
            alert('Error: ' + data.error);
            document.getElementById('resultsContainer').classList.add('d-none');
        } else {
            // Guardar resultados para merge
            currentSearchResults = data.results || [];

            // Mostrar filtros activos
            document.getElementById('activeFilters').textContent =
                activeFiltersList.length > 0
                    ? `Filtros: ${activeFiltersList.join(' | ')}`
                    : 'Sin filtros aplicados';

            // Mostrar botón merge si hay múltiples resultados
            if (currentSearchResults.length > 1) {
                document.getElementById('mergeButtonContainer').classList.remove('d-none');
            } else {
                document.getElementById('mergeButtonContainer').classList.add('d-none');
            }

            displayResults(data);
        }
    } catch (error) {
        alert('Error en la búsqueda: ' + error);
        document.getElementById('resultsContainer').classList.add('d-none');
    } finally {
        document.getElementById('searchBtn').classList.remove('d-none');
        document.getElementById('loadingBtn').classList.add('d-none');
    }
});

function displayResults(data) {
    const container = document.getElementById('results');
    const totalEl = document.getElementById('totalResults');
    const resultsContainer = document.getElementById('resultsContainer');

    if (!data || typeof data.total === 'undefined' || !Array.isArray(data.results)) {
        console.error('Datos inválidos:', data);
        alert('Error: Respuesta del servidor inválida');
        return;
    }

    totalEl.textContent = `📄 Se encontraron ${data.total} documento(s)`;
    resultsContainer.classList.remove('d-none');

    if (data.total === 0) {
        container.innerHTML = '<div class="col-12"><p class="text-muted text-center">No se encontraron resultados con los filtros aplicados.</p></div>';
        return;
    }

    container.innerHTML = data.results.map(r => `
                <div class="col-md-6 col-lg-4 mb-3">
                    <div class="card result-card h-100">
                        <div class="card-body">
                            <h6 class="card-title text-truncate" title="${r.filename}">
                                📄 ${r.filename.split('/').pop()}
                            </h6>
                            <div class="mb-2">
                                <span class="badge bg-primary">${r.metadata.año || 'N/A'}</span>
                                <span class="badge bg-secondary">${r.metadata.mes ? getMesNombre(r.metadata.mes) : 'N/A'}</span>
                                <span class="badge bg-info text-dark">${r.metadata.banco}</span>
                            </div>
                            <p class="card-text small mb-2">
                                <span class="metadata-item">
                                    <span class="metadata-label">🏢 Razón Social:</span> ${r.metadata.razon_social}
                                </span><br>
                                <span class="metadata-item">
                                    <span class="metadata-label">📁 Tipo:</span> ${r.metadata.tipo_documento}
                                </span><br>
                                <span class="metadata-item">
                                    <span class="metadata-label">📦 Tamaño:</span> ${r.size_kb} KB
                                </span>
                            </p>
                            <small class="text-muted d-block mb-2" style="font-size: 0.7rem;">
                                ${r.filename}
                            </small>
                            <button class="btn btn-sm btn-primary w-100" data-action="download" data-url="${encodeURIComponent(r.download_url)}">
                                📥 Descargar
                            </button>
                        </div>
                    </div>
                </div>
            `).join('');
}

// Helper para obtener nombre del mes
function getMesNombre(mesNum) {
    const meses = {
        '01': 'Enero', '02': 'Febrero', '03': 'Marzo', '04': 'Abril',
        '05': 'Mayo', '06': 'Junio', '07': 'Julio', '08': 'Agosto',
        '09': 'Septiembre', '10': 'Octubre', '11': 'Noviembre', '12': 'Diciembre'
    };
    return meses[mesNum] || mesNum;
}

// ========================================
// BÚSQUEDA MASIVA (DNI)
// ========================================
document.getElementById('bulkSearchForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    document.getElementById('bulkSearchBtn').classList.add('d-none');
    document.getElementById('bulkLoadingBtn').classList.remove('d-none');

    const codigos = document.getElementById('bulkCodigos').value;
    const año = document.getElementById('bulkAño').value;
    const mes = document.getElementById('bulkMes').value;
    const banco = document.getElementById('bulkBanco').value;
    const razonSocial = document.getElementById('bulkRazonSocial').value;
    const tipoDocumento = document.getElementById('bulkTipoDocumento').value;

    if (!codigos.trim()) {
        alert('Ingresa al menos un DNI');
        document.getElementById('bulkSearchBtn').classList.remove('d-none');
        document.getElementById('bulkLoadingBtn').classList.add('d-none');
        return;
    }

    try {
        const response = await fetch('/api/search/bulk', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify({
                codigos: codigos,
                año: año,
                mes: mes,
                banco: banco,
                razon_social: razonSocial,
                tipo_documento: tipoDocumento
            })
        });

        if (response.status === 401) {
            alert('Sesión expirada');
            logout();
            return;
        }

        const data = await response.json();

        if (data.error) {
            alert('Error: ' + data.error);
            return;
        }

        // Guardar resultados para merge
        currentSearchResults = data.results || [];

        // Mostrar resumen de búsqueda masiva
        const summaryDiv = document.getElementById('bulkSearchSummary');
        summaryDiv.classList.remove('d-none');

        document.getElementById('codigosEncontrados').innerHTML =
            data.codigos_encontrados.length > 0
                ? data.codigos_encontrados.map(c => `<span class="badge bg-success me-1">${c}</span>`).join('')
                : '<span class="text-muted">Ninguno</span>';

        document.getElementById('codigosNoEncontrados').innerHTML =
            data.codigos_no_encontrados.length > 0
                ? data.codigos_no_encontrados.map(c => `<span class="badge bg-danger me-1">${c}</span>`).join('')
                : '<span class="text-muted">Ninguno</span>';

        // Mostrar filtros activos
        const activeFilters = [];
        if (año) activeFilters.push(`Año: ${año}`);
        if (mes) activeFilters.push(`Mes: ${getMesNombre(mes)}`);
        if (banco) activeFilters.push(`Banco: ${banco}`);
        if (razonSocial) activeFilters.push(`Razón Social: ${razonSocial}`);
        if (tipoDocumento) activeFilters.push(`Tipo: ${tipoDocumento}`);

        document.getElementById('activeFilters').textContent =
            activeFilters.length > 0
                ? `Filtros: ${activeFilters.join(' | ')}`
                : `Búsqueda: ${data.codigos_buscados.length} DNI(s)`;

        // Mostrar botón merge si hay múltiples resultados
        if (data.can_merge && currentSearchResults.length > 1) {
            document.getElementById('mergeButtonContainer').classList.remove('d-none');
        } else {
            document.getElementById('mergeButtonContainer').classList.add('d-none');
        }

        displayResults(data);

    } catch (error) {
        alert('Error en búsqueda masiva: ' + error);
    } finally {
        document.getElementById('bulkSearchBtn').classList.remove('d-none');
        document.getElementById('bulkLoadingBtn').classList.add('d-none');
    }
});

// ========================================
// FUSIONAR Y DESCARGAR PDFs
// ========================================
async function mergeAndDownload() {
    if (!currentSearchResults || currentSearchResults.length === 0) {
        alert('No hay resultados para fusionar');
        return;
    }

    if (currentSearchResults.length > 100) {
        alert('Máximo 100 archivos por fusión. Aplica más filtros para reducir los resultados.');
        return;
    }

    document.getElementById('mergeBtn').classList.add('d-none');
    document.getElementById('mergingBtn').classList.remove('d-none');

    const paths = currentSearchResults.map(r => r.filename);

    try {
        const response = await fetch('/api/merge-pdfs', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify({
                paths: paths,
                output_name: `documentos_${currentSearchResults.length}_archivos`
            })
        });

        if (response.status === 401) {
            alert('Sesión expirada');
            logout();
            return;
        }

        if (!response.ok) {
            const error = await response.json();
            alert('Error: ' + (error.error || 'No se pudo fusionar los archivos'));
            return;
        }

        // Descargar el PDF combinado
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = `documentos_combinados_${currentSearchResults.length}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(downloadUrl);

        // Mostrar info de merge
        const filesMerged = response.headers.get('X-Files-Merged') || currentSearchResults.length;
        const mergeErrors = response.headers.get('X-Merge-Errors') || '0';

        alert(`✓ PDF combinado descargado:\n- ${filesMerged} archivo(s) fusionados\n- ${mergeErrors} error(es)`);

    } catch (error) {
        alert('Error fusionando archivos: ' + error);
    } finally {
        document.getElementById('mergeBtn').classList.remove('d-none');
        document.getElementById('mergingBtn').classList.add('d-none');
    }
}

// ========================================
// DESCARGA (con JWT)
// ========================================
async function downloadFile(url) {
    try {
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.status === 401) {
            alert('Sesión expirada');
            logout();
            return;
        }

        if (!response.ok) {
            const error = await response.json();
            alert('Error: ' + (error.error || 'No se pudo descargar el archivo'));
            return;
        }

        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = url.split('/').pop();
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(downloadUrl);
    } catch (error) {
        alert('Error descargando archivo: ' + error);
    }
}

// ========================================
// GESTIÓN DE ARCHIVOS - DRAG & DROP
// ========================================
let selectedFilesArray = [];
const MAX_UPLOAD_FILES = 200; // límite aumentado para subidas masivas
const UPLOAD_CHUNK_SIZE = 20; // enviar en lotes de 20 archivos por petición

// Configurar drag & drop
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');

dropZone.addEventListener('click', () => fileInput.click());

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.style.backgroundColor = '#e7f3ff';
    dropZone.style.borderColor = '#0d6efd';
});

dropZone.addEventListener('dragleave', () => {
    dropZone.style.backgroundColor = '#f8f9fa';
    dropZone.style.borderColor = '#dee2e6';
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.style.backgroundColor = '#f8f9fa';
    dropZone.style.borderColor = '#dee2e6';

    const files = Array.from(e.dataTransfer.files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
    if (files.length > 0) {
        handleFileSelection(files);
    } else {
        alert('Solo se permiten archivos PDF');
    }
});

fileInput.addEventListener('change', (e) => {
    const files = Array.from(e.target.files);
    handleFileSelection(files);
});

function handleFileSelection(files) {
    // Filtrar solo PDFs
    const pdfs = files.filter(f => f.name.toLowerCase().endsWith('.pdf'));

    const accepted = pdfs.slice(0, MAX_UPLOAD_FILES);
    const rejected = pdfs.slice(MAX_UPLOAD_FILES);

    selectedFilesArray = accepted;
    displaySelectedFiles(rejected.length);

    if (rejected.length > 0) {
        alert(`Has seleccionado ${pdfs.length} PDFs. Se aceptan máximo ${MAX_UPLOAD_FILES}; ${rejected.length} serán ignorados.`);
    }
}

function displaySelectedFiles(rejectedCount = 0) {
    const filesList = document.getElementById('filesList');
    const selectedFilesDiv = document.getElementById('selectedFiles');

    if (selectedFilesArray.length === 0) {
        selectedFilesDiv.classList.add('d-none');
        return;
    }

    selectedFilesDiv.classList.remove('d-none');
    // console.log('🔍 DEBUG: Token presente?', !!authToken);
    // console.log('🔍 DEBUG: Archivos seleccionados:', selectedFilesArray.length);
    // console.log('🔍 DEBUG: Carpeta destino:', document.getElementById('uploadFolder').value);
    // Header resumen
    const summary = `<li class="list-group-item bg-light">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <strong>${selectedFilesArray.length} archivo(s) listos para subir</strong>
                            ${rejectedCount ? `<br><small class="text-muted">${rejectedCount} archivo(s) ignorados por exceder el límite (${MAX_UPLOAD_FILES})</small>` : ''}
                        </div>
                        <div>
                            <small class="text-muted">Máx por petición: ${UPLOAD_CHUNK_SIZE}</small>
                        </div>
                    </div>
                </li>`;

    const items = selectedFilesArray.map((file, idx) => {
        const sizeKB = (file.size / 1024).toFixed(1);
        return `
                    <li id="file-item-${idx}" class="list-group-item d-flex justify-content-between align-items-center">
                        <div>
                            <strong>${file.name}</strong>
                            <br><small class="text-muted">${sizeKB} KB</small>
                            <div id="progress-${idx}" class="mt-1" style="display:none;">
                                <div class="progress" style="height:8px;"><div class="progress-bar" role="progressbar" style="width: 0%;"></div></div>
                            </div>
                        </div>
                        <div>
                            <button type="button" class="btn btn-sm btn-outline-danger" data-action="remove-file" data-index="${idx}">🗑️</button>
                        </div>
                    </li>
                `;
    }).join('');

    filesList.innerHTML = summary + items;
}

function removeFile(index) {
    selectedFilesArray.splice(index, 1);
    displaySelectedFiles();
}

// ========================================
// SUBIR ARCHIVOS
// ========================================
async function uploadFiles() {
    if (selectedFilesArray.length === 0) {
        alert('Selecciona al menos un archivo');
        return;
    }

    const folder = document.getElementById('uploadFolder').value;

    document.getElementById('uploadBtn').classList.add('d-none');
    document.getElementById('uploadingBtn').classList.remove('d-none');

    let totalUploaded = 0;
    let totalIndexed = 0;
    let totalErrors = 0;

    // Disable UI while uploading
    const chunks = [];
    for (let i = 0; i < selectedFilesArray.length; i += UPLOAD_CHUNK_SIZE) {
        chunks.push(selectedFilesArray.slice(i, i + UPLOAD_CHUNK_SIZE));
    }

    try {
        for (let c = 0; c < chunks.length; c++) {
            const chunk = chunks[c];

            // Show per-file progress bars
            chunk.forEach((file, idx) => {
                const globalIdx = c * UPLOAD_CHUNK_SIZE + idx;
                const progressEl = document.getElementById(`progress-${globalIdx}`);
                if (progressEl) progressEl.style.display = 'block';
            });

            const formData = new FormData();
            chunk.forEach(file => formData.append('files[]', file));
            formData.append('folder', folder);

            const xhr = new XMLHttpRequest();
            const uploadPromise = new Promise((resolve, reject) => {
                xhr.open('POST', '/api/files/upload');
                xhr.setRequestHeader('Authorization', `Bearer ${authToken}`);

                xhr.onload = () => {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        resolve(JSON.parse(xhr.responseText));
                    } else {
                        try { resolve(JSON.parse(xhr.responseText)); } catch (e) { reject(xhr.statusText); }
                    }
                };

                xhr.onerror = () => reject(xhr.statusText);

                // track progress for the whole request and distribute roughly across files
                xhr.upload.onprogress = (event) => {
                    if (!event.lengthComputable) return;
                    const percent = Math.round((event.loaded / event.total) * 100);
                    // Update each file progress bar in the chunk
                    chunk.forEach((file, idx) => {
                        const globalIdx = c * UPLOAD_CHUNK_SIZE + idx;
                        const bar = document.querySelector(`#file-item-${globalIdx} .progress-bar`);
                        if (bar) bar.style.width = percent + '%';
                    });
                };

                xhr.send(formData);
            });

            const data = await uploadPromise;

            if (data && Array.isArray(data.uploaded)) {
                totalUploaded += data.uploaded.length;
                totalIndexed += data.uploaded.filter(u => u.indexed).length;
            }
            if (data && Array.isArray(data.errors)) {
                totalErrors += data.errors.length;
            }

            // small delay to let UI update
            await new Promise(r => setTimeout(r, 200));
        }

        alert(`✓ Proceso completado:\n- Subidos: ${totalUploaded}\n- Indexados: ${totalIndexed}\n- Errores: ${totalErrors}`);

        // Limpiar selección
        selectedFilesArray = [];
        fileInput.value = '';
        displaySelectedFiles();

        // Recargar lista de archivos
        loadFilesList();
    } catch (error) {
        alert('Error durante la subida: ' + error);
    } finally {
        document.getElementById('uploadBtn').classList.remove('d-none');
        document.getElementById('uploadingBtn').classList.add('d-none');
    }
}

// ========================================
// LISTAR ARCHIVOS
// ========================================
let currentFilesPage = 1;
const filesPerPage = 100;

function populateFileFilters() {
    if (!filterOptions) return;

    // Poblar Año
    const filterAño = document.getElementById('filterAño');
    if (filterAño) {
        let añosHtml = '<option value="">Todos</option>';
        filterOptions.años.forEach(año => {
            añosHtml += `<option value="${año}">${año}</option>`;
        });
        filterAño.innerHTML = añosHtml;
    }

    // Poblar Mes
    const filterMes = document.getElementById('filterMes');
    if (filterMes) {
        let mesesHtml = '<option value="">Todos</option>';
        filterOptions.meses.forEach(mes => {
            mesesHtml += `<option value="${mes.value}">${mes.label}</option>`;
        });
        filterMes.innerHTML = mesesHtml;
    }

    // Poblar Banco
    const filterBanco = document.getElementById('filterBanco');
    if (filterBanco) {
        let bancosHtml = '<option value="">Todos</option>';
        filterOptions.bancos.forEach(banco => {
            bancosHtml += `<option value="${banco}">${banco}</option>`;
        });
        filterBanco.innerHTML = bancosHtml;
    }

    // Poblar Razón Social
    const filterRazonSocial = document.getElementById('filterRazonSocial');
    if (filterRazonSocial) {
        let razonesHtml = '<option value="">Todas</option>';
        filterOptions.razones_sociales.forEach(rs => {
            razonesHtml += `<option value="${rs}">${rs}</option>`;
        });
        filterRazonSocial.innerHTML = razonesHtml;
    }

    // Poblar datalist de Tipos de Documento (gestión de archivos)
    const filterTiposDocumentoList = document.getElementById('filterTiposDocumentoList');
    if (filterTiposDocumentoList && filterOptions.tipos_documento) {
        let tiposHtml = '';
        filterOptions.tipos_documento.forEach(tipo => {
            tiposHtml += `<option value="${tipo}">`;
        });
        filterTiposDocumentoList.innerHTML = tiposHtml;
    }
}

function clearFileFilters() {
    document.getElementById('searchFileName').value = '';
    document.getElementById('filterAño').value = '';
    document.getElementById('filterMes').value = '';
    document.getElementById('filterBanco').value = '';
    document.getElementById('filterRazonSocial').value = '';
    document.getElementById('filterTipoDocumento').value = '';
    currentFilesPage = 1;
    loadFilesList();
}

async function loadFilesList(page = 1) {
    const container = document.getElementById('filesListContainer');
    const searchName = document.getElementById('searchFileName')?.value || '';
    const año = document.getElementById('filterAño')?.value || '';
    const mes = document.getElementById('filterMes')?.value || '';
    const razonSocial = document.getElementById('filterRazonSocial')?.value || '';
    const banco = document.getElementById('filterBanco')?.value || '';
    const tipoDocumento = document.getElementById('filterTipoDocumento')?.value || '';

    currentFilesPage = page;

    container.innerHTML = `
                <div class="d-flex justify-content-center p-5">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">Cargando...</span>
                    </div>
                </div>
            `;

    try {
        const params = new URLSearchParams({
            page: page,
            per_page: filesPerPage
        });

        if (searchName) params.append('search', searchName);
        if (año) params.append('año', año);
        if (mes) params.append('mes', mes);
        if (banco) params.append('banco', banco);
        if (razonSocial) params.append('razon_social', razonSocial);
        if (tipoDocumento) params.append('tipo_documento', tipoDocumento);

        const url = `/api/files/list?${params.toString()}`;
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.status === 401) {
            alert('Sesión expirada');
            logout();
            return;
        }

        const data = await response.json();

        if (data.files && data.files.length > 0) {
            displayFilesList(data);
        } else {
            container.innerHTML = `
                        <div class="alert alert-info text-center">
                            📂 No se encontraron archivos con los filtros aplicados
                        </div>
                    `;
        }
    } catch (error) {
        container.innerHTML = `
                    <div class="alert alert-danger">
                        ✗ Error cargando archivos: ${error}
                    </div>
                `;
    }
}

function displayFilesList(data) {
    const container = document.getElementById('filesListContainer');
    const isAdmin = currentUser && currentUser.role === 'admin';

    // Construir paginación
    let pagination = '';
    if (data.total_pages > 1) {
        pagination = '<nav><ul class="pagination justify-content-center mb-0">';

        // Botón anterior
        pagination += `<li class="page-item ${!data.has_prev ? 'disabled' : ''}">
                    <a class="page-link" href="#" data-action="paginate" data-page="${currentFilesPage - 1}">‹ Anterior</a>
                </li>`;

        // Páginas
        const maxButtons = 5;
        let startPage = Math.max(1, currentFilesPage - 2);
        let endPage = Math.min(data.total_pages, startPage + maxButtons - 1);

        if (endPage - startPage < maxButtons - 1) {
            startPage = Math.max(1, endPage - maxButtons + 1);
        }

        for (let i = startPage; i <= endPage; i++) {
            pagination += `<li class="page-item ${i === currentFilesPage ? 'active' : ''}">
                        <a class="page-link" href="#" data-action="paginate" data-page="${i}">${i}</a>
                    </li>`;
        }

        // Botón siguiente
        pagination += `<li class="page-item ${!data.has_next ? 'disabled' : ''}">
                    <a class="page-link" href="#" data-action="paginate" data-page="${currentFilesPage + 1}">Siguiente ›</a>
                </li>`;

        pagination += '</ul></nav>';
    }

    container.innerHTML = `
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <strong>📄 ${data.total.toLocaleString()} archivo(s) encontrado(s)</strong>
                        <span class="text-muted">Página ${data.page} de ${data.total_pages}</span>
                    </div>
                    <div class="table-responsive">
                        <table class="table table-hover mb-0">
                            <thead>
                                <tr>
                                    <th>Archivo</th>
                                    <th>Banco</th>
                                    <th>Año/Mes</th>
                                    <th>Razón Social</th>
                                    <th>Tamaño</th>
                                    <th>Indexado</th>
                                    <th>Acciones</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${data.files.map(file => {
        const mesNombre = file.mes ? getMesNombre(file.mes) : 'N/A';
        return `
                                    <tr>
                                        <td>
                                            <div>
                                                <strong>${file.name}</strong>
                                                <br><small class="text-muted" style="font-size: 0.75rem;">${file.folder || '(raíz)'}</small>
                                            </div>
                                        </td>
                                        <td><span class="badge bg-info text-dark">${file.banco || 'N/A'}</span></td>
                                        <td>
                                            <span class="badge bg-primary">${file.año || 'N/A'}</span>
                                            <span class="badge bg-secondary">${mesNombre}</span>
                                        </td>
                                        <td><small>${file.razon_social || 'N/A'}</small></td>
                                        <td>${file.size_human}</td>
                                        <td>
                                            ${file.indexed
                ? '<span class="badge bg-success">✓</span>'
                : '<span class="badge bg-warning">⏳</span>'}
                                        </td>
                                        <td>
                                            <div class="btn-group btn-group-sm">
                                                <button class="btn btn-primary" 
                                                        data-action="download"
                                                        data-url="${encodeURIComponent(file.download_url)}"
                                                        title="Descargar">
                                                    📥
                                                </button>
                                                ${isAdmin ? `
                                                    <button class="btn btn-danger" 
                                                            data-action="delete-file"
                                                            data-path="${encodeURIComponent(file.path)}"
                                                            title="Eliminar">
                                                        🗑️
                                                    </button>
                                                ` : ''}
                                            </div>
                                        </td>
                                    </tr>
                                `;
    }).join('')}
                            </tbody>
                        </table>
                    </div>
                    ${pagination ? `<div class="card-footer">${pagination}</div>` : ''}
                </div>
            `;
}

// ========================================
// ELIMINAR ARCHIVO
// ========================================
async function deleteFile(path) {
    if (!confirm(`¿Estás seguro de eliminar este archivo?\n\n${path}\n\nEsta acción no se puede deshacer.`)) {
        return;
    }

    try {
        const response = await fetch('/api/files/delete', {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify({ path: path })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            alert('✓ Archivo eliminado correctamente');
            loadFilesList();
        } else {
            alert('Error: ' + (data.error || 'No se pudo eliminar el archivo'));
        }
    } catch (error) {
        alert('Error eliminando archivo: ' + error);
    }
}

// ========================================
// EXPLORADOR DE CARPETAS (Modal)
// ========================================
let currentBrowserPath = '';

function openFolderBrowser() {
    currentBrowserPath = '';
    loadFolderBrowser('');
    const modal = new bootstrap.Modal(document.getElementById('folderBrowserModal'));
    modal.show();
}

async function loadFolderBrowser(path) {
    currentBrowserPath = path;
    const listContainer = document.getElementById('folderBrowserList');
    const breadcrumb = document.getElementById('folderBreadcrumb');
    const currentPathDisplay = document.getElementById('currentFolderPath');

    listContainer.innerHTML = `
                <div class="text-center py-4">
                    <div class="spinner-border text-primary" role="status"></div>
                    <p class="mt-2">Cargando carpetas...</p>
                </div>
            `;

    try {
        const response = await fetch(`/api/folders?parent=${encodeURIComponent(path)}`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Error cargando carpetas');
        }

        // Actualizar breadcrumb
        breadcrumb.innerHTML = `
                    <li class="breadcrumb-item">
                        <a href="#" data-action="browse-folder" data-path="">🏠 Raíz</a>
                    </li>
                `;
        data.breadcrumb.forEach((item, index) => {
            const isLast = index === data.breadcrumb.length - 1;
            if (isLast) {
                breadcrumb.innerHTML += `<li class="breadcrumb-item active">${item.name}</li>`;
            } else {
                breadcrumb.innerHTML += `
                            <li class="breadcrumb-item">
                                <a href="#" data-action="browse-folder" data-path="${encodeURIComponent(item.path)}">${item.name}</a>
                            </li>
                        `;
            }
        });

        // Actualizar path actual
        currentPathDisplay.value = path || '(raíz del bucket)';

        // Renderizar lista de carpetas
        const timeInfo = data.time_ms ? `<small class="text-success ms-2">⚡ ${data.time_ms}ms</small>` : '';

        if (data.folders.length === 0) {
            listContainer.innerHTML = `
                        <div class="text-center py-4 text-muted">
                            <p>📁 No hay subcarpetas aquí ${timeInfo}</p>
                            <small>Puedes usar esta ubicación o crear una nueva subcarpeta</small>
                        </div>
                    `;
        } else {
            listContainer.innerHTML = `
                        <div class="small text-muted mb-2">${data.folders.length} carpeta(s) encontrada(s) ${timeInfo}</div>
                    ` + data.folders.map(folder => `
                        <div class="list-group-item list-group-item-action d-flex justify-content-between align-items-center"
                             style="cursor: pointer;"
                             data-action="browse-folder"
                             data-path="${encodeURIComponent(folder.path)}">
                            <div>
                                <span class="me-2">📁</span>
                                <strong>${folder.name}</strong>
                            </div>
                            <div>
                                <span class="badge bg-secondary me-2">${folder.count} PDF(s)</span>
                                <button class="btn btn-sm btn-success" 
                                        data-action="select-folder"
                                        data-path="${encodeURIComponent(folder.path)}"
                                        title="Seleccionar esta carpeta">
                                    ✓ Usar
                                </button>
                            </div>
                        </div>
                    `).join('');
        }

    } catch (error) {
        listContainer.innerHTML = `
                    <div class="alert alert-danger">
                        Error: ${error.message}
                    </div>
                `;
    }
}

function selectFolder(path) {
    document.getElementById('uploadFolder').value = path;
    bootstrap.Modal.getInstance(document.getElementById('folderBrowserModal')).hide();
}

function selectCurrentFolder() {
    document.getElementById('uploadFolder').value = currentBrowserPath;
    bootstrap.Modal.getInstance(document.getElementById('folderBrowserModal')).hide();
}

function createNewSubfolder() {
    const folderName = document.getElementById('newSubfolderName').value.trim();
    if (!folderName) {
        alert('Ingresa un nombre para la nueva carpeta');
        return;
    }

    // Sanitizar nombre de carpeta
    const safeName = folderName.replace(/[<>:"/\\|?*]/g, '').trim();
    if (!safeName) {
        alert('Nombre de carpeta inválido');
        return;
    }
    const newPath = currentBrowserPath + safeName + '/';

    // Llamar al backend para crear la carpeta (placeholder)
    try {
        fetch('/api/files/create-folder', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify({ path: newPath })
        }).then(async res => {
            const data = await res.json().catch(() => ({}));
            if (res.ok) {
                document.getElementById('uploadFolder').value = newPath;
                document.getElementById('newSubfolderName').value = '';
                bootstrap.Modal.getInstance(document.getElementById('folderBrowserModal')).hide();
                alert('✓ Carpeta creada: ' + newPath);
                // refrescar navegador de carpetas
                loadFolderBrowser(newPath);
            } else {
                alert('Error creando carpeta: ' + (data.error || res.statusText));
            }
        }).catch(err => {
            alert('Error creando carpeta: ' + err);
        });
    } catch (err) {
        alert('Error creando carpeta: ' + err);
    }
}

function goUpFolder() {
    if (!currentBrowserPath) return;

    const parts = currentBrowserPath.replace(/\/$/, '').split('/');
    parts.pop();
    const parentPath = parts.length > 0 ? parts.join('/') + '/' : '';
    loadFolderBrowser(parentPath);
}

// ========================================
// SINCRONIZACIÓN DE ÍNDICE (BATCH)
// ========================================
let syncStopped = false;  // Flag para detener sincronización
let syncTotals = { new: 0, moved: 0, removed: 0, time: 0 };  // Acumuladores

async function syncIndex() {
    const btnText = document.getElementById('syncBtnText');
    const btnLoading = document.getElementById('syncBtnLoading');
    const syncButton = document.getElementById('syncButton');
    const stopButton = document.getElementById('syncStopButton');
    const syncResults = document.getElementById('syncResults');
    const progressContainer = document.getElementById('syncProgressContainer');
    const progressBar = document.getElementById('syncProgressBar');
    const progressText = document.getElementById('syncProgressText');
    const progressInfo = document.getElementById('syncProgressInfo');
    const batchSizeSelect = document.getElementById('syncBatchSize');

    // Reiniciar acumuladores y flag
    syncStopped = false;
    syncTotals = { new: 0, moved: 0, removed: 0, time: 0 };

    // UI: mostrar loading
    syncResults.classList.add('d-none');
    btnText.classList.add('d-none');
    btnLoading.classList.remove('d-none');
    syncButton.disabled = true;
    stopButton.classList.remove('d-none');
    progressContainer.classList.remove('d-none');
    batchSizeSelect.disabled = true;

    const batchSize = parseInt(batchSizeSelect.value) || 50;
    let hasMore = true;
    let batchNumber = 0;

    try {
        while (hasMore && !syncStopped) {
            batchNumber++;

            const response = await fetch('/api/index/sync', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${authToken}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ batch_size: batchSize })
            });

            if (response.status === 401) {
                alert('Sesión expirada. Por favor inicia sesión nuevamente.');
                logout();
                return;
            }

            if (response.status === 403) {
                alert('Permiso denegado. Solo administradores pueden sincronizar.');
                return;
            }

            const data = await response.json();

            if (data.error) {
                alert('Error en sincronización: ' + data.error);
                return;
            }

            // Acumular totales
            syncTotals.new += data.new_files || 0;
            syncTotals.moved += data.moved_files || 0;
            syncTotals.removed += data.removed_orphans || 0;
            syncTotals.time += data.time_seconds || 0;

            // Actualizar barra de progreso
            const percent = data.progress_percent || 0;
            progressBar.style.width = percent + '%';
            progressText.textContent = percent + '%';
            progressInfo.textContent = `Lote ${batchNumber} | Pendientes: ${data.pending_new || 0} | Nuevos: ${syncTotals.new}`;

            // Actualizar resultados parciales visualmente
            document.getElementById('syncNewFiles').textContent = syncTotals.new;
            document.getElementById('syncMovedFiles').textContent = syncTotals.moved;
            document.getElementById('syncRemovedFiles').textContent = syncTotals.removed;
            document.getElementById('syncTime').textContent = syncTotals.time.toFixed(1) + 's';
            syncResults.classList.remove('d-none');

            // Mostrar archivos movidos (solo primer lote)
            if (batchNumber === 1 && data.moved_details && data.moved_details.length > 0) {
                const movedList = document.getElementById('syncMovedList');
                movedList.innerHTML = data.moved_details.map(item => `
                            <li class="list-group-item py-1 px-2">
                                <span class="text-danger text-decoration-line-through">${item.old_path}</span>
                                <br>
                                <span class="text-success">→ ${item.new_path}</span>
                            </li>
                        `).join('');
                document.getElementById('syncMovedDetails').classList.remove('d-none');
            }

            hasMore = data.has_more;

            // Pequeña pausa entre lotes para no saturar el servidor
            if (hasMore && !syncStopped) {
                await new Promise(resolve => setTimeout(resolve, 500));
            }
        }

        // Mostrar mensaje final
        if (syncStopped) {
            progressInfo.textContent = `⏹️ Detenido después de ${batchNumber} lotes`;
            progressBar.classList.remove('progress-bar-animated');
            progressBar.classList.add('bg-warning');
        } else {
            progressInfo.textContent = `✅ Completado en ${batchNumber} lotes`;
            progressBar.classList.remove('progress-bar-animated');
        }

        // Recargar la lista de archivos
        if (document.getElementById('files-panel').classList.contains('show')) {
            loadFilesList();
        }

        // Recargar opciones de filtros
        await loadFilterOptions();

    } catch (error) {
        console.error('Error en sincronización:', error);
        alert('Error de conexión al sincronizar: ' + error.message);
    } finally {
        // Restaurar UI
        btnText.classList.remove('d-none');
        btnLoading.classList.add('d-none');
        syncButton.disabled = false;
        stopButton.classList.add('d-none');
        batchSizeSelect.disabled = false;
    }
}


function stopSync() {
    syncStopped = true;
    document.getElementById('syncProgressInfo').textContent = '⏳ Deteniendo...';
}

// ========================================
// POBLAR HASHES MD5 (MIGRACIÓN)
// ========================================
async function populateHashes() {
    const btnText = document.getElementById('hashBtnText');
    const btnLoading = document.getElementById('hashBtnLoading');
    const hashButton = document.getElementById('hashButton');
    const progressContainer = document.getElementById('hashProgressContainer');
    const progressBar = document.getElementById('hashProgressBar');
    const progressText = document.getElementById('hashProgressText');
    const progressInfo = document.getElementById('hashProgressInfo');

    // UI: mostrar loading
    btnText.classList.add('d-none');
    btnLoading.classList.remove('d-none');
    hashButton.disabled = true;
    progressContainer.classList.remove('d-none');

    let hasMore = true;
    let batchNumber = 0;
    let totalUpdated = 0;

    try {
        while (hasMore) {
            batchNumber++;

            const response = await fetch('/api/index/populate-hashes', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${authToken}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ batch_size: 1000 })
            });

            if (response.status === 401) {
                alert('Sesión expirada. Por favor inicia sesión nuevamente.');
                logout();
                return;
            }

            const data = await response.json();

            if (data.error) {
                alert('Error: ' + data.error);
                return;
            }

            totalUpdated += data.updated || 0;

            // Actualizar barra de progreso
            const percent = data.progress_percent || 0;
            progressBar.style.width = percent + '%';
            progressText.textContent = percent + '%';
            progressInfo.textContent = `Lote ${batchNumber} | Actualizados: ${totalUpdated} | Pendientes: ${data.pending || 0}`;

            hasMore = data.has_more;

            // Pequeña pausa
            if (hasMore) {
                await new Promise(resolve => setTimeout(resolve, 300));
            }
        }

        // Completado
        progressInfo.textContent = `✅ Completado: ${totalUpdated} hashes poblados`;
        progressBar.classList.remove('progress-bar-animated');
        progressBar.classList.add('bg-success');

        // Ocultar la sección después de completar (ya no se necesita)
        setTimeout(() => {
            document.getElementById('hashSection').classList.add('d-none');
            alert(`✅ Migración completada: ${totalUpdated} hashes MD5 poblados.\n\nAhora puedes usar la sincronización inteligente.`);
        }, 1500);

    } catch (error) {
        console.error('Error poblando hashes:', error);
        alert('Error: ' + error.message);
    } finally {
        btnText.classList.remove('d-none');
        btnLoading.classList.add('d-none');
        hashButton.disabled = false;
    }
}

function registerActionHandlers() {
    const bindings = [
        ['logoutButton', 'click', () => logout()],
        ['files-tab', 'click', () => loadFilesList()],
        ['clearFiltersButton', 'click', () => clearFilters()],
        ['mergeButton', 'click', () => mergeAndDownload()],
        ['openFolderBrowserButton', 'click', () => openFolderBrowser()],
        ['uploadFilesButton', 'click', () => uploadFiles()],
        ['syncButton', 'click', () => syncIndex()],
        ['syncStopButton', 'click', () => stopSync()],
        ['hashButton', 'click', () => populateHashes()],
        ['filesSearchButton', 'click', () => loadFilesList()],
        ['clearFileFiltersButton', 'click', () => clearFileFilters()],
        ['goUpFolderButton', 'click', () => goUpFolder()],
        ['refreshFolderBrowserButton', 'click', () => loadFolderBrowser(currentBrowserPath)],
        ['createSubfolderButton', 'click', () => createNewSubfolder()],
        ['selectCurrentFolderButton', 'click', () => selectCurrentFolder()],
    ];

    bindings.forEach(([id, eventName, handler]) => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener(eventName, handler);
        }
    });

    const selectFilesButton = document.getElementById('selectFilesButton');
    if (selectFilesButton) {
        selectFilesButton.addEventListener('click', (event) => {
            event.stopPropagation();
            document.getElementById('fileInput').click();
        });
    }
}

function registerDelegatedListeners() {
    document.addEventListener('click', (event) => {
        const actionElement = event.target.closest('[data-action]');
        if (!actionElement) {
            return;
        }

        const action = actionElement.dataset.action;

        if (action === 'download') {
            const encodedUrl = actionElement.dataset.url;
            if (encodedUrl) {
                downloadFile(decodeURIComponent(encodedUrl));
            }
            return;
        }

        if (action === 'remove-file') {
            const index = Number.parseInt(actionElement.dataset.index, 10);
            if (!Number.isNaN(index)) {
                removeFile(index);
            }
            return;
        }

        if (action === 'paginate') {
            event.preventDefault();
            const page = Number.parseInt(actionElement.dataset.page, 10);
            if (!Number.isNaN(page)) {
                loadFilesList(page);
            }
            return;
        }

        if (action === 'delete-file') {
            const encodedPath = actionElement.dataset.path;
            if (encodedPath) {
                deleteFile(decodeURIComponent(encodedPath));
            }
            return;
        }

        if (action === 'browse-folder') {
            event.preventDefault();
            const encodedPath = actionElement.dataset.path || '';
            loadFolderBrowser(encodedPath ? decodeURIComponent(encodedPath) : '');
            return;
        }

        if (action === 'select-folder') {
            event.preventDefault();
            event.stopPropagation();
            const encodedPath = actionElement.dataset.path;
            if (encodedPath) {
                selectFolder(decodeURIComponent(encodedPath));
            }
        }
    });
}

registerActionHandlers();
registerDelegatedListeners();