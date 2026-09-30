/* One real-app E2E for the new-session project picker: every project newest first, «Add project…»
   turns a plain folder into a project with the real new-wiki, the session opens there, and its
   tasks (written by the real kb-board) show on the board and in Tasks. */
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
const OUT = fs.mkdtempSync(path.join(evidenceBase, 'vepol-projects-evidence-'));
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function waitUntil(fn, label, timeout = 10000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (await fn()) return; await sleep(100); }
  throw new Error(`Timed out: ${label}`);
}

(async () => {
  let browser, server;
  const evidence = { status: 'running', app: APP, fixture: OUT, steps: [], pageErrors: [], httpErrors: [], runtimeCalls: [] };
  try {
    server = spawn(PYTHON, [path.join(ROOT, 'fixture_server.py'), APP, OUT], {
      stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, VEPOL_FIXTURE_PROJECTS: '1' },
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
    const { order, fresh, agents } = fixture.projects;
    const hub = path.join(OUT, 'hub');
    const base = `http://127.0.0.1:${boot.port}`;
    const api = async (url) => {
      const res = await fetch(base + url, { headers: { 'X-Vepol-Token': boot.token } });
      assert(res.ok, `GET ${url}: ${res.status}`);
      return res.json();
    };
    await waitUntil(async () => { try { return (await api('/api/health')).ok; } catch { return false; } }, 'fixture health');

    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
    await context.addInitScript(token => { window.__VEPOL_TOKEN__ = token; }, boot.token);
    const page = await context.newPage();
    page.on('pageerror', e => evidence.pageErrors.push(e.message));
    page.on('response', r => { if (r.status() >= 400) evidence.httpErrors.push({ url: new URL(r.url()).pathname, status: r.status() }); });
    page.on('request', r => { const p = new URL(r.url()).pathname; if (r.method() === 'POST' && /\/(messages|retry|stop)$/.test(p)) evidence.runtimeCalls.push(p); });
    await page.goto(base);
    await page.locator('#board-view').waitFor({ state: 'visible' });
    const pickerSlugs = () => page.locator('#picker-list [data-pick]').evaluateAll(rows => rows.map(r => r.dataset.pick));
    const convOf = async (slug) => (await api('/api/conversations')).find(c => c.target === slug);

    // 1. «+ New session» (sidebar; the app opens on Memory) lists every project, newest activity first, though none has a session yet.
    await page.locator('#newconv').click();
    await page.locator('#picker').waitFor({ state: 'visible' });
    await waitUntil(async () => JSON.stringify(await pickerSlugs()) === JSON.stringify(order), `picker order ${order}`);
    assert.match(await page.locator('#picker-list [data-pick="gamma"] .pwhen').textContent(), /^1 h ago$/);
    assert.match(await page.locator('#picker-list [data-pick="delta"] .pwhen').textContent(), /^no activity yet$/);
    // Every installed terminal agent from the roster is offered; notebooklm (not an agent) is not.
    const chips = () => page.locator('#picker-runtimes [data-pick-runtime]').evaluateAll(b => b.map(x => x.dataset.pickRuntime));
    await waitUntil(async () => JSON.stringify(await chips()) === JSON.stringify(agents), `agent chips ${agents}`);
    await page.locator('#picker-search').fill('alp');
    assert.deepEqual(await pickerSlugs(), ['alpha']);
    await page.locator('#picker-search').fill('');
    await page.screenshot({ path: path.join(OUT, 'picker.png') });
    evidence.steps.push(`P1 picker lists all ${order.length} projects newest first (${order.join(', ')}); search narrows it`);

    // 2. Picking a listed project starts its session there.
    await page.locator('#picker-list [data-pick="alpha"]').click();
    await waitUntil(async () => /· alpha ·/.test(await page.locator('#conversation-title').textContent()), 'alpha session opened');
    assert(await page.locator('#picker').isHidden());
    const alpha = await api(`/api/conversations/${(await convOf('alpha')).id}`);
    assert.equal(alpha.transport, 'terminal');
    evidence.steps.push('P2 picking alpha opens an alpha terminal session');

    // 3. The sidebar tree lists every project with alpha (just used) on top.
    const treeSlugs = () => page.locator('#tree .tree-project').evaluateAll(els => els.map(e => e.dataset.slug));
    const wantTree = ['alpha', ...order.filter(s => s !== 'alpha')];
    await waitUntil(async () => JSON.stringify(await treeSlugs()) === JSON.stringify(wantTree), `tree ${wantTree}`);
    evidence.steps.push('P3 sidebar tree lists every project, the one just used first');

    // 4. «Add project…» with a plain folder: new-wiki makes it a project and the session opens there.
    await page.locator('#newconv').click();
    await page.locator('#picker').waitFor({ state: 'visible' });
    page.once('dialog', d => d.accept(fresh));
    await page.locator('#picker-add').click();
    await waitUntil(async () => /· fresh-app ·/.test(await page.locator('#conversation-title').textContent()), 'fresh-app session opened', 20000);
    const link = path.join(hub, 'projects', 'fresh-app');
    assert.equal(fs.realpathSync(link), fs.realpathSync(path.join(fresh, 'knowledge')));
    for (const f of ['AGENTS.md', 'CLAUDE.md', 'knowledge/backlog.md', 'knowledge/state.md', 'knowledge/log.md']) {
      assert(fs.existsSync(path.join(fresh, f)), `new-wiki created ${f}`);
    }
    const freshConv = await api(`/api/conversations/${(await convOf('fresh-app')).id}`);
    assert.equal(freshConv.transport, 'terminal');
    assert.equal(freshConv.agent, 'alive', JSON.stringify(freshConv));
    const cmd = () => spawnSync('ps', ['-o', 'command=', '-p', String(freshConv.pid)], { encoding: 'utf8' }).stdout.trim();
    await waitUntil(async () => cmd() === '/bin/cat', `agent stand-in runs, got ${cmd()}`, 5000);
    assert.match(await page.locator('#conversation-path').textContent(), /Fresh App · fresh-app · /);
    await page.screenshot({ path: path.join(OUT, 'fresh-session.png') });
    evidence.steps.push(`P4 Add project: "${fresh}" became project fresh-app (new-wiki), its terminal session runs in it`);

    // 5. The project's agent writes tasks with the real kb-board; the app shows them.
    const board = path.join(fresh, 'knowledge', 'backlog.md');
    const kb = (...args) => spawnSync(path.join(hub, 'bin', 'kb-board'), args, { encoding: 'utf8' });
    for (const [id, title, status] of [['fresh-1', 'Ship the first screen', 'Ready'], ['fresh-2', 'Someday: invite the team', 'Backlog']]) {
      const r = kb('append', board, title, '--plan-item-id', id, '--status', status, '--actor', 'fixture');
      assert.equal(r.status, 0, r.stderr);
    }
    assert.equal(kb('check', board).status, 0);
    await page.locator('[data-board-view="sessions"]').click();
    await page.locator('#sessions-pane').waitFor({ state: 'visible' });
    await page.locator(`#board-view [data-conversation-id="${freshConv.id}"]`).waitFor();
    assert.match(await page.locator(`#board-view [data-conversation-id="${freshConv.id}"] .session-meta`).textContent(), /^fresh-app · /);
    const filterSlugs = await page.locator('#board-project-filter option').evaluateAll(o => o.map(x => x.value));
    assert.equal(filterSlugs[1], 'fresh-app');
    assert.deepEqual([...filterSlugs.slice(1)].sort(), [...order, 'fresh-app'].sort());
    await page.screenshot({ path: path.join(OUT, 'board.png') });
    await page.locator('[data-board-view="tasks"]').click();
    await page.locator('#tasks-pane').waitFor({ state: 'visible' });
    await waitUntil(async () => await page.locator('#tasks-project option[value="fresh-app"]').count() === 1, 'fresh-app in Tasks');
    await page.locator('#tasks-project').selectOption('fresh-app');
    const ids = () => page.locator('#tasks-table tbody tr[data-task-id]').evaluateAll(t => t.map(r => r.dataset.taskId));
    // One project selected: no Project column, and only this backlog's rows.
    const oneProject = async () => await page.locator('#tasks-table th', { hasText: 'Project' }).count() === 0;
    await waitUntil(async () => await oneProject() && JSON.stringify(await ids()) === '["fresh-1"]', 'Active shows fresh-1');
    assert(await page.locator('#tasks-none').isHidden(), 'fresh-app has its backlog.md');
    await page.screenshot({ path: path.join(OUT, 'tasks-active.png') });
    await page.locator('[data-task-chip="backlog"]').click();
    await waitUntil(async () => await oneProject() && JSON.stringify(await ids()) === '["fresh-2"]', 'Backlog shows fresh-2');
    await page.screenshot({ path: path.join(OUT, 'tasks-backlog.png') });
    evidence.steps.push('P5 fresh-app: its session card is on the board, first in the project filter; Tasks shows fresh-1 (Active) and fresh-2 (Backlog)');

    // 6. A column «+» asks for the project too and places the session in its stage.
    await page.locator('[data-board-view="sessions"]').click();
    await page.locator('#sessions-pane').waitFor({ state: 'visible' });
    await page.locator('[data-new-in="research"]').click();
    await page.locator('#picker').waitFor({ state: 'visible' });
    await page.locator('#picker-list [data-pick="beta"]').click();
    await waitUntil(async () => /· beta ·/.test(await page.locator('#conversation-title').textContent()), 'beta session opened');
    assert.equal((await convOf('beta')).board_stage, 'research');
    evidence.steps.push('P6 column «+» Research → picker → beta session in Research');

    // 7. Another agent CLI: hermes in delta runs in its own tmux session kb-delta-hermes.
    await page.locator('[data-board-view="sessions"]').click();
    await page.locator('#board-newconv').click();
    await page.locator('#picker').waitFor({ state: 'visible' });
    await page.locator('#picker-runtimes [data-pick-runtime="hermes"]').click();
    assert.equal(await page.locator('#picker-runtimes [aria-pressed="true"]').textContent(), 'hermes');
    await page.locator('#picker-list [data-pick="delta"]').click();
    await waitUntil(async () => /· delta · hermes$/.test(await page.locator('#conversation-title').textContent()), 'delta/hermes session opened');
    const hermes = await api(`/api/conversations/${(await convOf('delta')).id}`);
    assert.equal(hermes.runtime, 'hermes');
    assert.equal(hermes.transport, 'terminal');
    assert.equal((await api(`/api/conversations/${hermes.id}/attach`)).session, 'kb-delta-hermes');
    await waitUntil(async () => (await api(`/api/conversations/${hermes.id}`)).agent === 'alive', 'hermes stand-in alive');
    await page.screenshot({ path: path.join(OUT, 'hermes-session.png') });
    evidence.steps.push(`P7 agent chips ${agents.join(', ')}; hermes picked → delta terminal kb-delta-hermes is running`);

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
