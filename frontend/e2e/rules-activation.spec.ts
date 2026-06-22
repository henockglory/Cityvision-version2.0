import { test, expect } from '@playwright/test';

const EMAIL = process.env.EMAIL ?? 'glory.henock@hologram.cd';
const PASS = process.env.PASS ?? 'Hologram2026!';
const TEST_RULE_ID = process.env.TEST_RULE_ID;

async function disableAutoTours(page: import('@playwright/test').Page) {
  await page.addInitScript(() => {
    (window as unknown as { __CV_E2E__?: boolean }).__CV_E2E__ = true;
    const key = 'cv-ui';
    const raw = localStorage.getItem(key);
    const parsed = raw ? JSON.parse(raw) : { state: {}, version: 0 };
    parsed.state = {
      ...(parsed.state ?? {}),
      toursAutoStart: false,
      completedTours: {
        ...(parsed.state?.completedTours ?? {}),
        rules: true,
        dashboard: true,
        alerts: true,
        liveView: true,
        settings: true,
      },
    };
    localStorage.setItem(key, JSON.stringify(parsed));
  });
}

test('rules activation toggles the clicked rule row', async ({ page }) => {
  if (!TEST_RULE_ID) {
    throw new Error('TEST_RULE_ID env var required (set by scripts/validate-rules-ux.sh)');
  }

  await disableAutoTours(page);

  await page.goto('/login');
  await page.fill('#email, input[name=email], input[type=email]', EMAIL);
  await page.fill('#password, input[name=password], input[type=password]', PASS);
  const submit = page.locator('button[type=submit]').first();
  await expect(submit).toBeVisible({ timeout: 20_000 });
  await submit.click();
  await page.waitForURL(/\/(dashboard|live|alerts|rules)/, { timeout: 20_000 }).catch(() => {});

  await page.goto('/rules');
  await page.waitForTimeout(800);
  await page.evaluate(() => {
    document.querySelectorAll('.driver-overlay, .driver-popover').forEach((el) => el.remove());
    document.body.classList.remove('driver-active');
  });

  const row = page.locator(`[data-testid='rule-row-${TEST_RULE_ID}']`);
  await expect(row).toBeVisible({ timeout: 30_000 });
  await expect(row).toContainText('UX toggle test');

  const enableBtn = row.getByRole('button', { name: /activer|enable/i });
  await expect(enableBtn).toBeVisible();
  await enableBtn.scrollIntoViewIfNeeded();
  await enableBtn.click();

  await expect(row).toHaveAttribute('data-highlighted', 'true', { timeout: 5000 });
  await expect(row.getByText(/activée|enabled/i)).toBeVisible({ timeout: 10_000 });

  const toggledRuleId = await row.getAttribute('data-testid');
  expect(toggledRuleId).toBe(`rule-row-${TEST_RULE_ID}`);

  await page.waitForTimeout(2200);
  await expect(row).toHaveAttribute('data-highlighted', 'false', { timeout: 3000 });
});
