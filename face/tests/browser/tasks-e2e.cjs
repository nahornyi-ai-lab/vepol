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

    // 4. Start session asks the agent, links the session to the task, reopens it for the same task, makes a new one for another.
    const taskConv = async (id) => (await api('/api/conversations')).find(c => c.task && c.task.project === 'alpha' && c.task.plan_item_id === id);
    const startTask = async (task) => {
      await page.locator('[data-board-view="tasks"]').click();
      await page.locator('#tasks-pane').waitFor({ state: 'visible' });
      await page.locator('#tasks-project').selectOption('alpha');
      await page.locator(`#tasks-table tr[data-task-project="alpha"][data-task-id="${task.id}"] [data-start-task]`).click();
      // The one-project picker: agent chips only, naming the task.
      await page.locator('#picker').waitFor({ state: 'visible' });
      assert.equal(await page.locator('#picker-title').textContent(), 'Start task in alpha');
      assert.equal(await page.locator('#picker-sub').textContent(), `Pick the agent for task ${task.id}: ${task.title}.`);
      assert(await page.locator('#picker-list').isHidden(), 'no project list for a task');
      const chip = page.locator('#picker-runtimes [data-pick-runtime]').first();
      const runtime = await chip.getAttribute('data-pick-runtime');
      const created = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/conversations');
      await chip.click();
      await page.locator('#picker').waitFor({ state: 'hidden' });
      const reply = await (await created).json();
      // A task that already has a session says so; a plain open shows no note.
      const note = reply.existing ? 'This task already has a session — opened it.' : '';
      if (note) await waitUntil(async () => await page.locator('#session-note').isVisible() && await page.locator('#session-note').textContent() === note, 'existing-task note');
      const text = `Task ${task.id} from knowledge/backlog.md: "${task.title}".`;
      await waitUntil(async () => await page.locator('#task-line').isVisible() && await page.locator('#task-text').textContent() === text, `task line for ${task.id}`);
      // The status arrives with the server's task sync (every 2 s in the fixture).
      await waitUntil(async () => { const c = await taskConv(task.id); return c && c.task_status === task.status; }, `${task.id} status on its card`);
      const conv = await taskConv(task.id);
      const detail = await api(`/api/conversations/${conv.id}`);
      assert.equal(detail.target, 'alpha');
      assert.equal(detail.runtime, runtime);
      assert.deepEqual(detail.task, { project: 'alpha', plan_item_id: task.id });
      assert.equal(detail.task_status, task.status);
      assert.equal(detail.terminal_name, `kb-alpha-${conv.id}-${runtime}`);
      assert.equal(detail.title, task.title);
      assert.deepEqual(detail.runs, []);
      assert.deepEqual(detail.messages.filter(m => m.role === 'user'), []);
      await waitUntil(async () => await page.locator('#conversation-task').textContent() === `Task ${task.id} · ${task.status}`, `header task line for ${task.id}`);
      // The owner's click started the agent in the fixture's own tmux: a /bin/cat stand-in, never a real CLI.
      assert.equal(detail.transport, 'terminal');
      assert.equal(detail.agent, 'alive', JSON.stringify(detail));
      const psCommand = () => spawnSync('ps', ['-o', 'command=', '-p', String(detail.pid)], { encoding: 'utf8' }).stdout.trim();
      // The stand-in script execs /bin/cat; right after start the pane may still show the script.
      await waitUntil(async () => psCommand() === '/bin/cat', `pid ${detail.pid} is /bin/cat, got ${psCommand()}`, 5000);
      const cmd = psCommand();
      const ppid = spawnSync('ps', ['-o', 'ppid=', '-p', String(detail.pid)], { encoding: 'utf8' }).stdout.trim();
      const parent = spawnSync('ps', ['-o', 'command=', '-p', ppid], { encoding: 'utf8' }).stdout.trim();
      assert.equal(parent, '/bin/zsh -f', 'the agent runs inside the pane shell');
      evidence.cases.T4.push({ task: task.id, runtime, conversation: conv.id, terminal: detail.terminal_name, title: detail.title,
        taskLine: await page.locator('#conversation-task').textContent(), composer: text, runs: detail.runs.length,
        agent: detail.agent, pid: detail.pid, command: cmd, parent: parent.split(" /usr/bin/env")[0], note });
      assert.equal(reply.id, conv.id);
      return { id: conv.id, existing: reply.existing, note };
    };
    const sessionCard = (id) => page.locator(`#board-view [data-conversation-id="${id}"]`);
    const cardStage = (id) => sessionCard(id).evaluate(el => el.closest('.board-column').dataset.stage);
    evidence.cases.T4 = [];
    const byId = Object.fromEntries(expected.alpha.map(t => [t.id, t]));
    const first = (await startTask(byId['alpha-2'])).id;
    assert(await page.locator('#composer').isHidden(), 'no Send box under a terminal session');
    // The card on the session board carries the task line.
    await page.locator('[data-board-view="sessions"]').click();
    await page.locator('#sessions-pane').waitFor({ state: 'visible' });
    await sessionCard(first).waitFor();
    await waitUntil(async () => await sessionCard(first).locator('.session-task').textContent() === 'Task alpha-2 · Ready', 'alpha-2 card task line');
    await page.screenshot({ path: path.join(OUT, 'tasks-session-card.png'), fullPage: true });
    // The same task again opens its session; a different task gets a new one.
    const again = await startTask(byId['alpha-2']);
    assert.equal(again.id, first);
    assert.equal(again.existing, true);
    const other = (await startTask(byId['alpha-1'])).id;
    assert.notEqual(other, first);
    assert.notEqual(evidence.cases.T4[0].terminal, evidence.cases.T4[2].terminal, 'two sessions, two terminals');
    await page.screenshot({ path: path.join(OUT, 'tasks-start-session.png'), fullPage: true });
    evidence.steps.push('T4 Start session asks the agent (chips), card and header show "Task alpha-2 · Ready"; the same task reopens its session with a note; alpha-1 gets a new session');

    // 5. The app never wrote a board.
    assert.deepEqual(boardHashes(), hashesBefore);
    evidence.cases.T5 = hashesBefore;
    evidence.steps.push('T5 sha256 of every fixture backlog.md unchanged');

    // T4 continued: an agent finishes alpha-1 through the real kb-board (request-review, close) -> its card lands in Done.
    const KB = path.join(OUT, 'hub', 'bin', 'kb-board');
    const alphaBoard = path.join(OUT, 'hub', 'projects', 'alpha', 'backlog.md');
    const kb = (...args) => spawnSync(KB, args, { encoding: 'utf8' });
    const alpha1 = JSON.parse(kb('list', alphaBoard, '--all', '--json').stdout).find(r => r.plan_item_id === 'alpha-1');
    for (const args of [['request-review', alphaBoard, '--plan-item-id', 'alpha-1', '--claim-id', alpha1.claim_id, '--actor', alpha1.claim_owner],
      ['close', alphaBoard, '--plan-item-id', 'alpha-1', '--claim-id', alpha1.claim_id, '--actor', alpha1.claim_owner, '--outcome', 'closed']]) {
      const r = kb(...args);
      assert.equal(r.status, 0, `${args[0]}: ${r.stdout}${r.stderr}`);
    }
    await page.locator('[data-board-view="sessions"]').click();
    await page.locator('#sessions-pane').waitFor({ state: 'visible' });
    await waitUntil(async () => await sessionCard(other).count() === 1 && await cardStage(other) === 'completed', 'alpha-1 card in Done', 15000);
    assert.equal(await sessionCard(other).locator('.session-task').textContent(), 'Task alpha-1 · Done');
    assert.notEqual(await cardStage(first), 'completed', 'the alpha-2 card stays');
    await page.screenshot({ path: path.join(OUT, 'tasks-card-done.png'), fullPage: true });
    evidence.cases.T4.push({ closed: 'alpha-1', card: other, stage: 'completed' });
    evidence.steps.push('T4 kb-board request-review + close of alpha-1 moves its card to Done within one board refresh');

    // 6. Close: this repo's kb-board cancels alpha-2 with the owner's reason, Undo reopens it; a stale hash changes nothing.
    const repoKb = path.resolve(APP, '..', 'bin', 'kb-board');
    if (!process.env.VEPOL_FIXTURE_KB_ROOT && fs.existsSync(repoKb)) assert.equal(fs.realpathSync(KB), fs.realpathSync(repoKb));
    const alpha2 = () => JSON.parse(kb('list', alphaBoard, '--all', '--json').stdout).find(r => r.plan_item_id === 'alpha-2');
    const taskRow = (id) => page.locator(`#tasks-table tr[data-task-project="alpha"][data-task-id="${id}"]`);
    const notice = async () => await page.locator('#tasks-notice').isVisible() ? await page.locator('#tasks-notice-text').textContent() : null;
    await page.locator('[data-board-view="tasks"]').click();
    await page.locator('#tasks-pane').waitFor({ state: 'visible' });
    await page.locator('#tasks-project').selectOption('alpha');
    await taskRow('alpha-2').locator('[data-close-task]').click();
    assert.equal(await page.locator('#tasks-table tr.confirm-row span').textContent(), `Close “${byId['alpha-2'].title}” as not needed?`);
    await page.locator('#task-close-reason').fill('test');
    await page.screenshot({ path: path.join(OUT, 'tasks-close-confirm.png'), fullPage: true });
    await page.locator('#task-close-confirm').click();
    const closed = `Closed alpha-2 “${byId['alpha-2'].title}”`;
    await waitUntil(async () => await notice() === closed && await page.locator('#tasks-undo').isVisible(), 'closed banner with Undo');
    await waitUntil(async () => await taskRow('alpha-2').count() === 0, 'alpha-2 leaves Active');
    await page.locator('[data-task-chip="closed"]').click();
    assert((await tableRows(page)).some(r => r.id === 'alpha-2' && r.status === 'Cancelled'), 'alpha-2 is Cancelled under Closed');
    assert.equal(alpha2().status, 'Cancelled');
    const cancelReason = fs.readFileSync(alphaBoard, 'utf8').split('\n').find(l => l.trim().startsWith('cancel_reason:'));
    assert.match(cancelReason || '', /^\s*cancel_reason: cancelled by owner at \S+: test$/);
    const check = kb('check', alphaBoard);
    assert.equal(check.status, 0, check.stdout + check.stderr);
    const afterClose = boardHashes();
    for (const slug of ['beta', 'gamma']) assert.equal(afterClose[slug], hashesBefore[slug], `${slug} unchanged`);
    await page.screenshot({ path: path.join(OUT, 'tasks-closed.png'), fullPage: true });
    await page.locator('#tasks-undo').click();
    await waitUntil(async () => !(await tableRows(page)).some(r => r.id === 'alpha-2'), 'alpha-2 leaves Closed');
    await page.locator('[data-task-chip="active"]').click();
    assert((await tableRows(page)).some(r => r.id === 'alpha-2' && r.status === 'Ready'), 'alpha-2 is Ready again');
    assert.equal(alpha2().status, 'Ready');
    evidence.cases.T6 = { kbBoard: fs.realpathSync(KB), banner: closed, cancelReason: cancelReason.trim(), check: check.stdout.trim(), undo: alpha2().status };

    // The task changes after the list was loaded: Close is refused, the table reloads, the board stays as it was.
    await taskRow('alpha-2').locator('[data-close-task]').click();
    await page.locator('#task-close-reason').waitFor();
    const edit = kb('progress', alphaBoard, '--plan-item-id', 'alpha-2', '--field', 'priority=P1', '--actor', 'fixture');
    assert.equal(edit.status, 0, edit.stderr);
    const beforeStale = boardHashes();
    await page.locator('#task-close-confirm').click();
    const stale = 'The task changed since the list was loaded — refreshed.';
    await waitUntil(async () => await notice() === stale, 'stale-hash banner');
    assert.equal(await page.locator('#tasks-notice').getAttribute('class'), 'banner bad');
    assert(await page.locator('#tasks-undo').isHidden(), 'no Undo on a refusal');
    assert.equal(await page.locator('#tasks-table tr.confirm-row').count(), 0);
    assert.equal(await taskRow('alpha-2').locator('td').first().textContent(), 'Ready');
    assert.deepEqual(boardHashes(), beforeStale);
    assert.equal(alpha2().status, 'Ready');
    assert.deepEqual(evidence.httpErrors, [{ url: '/api/tasks/cancel', status: 409 }]);
    evidence.httpErrors = [];
    await page.screenshot({ path: path.join(OUT, 'tasks-close-stale.png'), fullPage: true });
    evidence.cases.T6.stale = { banner: stale, boards: 'unchanged' };
    evidence.steps.push(`T6 Close alpha-2 with reason "test": Cancelled under Closed, cancel_reason on the board, check ok, beta/gamma unchanged; Undo -> Ready; stale hash -> "${stale}", nothing changed`);

    // TASK-07: without kb-board the view says so in red and clears the table; the session board is unaffected.
    await page.locator('[data-board-view="tasks"]').click();
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
