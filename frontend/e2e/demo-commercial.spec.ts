import { test, expect, type Page } from '@playwright/test';

const EMAIL = process.env.DEMO_EMAIL ?? 'glory.henock@hologram.cd';
const PASS = process.env.DEMO_PASS ?? 'Hologram2026!';

async function dismissTourIfNeeded(page: Page) {
  // driver.js overlays the entire viewport with an SVG that intercepts all pointer events.
  // Use JavaScript evaluation to click the skip button, bypassing the overlay entirely.
  await page.evaluate(() => {
    const allButtons = Array.from(document.querySelectorAll('button'));
    const skipBtn = allButtons.find((b) => /Passer la visite|Skip tour/i.test(b.textContent ?? ''));
    if (skipBtn) (skipBtn as HTMLButtonElement).click();
  });
  // Wait for the driver-active class to be removed (tour dismissed).
  await page.waitForFunction(
    () => !document.body.classList.contains('driver-active'),
    { timeout: 5000 },
  ).catch(() => {});
}

test.describe('Demo commercial workspace', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#email', EMAIL);
    await page.fill('#password', PASS);
    await page.locator('button[type="submit"]').first().click();
    await expect(page).not.toHaveURL(/\/login/, { timeout: 30_000 });
    await page.goto('/demo');
    await expect(page).toHaveURL(/\/demo/, { timeout: 30_000 });
    await dismissTourIfNeeded(page);
  });

  test('login → header → empty or active stream → catalog', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    // Wait for page to finish loading (may show spinner first).
    await expect(
      page.getByRole('heading', { level: 1, name: /Validation|Démonstration|Demonstration/i }),
    ).toBeVisible({ timeout: 20_000 });

    const contextLine = page.locator('text=/Ministère|Ministry/i').first();
    await expect(contextLine).toBeVisible();

    // Player area: either an empty state, stream unavailable message, or an active iframe player.
    const emptyState = page.getByText(/Importez un MP4|Upload an MP4|Importez une vid|Import a video/i);
    const streamUnavailable = page.getByText(/Flux vidéo indisponible|indisponible/i);
    const playerArea = page.locator('.cv-demo-player-shell');
    await expect(emptyState.or(streamUnavailable).or(playerArea).first()).toBeVisible({ timeout: 15_000 });

    await page.screenshot({ path: 'test-results/demo-desktop-1440.png', fullPage: true });

    await expect(page.getByText(/Catalogue de règles|Rule catalog/i)).toBeVisible({ timeout: 10_000 });
  });

  test('zone panel renders in correct state', async ({ page }) => {
    // Wait for demo page to finish loading.
    await expect(
      page.getByRole('heading', { level: 1, name: /Validation|Démonstration|Demonstration/i }),
    ).toBeVisible({ timeout: 20_000 });
    // Zone panel is either in "select source" blocked state, or need-stream state, or edit mode.
    const blockedMsg = page.getByText(/Sélectionnez explicitement|Select a video source/i);
    const zoneHeader = page.getByText(/Dessinez une zone|Dessiner une zone|Draw a zone/i);
    const needStream = page.getByText(/Importez une vidéo de test|caméra pour dessiner|Upload a test video/i);
    const zoneCard = page.locator('.cv-demo-zone-inline');
    await expect(blockedMsg.or(zoneHeader).or(needStream).or(zoneCard).first()).toBeVisible({ timeout: 15_000 });
  });

  test('nav label hint visible', async ({ page }) => {
    await expect(page.getByText(/menu latéral|sidebar menu/i)).toBeVisible();
  });

  test('reset demo button visible', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Reset démo|Reset demo/i })).toBeVisible();
  });

  test('mobile layout screenshot', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByRole('heading', { level: 1, name: /Validation|Démonstration|Demonstration/i })).toBeVisible({ timeout: 20_000 });
    await page.screenshot({ path: 'test-results/demo-mobile-390.png', fullPage: true });
  });

  test('rule activation controls visible in catalog', async ({ page }) => {
    await expect(page.getByText(/Catalogue de règles|Rule catalog/i)).toBeVisible();
    const configureBtn = page.getByRole('button', { name: /Activer|Configurer|Activate|Configure/i }).first();
    await expect(configureBtn).toBeVisible();
  });

  test('feeds panel visible', async ({ page }) => {
    await expect(page.getByText(/Détections live|Live detections/i).first()).toBeVisible();
    await expect(page.getByText(/Alertes live|Live alerts/i).first()).toBeVisible();
  });
});
