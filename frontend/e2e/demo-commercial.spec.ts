import { test, expect } from '@playwright/test';

const EMAIL = process.env.DEMO_EMAIL ?? 'glory.henock@hologram.cd';
const PASS = process.env.DEMO_PASS ?? 'Hologram2026!';

test('demo commercial flow: login → video → catalog → alerts', async ({ page }) => {
  await page.goto('/login');
  await page.fill('#email', EMAIL);
  await page.fill('#password', PASS);
  await page.getByRole('button', { name: /connexion|login|submit/i }).click();

  await expect(page).toHaveURL(/\/demo/, { timeout: 30_000 });

  const iframe = page.locator('iframe[title*="Flux"], iframe[title*="vidéo"]').first();
  await expect(iframe).toBeVisible({ timeout: 15_000 });

  await expect(page.getByText(/Catalogue de règles/i)).toBeVisible();
  const activateBtn = page.getByRole('button', { name: 'Activer' }).first();
  if (await activateBtn.isVisible()) {
    await activateBtn.click();
    await expect(page.getByText(/activée/i)).toBeVisible({ timeout: 10_000 });
  }

  await page.goto('/zones');
  await expect(page.getByText(/Zone|zones/i).first()).toBeVisible();

  await page.goto('/demo');
  await expect(page.getByText(/Détections live|Alertes live/i).first()).toBeVisible();
});
