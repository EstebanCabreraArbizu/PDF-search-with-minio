/**
 * T-REGISTRO v2 Search - Refactored to use DocSearchCore
 */

const UI_CONFIG = {
  formId: 'tregistroForm',
  statsId: 'statsTRegistro',
  domain: 'TREGISTRO',
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
  const empresa = metadata.razon_social || '-';
  const tipoMovimiento = metadata.tipo_movimiento || '-';
  const dni = metadata.dni || '-';
  const periodo = core.formatPeriodo(metadata);
  const estado = result.indexed ? 'Indexado' : 'Pendiente';
  const sizeText = `${Number(result.size_kb || 0).toFixed(2)} KB`;

  return {
    filename,
    empresa,
    tipoMovimiento,
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
  const altas = rows.filter(item => item.tipoMovimiento.toUpperCase() === 'ALTA').length;
  const bajas = rows.filter(item => item.tipoMovimiento.toUpperCase() === 'BAJA').length;
  const empresas = new Set(rows.map(item => item.empresa).filter(Boolean)).size;

  const html = `
    <article class="stat-card acrylic-surface stat-border-1">
      <div class="label">Total</div>
      <div class="value">${rows.length}</div>
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
    const isAlta = row.tipoMovimiento.toUpperCase() === 'ALTA';
    return `
      <tr>
        <td>
          <div class="fw-500">${core.safeText(fileNameOnly)}</div>
          <div class="doc-meta">${core.safeText(row.sizeText)} - ${core.safeText(row.estado)}</div>
        </td>
        <td>${core.safeText(row.empresa)}</td>
        <td>${isAlta ? '<span class="badge badge-green">ALTA</span>' : '<span class="badge badge-red">BAJA</span>'}</td>
        <td><span class="badge badge-blue">${core.safeText(row.dni)}</span></td>
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
  const mode = document.querySelector('.mode-tab.active').dataset.mode;
  const empresa = document.getElementById('empresaSelect')?.value || '';
  const tipo = document.getElementById('tipoSelect')?.value || '';
  const dniSimple = document.getElementById('dniInput')?.value || '';
  const periodo = document.getElementById('periodoSelect')?.value || '';

  const payload = {};
  if (empresa) payload.razon_social = empresa;
  if (tipo) payload.tipo = tipo;
  if (periodo) payload.periodo = periodo;

  if (mode === 'masiva') {
    const massInput = document.getElementById('dniMasivo')?.value || '';
    const codes = core.validateCodes(core.parseMasivo(massInput));
    if (codes.length === 0) throw new Error('Ingresa al menos un DNI para busqueda masiva.');
    payload.codigos = codes;
  } else if (dniSimple) {
    const codes = core.validateCodes([dniSimple]);
    payload.codigo_empleado = codes[0];
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
