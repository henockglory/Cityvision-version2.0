import { test, expect } from '@playwright/test';

test.describe('Citévision v2 smoke', () => {
  test('setup page loads', async ({ page }) => {
    await page.goto('http://localhost:5174/setup');
    await expect(page).toHaveTitle(/Citévision|Citevision/i);
  });

  test('login page loads', async ({ page }) => {
    await page.goto('http://localhost:5174/login');
    await expect(page.getByRole('button')).toBeVisible();
  });
});
