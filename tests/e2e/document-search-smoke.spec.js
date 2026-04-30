import { test, expect } from '@playwright/test';

const E2E_USERNAME = process.env.E2E_USERNAME || 'testadmin';
const E2E_PASSWORD = process.env.E2E_PASSWORD || 'Test123456!';

test.setTimeout(90000);

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

async function expectCleanPage(page, path) {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') {
      errors.push(message.text());
    }
  });

  await page.goto(path, { waitUntil: 'networkidle' });
  await expect(page.locator('#themeToggleBtn')).toBeVisible();
  await expect.poll(() => page.locator('#empresaSelect option').count()).toBeGreaterThan(1);
  await expect(page.locator('#downloadZipBtn')).toContainText('ZIP');
  expect(errors).toEqual([]);
}

test.describe('Document search smoke', () => {
  test('loads filters and search UI for Seguros, T-Registro and Constancias', async ({ page, request }) => {
    await authenticate(page, request);

    await expectCleanPage(page, '/ui/seguros/');
    await expectCleanPage(page, '/ui/tregistro/');
    await expectCleanPage(page, '/ui/constancias/');
  });

  test('searches valid Planillas constancias and exports results as ZIP', async ({ page, request }) => {
    const token = await authenticate(page, request);

    const apiResponse = await request.get('/api/v2/constancias/search/?razon_social=RESGUARDO', {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(apiResponse.ok()).toBeTruthy();
    const apiPayload = await apiResponse.json();
    expect(apiPayload.total).toBeGreaterThan(0);
    expect(apiPayload.results[0].filename).toMatch(/^Planillas 20\d{2}\//);

    await page.goto('/ui/constancias/', { waitUntil: 'networkidle' });
    await page.waitForFunction(() => window._currentApp && !window._currentApp.state.loading);
    await page.locator('#empresaSelect').selectOption('RESGUARDO');
    const searchResponsePromise = page.waitForResponse(response => response.url().includes('/api/v2/constancias/search/'));
    await page.getByRole('button', { name: /buscar/i }).click();
    const searchResponse = await searchResponsePromise;
    expect(searchResponse.ok()).toBeTruthy();
    const searchPayload = await searchResponse.json();
    expect(searchPayload.total).toBeGreaterThan(0);
    await expect(page.locator('#stateTable')).toBeVisible();
    await expect.poll(() => page.locator('#tableBody tr').count()).toBeGreaterThan(0);

    const zipResponse = await request.post('/api/v2/documents/download-zip', {
      headers: { Authorization: `Bearer ${token}` },
      data: { document_ids: apiPayload.results.slice(0, 2).map(doc => doc.id) },
    });
    expect(zipResponse.ok()).toBeTruthy();
    expect(zipResponse.headers()['content-type']).toContain('application/zip');
    expect(zipResponse.headers()['x-files-zipped']).toBeTruthy();
    const zipBytes = await zipResponse.body();
    expect(zipBytes[0]).toBe(0x50);
    expect(zipBytes[1]).toBe(0x4b);
  });

  test('does not expose loose 20XX root folders in file management', async ({ page, request }) => {
    const token = await authenticate(page, request);
    const response = await request.get('/api/folders/list', {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(response.ok()).toBeTruthy();
    const payload = await response.json();
    const paths = payload.folders.map(folder => folder.path);
    expect(paths.some(path => /^20\d{2}\/$/.test(path))).toBeFalsy();
    expect(paths.some(path => /^Planillas 20\d{2}\/$/.test(path))).toBeTruthy();

    await page.goto('/ui/files/', { waitUntil: 'networkidle' });
    await expect(page.locator('#filesTableBody tr.folder-row', { hasText: /^20\d{2}$/ })).toHaveCount(0);
    await expect.poll(() => page.locator('#filesTableBody tr.folder-row', { hasText: /Planillas 20\d{2}/ }).count()).toBeGreaterThan(0);
  });
});
