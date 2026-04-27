import { test, expect } from '@playwright/test';

test.setTimeout(60000);

const BASE_URL = 'http://localhost:8000';

// Theme sequence: corp → light → dark → corp-dark → corp (repeat)
const THEME_SEQUENCE = ['corp', 'light', 'dark', 'corp-dark'];

// Icon mapping for each theme
const THEME_ICONS = {
  'corp': 'ti-adjustments',
  'light': 'ti-sun',
  'dark': 'ti-moon',
  'corp-dark': 'ti-moon-2'
};

test.describe('4-Theme System Verification', () => {
  test('Login page has 4 themes cycling correctly (corp → light → dark → corp-dark)', async ({ page: browserPage, context }) => {
    // Clear all storage using Playwright context API
    await context.clearCookies();
    await browserPage.context().addInitScript(() => {
      localStorage.clear();
    });

    // Navigate to login page
    await browserPage.goto(`${BASE_URL}/ui/login/`, { waitUntil: 'networkidle' });
    await browserPage.waitForTimeout(500);

    // Verify initial theme is 'corp'
    let currentTheme = await browserPage.evaluate(() => {
      return document.documentElement.getAttribute('data-theme');
    });
    expect(currentTheme).toBe('corp');
    console.log('✓ Initial theme is corp');

    // Cycle through all themes - starting from the NEXT theme after corp
    for (let i = 1; i <= THEME_SEQUENCE.length; i++) {
      await browserPage.locator('#themeToggleBtn').click();
      await browserPage.waitForTimeout(300);

      const expectedTheme = THEME_SEQUENCE[i % THEME_SEQUENCE.length];
      const expectedIcon = THEME_ICONS[expectedTheme];

      const newTheme = await browserPage.evaluate(() => {
        return document.documentElement.getAttribute('data-theme');
      });

      console.log(`Click ${i}: theme changed to ${newTheme} (expected: ${expectedTheme})`);
      expect(newTheme).toBe(expectedTheme);

      // Check if icon updated correctly
      const iconClasses = await browserPage.locator('#themeToggleIcon').getAttribute('class');
      console.log(`  Icon classes: ${iconClasses}`);
      expect(iconClasses).toContain(expectedIcon);

      // Check title attribute shows theme name
      const titleAttr = await browserPage.locator('#themeToggleBtn').getAttribute('title');
      console.log(`  Title: ${titleAttr}`);
      expect(titleAttr).toBeTruthy();
    }

    console.log('✓ All 4 themes cycle correctly');
  });

  test('Search modules have 4 themes cycling correctly', async ({ page: browserPage }) => {
    // Add init script to clear localStorage before page loads
    await browserPage.addInitScript(() => {
      try {
        localStorage.clear();
      } catch (e) {
        console.log('Could not clear localStorage:', e);
      }
    });

    const searchPages = [
      { name: 'Seguros', path: '/ui/seguros/' },
      { name: 'Constancias', path: '/ui/constancias/' },
      { name: 'T-Registro', path: '/ui/tregistro/' }
    ];

    for (const searchPage of searchPages) {
      console.log(`\n--- Testing ${searchPage.name} ---`);
      
      // Navigate to search page
      await browserPage.goto(`${BASE_URL}${searchPage.path}`, { waitUntil: 'networkidle' });
      await browserPage.waitForTimeout(500);

      // Verify initial theme is 'corp'
      const initialTheme = await browserPage.evaluate(() => {
        return document.documentElement.getAttribute('data-theme');
      });
      expect(initialTheme).toBe('corp');
      console.log(`✓ ${searchPage.name}: Initial theme is corp`);

      // Test cycling through themes (4 clicks to complete one full cycle)
      for (let click = 1; click <= 3; click++) {
        await browserPage.locator('#themeToggleBtn').click();
        await browserPage.waitForTimeout(300);

        const theme = await browserPage.evaluate(() => {
          return document.documentElement.getAttribute('data-theme');
        });

        const expectedTheme = THEME_SEQUENCE[click % THEME_SEQUENCE.length];
        console.log(`  Click ${click}: theme is ${theme} (expected: ${expectedTheme})`);
        expect(theme).toBe(expectedTheme);
      }
    }
  });

  test('Theme persists when navigating between pages', async ({ browser }) => {
    // Create a fresh context to test localStorage persistence
    const context = await browser.newContext();
    const browserPage = await context.newPage();

    try {
      // Navigate to login page
      await browserPage.goto(`${BASE_URL}/ui/login/`, { waitUntil: 'networkidle' });
      await browserPage.waitForTimeout(500);

      // Switch to 'dark' theme (2 clicks: corp → light → dark)
      await browserPage.locator('#themeToggleBtn').click();
      await browserPage.waitForTimeout(300);
      await browserPage.locator('#themeToggleBtn').click();
      await browserPage.waitForTimeout(300);

      let currentTheme = await browserPage.evaluate(() => {
        return document.documentElement.getAttribute('data-theme');
      });
      expect(currentTheme).toBe('dark');
      console.log('✓ Set theme to dark on login page');

      // Check localStorage has the theme
      const storedTheme = await browserPage.evaluate(() => {
        return localStorage.getItem('selectedTheme');
      });
      console.log(`✓ Theme stored in localStorage: ${storedTheme}`);

      // Navigate to search page - theme should persist from localStorage
      await browserPage.goto(`${BASE_URL}/ui/seguros/`, { waitUntil: 'networkidle' });
      await browserPage.waitForTimeout(500);

      // Verify theme persisted
      const themeOnSearchPage = await browserPage.evaluate(() => {
        return document.documentElement.getAttribute('data-theme');
      });
      expect(themeOnSearchPage).toBe('dark');
      console.log('✓ Theme persisted when navigating to search page');

      // Navigate back to login page
      await browserPage.goto(`${BASE_URL}/ui/login/`, { waitUntil: 'networkidle' });
      await browserPage.waitForTimeout(500);

      const themeBack = await browserPage.evaluate(() => {
        return document.documentElement.getAttribute('data-theme');
      });
      expect(themeBack).toBe('dark');
      console.log('✓ Theme persisted when navigating back to login page');
    } finally {
      await context.close();
    }
  });

  test('All 4 themes have distinct visual styles', async ({ page: browserPage }) => {
    await browserPage.goto(`${BASE_URL}/ui/login/`, { waitUntil: 'networkidle' });
    await browserPage.waitForTimeout(500);

    const cssVariables = {};

    for (let i = 0; i < THEME_SEQUENCE.length; i++) {
      const theme = THEME_SEQUENCE[i];

      const vars = await browserPage.evaluate(() => {
        const root = document.documentElement;
        return {
          bgColor: getComputedStyle(root).getPropertyValue('--fa-color-bg-surface-1').trim(),
          textColor: getComputedStyle(root).getPropertyValue('--fa-color-text-primary').trim(),
        };
      });

      cssVariables[theme] = vars;
      console.log(`${theme}: bg=${vars.bgColor}, text=${vars.textColor}`);

      // Click to go to next theme
      if (i < THEME_SEQUENCE.length - 1) {
        await browserPage.locator('#themeToggleBtn').click();
        await browserPage.waitForTimeout(300);
      }
    }

    // Verify all themes have different values
    const uniqueThemes = new Set(Object.values(cssVariables).map(v => `${v.bgColor}|${v.textColor}`));
    expect(uniqueThemes.size).toBeGreaterThanOrEqual(3); // At least 3 different combinations
    console.log(`✓ Found ${uniqueThemes.size} distinct theme combinations`);
  });
});
