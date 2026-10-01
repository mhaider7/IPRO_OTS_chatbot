// Browser responses for delivery are intercepted. This test never sends mail.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.HAWK_BROWSER_CHANNEL ? { channel: process.env.HAWK_BROWSER_CHANNEL } : {}) });
  const screenshots = process.env.HAWK_SCREENSHOT_DIR || path.join(__dirname, '..', '.browser-output');
  await fs.mkdir(screenshots, { recursive: true });
  const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  const errors = [], sends = [];
  page.on('pageerror', error => errors.push(error.message));
  let delivery = 'accepted';
  await page.route('**/api/email/send', async route => {
    sends.push(route.request().postDataJSON());
    if (delivery === 'offline') return route.abort();
    return route.fulfill({ json: { status: delivery } });
  });
  const idle = () => page.waitForFunction(() => !document.getElementById('message').disabled);
  async function send(text) {
    await page.locator('#message').fill(text);
    await page.locator('#send').click(); await idle();
  }
  async function prepare() {
    await page.locator('#choose-email').click(); await idle();
    if (!(await page.locator('.email').count())) await send('A fictional laptop shows a connection error');
    await page.locator('.email').waitFor();
  }
  async function confirm() {
    await page.locator('.email input[type=email]').fill('student@example.test');
    await page.locator('.confirm-send input').check();
    await page.locator('.send-email').click();
  }
  try {
    await page.goto(process.env.HAWK_BASE_URL || 'http://127.0.0.1:8000');
    await page.locator('#launcher').click();
    assert.equal(await page.getByRole('button', { name: 'Talk to a technician', exact: true }).count(), 0);
    assert.equal(await page.locator('#options').isVisible(), false);
    await send('My Wi-Fi will not connect');
    assert.equal(await page.locator('#options').isVisible(), true);
    assert.equal(await page.locator('.email').count(), 0);
    await page.screenshot({ path: path.join(screenshots, 'hawk-choices.png') });
    await page.locator('#choose-diagnose').click(); await idle();
    assert.match(await page.locator('#messages').innerText(), /1\. Check that Wi-Fi is on/);
    await send('It still does that on my phone');
    await prepare();
    await page.waitForFunction(() => document.querySelector('.delivery-status').textContent.includes('not configured'));
    assert.equal(await page.locator('.send-email').isDisabled(), true);
    assert.equal(await page.getByRole('button', { name: 'Copy email', exact: true }).count(), 0);
    assert.equal(sends.length, 0);

    // UI-only configured-provider simulation; Graph itself is mocked in Python tests.
    await page.route('**/api/email/status', route => route.fulfill({ json: { available: true, recipient: 'supportdesk@illinoistech.edu' } }));
    await prepare();
    await page.waitForFunction(() => !document.querySelector('.send-email').disabled);
    await page.locator('.send-email').click(); // Native form validation prevents sending.
    assert.equal(sends.length, 0);
    await confirm();
    await page.waitForFunction(() => document.querySelector('.delivery-status').textContent.includes('accepted your email'));
    assert.equal(sends.length, 1);
    assert.equal(sends[0].confirmed, true);
    assert.equal(await page.locator('.send-email').isDisabled(), true);
    assert.equal(await page.locator('.email textarea').getAttribute('readonly'), '');
    await page.screenshot({ path: path.join(screenshots, 'hawk-email.png') });

    await page.locator('#reset').click();
    await send('What is my ticket status?');
    assert.equal(await page.locator('.email').count(), 0);
    await page.locator('#choose-diagnose').click(); await idle();
    assert.match(await page.locator('#messages').innerText(), /cannot reset your account or retrieve ticket records/);
    await prepare();
    delivery = 'offline';
    await confirm();
    await page.waitForFunction(() => document.querySelector('.send-email').textContent.includes('Check this attempt'));
    delivery = 'accepted';
    await page.locator('.send-email').click();
    await page.waitForFunction(() => document.querySelector('.delivery-status').textContent.includes('accepted your email'));
    assert.deepEqual(sends[1], sends[2]); // Retry uses the frozen payload and id.

    await page.locator('#reset').click();
    await send("How's the weather today?");
    assert.equal(await page.locator('#options').isVisible(), false);
    assert.equal(await page.locator('.email').count(), 0);
    assert.match(await page.locator('#messages').innerText(), /OTS technology questions/);
    await send('My Bluetooth mouse is not working');
    await page.locator('#choose-diagnose').click(); await idle();
    assert.match(await page.locator('#messages').innerText(), /do not have verified self-service instructions/);
    await prepare();
    delivery = 'unknown'; await confirm();
    await page.waitForFunction(() => document.querySelector('.delivery-status').textContent.includes('uncertain'));
    assert.doesNotMatch(await page.locator('.delivery-status').innerText(), /accepted your email/);
    await page.locator('.send-email').click();
    await page.waitForFunction(() => !document.getElementById('message').disabled);
    assert.deepEqual(sends[3], sends[4]);

    await page.locator('#reset').click();
    let fail = true;
    await page.route('**/api/chat', route => fail ? route.abort() : route.continue());
    await page.locator('#message').fill('Printing on campus'); await page.locator('#send').click();
    await page.locator('#retry').waitFor();
    fail = false; await page.locator('#retry').click(); await idle();
    assert.equal(await page.locator('.user').count(), 1);
    await page.unroute('**/api/chat');
    await page.locator('#close').click(); await page.locator('#launcher').click();
    assert.equal(await page.locator('.user').count(), 1);
    await send('Is it raining?');
    assert.equal(await page.locator('#options').isVisible(), false);
    await send('My Wi-Fi will not connect');

    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      assert.equal(await page.locator('#choose-email').isVisible(), true);
      assert.equal(await page.locator('#choose-diagnose').isVisible(), true);
    }
    await page.screenshot({ path: path.join(screenshots, 'hawk-mobile.png') });
    await page.reload(); await page.locator('#launcher').click();
    assert.equal(await page.locator('.user').count(), 0);
    assert.deepEqual(errors, []);
    console.log('PASS: options, diagnosis, account limits, switch to email, disabled configuration, confirmation, acceptance, uncertain status, idempotent retry, chat retry, mobile; no real mail sent.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
