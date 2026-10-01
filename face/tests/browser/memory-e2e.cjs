/* One real-app E2E for Memory Home and the project screen (state box, sessions, board) on a copy of demo/workspace. */
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
const WORKSPACE = path.resolve(APP, '..', 'demo', 'workspace');
const evidenceBase = process.env.VEPOL_BOARD_EVIDENCE_DIR || os.tmpdir();
fs.mkdirSync(evidenceBase, { recursive: true });
const OUT = fs.mkdtempSync(path.join(evidenceBase, 'vepol-memory-evidence-'));
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

// Values written in the sample files (demo/workspace/code/acme-web/knowledge).
const SAMPLE = {
  order: ['hub', 'acme-web', 'billing-api', 'design-system'],
  now: 'Checkout v2 is live for 20% of shoppers behind the checkout-v2 flag. Card payments work; saved addresses are the last missing piece before a full rollout.',
  stateHeading: 'acme-web — current state',
  inProgress: 'Saved addresses in checkout v2',
  columns: [['In Progress', 1], ['Review', 0], ['Blocked', 1], ['Ready', 1], ['Backlog', 1]],
  done: 3,
  decisions: ['Feature flags live in a config file, not a flag service', 'Server-render the checkout pages'],
  newestHistory: ['2026-09-26', 'progress | acme-web | "Saved addresses started"'],
  rule: 'Lock every payment submit button on the first click and send an idempotency key with each payment request',
  files: ['decisions', 'backlog.md', 'incidents.md', 'index.md', 'log.md', 'state.md'],
};

async function waitUntil(fn, label, timeout = 10000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (await fn()) return; await sleep(100); }
  throw new Error(`Timed out: ${label}`);
}

(async () => {
  let browser, server;
  const evidence = { status: 'running', app: APP, fixture: OUT, steps: [], cases: {}, pageErrors: [], httpErrors: [], runtimeCalls: [] };
  try {
    server = spawn(PYTHON, [path.join(ROOT, 'fixture_server.py'), APP, OUT], {
      stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, VEPOL_FIXTURE_WORKSPACE: WORKSPACE },
    });
    let stderr = '';
    server.stderr.on('data', b => { stderr += b.toString(); });
    const lines = readline.createInterface({ input: server.stdout });
    const [boot, fixture] = await new Promise((resolve, reject) => {
      const got = [];
      const timer = setTimeout(() => reject(new Error(`Fixture server did not start: ${stderr}`)), 30000);
      lines.on('line', line => {
        try { got.push(JSON.parse(line)); } catch (e) { clearTimeout(timer); reject(e); return; }
        if (got.length === 2) { clearTimeout(timer); resolve(got); }
      });
      server.once('exit', code => { clearTimeout(timer); reject(new Error(`Fixture server exited ${code}: ${stderr}`)); });
    });
    assert.deepEqual(fixture.memory.slugs, ['acme-web', 'billing-api', 'design-system']);
    const base = `http://127.0.0.1:${boot.port}`;
    const api = async (url, method = 'GET', data) => {
      const res = await fetch(base + url, { method, headers: { 'X-Vepol-Token': boot.token, 'Content-Type': 'application/json' }, body: data === undefined ? undefined : JSON.stringify(data) });
      assert(res.ok, `${method} ${url}: ${res.status}`);
      return res.json();
    };
    await waitUntil(async () => { try { return (await api('/api/health')).ok; } catch { return false; } }, 'fixture health');
    // Two acme-web terminal sessions: one never started, then one started (the /bin/cat stand-in).
    const idle = await api('/api/conversations', 'POST', { target: 'acme-web', runtime: 'codex', transport: 'terminal' });
    const live = await api('/api/conversations', 'POST', { target: 'acme-web', runtime: 'claude', transport: 'terminal' });
    await api(`/api/conversations/${live.id}/terminal/start`, 'POST');
    await waitUntil(async () => (await api(`/api/conversations/${live.id}`)).agent === 'alive', 'acme-web/claude started');
    await api(`/api/conversations/${idle.id}/board`, 'PATCH', { board_stage: 'review' });
    evidence.steps.push(`Fixture: a copy of demo/workspace at ${fixture.memory.workspace}, the repo's kb-board linked into its hub; acme-web sessions: claude started, codex not started`);

    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
    await context.addInitScript(token => { window.__VEPOL_TOKEN__ = token; }, boot.token);
    const page = await context.newPage();
    page.on('pageerror', e => evidence.pageErrors.push(e.message));
    page.on('response', r => { if (r.status() >= 400) evidence.httpErrors.push({ url: new URL(r.url()).pathname, status: r.status() }); });
    page.on('request', r => { const p = new URL(r.url()).pathname; if (r.method() === 'POST' && /\/(messages|retry|stop)$/.test(p)) evidence.runtimeCalls.push(p); });
    await page.goto(base);

    // M1. The app opens on Memory with 4 cards, hub first.
    await page.locator('#memory-pane').waitFor({ state: 'visible' });
    assert.equal(await page.locator('[data-board-view="memory"]').getAttribute('aria-selected'), 'true');
    const cardSlugs = () => page.locator('#memory-grid .memory-card').evaluateAll(els => els.map(e => e.dataset.memorySlug));
    await waitUntil(async () => JSON.stringify(await cardSlugs()) === JSON.stringify(SAMPLE.order), 'four cards, hub first');
    const acmeCard = page.locator('#memory-grid [data-memory-slug="acme-web"]');
    assert((await acmeCard.textContent()).includes(SAMPLE.now), 'acme-web card shows Now');
    assert((await acmeCard.textContent()).includes(SAMPLE.inProgress), 'acme-web card shows Next');
    assert.equal(await page.locator('#memory-grid [data-memory-slug="hub"] h3').textContent(), 'Vepol hub');
    assert.equal(await page.locator('#memory-count').textContent(), 'Total: 4');
    await page.screenshot({ path: path.join(OUT, 'memory-home.png'), fullPage: true });
    evidence.cases.M1 = { cards: SAMPLE.order };
    evidence.steps.push('M1 the app opens on Memory with 4 cards: hub, acme-web, billing-api, design-system');

    // M2. A sidebar click opens the acme-web screen (owner 2026-10-01): no dialog, no terminal; the row is highlighted.
    // The State box shows the snapshot, Next and the date; «Show full state» unfolds state.md rendered, no raw '##' or frontmatter.
    await page.locator('#tree .tree-project[data-slug="acme-web"]').click();
    await page.locator('#memory-project').waitFor({ state: 'visible' });
    assert(await page.locator('#memory-pane').isHidden());
    assert(await page.locator('#picker').isHidden(), 'a project click opens no dialog');
    assert(await page.locator('#terminal').isHidden(), 'a project click opens no terminal');
    assert.equal((await api(`/api/conversations/${idle.id}`)).agent, 'not_running', 'a project click starts nothing');
    assert.equal(await page.locator('#mem-name').textContent(), 'acme-web');
    assert.deepEqual(await page.locator('#tree .tree-project.active').evaluateAll(els => els.map(e => e.dataset.slug)), ['acme-web']);
    await waitUntil(async () => (await page.locator('#mem-now').textContent()) === SAMPLE.now, 'state box snapshot');
    const meta = await page.locator('#mem-state-meta').textContent();
    assert(meta.includes(`Next: ${SAMPLE.inProgress}`) && meta.includes('updated today'), `state box meta: ${meta}`);
    assert(await page.locator('#mem-state').isHidden(), 'full state folded by default');
    await page.locator('#mem-state-toggle').click();
    await page.locator('#mem-state').waitFor({ state: 'visible' });
    assert.equal(await page.locator('#mem-state-toggle').textContent(), 'Hide full state');
    await waitUntil(async () => await page.locator('#mem-state h1').count() === 1, 'state heading rendered');
    assert.equal(await page.locator('#mem-state h1').textContent(), SAMPLE.stateHeading);
    assert(await page.locator('#mem-state h2', { hasText: 'Current Snapshot' }).count() === 1);
    const stateText = await page.locator('#mem-state').textContent();
    assert(!stateText.includes('##') && !stateText.includes('---'), 'no raw markdown or frontmatter in State');
    evidence.steps.push(`M2 sidebar click → acme-web screen (no dialog/terminal, row highlighted); State box: snapshot, Next, «updated today»; Show full state renders "${SAMPLE.stateHeading}", no raw ## or frontmatter`);

    // M3. Board: columns with counts (Blocked shown because it has a task), the In Progress task with its owner, Done folded.
    const columns = () => page.locator('#mem-plans .kb-col').evaluateAll(els => els.map(e => [e.dataset.column, +e.querySelector('.count').textContent]));
    await waitUntil(async () => JSON.stringify(await columns()) === JSON.stringify(SAMPLE.columns), 'board columns')
      .catch(async (e) => { throw new Error(`${e.message}; columns: ${JSON.stringify(await columns())}`); });
    const inProgress = page.locator('#mem-plans .kb-col[data-column="In Progress"] .kb-task');
    assert.equal(await inProgress.count(), 1);
    assert.equal(await inProgress.first().textContent(), `${SAMPLE.inProgress}claude`);
    assert.equal(await page.locator('#mem-done summary').textContent(), `Done · ${SAMPLE.done}`);
    assert.equal(await page.locator('#mem-done').getAttribute('open'), null, 'Done folded');
    evidence.cases.M3 = { columns: await columns() };
    evidence.steps.push(`M3 Board: ${SAMPLE.columns.map(([c, n]) => `${c} ${n}`).join(' · ')}; "${SAMPLE.inProgress}" (claude) under In Progress; Done · ${SAMPLE.done} folded`);

    // M3b. Sessions: the running one first with «Agent running», then the stopped one; a card click opens its tab and terminal.
    const sessionCards = () => page.locator('#mem-sessions [data-project-session]').evaluateAll(els => els.map(e => [e.dataset.projectSession, e.querySelector('.ps-state').textContent, e.querySelector('.ps-meta').textContent]));
    await waitUntil(async () => (await sessionCards()).length === 2, 'two session cards');
    const shownSessions = await sessionCards();
    assert.deepEqual(shownSessions.map(([id, label]) => [id, label]), [[live.id, 'Agent running'], [idle.id, 'Agent not running']]);
    assert(shownSessions[1][2].startsWith('codex · Review · '), `stopped card meta: ${shownSessions[1][2]}`);
    assert(await page.locator(`#mem-sessions [data-project-session="${live.id}"]`).evaluate(e => e.classList.contains('tone-ok')), 'running card highlighted');
    await page.locator(`#mem-sessions [data-project-session="${live.id}"]`).click();
    await page.locator('#board-view').waitFor({ state: 'hidden' });
    await page.locator('#terminal').waitFor({ state: 'visible' });
    await waitUntil(async () => (await page.locator('#tabstrip .tab[aria-selected="true"]').evaluateAll(t => t.map(x => x.dataset.tab)))[0] === live.id, 'its tab is selected');
    assert.equal((await api(`/api/conversations/${idle.id}`)).agent, 'not_running', 'opening a card starts nothing else');
    // Back to the screen through the sidebar (switching projects is the same click).
    await page.locator('#tree .tree-project[data-slug="acme-web"]').click();
    await page.locator('#memory-project').waitFor({ state: 'visible' });
    assert.equal(await page.locator('#tabstrip .tab[aria-selected="true"]').count(), 0, 'the screen releases the selected tab');
    await waitUntil(async () => (await sessionCards()).length === 2, 'sessions again');
    await waitUntil(async () => await page.locator('#mem-decisions [data-decision]').count() === SAMPLE.decisions.length, 'page data again');
    assert(await page.locator('#mem-state').isHidden(), 'another visit starts with the full state folded');
    await page.screenshot({ path: path.join(OUT, 'project-screen.png'), fullPage: true });
    evidence.cases.M3b = { sessions: shownSessions };
    evidence.steps.push('M3b Sessions: claude «Agent running» (green) first, codex «Agent not running» · Review second; a card click opens its tab and terminal; the sidebar click returns to the screen');

    // M4. Decisions newest first; one opens rendered with its frontmatter folded into Details.
    const decisionTitles = await page.locator('#mem-decisions [data-decision]').evaluateAll(els => els.map(e => e.children[1].textContent.replace(/^· /, '')));
    assert.deepEqual(decisionTitles, SAMPLE.decisions);
    const firstDecision = page.locator('#mem-decisions [data-decision]').first();
    await firstDecision.click();
    const inline = page.locator('#mem-decisions .mem-inline').first();
    await waitUntil(async () => await inline.locator('h1').count() === 1, 'decision rendered');
    assert.equal(await inline.locator('h1').textContent(), SAMPLE.decisions[0]);
    assert.equal(await inline.locator('details.md-details summary').textContent(), 'Details');
    assert.equal(await inline.locator('details.md-details').getAttribute('open'), null, 'frontmatter folded');
    evidence.cases.M4 = { decisions: decisionTitles };
    evidence.steps.push('M4 Decisions list both sample decisions newest first; the first opens rendered, frontmatter folded into Details');

    // M5. History starts with the newest entry; M6. Lessons shows the sample rule.
    const firstHistory = page.locator('#mem-history [data-history]').first();
    const historyHead = await firstHistory.locator('summary span').evaluateAll(els => els.map(e => e.textContent));
    assert.deepEqual(historyHead, SAMPLE.newestHistory);
    await firstHistory.locator('summary').click();
    await waitUntil(async () => await firstHistory.locator('.mem-inline p, .mem-inline li').count() > 0, 'history body rendered');
    assert((await page.locator('#mem-lessons li').first().textContent()).startsWith(SAMPLE.rule));
    evidence.steps.push(`M5 History starts with ${SAMPLE.newestHistory.join(' ')}; M6 Lessons shows the sample prevention rule`);

    // M7. Files lists the tree; a file opens rendered in the Files section.
    const kbPaths = () => page.locator('#mem-files #kb-tree .kb-entry').evaluateAll(els => els.map(e => e.title));
    await waitUntil(async () => JSON.stringify(await kbPaths()) === JSON.stringify(SAMPLE.files), 'files tree');
    await page.locator('#mem-files [data-kb-path="state.md"]').click();
    await waitUntil(async () => await page.locator('#mem-files #kb-file-text h1').count() === 1, 'state.md rendered in Files');
    await page.screenshot({ path: path.join(OUT, 'project-memory.png'), fullPage: true });
    evidence.steps.push(`M7 Files lists ${SAMPLE.files.join(', ')}; state.md opens rendered`);

    // M8. "← Memory" returns to the cards.
    await page.locator('#memory-back').click();
    await page.locator('#memory-pane').waitFor({ state: 'visible' });
    assert(await page.locator('#memory-project').isHidden());
    assert.deepEqual(await cardSlugs(), SAMPLE.order);
    evidence.steps.push('M8 "← Memory" returns to the four cards');

    // M9. «New session here» offers the agents for this project; the new session opens (the /bin/cat stand-in);
    // the right-panel Memory tab renders the same markdown.
    await acmeCard.click();
    await page.locator('#memory-project').waitFor({ state: 'visible' });
    const before = new Set((await api('/api/conversations')).map(c => c.id));
    await page.locator('#mem-newconv').click();
    await page.locator('#picker').waitFor({ state: 'visible' });
    assert.equal(await page.locator('#picker-title').textContent(), 'New session in acme-web');
    await page.locator('#picker-runtimes button').first().click();
    await page.locator('#board-view').waitFor({ state: 'hidden' });
    let conv;
    await waitUntil(async () => { conv = (await api('/api/conversations')).find(c => !before.has(c.id)); return !!conv; }, 'a new session');
    assert.equal(conv.target, 'acme-web');
    const panelTab = page.locator('[data-panel="knowledge"]');
    assert.equal(await panelTab.textContent(), 'Memory');
    await panelTab.click();
    await page.locator('#panel-knowledge [data-kb-path="state.md"]').click();
    await waitUntil(async () => await page.locator('#panel-knowledge #kb-file-text h1').count() === 1, 'panel renders state.md');
    assert.equal(await page.locator('#panel-knowledge #kb-file-text h1').textContent(), SAMPLE.stateHeading);
    assert(!(await page.locator('#panel-knowledge #kb-file-text').textContent()).includes('##'));
    await page.screenshot({ path: path.join(OUT, 'panel-memory.png'), fullPage: true });
    await page.locator('#kb-open-memory').click();
    await page.locator('#memory-project').waitFor({ state: 'visible' });
    assert.equal(await page.locator('#mem-name').textContent(), 'acme-web');
    evidence.cases.M9 = { conversation: conv.id, target: conv.target };
    evidence.steps.push('M9 «New session here» → «New session in acme-web» → an agent click opens a new acme-web session; the right-panel "Memory" tab renders state.md the same way; "Open project memory" returns to the acme-web page');

    assert.deepEqual(evidence.pageErrors, [], 'No browser exceptions');
    assert.deepEqual(evidence.httpErrors, [], 'No HTTP errors');
    assert.deepEqual(evidence.runtimeCalls, [], 'No LLM/user session calls');
    evidence.status = 'passed';
    console.log(JSON.stringify({ status: 'passed', evidence: OUT, steps: evidence.steps, cases: evidence.cases }, null, 2));
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
