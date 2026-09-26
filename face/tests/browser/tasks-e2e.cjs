/* One real-app E2E for the Tasks view: real kb-board boards, real API, real browser. */
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
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
const OUT = fs.mkdtempSync(path.join(evidenceBase, 'vepol-tasks-evidence-'));
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));
const CHIPS = {
  active: ['In Progress', 'Review', 'Blocked', 'Ready'],
  backlog: ['Backlog'],
  closed: ['Done', 'Cancelled'],
  all: ['In Progress', 'Review', 'Blocked', 'Ready', 'Backlog', 'Done', 'Cancelled'],
};

async function waitUntil(fn, label, timeout = 10000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (await fn()) return; await sleep(100); }
  throw new Error(`Timed out: ${label}`);
}

function boardHashes() {
  const projects = path.join(OUT, 'hub', 'projects');
  const out = {};
  for (const slug of fs.readdirSync(projects)) {
    const file = path.join(projects, slug, 'backlog.md');
    if (fs.existsSync(file)) out[slug] = crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
  }
  return out;
}

// Expected table rows for one chip: chip status order, then file order.
function expectedRows(tasks, chip) {
  const order = CHIPS[chip];
  return tasks.filter(t => order.includes(t.status))
    .sort((a, b) => order.indexOf(a.status) - order.indexOf(b.status))
    .map(t => ({ status: t.status, title: t.title, id: t.id || '—', owner: t.owner || '' }));
}

async function tableRows(page, withProject = false) {
  return page.locator('#tasks-table tbody tr[data-task-project]').evaluateAll((trs, withProject) => trs.map(tr => {
    const td = [...tr.querySelectorAll('td')].map(c => c.textContent.trim());
    const row = { status: td[0], title: td[1], id: td[2], owner: td[3] };
    if (withProject) row.project = td[4];
    return row;
  }), withProject);
}

(async () => {
  let browser, server;
  const evidence = { status: 'running', app: APP, fixture: OUT, steps: [], cases: {}, pageErrors: [], httpErrors: [], runtimeCalls: [] };
  try {
    server = spawn(PYTHON, [path.join(ROOT, 'fixture_server.py'), APP, OUT], {
      stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, VEPOL_FIXTURE_TASKS: '1' },
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
    const expected = fixture.tasks;
    const base = `http://127.0.0.1:${boot.port}`;
    const api = async (url) => {
      const res = await fetch(base + url, { headers: { 'X-Vepol-Token': boot.token } });
      assert(res.ok, `GET ${url}: ${res.status}`);
      return res.json();
    };
    await waitUntil(async () => { try { return (await api('/api/health')).ok; } catch { return false; } }, 'fixture health');
    const hashesBefore = boardHashes();
    assert.deepEqual(Object.keys(hashesBefore).sort(), ['alpha', 'beta', 'gamma']);
    evidence.steps.push('Fixture boards filled by the real kb-board; sha256 of every backlog.md recorded');

    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
    await context.addInitScript(token => { window.__VEPOL_TOKEN__ = token; }, boot.token);
    const page = await context.newPage();
    page.on('pageerror', e => evidence.pageErrors.push(e.message));
    page.on('response', r => { if (r.status() >= 400) evidence.httpErrors.push({ url: new URL(r.url()).pathname, status: r.status() }); });
    page.on('request', r => { const p = new URL(r.url()).pathname; if (r.method() === 'POST' && /\/(messages|retry|stop)$/.test(p)) evidence.runtimeCalls.push(p); });
    await page.goto(base);
    await page.locator('#board-view').waitFor({ state: 'visible' });
    await page.locator('[data-board-view="tasks"]').click();
    await page.locator('#tasks-pane').waitFor({ state: 'visible' });
    await waitUntil(async () => await page.locator('#tasks-project option[value="alpha"]').count() === 1, 'alpha in project picker');

    // 1. alpha, Active: exactly the kb-board rows for the Active statuses.
    await page.locator('#tasks-project').selectOption('alpha');
    const alphaActive = expectedRows(expected.alpha, 'active');
    await waitUntil(async () => JSON.stringify(await tableRows(page)) === JSON.stringify(alphaActive), 'alpha active rows');
    assert.equal(await page.locator('#tasks-table th', { hasText: 'Project' }).count(), 0);
    evidence.cases.T1 = { rows: alphaActive };
    await page.screenshot({ path: path.join(OUT, 'tasks-alpha.png'), fullPage: true });
    evidence.steps.push(`T1 alpha Active shows the ${alphaActive.length} kb-board rows with status, ID and owner`);

    // 2. Chips and search.
    evidence.cases.T2 = { chips: { active: alphaActive.length } };
    for (const chip of ['backlog', 'closed', 'all']) {
      await page.locator(`[data-task-chip="${chip}"]`).click();
      const want = expectedRows(expected.alpha, chip);
      assert.deepEqual(await tableRows(page), want, `chip ${chip}`);
      evidence.cases.T2.chips[chip] = want.length;
    }
    await page.locator('#tasks-search').fill('RELEASE notes');
    assert.deepEqual((await tableRows(page)).map(r => r.id), ['alpha-2']);
    await page.locator('#tasks-search').fill('alpha-3');
    assert.deepEqual((await tableRows(page)).map(r => r.id), ['alpha-3']);
    assert.equal(await page.locator('#tasks-count').textContent(), `Showing 1 of ${expected.alpha.length}`);
    evidence.cases.T2.search = { 'RELEASE notes': ['alpha-2'], 'alpha-3': ['alpha-3'], count: `Showing 1 of ${expected.alpha.length}` };
    await page.locator('#tasks-search').fill('');
    await page.locator('[data-task-chip="active"]').click();
    evidence.steps.push('T2 Backlog / Closed / All chips and title/ID search narrow the table as specified');

    // 3. All projects: alpha and beta rows with Project, a red line for gamma, one grey line for boards that do not exist.
    await page.locator('#tasks-project').selectOption('');
    const allActive = [...expected.alpha.map(t => ({ ...t, project: 'alpha' })), ...expected.beta.map(t => ({ ...t, project: 'beta' }))];
    const order = CHIPS.active;
    const wantAll = allActive.filter(t => order.includes(t.status))
      .sort((a, b) => order.indexOf(a.status) - order.indexOf(b.status))
      .map(t => ({ status: t.status, title: t.title, id: t.id || '—', owner: t.owner || '', project: t.project }));
    await waitUntil(async () => JSON.stringify(await tableRows(page, true)) === JSON.stringify(wantAll), 'all-projects active rows');
    const errorRow = page.locator('#tasks-table tr.error-row');
    assert.equal(await errorRow.count(), 1);
    assert.match(await errorRow.textContent(), /^gamma: backlog unreadable — \S/);
    const none = Object.keys(expected).filter(k => expected[k] === 'none');
    assert(none.includes('delta'));
    const noneText = await page.locator('#tasks-none').textContent();
    assert(noneText.startsWith('No backlog.md: '), noneText);
    assert.deepEqual(noneText.slice('No backlog.md: '.length).split(', ').sort(), none.sort());
    await page.screenshot({ path: path.join(OUT, 'tasks-all.png'), fullPage: true });
    evidence.cases.T3 = { rows: wantAll.length, errorRow: await errorRow.textContent(), none: noneText };
    evidence.steps.push(`T3 All projects: alpha+beta rows with Project, red gamma line, "${noneText}"`);

    // 4. Start session: target alpha, the task title, the pre-typed text, and no run.
    const startTask = async (task, expectedTitle = task.title) => {
      await page.locator(`#tasks-table tr[data-task-project="alpha"][data-task-id="${task.id}"] [data-start-task]`).click();
      const text = `Task ${task.id} from knowledge/backlog.md: "${task.title}".`;
      await waitUntil(async () => await page.locator('#prompt').inputValue() === text, `pre-typed text for ${task.id}`);
      const conv = (await api('/api/conversations')).find(c => c.target === 'alpha');
      assert(conv, 'an alpha conversation exists');
      const detail = await api(`/api/conversations/${conv.id}`);
      assert.equal(detail.target, 'alpha');
      assert.equal(detail.title, expectedTitle);
      assert.deepEqual(detail.runs, []);
      assert.deepEqual(detail.messages.filter(m => m.role === 'user'), []);
      assert.match(await page.locator('#conversation-title').textContent(), new RegExp(expectedTitle));
      // The owner's click started the agent in the fixture's own tmux: a /bin/cat stand-in, never a real CLI.
      assert.equal(detail.transport, 'terminal');
      assert.equal(detail.agent, 'alive', JSON.stringify(detail));
      const psCommand = () => spawnSync('ps', ['-o', 'command=', '-p', String(detail.pid)], { encoding: 'utf8' }).stdout.trim();
      // The stand-in script execs /bin/cat; right after start the pane may still show the script.
      await waitUntil(async () => psCommand() === '/bin/cat', `pid ${detail.pid} is /bin/cat, got ${psCommand()}`, 5000);
      const cmd = psCommand();
      const ppid = spawnSync('ps', ['-o', 'ppid=', '-p', String(detail.pid)], { encoding: 'utf8' }).stdout.trim();
      const parent = spawnSync('ps', ['-o', 'command=', '-p', ppid], { encoding: 'utf8' }).stdout.trim();
      assert.equal(cmd, '/bin/cat');
      assert.match(parent, /tmux/);
      evidence.cases.T4.push({ task: task.id, conversation: conv.id, target: detail.target, title: detail.title,
        composer: text, runs: detail.runs.length, userMessages: 0, agent: detail.agent, pid: detail.pid, command: cmd, parent: parent.split(" /usr/bin/env")[0] });
      return conv.id;
    };
    evidence.cases.T4 = [];
    const byId = Object.fromEntries(expected.alpha.map(t => [t.id, t]));
    await page.locator('#tasks-project').selectOption('alpha');
    await page.locator('#tasks-table tr[data-task-id="alpha-2"]').waitFor();
    const first = await startTask(byId['alpha-2']);
    // The back button returns to Tasks and says so; a second task reuses the one alpha terminal and keeps its title.
    assert.equal(await page.locator('#show-board').textContent(), '← Tasks');
    await page.locator('#show-board').click();
    await page.locator('#tasks-pane').waitFor({ state: 'visible' });
    await page.locator('#tasks-table tr[data-task-id="alpha-1"]').waitFor();
    assert.equal(await startTask(byId['alpha-1'], byId['alpha-2'].title), first);
    await page.screenshot({ path: path.join(OUT, 'tasks-start-session.png'), fullPage: true });
    evidence.steps.push('T4 Start session opens an alpha chat named after the task with the pre-typed text; no run, no message sent');

    // 5. The app never wrote a board.
    assert.deepEqual(boardHashes(), hashesBefore);
    evidence.cases.T5 = hashesBefore;
    evidence.steps.push('T5 sha256 of every fixture backlog.md unchanged');

    // TASK-07: without kb-board the view says so in red and clears the table; the session board is unaffected.
    await page.locator('#show-board').click();
    await page.locator('#tasks-pane').waitFor({ state: 'visible' });
    const kbBoard = path.join(OUT, 'hub', 'bin', 'kb-board');
    fs.unlinkSync(kbBoard);
    await page.locator('#tasks-refresh').click();
    const banner = `kb-board not found: ${kbBoard}`;
    await waitUntil(async () => await page.locator('#tasks-feedback').isVisible() && await page.locator('#tasks-feedback').textContent() === banner, 'kb-board missing banner');
    assert.equal(await page.locator('#tasks-table tr').count(), 0);
    assert.equal(await page.locator('#tasks-count').textContent(), '');
    assert(await page.locator('#tasks-empty').isHidden(), 'no "Nothing found" under the banner');
    await page.screenshot({ path: path.join(OUT, 'tasks-kb-board-missing.png'), fullPage: true });
    await page.locator('[data-board-view="sessions"]').click();
    await page.locator('#sessions-pane').waitFor({ state: 'visible' });
    await page.locator(`#board-view [data-conversation-id="${first}"]`).waitFor();
    assert(await page.locator('#board-feedback').isHidden(), 'the session board shows no error');
    evidence.cases.T7 = { banner, sessionsCard: first };
    evidence.steps.push(`T7 kb-board removed: red "${banner}", table and count cleared; Sessions still shows the alpha card`);
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
