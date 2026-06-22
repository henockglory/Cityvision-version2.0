import { test, expect } from '@playwright/test';

const DEMO_EMAIL = process.env.DEMO_EMAIL ?? 'glory.henock@hologram.cd';
const DEMO_PASSWORD = process.env.DEMO_PASSWORD ?? 'Hologram2026!';
const BASE = process.env.E2E_BASE_URL ?? 'http://localhost:5174';
const SAMPLE_SEC = Number(process.env.VIDEO_SMOOTH_SEC ?? 20);
const INTERVAL_MS = 400;

async function login(page: import('@playwright/test').Page) {
  await page.goto(`${BASE}/login`);
  await page.getByLabel('Email').fill(DEMO_EMAIL);
  await page.getByLabel('Mot de passe').fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: 'Se connecter' }).click();
  await page.waitForURL(/\/(demo|dashboard|setup)/, { timeout: 30_000 });
}

test.describe('Fluidité vidéo WebRTC démo', () => {
  test('lecture monotone sans recul ni freeze prolongé', async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/demo`);
    await page.waitForSelector('video', { timeout: 30_000 });

    const video = page.locator('video').first();
    await expect(video).toBeVisible();

    // Flux actif = dimensions vidéo connues (plus fiable que le badge LIVE)
    await page.waitForFunction(
      () => {
        const v = document.querySelector('video');
        return v instanceof HTMLVideoElement && v.videoWidth > 0 && v.readyState >= 2;
      },
      { timeout: 60_000 },
    );

    const metrics = await page.evaluate(
      async ({ sampleSec, intervalMs }) => {
        const v = document.querySelector('video');
        if (!v) throw new Error('no video element');

        const samples: { t: number; ct: number; ready: number; paused: boolean }[] = [];
        const start = performance.now();
        while (performance.now() - start < sampleSec * 1000) {
          samples.push({
            t: performance.now() - start,
            ct: v.currentTime,
            ready: v.readyState,
            paused: v.paused,
          });
          await new Promise((r) => setTimeout(r, intervalMs));
        }

        let backward = 0;
        let maxBackward = 0;
        let freezes = 0;
        for (let i = 1; i < samples.length; i++) {
          const delta = samples[i].ct - samples[i - 1].ct;
          if (delta < -0.05) {
            backward++;
            maxBackward = Math.max(maxBackward, -delta);
          }
          if (Math.abs(delta) < 0.001 && !samples[i].paused) {
            freezes++;
          }
        }

        const wallSec = (samples[samples.length - 1].t - samples[0].t) / 1000;
        const ctSpan = samples[samples.length - 1].ct - samples[0].ct;
        const ratio = wallSec > 0 ? ctSpan / wallSec : 0;

        return {
          samples: samples.length,
          backward,
          maxBackward,
          freezes,
          wallSec,
          ctSpan,
          ratio,
          width: v.videoWidth,
          height: v.videoHeight,
          paused: v.paused,
        };
      },
      { sampleSec: SAMPLE_SEC, intervalMs: INTERVAL_MS },
    );

    console.log(JSON.stringify(metrics, null, 2));

    expect(metrics.width, 'videoWidth doit être > 0').toBeGreaterThan(0);
    expect(metrics.height, 'videoHeight doit être > 0').toBeGreaterThan(0);
    expect(metrics.paused, 'la vidéo ne doit pas être en pause').toBe(false);
    expect(metrics.backward, 'reculs currentTime > 50ms').toBeLessThanOrEqual(1);
    expect(metrics.maxBackward, 'recul max trop important').toBeLessThan(0.5);
    expect(metrics.freezes, 'frames gelées trop longtemps').toBeLessThanOrEqual(
      Math.ceil(SAMPLE_SEC * 2),
    );
    expect(metrics.ratio, 'dérive timing vs temps réel').toBeGreaterThan(0.85);
    expect(metrics.ratio).toBeLessThan(1.15);
  });
});
