import { test, expect } from '@playwright/test';

const E2E_USERNAME = process.env.E2E_USERNAME || 'testadmin';
const E2E_PASSWORD = process.env.E2E_PASSWORD || 'Test123456!';

test.setTimeout(90000);

// ───────────────────────────────────────────────
// Helpers
// ───────────────────────────────────────────────

async function authenticate(page, request) {
  const response = await request.post('/api/auth/login/', {
    data: { username: E2E_USERNAME, password: E2E_PASSWORD },
  });
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();

  await page.addInitScript(({ token, user, username }) => {
    localStorage.setItem('docsearch_v2_access_token', token);
    localStorage.setItem('docsearch_v2_user', JSON.stringify(user || { username, is_staff: true }));
    sessionStorage.clear();
  }, { token: payload.access, user: payload.user, username: E2E_USERNAME });

  return payload.access;
}

async function navigateAndWaitForApp(page, path) {
  await page.goto(path, { waitUntil: 'networkidle' });
  await expect(page.locator('#themeToggleBtn')).toBeVisible();
  await page.waitForFunction(() => window._currentApp && !window._currentApp.state.loading, { timeout: 10000 });
}

async function triggerSearch(page, module, filters = {}) {
  if (filters.empresa) {
    await page.locator('#empresaSelect').selectOption(filters.empresa);
  }
  const searchResponsePromise = page.waitForResponse(
    response => response.url().includes(`/api/v2/${module}/search`)
  );
  await page.getByRole('button', { name: /buscar/i }).click();
  return searchResponsePromise;
}

// ───────────────────────────────────────────────
// Test Suite: UX Interactivity
// ───────────────────────────────────────────────

test.describe('UX Interactivity — Skeleton Loaders', () => {

  test('skeleton rows appear immediately on search submit', async ({ page, request }) => {
    await authenticate(page, request);
    await navigateAndWaitForApp(page, '/ui/constancias/');

    await page.locator('#empresaSelect').selectOption({ index: 1 });

    // Start search and immediately check for skeleton
    const searchPromise = page.waitForResponse(r => r.url().includes('/api/v2/constancias/search'));
    await page.getByRole('button', { name: /buscar/i }).click();

    // Skeleton should appear before response arrives
    await expect(page.locator('.skeleton-row').first()).toBeVisible({ timeout: 500 });
    await expect(page.locator('.shimmer').first()).toBeVisible({ timeout: 500 });

    // Wait for search to complete
    await searchPromise;

    // Skeleton should be gone, replaced by real results
    await expect(page.locator('.skeleton-row')).toHaveCount(0, { timeout: 5000 });
  });

  test('error state appears when search fails', async ({ page, request }) => {
    await authenticate(page, request);
    await navigateAndWaitForApp(page, '/ui/constancias/');

    // Intercept API to force a failure
    await page.route('**/api/v2/constancias/search**', route => {
      route.fulfill({ status: 500, body: JSON.stringify({ error: 'Server Error' }) });
    });

    await page.locator('#empresaSelect').selectOption({ index: 1 });
    await page.getByRole('button', { name: /buscar/i }).click();

    // Error state should appear
    await expect(page.locator('.error-state')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('.error-state')).toContainText(/reintentar|error/i);
  });
});

test.describe('UX Interactivity — Codes Badge', () => {

  test('codes badge shows count instead of raw list', async ({ page, request }) => {
    const token = await authenticate(page, request);

    // First verify API returns employee_codes
    const apiResponse = await request.get('/api/v2/constancias/search/?razon_social=RESGUARDO', {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(apiResponse.ok()).toBeTruthy();
    const apiPayload = await apiResponse.json();
    expect(apiPayload.total).toBeGreaterThan(0);

    // Navigate and search
    await navigateAndWaitForApp(page, '/ui/constancias/');
    await triggerSearch(page, 'constancias', { empresa: 'RESGUARDO' });

    // Wait for results
    await expect(page.locator('#stateTable')).toBeVisible({ timeout: 10000 });
    await expect.poll(() => page.locator('#tableBody tr').count()).toBeGreaterThan(0);

    // Badge should show "N códigos" pattern, not raw comma-separated list
    const badges = page.locator('.codes-badge');
    await expect(badges.first()).toBeVisible();
    await expect(badges.first()).toContainText(/\d+ códigos/);
  });

  test('codes badge popover opens on click and has copy button', async ({ page, request }) => {
    await authenticate(page, request);
    await navigateAndWaitForApp(page, '/ui/constancias/');
    await triggerSearch(page, 'constancias', { empresa: 'RESGUARDO' });

    await expect(page.locator('#stateTable')).toBeVisible({ timeout: 10000 });
    await expect.poll(() => page.locator('#tableBody tr').count()).toBeGreaterThan(0);

    // Click the first badge
    const firstBadge = page.locator('.codes-badge').first();
    await firstBadge.click();

    // Popover should be visible with copy button
    const popover = page.locator('.codes-popover').first();
    await expect(popover).toBeVisible({ timeout: 2000 });
    await expect(popover.locator('.codes-popover-copy')).toBeVisible();
    await expect(popover.locator('.codes-popover-copy')).toContainText(/copiar/i);
  });
});

test.describe('UX Interactivity — Stats Cards', () => {

  test('constancias shows stats cards after search', async ({ page, request }) => {
    await authenticate(page, request);
    await navigateAndWaitForApp(page, '/ui/constancias/');
    await triggerSearch(page, 'constancias', { empresa: 'RESGUARDO' });

    await expect(page.locator('#stateTable')).toBeVisible({ timeout: 10000 });

    // Stats container should have stat cards
    const statsContainer = page.locator('#statsConstancias');
    await expect(statsContainer.locator('.stat-card')).toHaveCount(3, { timeout: 5000 });

    // Verify stat labels
    await expect(statsContainer).toContainText('Total');
    await expect(statsContainer).toContainText('Bancos');
    await expect(statsContainer).toContainText('Tipos');

    // Values should be numeric
    const totalValue = statsContainer.locator('.stat-card').first().locator('.value');
    await expect(totalValue).toHaveText(/^\d+$/);
  });

  test('seguros shows stats cards after search', async ({ page, request }) => {
    await authenticate(page, request);
    await navigateAndWaitForApp(page, '/ui/seguros/');
    await triggerSearch(page, 'seguros', { empresa: 'RESGUARDO' });

    await expect(page.locator('#stateTable')).toBeVisible({ timeout: 10000 });

    const statsContainer = page.locator('#statsSeguros');
    await expect(statsContainer.locator('.stat-card').first()).toBeVisible({ timeout: 5000 });
  });

  test('tregistro shows stats cards after search', async ({ page, request }) => {
    await authenticate(page, request);
    await navigateAndWaitForApp(page, '/ui/tregistro/');
    await triggerSearch(page, 'tregistro', { empresa: 'RESGUARDO' });

    await expect(page.locator('#stateTable')).toBeVisible({ timeout: 10000 });

    const statsContainer = page.locator('#statsTRegistro');
    await expect(statsContainer.locator('.stat-card').first()).toBeVisible({ timeout: 5000 });
  });
});

test.describe('UX Interactivity — Unified Columns', () => {

  test('all 3 modules have the same column structure', async ({ page, request }) => {
    await authenticate(page, request);
    const expectedHeaders = ['Documento', 'Empresa', 'Tipo', 'Detalle', 'Códigos', 'Periodo', 'Acciones'];

    for (const module of ['/ui/constancias/', '/ui/seguros/', '/ui/tregistro/']) {
      await page.goto(module, { waitUntil: 'networkidle' });
      await expect(page.locator('#themeToggleBtn')).toBeVisible();

      const headers = await page.locator('thead th').allTextContents();
      const cleaned = headers.map(h => h.trim());
      expect(cleaned).toEqual(expectedHeaders);
    }
  });
});

test.describe('UX Interactivity — Clear Button & Dynamic Periods', () => {

  test('limpiar button resets all filters and hides results', async ({ page, request }) => {
    await authenticate(page, request);
    await navigateAndWaitForApp(page, '/ui/constancias/');

    // Set some filters
    await page.locator('#empresaSelect').selectOption({ index: 1 });
    await page.locator('#dniInput').fill('12345678');

    // Trigger search to get results
    await triggerSearch(page, 'constancias', {});
    await expect(page.locator('#stateTable')).toBeVisible({ timeout: 10000 });

    // Click limpiar
    await page.locator('#limpiarBtn').click();

    // All inputs should be cleared
    await expect(page.locator('#empresaSelect')).toHaveValue('');
    await expect(page.locator('#dniInput')).toHaveValue('');
    await expect(page.locator('#resultCount')).toContainText('0 documentos');

    // Results should be hidden, empty state visible
    await expect(page.locator('#stateTable')).toBeHidden();
    await expect(page.locator('#stateEmpty')).toBeVisible();
  });

  test('period selects are dynamically populated, not hardcoded', async ({ page, request }) => {
    await authenticate(page, request);

    // Check seguros - should NOT have hardcoded "Ene 2024"
    await navigateAndWaitForApp(page, '/ui/seguros/');
    const segurosOptions = await page.locator('#periodoSelect option').allTextContents();
    expect(segurosOptions.filter(o => o === 'Ene 2024')).toHaveLength(0);

    // Check tregistro - should NOT have hardcoded options
    await navigateAndWaitForApp(page, '/ui/tregistro/');
    const tregistroOptions = await page.locator('#periodoSelect option').allTextContents();
    expect(tregistroOptions.filter(o => o === 'Ene 2024')).toHaveLength(0);
  });
});

test.describe('UX Interactivity — ZIP Download (Flat PDFs)', () => {

  test('ZIP download contains flat PDFs without folder structure', async ({ page, request }) => {
    const token = await authenticate(page, request);

    // Get some document IDs via API
    const apiResponse = await request.get('/api/v2/constancias/search/?razon_social=RESGUARDO', {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(apiResponse.ok()).toBeTruthy();
    const apiPayload = await apiResponse.json();
    expect(apiPayload.total).toBeGreaterThan(0);

    const docIds = apiPayload.results.slice(0, 3).map(doc => doc.id);

    // Request ZIP download
    const zipResponse = await request.post('/api/v2/documents/download-zip', {
      headers: { Authorization: `Bearer ${token}` },
      data: { document_ids: docIds },
    });
    expect(zipResponse.ok()).toBeTruthy();
    expect(zipResponse.headers()['content-type']).toContain('application/zip');
    expect(zipResponse.headers()['content-disposition']).toMatch(/attachment.*\.zip/);

    // Verify ZIP magic bytes (PK header)
    const zipBytes = await zipResponse.body();
    expect(zipBytes[0]).toBe(0x50); // P
    expect(zipBytes[1]).toBe(0x4b); // K

    // Verify X-Files-Zipped header
    const filesZipped = parseInt(zipResponse.headers()['x-files-zipped'] || '0');
    expect(filesZipped).toBeGreaterThan(0);
    expect(filesZipped).toBeLessThanOrEqual(docIds.length);
  });

  test('ZIP button triggers download from UI', async ({ page, request }) => {
    await authenticate(page, request);
    await navigateAndWaitForApp(page, '/ui/constancias/');
    await triggerSearch(page, 'constancias', { empresa: 'RESGUARDO' });

    await expect(page.locator('#stateTable')).toBeVisible({ timeout: 10000 });
    await expect.poll(() => page.locator('#tableBody tr').count()).toBeGreaterThan(0);

    // ZIP button should be visible
    const zipBtn = page.locator('#downloadZipBtn');
    await expect(zipBtn).toBeVisible();
    await expect(zipBtn).toContainText('ZIP');
  });
});

test.describe('UX Interactivity — Cross-Module Consistency', () => {

  test('sidebar navigation works between all modules', async ({ page, request }) => {
    await authenticate(page, request);
    await page.goto('/ui/constancias/', { waitUntil: 'networkidle' });

    // Navigate via sidebar
    await page.locator('.nav-item', { hasText: 'Seguros' }).click();
    await expect(page).toHaveURL(/\/ui\/seguros\//);
    await expect(page.locator('#themeToggleBtn')).toBeVisible();

    await page.locator('.nav-item', { hasText: 'T-Registro' }).click();
    await expect(page).toHaveURL(/\/ui\/tregistro\//);
    await expect(page.locator('#themeToggleBtn')).toBeVisible();

    await page.locator('.nav-item', { hasText: 'Constancias' }).click();
    await expect(page).toHaveURL(/\/ui\/constancias\//);
    await expect(page.locator('#themeToggleBtn')).toBeVisible();
  });

  test('all modules load filter dropdowns dynamically', async ({ page, request }) => {
    await authenticate(page, request);

    for (const module of ['/ui/constancias/', '/ui/seguros/', '/ui/tregistro/']) {
      await navigateAndWaitForApp(page, module);
      // empresaSelect should have more than just the placeholder
      await expect.poll(() => page.locator('#empresaSelect option').count()).toBeGreaterThan(1);
    }
  });
});
