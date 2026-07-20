#!/usr/bin/env node
/**
 * Sprint 2 — UI capture artefact for validate_rule (Décision 3 / R.3).
 * Run with cwd=frontend/ so node_modules resolves (createRequire + cwd).
 *
 * Env: UI_URL, OUT_PNG, EMAIL, PASS, ALERT_ID (optional)
 */
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';

const require = createRequire(path.resolve(process.cwd(), 'package.json'));
const { chromium } = require('@playwright/test');

const UI = (process.env.UI_URL || 'http://127.0.0.1:5174').replace(/\/$/, '');
const OUT = process.env.OUT_PNG || path.resolve('ui-capture.png');
const EMAIL = process.env.EMAIL || 'glory.henock@hologram.cd';
const PASS = process.env.PASS || 'Hologram2026!';
const ALERT_ID = process.env.ALERT_ID || '';

async function main() {
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.addInitScript(() => {
    window.__CV_E2E__ = true;
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

  await page.goto(`${UI}/login`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.fill('#email, input[name=email], input[type=email]', EMAIL);
  await page.fill('#password, input[name=password], input[type=password]', PASS);
  await page.locator('button[type=submit]').first().click();
  await page.waitForURL(/\/(dashboard|live|alerts|rules)/, { timeout: 25000 }).catch(() => {});

  const alertsUrl = ALERT_ID ? `${UI}/alerts?alert=${ALERT_ID}` : `${UI}/alerts`;
  await page.goto(alertsUrl, { waitUntil: 'networkidle', timeout: 45000 }).catch(async () => {
    await page.goto(`${UI}/alerts`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: OUT, fullPage: true });
  await browser.close();

  const st = fs.statSync(OUT);
  if (st.size < 1000) {
    console.error('screenshot too small', st.size);
    process.exit(1);
  }
  console.log('OK', OUT, st.size);
}

main().catch((err) => {
  console.error(String(err && err.stack ? err.stack : err));
  process.exit(1);
});
