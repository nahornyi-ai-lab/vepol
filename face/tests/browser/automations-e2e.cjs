/* Real-app browser check for the Automations view against owned fixture hubs. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawn } = require('node:child_process');
const readline = require('node:readline');
const { chromium } = require('playwright');

const ROOT = __dirname;
const APP = process.env.VEPOL_TEST_APP || path.resolve(ROOT, '../..');
const PYTHON = process.env.VEPOL_FACE_PYTHON || path.join(APP, '.venv', 'bin', 'python');
const evidenceBase = process.env.VEPOL_BOARD_EVIDENCE_DIR || os.tmpdir();
fs.mkdirSync(evidenceBase, { recursive: true });
const OUT = fs.mkdtempSync(path.join(evidenceBase, 'vepol-automations-evidence-'));
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function waitUntil(fn, label, timeout = 10000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (await fn()) return; await sleep(100); }
  throw new Error(`Timed out: ${label}`);
}

// Fixture server on its own fixture dir; Hermes jobs point at a folder that does not exist.
async function startServer(name, env) {
  const dir = path.join(OUT, name);
  const server = spawn(PYTHON, [path.join(ROOT, 'fixture_server.py'), APP, dir], {
    stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, HERMES_HOME: path.join(dir, 'no-hermes'), ...env },
  });
  let stderr = '';
  server.stderr.on('data', b => { stderr += b.toString(); });
  const lines = readline.createInterface({ input: server.stdout });
  const boot = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`Fixture server did not start: ${stderr}`)), 30000);
    lines.once('line', line => { clearTimeout(timer); try { resolve(JSON.parse(line)); } catch (e) { reject(e); } });
    server.once('exit', code => { clearTimeout(timer); reject(new Error(`Fixture server exited ${code}: ${stderr}`)); });
  });
  return { server, boot, base: `http://127.0.0.1:${boot.port}` };
}

async function stopServer(s) {
  if (!s || s.server.exitCode !== null) return;
  s.server.kill('SIGTERM');
  await Promise.race([new Promise(resolve => s.server.once('exit', resolve)), sleep(5000)]);
  if (s.server.exitCode === null) s.server.kill('SIGKILL');
}

async function openAutomations(browser, s, evidence) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  await context.addInitScript(token => { window.__VEPOL_TOKEN__ = token; }, s.boot.token);
  const page = await context.newPage();
  page.on('pageerror', e => evidence.pageErrors.push(e.message));
  page.on('response', r => { if (r.status() >= 400) evidence.httpErrors.push({ url: new URL(r.url()).pathname, status: r.status() }); });
  await page.goto(s.base);
  await page.locator('#board-view').waitFor({ state: 'visible' });
  await page.locator('[data-board-view="automations"]').click();
  await page.locator('#automations-pane').waitFor({ state: 'visible' });
  await page.locator('#auto-strip').waitFor({ state: 'visible' });
  return { page, context };
}

(async () => {
  let browser, plain, seeded;
  const evidence = { status: 'running', app: APP, fixture: OUT, steps: [], cases: {}, pageErrors: [], httpErrors: [] };
  try {
    browser = await chromium.launch({ headless: true });

    // A1: the fixture hub has no processes.yaml; the view says so and shows no process table.
    plain = await startServer('plain', {});
    const a1 = await openAutomations(browser, plain, evidence);
    const errorNote = a1.page.locator('#auto-notes .banner.bad');
    await errorNote.waitFor();
    const noteText = await errorNote.textContent();
    assert.match(noteText, /^processes\.yaml invalid: .*processes\.yaml.* — the scheduler is not running any process right now$/);
    assert.equal(await a1.page.locator('#auto-table [data-process]').count(), 0);
    assert.equal((await a1.page.locator('#auto-table').innerHTML()).trim(), '');
    const strip = (await a1.page.locator('#auto-strip').textContent()).trim();
    await a1.page.screenshot({ path: path.join(OUT, 'automations-no-registry.png'), fullPage: true });
    evidence.cases.A1 = { note: noteText, processRows: 0, strip };
    evidence.steps.push(`A1 no processes.yaml: red note "${noteText}", 0 process rows`);
    await a1.context.close();
    await stopServer(plain);

    // A2: a valid registry and two failed kb-tick attempts today; the detail pane shows attempts and output.
    seeded = await startServer('seeded', { VEPOL_FIXTURE_AUTOMATIONS: '1' });
    const a2 = await openAutomations(browser, seeded, evidence);
    const row = a2.page.locator('#auto-table tr[data-process="fixture-report"]');
    await row.waitFor();
    const rowText = (await row.textContent()).replace(/\s+/g, ' ');
    assert.match(rowText, /Failed/);
    assert.match(rowText, /attempts today: 2 · fixture failure attempt 2: token expired/);
    await row.click();
    const pane = a2.page.locator('#auto-detail');
    await pane.waitFor({ state: 'visible' });
    await pane.locator('pre.output').first().waitFor();
    const occ = (await pane.locator('[data-occ]').first().textContent()).replace(/\s+/g, ' ');
    assert.match(occ, /attempts: 2/);
    const outputs = await pane.locator('pre.output').allTextContents();
    assert.equal(outputs[0], 'step one ok\nfixture failure attempt 2: token expired');
    assert.equal(outputs[1], 'fixture stdout attempt 2');
    const attemptLine = (await pane.locator('.reason.mono').first().textContent()).trim();
    assert.match(attemptLine, /^kbcr-fixture-2 · failed · exit 1 · /);
    await a2.page.screenshot({ path: path.join(OUT, 'automations-failed-detail.png'), fullPage: true });
    // AUTO-10: no plan for today is a grey note; a failed refresh keeps the rows with "Could not refresh" and Retry.
    const planNote = 'No plan for today — states come from the run ledger only';
    assert.deepEqual(await a2.page.locator('#auto-notes .grey-line').allTextContents(), [planNote]);
    const rowsBefore = await a2.page.locator('#auto-table [data-process]').count();
    await stopServer(seeded);
    await a2.page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    const refreshError = a2.page.locator('#auto-feedback');
    await waitUntil(async () => await refreshError.isVisible() && /^Could not refresh: /.test(await refreshError.textContent()), 'Could not refresh banner');
    assert.equal(await refreshError.locator('button').textContent(), 'Retry');
    assert.equal(await a2.page.locator('#auto-table [data-process]').count(), rowsBefore);
    assert(await a2.page.locator('#auto-notes .grey-line').isVisible(), 'plan note stays');
    const refreshText = await refreshError.textContent();
    await a2.page.screenshot({ path: path.join(OUT, 'automations-refresh-failed.png'), fullPage: true });
    evidence.cases.A2 = { row: rowText.trim(), occurrence: occ.trim(), attempt: attemptLine, stderr: outputs[0], stdout: outputs[1], planNote, refreshError: refreshText, rowsKept: rowsBefore };
    evidence.steps.push(`A2 Failed row with 2 attempts; detail pane shows attempts: 2, exit 1 and the stderr/stdout tail; grey "${planNote}"; server stopped: "${refreshText}" with ${rowsBefore} row kept`);
    await a2.context.close();

    assert.deepEqual(evidence.pageErrors, [], 'No browser exceptions');
    assert.deepEqual(evidence.httpErrors, [], 'No HTTP errors');
    evidence.status = 'passed';
    console.log(JSON.stringify({ status: 'passed', evidence: OUT, steps: evidence.steps, cases: evidence.cases }, null, 2));
  } catch (error) {
    evidence.status = 'failed';
    evidence.error = error.stack || String(error);
    console.error(evidence.error);
    process.exitCode = 1;
  } finally {
    if (browser) await browser.close();
    await stopServer(plain);
    await stopServer(seeded);
    fs.writeFileSync(path.join(OUT, 'result.json'), JSON.stringify(evidence, null, 2));
  }
})();
