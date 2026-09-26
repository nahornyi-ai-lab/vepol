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
      // Structured sessions: the desktop default is now one terminal per (project, runtime), and this journey needs 60 distinct cards.
      const r = await api('/api/conversations', 'POST', { target, runtime: i % 2 ? 'codex' : 'claude', transport: 'session' });
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
      p.on('request', r => { const pathname = new URL(r.url()).pathname; if (r.method() === 'POST' && /\/(messages|retry|stop|terminal\/start)$/.test(pathname)) evidence.runtimeCalls.push(pathname); });
    };
    observe(page);
    await page.goto(base);
    await page.locator('#board-view').waitFor({ state: 'visible' });
    await waitUntil(async () => await page.locator('#board-view [data-conversation-id]').count() === 60, '60 visible cards');
    await page.screenshot({ path: path.join(OUT, 'desktop.png'), fullPage: true });
    evidence.steps.push('Initial board renders 60 real API-backed cards at 1440x1000');

    // UI-01: the board chrome is English; fixture card text is data and is left out.
    const chrome = await page.evaluate(() => {
      const texts = (sel) => [...document.querySelectorAll(sel)].map(el => el.textContent.trim());
      return {
        columns: texts('#board-columns .board-column h2'),
        stageOptions: [...new Set(texts('#board-columns select[data-board-stage] option'))],
        filterFirst: document.querySelector('#board-project-filter option').textContent,
        count: document.querySelector('#board-count').textContent,
        footnote: document.querySelector('#sessions-pane .board-footnote').textContent,
        title: document.querySelector('#board-title').textContent,
        description: document.querySelector('#board-description').textContent,
        views: texts('#board-view .view-switch [data-board-view]'),
        newSession: document.querySelector('#board-newconv').textContent,
        columnAdd: [...document.querySelectorAll('#board-columns .column-add')].map(b => b.getAttribute('aria-label')),
        badges: [...new Set([...document.querySelectorAll('#board-columns .session-activity')].map(el => el.textContent.trim()))].sort(),
        searchPlaceholder: document.querySelector('#board-search').placeholder,
      };
    });
    const columnNames = ['Queue', 'Research', 'Working', 'Review', 'Done'];
    assert.doesNotMatch(JSON.stringify(chrome), /[\u0400-\u04ff]/, 'no Cyrillic in the board chrome');
    assert.deepEqual(chrome.columns, columnNames);
    assert.deepEqual(chrome.stageOptions, columnNames);
    assert.deepEqual(chrome.views, ['Sessions', 'Tasks', 'Automations']);
    assert.deepEqual(chrome.columnAdd, columnNames.map(n => `New session in ${n}`));
    const badgeSet = ['Agent replied', 'Stopped', 'No full answer', 'Error', 'Run interrupted', 'Agent working'];
    assert(chrome.badges.length && chrome.badges.every(b => badgeSet.includes(b)), `badges ${JSON.stringify(chrome.badges)}`);
    assert.equal(chrome.footnote, 'You choose the stage. “Agent replied” means the reply has ended, not that the task is done.');
    assert.equal(chrome.filterFirst, 'All projects');
    assert.equal(chrome.count, 'Total: 60');
    assert.equal(chrome.newSession, '+ New session');
    evidence.chrome = chrome;
    evidence.steps.push(`UI-01 board chrome is English: columns ${columnNames.join('/')}, views Sessions/Tasks/Automations, badges ${chrome.badges.join(', ')}`);
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

    // BOARD-07: folder · project · path, from /api/targets.
    const targets = await api('/api/targets');
    const pathText = slug => { const t = targets.find(x => x.slug === slug); return { text: `${path.basename(t.cwd)} · ${t.slug} · ${t.cwd}`, cwd: t.cwd }; };
    const alphaPath = card(page, records[0].id).locator('.session-path');
    assert.equal(await alphaPath.textContent(), pathText('alpha').text);
    assert.equal(await alphaPath.getAttribute('title'), pathText('alpha').cwd);
    assert(await page.locator('#board-project-path').isHidden(), 'no project path under All projects');

    const cardCount = () => page.locator('#board-view [data-conversation-id]').count();
    const boardCount = () => page.locator('#board-count').textContent();
    // Each column's count equals the cards it shows.
    const columnCounts = () => page.locator('#board-columns .board-column').evaluateAll(cols => cols.map(c => [c.querySelector('.stage-count').textContent, String(c.querySelectorAll('[data-conversation-id]').length)]));
    await page.locator('#board-project-filter').focus();
    await page.locator('#board-project-filter').selectOption('beta');
    await waitUntil(async () => await cardCount() === 15, 'project filter 15 cards');
    assert.equal(await boardCount(), 'Showing 15 of 60');
    for (const [shown, cards] of await columnCounts()) assert.equal(shown, cards);
    assert.equal(await page.locator('#board-project-path').textContent(), pathText('beta').text);
    assert(await page.locator('#board-project-path').isVisible(), 'beta path shown under the heading');
    await page.locator('#board-search').fill('уникальныймаяк');
    await waitUntil(async () => await cardCount() === 1, 'preview search one card');
    assert.equal(await card(page, records[37].id).count(), 1);
    assert.equal(await boardCount(), 'Showing 1 of 60');
    await page.locator('#board-search').fill('zzz-no-match');
    await waitUntil(async () => await cardCount() === 0, 'no match');
    assert(await page.locator('#board-empty').isVisible(), 'no-match state shown');
    assert.equal(await page.locator('#board-empty').textContent(), 'Nothing found. Change the search or pick another project.');
    await page.locator('#board-search').fill('');
    await page.locator('#board-project-filter').selectOption('');
    await waitUntil(async () => await cardCount() === 60, 'clear filters');
    assert.equal(await boardCount(), 'Total: 60');
    for (const [shown, cards] of await columnCounts()) assert.equal(shown, cards);
    assert(await page.locator('#board-project-path').isHidden(), 'project path hidden again under All projects');
    assert(await page.locator('#board-empty').isHidden(), 'no-match state cleared');
    evidence.steps.push('Project filter and preview search narrow 60 → 15 → 1 with "Showing n of 60" and matching column counts; no match shows "Nothing found…"; clear restores "Total: 60"; alpha card and beta heading carry folder · project · path');

    // BOARD-10: a stage save that fails shows the reason with Retry and leaves the card where it was.
    const goneId = records[2].id;
    const goneStage = stages[2];
    fs.unlinkSync(path.join(OUT, 'state', `conv-${goneId}.json`));
    const failedPatch = page.waitForResponse(r => r.request().method() === 'PATCH' && new URL(r.url()).pathname === `/api/conversations/${goneId}/board`);
    await card(page, goneId).locator('select[data-board-stage]').selectOption('review');
    const failed = await failedPatch;
    assert.equal(failed.status(), 404);
    assert.equal((await failed.json()).detail, 'no such conversation');
    const banner = page.locator('#board-feedback');
    await waitUntil(async () => await banner.isVisible() && await banner.textContent() === 'Stage not saved: no such conversationRetry', 'stage-not-saved banner');
    assert.equal(await banner.locator('button').textContent(), 'Retry');
    await column(page, goneStage).locator(`[data-conversation-id="${goneId}"]`).waitFor();
    assert.equal(await column(page, 'review').locator(`[data-conversation-id="${goneId}"]`).count(), 0);
    await page.screenshot({ path: path.join(OUT, 'stage-not-saved.png'), fullPage: true });
    // The page keeps the focused selector through polls; once focus leaves, the next poll drops the card and the banner stays.
    await page.locator('#board-search').focus();
    await waitUntil(async () => await card(page, goneId).count() === 0, 'deleted card gone after the next poll', 8000);
    assert(await banner.isVisible(), 'banner stays after the poll');
    const goneError = evidence.httpErrors.findIndex(e => e.url === `/api/conversations/${goneId}/board` && e.status === 404);
    assert(goneError >= 0, 'the 404 was recorded');
    evidence.httpErrors.splice(goneError, 1);
    evidence.steps.push('BOARD-10 failed stage save (404) shows "Stage not saved: no such conversation" + Retry; card stays in its column, then leaves with the next poll while the banner stays');

    const detailResponse = page.waitForResponse(r => r.request().method() === 'GET' && new URL(r.url()).pathname === `/api/conversations/${dragId}`);
    await card(page, dragId).locator('.session-preview').click();
    const opened = await (await detailResponse).json();
    assert.equal(opened.id, dragId);
    assert.deepEqual(opened.messages, before.messages);
    await page.locator('#thread').getByText(records[0].title, { exact: true }).waitFor();
    await page.locator('#thread').getByText(records[0].preview, { exact: true }).waitFor();
    assert.equal(await page.locator('#conversation-path').textContent(), pathText(opened.target).text);
    assert.equal(await page.locator('#show-board').textContent(), '← Sessions');
    await page.locator('#show-board').click();
    await page.locator('#board-view').waitFor({ state: 'visible' });
    evidence.steps.push('Card preview click opens original conversation with unchanged identity/messages and its folder · project · path; "← Sessions" returns without runtime call');

    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(OUT, 'narrow.png'), fullPage: true });
    const geometry = await page.locator('#board-columns').evaluate(el => ({ client: el.clientWidth, scroll: el.scrollWidth }));
    assert(geometry.scroll > geometry.client, 'narrow board has horizontal scrolling');
    assert(await page.evaluate(() => document.documentElement.scrollWidth) <= 390, 'no page-level horizontal scroll at 390px');
    for (const sel of ['#board-newconv', '#board-view .view-switch [data-board-view="sessions"]', '#board-view .view-switch [data-board-view="tasks"]', '#board-view .view-switch [data-board-view="automations"]']) {
      const box = await page.locator(sel).boundingBox();
      assert(box && box.x >= 0 && box.x + box.width <= 390, `${sel} not clipped at 390px: ${JSON.stringify(box)}`);
    }
    await column(page, 'completed').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(OUT, 'narrow-completed.png'), fullPage: true });
    evidence.narrowGeometry = geometry;
    evidence.steps.push('390px viewport retains horizontally scrollable five-column board, no page scroll, "+ New session" and view switch in view');

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
