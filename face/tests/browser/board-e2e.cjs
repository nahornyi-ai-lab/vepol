/* One real-app E2E for the complete session-board journey. No board mocks. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawn, spawnSync } = require('node:child_process');
const readline = require('node:readline');
const { chromium } = require('playwright');

const ROOT = __dirname;
const APP = process.env.VEPOL_TEST_APP || path.resolve(ROOT, '../..');
const PYTHON = process.env.VEPOL_FACE_PYTHON || path.join(APP, '.venv', 'bin', 'python');
const evidenceBase = process.env.VEPOL_BOARD_EVIDENCE_DIR || os.tmpdir();
fs.mkdirSync(evidenceBase, { recursive: true });
const OUT = fs.mkdtempSync(path.join(evidenceBase, 'vepol-board-evidence-'));
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));
const card = (page, id) => page.locator(`#board-view [data-conversation-id="${id}"]`);
const column = (page, stage) => page.locator(`#board-columns [data-stage="${stage}"]`);

async function waitUntil(fn, label, timeout = 10000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (await fn()) return; await sleep(100); }
  throw new Error(`Timed out: ${label}`);
}

(async () => {
  let browser, server;
  const evidence = { status: 'running', app: APP, fixture: OUT, steps: [], pageErrors: [], httpErrors: [], runtimeCalls: [] };
  try {
    server = spawn(PYTHON, [path.join(ROOT, 'fixture_server.py'), APP, OUT], { stdio: ['ignore', 'pipe', 'pipe'] });
    let stderr = '';
    server.stderr.on('data', b => { stderr += b.toString(); });
    const lines = readline.createInterface({ input: server.stdout });
    const boot = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`Fixture server did not start: ${stderr}`)), 15000);
      lines.once('line', line => { clearTimeout(timer); try { resolve(JSON.parse(line)); } catch (e) { reject(e); } });
      server.once('exit', code => { clearTimeout(timer); reject(new Error(`Fixture server exited ${code}: ${stderr}`)); });
    });
    const base = `http://127.0.0.1:${boot.port}`;
    const api = async (url, method = 'GET', data) => {
      const res = await fetch(base + url, { method, headers: { 'X-Vepol-Token': boot.token, 'Content-Type': 'application/json' }, body: data === undefined ? undefined : JSON.stringify(data) });
      assert(res.ok, `${method} ${url}: ${res.status} ${await (res.ok ? Promise.resolve('') : res.text())}`);
      return res.json();
    };
    await waitUntil(async () => { try { return (await api('/api/health')).ok; } catch { return false; } }, 'fixture health');
    const stages = ['queued', 'research', 'working', 'review', 'completed'];
    const projects = ['alpha', 'beta', 'gamma', 'delta'];
    const records = [];
    for (let i = 0; i < 60; i++) {
      const target = projects[i % 4];
      const r = await api('/api/conversations', 'POST', { target, runtime: i % 2 ? 'codex' : 'claude' });
      records.push({ ...r, title: `Сессия ${String(i).padStart(2, '0')} — ${target}: исследование и работа`, preview: `Результат ${String(i).padStart(2, '0')}: сохранён контекст проекта ${target}. ${i === 37 ? 'уникальныймаяк' : 'План и проверка результата.'}` });
    }
    const enriched = spawnSync(PYTHON, [path.join(ROOT, 'fixture_enrich.py'), APP, OUT], { input: JSON.stringify(records), encoding: 'utf8' });
    assert.equal(enriched.status, 0, enriched.stderr);
    for (let i = 0; i < records.length; i++) await api(`/api/conversations/${records[i].id}/board`, 'PATCH', { board_stage: stages[i % stages.length] });
    const before = await api(`/api/conversations/${records[0].id}`);
    evidence.steps.push('60 conversations created through real POST; representative history seeded using real RunStore; stages set by real PATCH');

    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
    await context.addInitScript(token => { window.__VEPOL_TOKEN__ = token; }, boot.token);
    let page = await context.newPage();
    const observe = p => {
      p.on('pageerror', e => evidence.pageErrors.push(e.message));
      p.on('response', r => { if (r.status() >= 400) evidence.httpErrors.push({ url: new URL(r.url()).pathname, status: r.status() }); });
      p.on('request', r => { const pathname = new URL(r.url()).pathname; if (r.method() === 'POST' && /\/(messages|retry|stop)$/.test(pathname)) evidence.runtimeCalls.push(pathname); });
    };
    observe(page);
    await page.goto(base);
    await page.locator('#board-view').waitFor({ state: 'visible' });
    await waitUntil(async () => await page.locator('#board-view [data-conversation-id]').count() === 60, '60 visible cards');
    await page.screenshot({ path: path.join(OUT, 'desktop.png'), fullPage: true });
    evidence.steps.push('Initial board renders 60 real API-backed cards at 1440x1000');
    await page.reload();
    await waitUntil(async () => await page.locator('#board-view [data-conversation-id]').count() === 60, 'injected authentication survives reload');
    assert.equal(new URL(page.url()).search, '');
    evidence.steps.push('Desktop document-start token injection survives reload at a bare URL');

    const dragId = records[0].id;
    const dragPatch = page.waitForResponse(r => r.request().method() === 'PATCH' && new URL(r.url()).pathname === `/api/conversations/${dragId}/board`);
    await card(page, dragId).scrollIntoViewIfNeeded();
    await card(page, dragId).evaluate(el => {
      window.__dragCard = el;
      window.__dragStarted = false;
      el.addEventListener('dragstart', () => { window.__dragStarted = true; }, { once: true });
    });
    const from = await card(page, dragId).boundingBox();
    const to = await column(page, 'research').boundingBox();
    await page.mouse.move(from.x + from.width / 2, from.y + 24);
    await page.mouse.down();
    await page.mouse.move(from.x + from.width / 2 + 24, from.y + 40, { steps: 8 });
    await waitUntil(() => page.evaluate(() => window.__dragStarted), 'native dragstart');
    await page.waitForTimeout(5400);
    assert(await page.evaluate(() => window.__dragCard.isConnected), 'poll preserves dragged card node');
    const dropX = to.x + to.width / 2;
    const dropY = Math.max(100, Math.min(850, to.y + 80));
    await page.mouse.move(dropX, dropY, { steps: 12 });
    await page.mouse.move(dropX, dropY + 2);
    await page.mouse.up();
    assert((await dragPatch).ok(), 'drag PATCH succeeded');
    await waitUntil(async () => (await api(`/api/conversations/${dragId}`)).board_stage === 'research', 'drag saved stage');
    await column(page, 'research').locator(`[data-conversation-id="${dragId}"]`).waitFor();
    evidence.steps.push('Native drag survives a polling interval, changes stage through real authenticated PATCH and repositions card');

    const selectId = records[1].id;
    const stageSelector = card(page, selectId).locator('select[data-board-stage]');
    await stageSelector.focus();
    await page.evaluate(() => { window.__focusedSelector = document.activeElement; });
    // The implementation may defer the poll itself or defer repaint while a
    // selector has focus; both satisfy the interaction contract.
    await page.waitForTimeout(5400);
    assert(await page.evaluate(() => window.__focusedSelector.isConnected && document.activeElement === window.__focusedSelector), 'poll preserves focused stage selector node');
    const selectPatch = page.waitForResponse(r => r.request().method() === 'PATCH' && new URL(r.url()).pathname === `/api/conversations/${selectId}/board`);
    await stageSelector.selectOption('completed');
    assert((await selectPatch).ok(), 'select PATCH succeeded');
    await waitUntil(async () => (await api(`/api/conversations/${selectId}`)).board_stage === 'completed', 'select saved stage');
    evidence.steps.push('Polling preserves focused selector; accessible selector changes another card to completed');

    await page.locator('#board-project-filter').focus();
    await page.locator('#board-project-filter').selectOption('beta');
    await waitUntil(async () => await page.locator('#board-view [data-conversation-id]').count() === 15, 'project filter 15 cards');
    await page.locator('#board-search').fill('уникальныймаяк');
    await waitUntil(async () => await page.locator('#board-view [data-conversation-id]').count() === 1, 'preview search one card');
    assert.equal(await card(page, records[37].id).count(), 1);
    await page.locator('#board-search').fill('');
    await page.locator('#board-project-filter').selectOption('');
    await waitUntil(async () => await page.locator('#board-view [data-conversation-id]').count() === 60, 'clear filters');
    evidence.steps.push('Project filter and preview search narrow 60 → 15 → 1, clear restores 60');

    const detailResponse = page.waitForResponse(r => r.request().method() === 'GET' && new URL(r.url()).pathname === `/api/conversations/${dragId}`);
    await card(page, dragId).locator('[data-open-conversation]').click();
    const opened = await (await detailResponse).json();
    assert.equal(opened.id, dragId);
    assert.deepEqual(opened.messages, before.messages);
    await page.locator('#thread').getByText(records[0].title, { exact: true }).waitFor();
    await page.locator('#thread').getByText(records[0].preview, { exact: true }).waitFor();
    await page.locator('#show-board').click();
    await page.locator('#board-view').waitFor({ state: 'visible' });
    evidence.steps.push('Card opens original conversation with unchanged identity/messages; Board returns without runtime call');

    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(OUT, 'narrow.png'), fullPage: true });
    const geometry = await page.locator('#board-columns').evaluate(el => ({ client: el.clientWidth, scroll: el.scrollWidth }));
    assert(geometry.scroll > geometry.client, 'narrow board has horizontal scrolling');
    await column(page, 'completed').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(OUT, 'narrow-completed.png'), fullPage: true });
    evidence.narrowGeometry = geometry;
    evidence.steps.push('390px viewport retains horizontally scrollable five-column board');

    await page.close();
    page = await context.newPage();
    observe(page);
    await page.goto(base);
    await page.locator('#board-view').waitFor({ state: 'visible' });
    await column(page, 'research').locator(`[data-conversation-id="${dragId}"]`).waitFor();
    await column(page, 'completed').locator(`[data-conversation-id="${selectId}"]`).waitFor();
    const savedDrag = JSON.parse(fs.readFileSync(path.join(OUT, 'state', `conv-${dragId}.json`), 'utf8'));
    const savedSelect = JSON.parse(fs.readFileSync(path.join(OUT, 'state', `conv-${selectId}.json`), 'utf8'));
    assert.equal(savedDrag.board_stage, 'research');
    assert.equal(savedSelect.board_stage, 'completed');
    assert(savedDrag.board_updated_at && savedSelect.board_updated_at);
    assert.deepEqual(savedDrag.messages, before.messages);
    evidence.steps.push('Fresh authenticated page restores stages; real JSON files preserve messages and board timestamps');
    assert.deepEqual(evidence.pageErrors, [], 'No browser exceptions');
    assert.deepEqual(evidence.httpErrors, [], 'No HTTP errors');
    assert.deepEqual(evidence.runtimeCalls, [], 'No LLM/user session calls');
    evidence.status = 'passed';
    console.log(JSON.stringify({ status: 'passed', evidence: OUT, steps: evidence.steps }, null, 2));
  } catch (error) {
    evidence.status = 'failed';
    evidence.error = error.stack || String(error);
    console.error(evidence.error);
    process.exitCode = 1;
  } finally {
    if (browser) await browser.close();
    if (server && server.exitCode === null) {
      server.kill('SIGTERM');
      await Promise.race([new Promise(resolve => server.once('exit', resolve)), sleep(5000)]);
      if (server.exitCode === null) server.kill('SIGKILL');
    }
    fs.writeFileSync(path.join(OUT, 'result.json'), JSON.stringify(evidence, null, 2));
  }
})();
