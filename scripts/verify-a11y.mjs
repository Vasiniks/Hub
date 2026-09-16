// Keyboard-only, reduced-motion, and "click while standing" verification.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import path from 'node:path';

const outDir = process.argv[2] ?? 'verify-a11y-out';
fs.mkdirSync(outDir, { recursive: true });
const chrome = process.env.CHROME_PATH ?? '/Applications/Google Chrome 3.app/Contents/MacOS/Google Chrome';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ executablePath: chrome, headless: true, args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
const results = {};
const errors = [];

// ---- 1. Keyboard only, reduced motion ------------------------------------
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push(`kb: ${e.message}`));
  page.on('console', (m) => m.type() === 'error' && errors.push(`kb console: ${m.text()}`));
  const room = (fn, arg) => page.evaluate(fn, arg);
  await page.goto('http://127.0.0.1:5173/?debug&hour=21', { waitUntil: 'load' });
  await page.waitForFunction(() => window.__room !== undefined);
  await wait(2500);

  await page.keyboard.press('Space');
  await wait(1300);
  results.spaceSits = await room(() => window.__room.mode());

  const c1 = await room(() => window.__room.camera());
  await wait(600);
  const c2 = await room(() => window.__room.camera());
  results.idleMotionUnderReducedMotion = JSON.stringify(c1) !== JSON.stringify(c2);

  await page.keyboard.press('Tab');
  await wait(300);
  results.tabFocus = await room(() => ({ text: document.activeElement?.textContent, inNav: !!document.activeElement?.closest('#object-nav') }));
  results.tabForcesHover = await room(() => window.__room.hovered());
  await page.screenshot({ path: path.join(outDir, 'kb-01-tab.png') });

  await page.keyboard.press('Enter');
  await wait(900);
  results.enterOpens = await room(() => ({ mode: window.__room.mode(), panelOpen: window.__room.panelOpen(), focusOnTitle: document.activeElement?.id === 'panel-title' }));
  await page.screenshot({ path: path.join(outDir, 'kb-02-open.png') });

  await page.keyboard.press('Escape');
  await wait(800);
  results.escapeReturns = await room(() => ({ mode: window.__room.mode(), panelOpen: window.__room.panelOpen(), focusRestoredToNav: !!document.activeElement?.closest('#object-nav') }));

  // Tab to the panel's close button path: open again, Tab, Enter on "Back to room"
  await page.keyboard.press('Enter');
  await wait(900);
  await page.keyboard.press('Tab');
  results.closeButtonFocusable = await room(() => document.activeElement?.id === 'panel-close');
  await page.keyboard.press('Enter');
  await wait(800);
  results.closeButtonReturns = await room(() => ({ mode: window.__room.mode(), panelOpen: window.__room.panelOpen() }));
  await ctx.close();
}

// ---- 2. Click an object while still standing ----------------------------
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push(`stand: ${e.message}`));
  const room = (fn, arg) => page.evaluate(fn, arg);
  await page.goto('http://127.0.0.1:5173/?debug&hour=21', { waitUntil: 'load' });
  await page.waitForFunction(() => window.__room !== undefined);
  await page.mouse.move(720, 450);
  await wait(2500);
  let hovered = false;
  for (let i = 0; i < 40 && !hovered; i++) {
    const s = await room((pid) => window.__room.hitPositionOf(pid), 'polyhedron');
    if (s) await page.mouse.move(s.x, s.y);
    await wait(120);
    hovered = (await room(() => window.__room.hovered())) === 'polyhedron';
  }
  results.standingHover = hovered;
  await page.mouse.down();
  await page.mouse.up();
  await wait(400);
  results.standingClickStartsSitting = await room(() => window.__room.mode());
  await wait(4800);
  results.standingClickThenOpens = await room(() => ({ mode: window.__room.mode(), panelOpen: window.__room.panelOpen(), title: document.getElementById('panel-title').textContent }));
  await page.screenshot({ path: path.join(outDir, 'stand-click-open.png') });
  await ctx.close();
}

results.errors = errors;
console.log(JSON.stringify(results, null, 2));
await browser.close();
