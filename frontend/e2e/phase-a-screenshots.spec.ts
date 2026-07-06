import { test } from '@playwright/test';

const pages = [
  { path: '/demo', name: 'demo-desktop-1440' },
  { path: '/rules', name: 'rules-desktop-1440' },
  { path: '/zones', name: 'zones-desktop-1440' },
];

test.describe('Phase A aesthetic captures [N.118] [M.109]', () => {
  for (const { path, name } of pages) {
    test(`desktop 1440 ${path}`, async ({ page }) => {
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(path);
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: `test-results/${name}.png`, fullPage: true });
    });

    test(`mobile 390 ${path}`, async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto(path);
      await page.waitForLoadState('networkidle');
      const mobileName = name.replace('desktop', 'mobile');
      await page.screenshot({ path: `test-results/${mobileName}.png`, fullPage: true });
    });
  }
});
