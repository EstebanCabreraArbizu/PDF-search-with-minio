const { test, expect } = require('@playwright/test');

test('main UI theme toggle cycles through 4 themes', async ({ page }) => {
  await page.goto('http://localhost:8000/ui/constancias/'); // adjust port if needed
  const html = page.locator('html');
  const button = page.locator('#themeToggleBtn');
  const themes = ['corp','dark','light','corp-dark'];
  for (let i = 0; i < themes.length; i++) {
    await button.click();
    await expect(html).toHaveAttribute('data-theme', themes[(i+1)%themes.length]);
  }
});
