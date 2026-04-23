/**
 * SEGUROS v2 Search - Refactored to use DocSearchCore
 */

const UI_CONFIG = {
  formId: 'segurosForm',
  statsId: 'statsSeguros',
  domain: 'SEGUROS',
  pageSize: 12
};

// Instance of Core using centralized API paths
const core = new window.DocSearchCore(UI_CONFIG, window.DocSearchCore.API_PATHS);

/**
 * Format metadata for the table
 */
function toRow(result) {
  const metadata = result.metadata || {};
  const filename = result.filename || '-';
  const empresa = metadata.empresa || '-';
  const titular = metadata.titular || '-';
  const dni = metadata.dni || '-';
  const periodo = core.formatPeriodo(metadata);
  const estado = result.indexed ? 'Indexado' : 'Pendiente';
  const sizeText = `${Number(result.size_kb || 0).toFixed(2)} KB`;

  return {
    filename,
    empresa,
    titular,
    dni,
    periodo,
    estado,
    downloadUrl: result.download_url || '',
    sizeText
  };
}

/**
 * Custom stats rendering
 */
function renderStats(results) {
  const rows = results.map(toRow);
  const dnis = new Set(rows.map(item => item.dni).filter(Boolean)).size;
  const empresas = new Set(rows.map(item => item.empresa).filter(Boolean)).size;

  const html = `
    <article class="stat-card acrylic-surface stat-border-1">
      <div class="label">Total</div>
      <div class="value">${rows.length}</div>
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
  
  const statsContainer = document.getElementById(UI_CONFIG.statsId);
  if (statsContainer) statsContainer.innerHTML = html;
}

/**
 * Custom table rendering
 */
function renderTable(results, page) {
  const tableBody = document.getElementById('tableBody');
  if (!tableBody) return;

  const rows = results.map(toRow);
  const startIndex = (page - 1) * UI_CONFIG.pageSize;
  const pageRows = rows.slice(startIndex, startIndex + UI_CONFIG.pageSize);

  tableBody.innerHTML = pageRows.map(row => {
    const fileNameOnly = row.filename.split('/').pop() || row.filename;
    return `
      <tr>
        <td>
          <div class="fw-500">${core.safeText(fileNameOnly)}</div>
          <div class="doc-meta">${core.safeText(row.sizeText)} - ${core.safeText(row.estado)}</div>
        </td>
        <td>${core.safeText(row.empresa)}</td>
        <td>
          <div class="fw-500">${core.safeText(row.titular)}</div>
          <div class="doc-meta">DNI: ${core.safeText(row.dni)}</div>
        </td>
        <td>${core.safeText(row.periodo)}</td>
        <td>${core.safeText(row.estado)}</td>
        <td>
          <div class="actions">
            <button
              type="button"
              class="btn btn-sm btn-success-soft js-download"
              data-url="${core.safeText(row.downloadUrl)}"
              data-name="${core.safeText(fileNameOnly)}"
              ${row.downloadUrl ? '' : 'disabled'}
            >
              <i class="ti ti-download"></i> Descargar
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

/**
 * Build search payload from form
 */
function buildPayload() {
  const isMasivo = !document.getElementById('masivoContainer')?.classList?.contains('d-none');
  const certificado = document.getElementById('id_certificado')?.value || '';
  const dni = document.getElementById('id_dni')?.value || '';
  const cuit = document.getElementById('id_cuit')?.value || '';
  const anio = document.getElementById('id_anio')?.value || '';
  const mes = document.getElementById('id_mes')?.value || '';

  const payload = {};
  if (certificado) payload.certificado = certificado;
  if (dni) payload.dni = dni;
  if (cuit) payload.cuit = cuit;
  if (anio) payload.anio = anio;
  if (mes) payload.mes = mes;

  if (isMasivo) {
    const massInput = document.getElementById('id_masivo_data')?.value || '';
    const codes = core.validateCodes(core.parseMasivo(massInput));
    if (codes.length === 0) throw new Error('Ingresa al menos un código para busqueda masiva.');
    payload.codigos = codes;
  }

  return payload;
}

// Wire up events and initialize
core.onRenderResults = (results, page) => {
  renderTable(results, page);
  renderStats(results);
};

core.onBuildPayload = buildPayload;

// Initialize
core.init();
