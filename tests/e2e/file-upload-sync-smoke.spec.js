import { test, expect } from '@playwright/test';

const E2E_USERNAME = process.env.E2E_USERNAME || 'testadmin';
const E2E_PASSWORD = process.env.E2E_PASSWORD || 'Test123456!';

test.setTimeout(300000);

function buildMinimalPdf(label) {
  const escaped = label.replace(/[()\\]/g, '\\$&');
  const objects = [
    '1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n',
    '2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n',
    '3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n',
    `4 0 obj\n<< /Length ${54 + escaped.length} >>\nstream\nBT /F1 12 Tf 72 720 Td (${escaped}) Tj ET\nendstream\nendobj\n`,
    '5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n',
  ];
  let body = '%PDF-1.4\n';
  const offsets = [0];
  for (const object of objects) {
    offsets.push(Buffer.byteLength(body, 'utf8'));
    body += object;
  }
  const xrefOffset = Buffer.byteLength(body, 'utf8');
  body += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  body += offsets.slice(1).map(offset => `${String(offset).padStart(10, '0')} 00000 n \n`).join('');
  body += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`;
  return Buffer.from(body, 'utf8');
}

async function authenticate(page, request) {
  const response = await request.post('/api/auth/login/', {
    data: { username: E2E_USERNAME, password: E2E_PASSWORD },
  });
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();

  await page.addInitScript(({ token, user, username }) => {
    localStorage.setItem('docsearch_v2_access_token', token);
    localStorage.setItem('docsearch_v2_user', JSON.stringify(user || { username, is_staff: true }));
    localStorage.removeItem('docsearch_theme');
  }, { token: payload.access, user: payload.user, username: E2E_USERNAME });

  return payload.access;
}

async function cleanupE2EFiles(request, token) {
  const response = await request.get('/api/files/list?search=E2E_&per_page=50', {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) return;
  const payload = await response.json();
  for (const file of payload.files || []) {
    if (file.path && file.name.includes('E2E_')) {
      await request.delete('/api/files/delete', {
        headers: { Authorization: `Bearer ${token}` },
        data: { path: file.path },
      });
    }
  }
}

test.describe('File upload and sync smoke', () => {
  test('uploads a unique PDF, verifies storage/index visibility, runs sync, and cleans up', async ({ page, request }) => {
    const token = await authenticate(page, request);
    await cleanupE2EFiles(request, token);

    const runId = Date.now();
    const filename = `FIN DE MES ENERO 2026 RESGUARDO BCP E2E_${runId}.pdf`;
    const pdf = buildMinimalPdf(`E2E upload sync ${runId}`);
    const browserErrors = [];
    const serverErrors = [];
    let uploadedPath = null;
    let cleanupError = null;

    page.on('pageerror', error => browserErrors.push(error.message));
    page.on('console', message => {
      if (message.type() === 'error') browserErrors.push(message.text());
    });
    page.on('response', response => {
      const url = response.url();
      if ((url.includes('/api/files/') || url.includes('/api/index/sync')) && response.status() >= 500) {
        serverErrors.push(`${response.status()} ${url}`);
      }
    });

    try {
      await page.goto('/ui/files/?section=sync#sync-section', { waitUntil: 'networkidle' });
      await expect(page.locator('#upload-section')).toBeVisible();
      await expect(page.locator('#sync-section')).toBeVisible();

      const previewResponsePromise = page.waitForResponse(response => (
        response.url().includes('/api/files/classify-preview') && response.request().method() === 'POST'
      ));
      await page.locator('#fileInput').setInputFiles({
        name: filename,
        mimeType: 'application/pdf',
        buffer: pdf,
      });
      const previewResponse = await previewResponsePromise;
      expect(previewResponse.ok()).toBeTruthy();
      const previewPayload = await previewResponse.json();
      expect(previewPayload.files?.[0]?.filename).toBe(filename);
      await expect(page.locator('#uploadPreviewArea')).toBeVisible();
      await expect(page.locator('#classifyPreviewBody')).toContainText(filename);

      const previewCheckbox = page.locator('.preview-checkbox').first();
      await expect(previewCheckbox).toBeVisible();
      await previewCheckbox.check();

      const uploadResponsePromise = page.waitForResponse(response => (
        response.url().includes('/api/files/upload') && response.request().method() === 'POST'
      ));
      await page.locator('#uploadApprovedBtn').click();
      const uploadResponse = await uploadResponsePromise;
      expect(uploadResponse.status(), await uploadResponse.text()).toBe(201);
      const uploadPayload = await uploadResponse.json();
      expect(uploadPayload.success).toBeTruthy();
      expect(uploadPayload.total_uploaded).toBe(1);
      expect(uploadPayload.uploaded[0].filename).toBe(filename);
      expect(uploadPayload.uploaded[0].docrepo_document_id).toBeTruthy();
      expect(uploadPayload.uploaded[0].path).toContain(filename);
      uploadedPath = uploadPayload.uploaded[0].path;

      await expect(page.locator('#uploadProgressText')).toContainText('Subida completada');

      const filesResponse = await request.get(`/api/files/list?search=${encodeURIComponent(filename)}&per_page=5`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      expect(filesResponse.ok()).toBeTruthy();
      const filesPayload = await filesResponse.json();
      expect(filesPayload.files.some(file => file.path === uploadedPath)).toBeTruthy();

      await page.locator('#filesSearchInput').fill(filename);
      await expect(page.locator('#filesTableBody')).toContainText(filename);

      await page.locator('#syncBatchSize').fill('50');
      await page.locator('#syncSkipNew').check();
      await expect(page.locator('#runSyncBtn')).toBeVisible();
      await expect(page.locator('#syncSkipNew')).toBeChecked();

      const syncResponse = await request.post('/api/index/sync', {
        headers: { Authorization: `Bearer ${token}` },
        data: { batch_size: 50, skip_new: true },
        timeout: 240000,
      });
      expect(syncResponse.ok()).toBeTruthy();
      const syncPayload = await syncResponse.json();
      expect(syncPayload.errors || 0).toBe(0);
      expect(syncPayload.has_more).toBeFalsy();
      expect(syncPayload.progress_percent).toBe(100);

      expect(browserErrors).toEqual([]);
      expect(serverErrors).toEqual([]);
    } finally {
      if (uploadedPath) {
        const deleteResponse = await request.delete('/api/files/delete', {
          headers: { Authorization: `Bearer ${token}` },
          data: { path: uploadedPath },
        });
        if (!deleteResponse.ok()) {
          cleanupError = `${deleteResponse.status()} ${await deleteResponse.text()}`;
        }
      }
      expect(cleanupError).toBeNull();
    }
  });
});
