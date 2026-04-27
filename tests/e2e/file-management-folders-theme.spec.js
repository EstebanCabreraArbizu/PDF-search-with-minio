import { test, expect } from '@playwright/test';

const AUTH_TOKEN_KEY = 'docsearch_v2_access_token';
const USER_KEY = 'docsearch_v2_user';
const THEME_KEY = 'docsearch_theme';
const THEMES = ['corp', 'light', 'dark', 'corp-dark'];

async function authenticate(page, request) {
  const response = await request.post('/api/auth/login/', {
    data: { username: 'admin', password: 'admin123' },
  });
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();

  await page.addInitScript(({ token, user }) => {
    localStorage.setItem('docsearch_v2_access_token', token);
    localStorage.setItem('docsearch_v2_user', JSON.stringify(user || { username: 'admin', is_staff: true }));
    localStorage.removeItem('docsearch_theme');
  }, { token: payload.access, user: payload.user });

  return payload.access;
}

test.describe('File management folders and themes', () => {
  test('renders API folders and cycles all 4 themes in /ui/files/', async ({ page, request }) => {
    const token = await authenticate(page, request);
    const browserErrors = [];
    const apiResponses = [];

    page.on('pageerror', error => browserErrors.push(error.message));
    page.on('console', message => {
      if (['error', 'warning'].includes(message.type())) {
        browserErrors.push(`${message.type()}: ${message.text()}`);
      }
    });
    page.on('response', response => {
      if (response.url().includes('/api/files/') || response.url().includes('/api/folders/')) {
        apiResponses.push(`${response.status()} ${response.url()}`);
      }
    });

    const foldersResponse = await request.get('/api/folders/list', {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(foldersResponse.ok()).toBeTruthy();
    const foldersPayload = await foldersResponse.json();
    expect(Array.isArray(foldersPayload.folders)).toBeTruthy();
    expect(foldersPayload.folders.length).toBeGreaterThan(0);

    await page.goto('/ui/files/', { waitUntil: 'networkidle' });

    expect(browserErrors).toEqual([]);
    expect(apiResponses.some(item => item.includes('/api/folders/list'))).toBeTruthy();
    await expect(page.locator('#filesStateTable')).toBeVisible();
    await expect(page.locator('#filesStateEmpty')).toBeHidden();

    const firstFolder = foldersPayload.folders[0];
    const folderRow = page.locator('#filesTableBody tr.folder-row', { hasText: firstFolder.name }).first();
    await expect(folderRow).toBeVisible();

    await folderRow.click();
    await expect(page).toHaveURL(new RegExp(`#files/${encodeURIComponent(firstFolder.name)}`));
    await expect(page.locator('#filesBreadcrumb')).toContainText(firstFolder.name);

    await page.locator('#themeToggleBtn').click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', THEMES[1]);

    await page.locator('#themeToggleBtn').click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', THEMES[2]);

    await page.locator('#themeToggleBtn').click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', THEMES[3]);

    await page.locator('#themeToggleBtn').click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', THEMES[0]);

    await expect.poll(() => page.evaluate(key => localStorage.getItem(key), THEME_KEY)).toBe(THEMES[0]);
    await expect.poll(() => page.evaluate(key => localStorage.getItem(key), AUTH_TOKEN_KEY)).not.toBeNull();
    await expect.poll(() => page.evaluate(key => localStorage.getItem(key), USER_KEY)).not.toBeNull();
  });
});
