// Screenshot a local audit viewer containing unmodified measured records.
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const root = path.resolve(__dirname, '..');
const candidates = [process.env.PLAYWRIGHT_PATH,
  path.join(root, '.runtime/browser/node_modules/playwright'),
  path.join(process.env.USERPROFILE || '', 'Downloads/airbnb-takehome-fixed/airbnb-takehome-fixed/node_modules/playwright')].filter(Boolean);
let playwright;
for (const candidate of candidates) {
  try { playwright = require(candidate); break; } catch {}
}
if (!playwright) {
  console.error('Install playwright in .runtime/browser or set PLAYWRIGHT_PATH to its package path.');
  process.exit(2);
}
(async () => {
  const browser = await playwright.chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1260, height: 1000 }, deviceScaleFactor: 1 });
    await page.goto(pathToFileURL(path.join(root, 'artifacts/evidence.html')).href);
    await page.screenshot({ path: path.join(root, 'artifacts/evidence-full.png'), fullPage: true });
    for (const id of ['query', 'idempotency', 'judge', 'position', 'adversarial']) {
      await page.locator('#' + id).screenshot({ path: path.join(root, 'artifacts/' + id + '.png') });
    }
    console.log('Captured five screenshots of actual audit and evaluation records.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
