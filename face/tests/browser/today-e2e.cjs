/* One real-app E2E for the Today card: the tree's own kb-dayplan, real API, real browser, /bin/cat as the agent. */
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
const OUT = fs.mkdtempSync(path.join(evidenceBase, 'vepol-today-evidence-'));
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function waitUntil(fn, label, timeout = 10000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (await fn()) return; await sleep(100); }
  throw new Error(`Timed out: ${label}`);
}

// Today in the machine's local zone, as the server sees it.
const now = new Date();
const pad = (n) => String(n).padStart(2, '0');
const TODAY = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
const DAY_LABEL = now.toLocaleDateString('en', { weekday: 'short', month: 'short', day: 'numeric' });
const SHORT = now.toLocaleDateString('en', { month: 'short', day: 'numeric' });
const stamp = (h, m) => new Date(now.getFullYear(), now.getMonth(), now.getDate(), h, m).toISOString();

// A plan written the way the shared contract says (day-plan/v1); the text is the owner's language plus markup that must stay text.
const PLAN = {
  schema: 'day-plan/v1', date: TODAY, version: 3, status: 'Confirmed',
  goal: 'Закончить отчёт по продукту', goal_source: 'personal/goals.md',
  outcomes: ['Отчёт отправлен', 'Notes for <b>Anna</b> & the team'],
  blocks: [
    { id: 'b1', start: '09:30', end: '10:00', title: 'Standup', kind: 'fixed', fixed: true, event_id: null },
    { id: 'b2', start: '10:00', end: '12:00', title: 'Deep work: отчёт', kind: 'focus', fixed: false, event_id: null },
    { id: 'b3', start: '14:00', end: '15:00', title: 'Review <b>draft</b> & send', kind: 'review', fixed: false, event_id: null },
  ],
  confirmed: { version: 3, at: stamp(9, 5), said: 'да' },
  calendar: null,
  history: [
    { version: 1, at: stamp(8, 40), change: 'proposed from the morning brief' },
    { version: 2, at: stamp(8, 52), change: 'moved the review to 14:00' },
    { version: 3, at: stamp(9, 4), change: 'dropped the gym block' },
  ],
};

(async () => {
  let browser, srv;
  const evidence = { status: 'running', app: APP, fixture: OUT, steps: [], cases: {}, pageErrors: [], httpErrors: [], runtimeCalls: [] };
  const hub = path.join(OUT, 'hub');
  const planFile = path.join(hub, 'personal', 'day-plans', `${TODAY}.json`);
  const sha = () => crypto.createHash('sha256').update(fs.readFileSync(planFile)).digest('hex');

  const startServer = async () => {
    const proc = spawn(PYTHON, [path.join(ROOT, 'fixture_server.py'), APP, OUT], {
      stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, VEPOL_FIXTURE_DAYPLAN: '1' },
    });
    let stderr = '';
    proc.stderr.on('data', b => { stderr += b.toString(); });
    const lines = readline.createInterface({ input: proc.stdout });
    const boot = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`Fixture server did not start: ${stderr}`)), 30000);
      lines.once('line', line => { clearTimeout(timer); try { resolve(JSON.parse(line)); } catch (e) { reject(e); } });
      proc.once('exit', code => { clearTimeout(timer); reject(new Error(`Fixture server exited ${code}: ${stderr}`)); });
    });
    const base = `http://127.0.0.1:${boot.port}`;
    const api = async (url, opts = {}) => {
      const res = await fetch(base + url, { ...opts, headers: { 'X-Vepol-Token': boot.token } });
      assert(res.ok, `${opts.method || 'GET'} ${url}: ${res.status}`);
      return res.json();
    };
    await waitUntil(async () => { try { return (await api('/api/health')).ok; } catch { return false; } }, 'fixture health');
    return { proc, boot, base, api };
  };
  const stopServer = async (proc) => {
    if (proc && proc.exitCode === null) {
      proc.kill('SIGTERM');
      await Promise.race([new Promise(resolve => proc.once('exit', resolve)), sleep(5000)]);
      if (proc.exitCode === null) proc.kill('SIGKILL');
    }
  };
  const openPage = async (srv) => {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
    await context.addInitScript(token => { window.__VEPOL_TOKEN__ = token; }, srv.boot.token);
    const page = await context.newPage();
    page.on('pageerror', e => evidence.pageErrors.push(e.message));
    page.on('response', r => { if (r.status() >= 400) evidence.httpErrors.push({ url: new URL(r.url()).pathname, status: r.status() }); });
    page.on('request', r => { const p = new URL(r.url()).pathname; if (r.method() === 'POST' && /\/(messages|retry|stop)$/.test(p)) evidence.runtimeCalls.push(p); });
    await page.goto(srv.base);
    await page.locator('#board-view').waitFor({ state: 'visible' });
    await page.locator('#today-card').waitFor({ state: 'visible' });
    return page;
  };
  // Memory Home reloads the card when it is shown again.
  const reloadToday = async (page) => {
    await page.locator('[data-board-view="sessions"]').click();
    await page.locator('#sessions-pane').waitFor({ state: 'visible' });
    await page.locator('[data-board-view="memory"]').click();
    await page.locator('#memory-pane').waitFor({ state: 'visible' });
  };
  const cardRows = (page) => page.locator('#today-blocks li').evaluateAll(lis => lis.map(li => ({
    when: li.querySelector('.when').textContent, title: li.querySelector('.title').textContent, fixed: !!li.querySelector('.chip'),
  })));
  const expectedRows = PLAN.blocks.map(b => ({ when: `${b.start}–${b.end}`, title: b.title, fixed: b.fixed }));

  try {
    srv = await startServer();
    const KB_DAYPLAN = path.join(hub, 'bin', 'kb-dayplan');
    const promptPath = path.join(path.dirname(fs.realpathSync(KB_DAYPLAN)), 'day-plan-prompt.md');
    browser = await chromium.launch({ headless: true });
    let page = await openPage(srv);

    // 1. No plan file yet: the card says so (kb-dayplan answers {"exists": false}), and Plan my day is offered.
    await waitUntil(async () => (await page.locator('#today-body').textContent()).trim() === 'No plan for today yet', 'no-plan text');
    assert.equal(await page.locator('#today-date').textContent(), DAY_LABEL);
    assert.equal(await page.locator('#today-plan').isEnabled(), true);
    assert(await page.locator('#today-error').isHidden());
    const none = await srv.api('/api/dayplan');
    assert.deepEqual({ exists: none.exists, date: none.date, prompt: none.prompt }, { exists: false, date: TODAY, prompt: promptPath });
    evidence.cases.D1 = { answer: none };
    evidence.steps.push('D1 no plan file: the card says "No plan for today yet"; /api/dayplan passes kb-dayplan\'s {exists:false} and its prompt path');

    // 2. The fixture plan, written directly per the shared contract: the card shows it all, as text.
    fs.mkdirSync(path.dirname(planFile), { recursive: true, mode: 0o700 });
    fs.writeFileSync(planFile, JSON.stringify(PLAN, null, 2), { mode: 0o600 });
    const planHash = sha();
    await reloadToday(page);
    await waitUntil(async () => await page.locator('#today-goal').count() === 1, 'plan on the card');
    assert.equal(await page.locator('#today-goal').textContent(), PLAN.goal);
    assert.equal(await page.locator('#today-card .today-goal .muted').textContent(), `· ${PLAN.goal_source}`);
    assert.deepEqual(await page.locator('#today-outcomes li').allTextContents(), PLAN.outcomes);
    assert.deepEqual(await cardRows(page), expectedRows);
    assert.equal((await page.locator('#today-status').textContent()).trim(), 'Confirmed');
    assert((await page.locator('#today-meta').textContent()).startsWith('Version 3 · Last change: dropped the gym block'), await page.locator('#today-meta').textContent());
    assert.equal(await page.locator('#today-card b').count(), 0, 'plan text is never read as markup');
    assert.equal(await page.locator('#today-date').textContent(), DAY_LABEL);
    const api2 = await srv.api('/api/dayplan');
    assert.equal(api2.exists, true);
    assert.equal(api2.version, 3);
    assert.equal(api2.prompt, promptPath);
    assert(path.isAbsolute(api2.prompt));
    await page.screenshot({ path: path.join(OUT, 'today-card.png'), fullPage: true });
    evidence.cases.D2 = { goal: PLAN.goal, rows: expectedRows, status: 'Confirmed', meta: await page.locator('#today-meta').textContent() };
    evidence.steps.push('D2 the card shows goal, outcomes, three blocks with the fixed mark, "Confirmed", "Version 3 · Last change: dropped the gym block"; markup in the text stays text');

    // 3. Plan my day -> the agent chips (one project: the hub) -> a hub session with the typed-not-sent banner.
    const convs = async () => (await srv.api('/api/conversations')).filter(c => c.day_plan === TODAY);
    assert.deepEqual(await convs(), []);
    const planClick = async () => {
      await page.locator('[data-board-view="memory"]').click();
      await page.locator('#today-plan').click();
      await page.locator('#picker').waitFor({ state: 'visible' });
      assert.equal(await page.locator('#picker-title').textContent(), 'Plan my day');
      assert.equal(await page.locator('#picker-sub').textContent(), `Pick the agent to plan ${DAY_LABEL} with.`);
      assert(await page.locator('#picker-list').isHidden(), 'no project list: the day is planned in the hub');
      // Claude when it is listed (its command carries the calendar deny flag), else the first agent.
      const claude = page.locator('#picker-runtimes [data-pick-runtime="claude"]');
      const chip = await claude.count() ? claude : page.locator('#picker-runtimes [data-pick-runtime]').first();
      const runtime = await chip.getAttribute('data-pick-runtime');
      const created = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/conversations');
      await chip.click();
      await page.locator('#picker').waitFor({ state: 'hidden' });
      const reply = await (await created).json();
      return { runtime, reply, request: (await created).request().postDataJSON() };
    };
    const first = await planClick();
    assert.equal(first.reply.existing, false);
    assert.deepEqual(first.request, { target: 'hub', runtime: first.runtime, transport: 'terminal', day_plan: TODAY });
    const text = `Plan my day for ${TODAY}: follow ${promptPath}`;
    await waitUntil(async () => await page.locator('#task-line').isVisible() && await page.locator('#task-text').textContent() === text, 'banner text');
    const detail = await srv.api(`/api/conversations/${first.reply.id}`);
    assert.equal(detail.target, 'hub');
    assert.equal(detail.runtime, first.runtime);
    assert.equal(detail.day_plan, TODAY);
    assert.equal(detail.title, `Plan my day · ${SHORT}`);
    assert.equal(detail.transport, 'terminal');
    assert.equal(detail.terminal_name, `kb-hub-${first.reply.id}-${first.runtime}`);
    assert.equal(detail.agent, 'alive', JSON.stringify(detail));
    assert.deepEqual(detail.runs, []);
    assert.deepEqual(detail.messages.filter(m => m.role === 'user'), []);
    assert(await page.locator('#composer').isHidden(), 'no Send box under a terminal session');
    // Nothing was sent by itself: the line reaches the terminal only when the owner presses the button, and then
    // sits typed on the command line (no Enter) exactly once.
    // tmux on the fixture's own socket only; without TMUX/TMUX_PANE it cannot reach a caller's server.
    const tmuxEnv = { ...process.env }; delete tmuxEnv.TMUX; delete tmuxEnv.TMUX_PANE;
    const tmux = (...args) => spawnSync('tmux', ['-S', srv.boot.tmux_socket, ...args], { encoding: 'utf8', env: tmuxEnv });
    const pane = () => tmux('capture-pane', '-p', '-J', '-t', detail.terminal_name).stdout.replace(/\s+/g, ' ');
    const flag = '--disallowedTools mcp__claude_ai_Google_Calendar';
    if (first.runtime === 'claude') {
      assert(pane().includes(flag), `the Claude command carries the calendar deny flag: ${pane()}`);
    }
    assert(!pane().includes(text), 'the opening line is not in the terminal before the owner asks');
    await page.locator('#task-type').click();
    await waitUntil(async () => pane().includes(text), 'banner text typed into the terminal');
    assert.equal(pane().split(text).length - 1, 1, 'typed once, not submitted');
    assert(await page.locator('#task-line').isHidden());
    await page.screenshot({ path: path.join(OUT, 'today-session.png'), fullPage: true });
    evidence.cases.D3 = { runtime: first.runtime, conversation: first.reply.id, terminal: detail.terminal_name, title: detail.title, banner: text,
      denyFlagChecked: first.runtime === 'claude' };
    evidence.steps.push(`D3 Plan my day -> "${first.runtime}" chip -> hub session "${detail.title}", banner "${text}", typed into the terminal on the owner's click only`);

    // 4. A second click reopens the same session (and says so); no second session exists.
    const second = await planClick();
    assert.equal(second.reply.existing, true);
    assert.equal(second.reply.id, first.reply.id);
    await waitUntil(async () => await page.locator('#session-note').isVisible()
      && await page.locator('#session-note').textContent() === 'This day already has a planning session — opened it.', 'reopen note');
    assert((await page.locator('#task-line').isHidden()), 'a reopened session gets no second banner');
    assert.equal((await convs()).length, 1);
    evidence.cases.D4 = { reopened: second.reply.id, sessionsForToday: 1 };
    evidence.steps.push('D4 a second Plan my day click reopens the same session with a note; one session for today');

    // 5. The server restarts: the same plan, the same version; the app never wrote the file.
    await page.context().close();
    await stopServer(srv.proc);
    assert.equal(sha(), planHash, 'the app never writes the plan');
    srv = await startServer();
    page = await openPage(srv);
    await waitUntil(async () => await page.locator('#today-goal').count() === 1, 'plan after restart');
    assert.equal(await page.locator('#today-goal').textContent(), PLAN.goal);
    assert.deepEqual(await cardRows(page), expectedRows);
    assert((await page.locator('#today-meta').textContent()).startsWith('Version 3 · Last change: dropped the gym block'));
    assert.equal((await page.locator('#today-status').textContent()).trim(), 'Confirmed');
    assert.equal((await srv.api('/api/dayplan')).version, 3);
    assert.equal((await convs()).length, 1, 'the planning session survived the restart');
    assert.equal(sha(), planHash);
    await page.screenshot({ path: path.join(OUT, 'today-after-restart.png'), fullPage: true });
    evidence.cases.D5 = { version: 3, sha256: planHash };
    evidence.steps.push('D5 after a server restart the card shows version 3 again; the plan file is byte-identical');

    // 6. Without kb-dayplan the card says why, in red, and shows no plan (never an empty one); Plan my day waits.
    fs.unlinkSync(KB_DAYPLAN);
    await reloadToday(page);
    const banner = `kb-dayplan not found: ${KB_DAYPLAN}`;
    await waitUntil(async () => await page.locator('#today-error').isVisible() && await page.locator('#today-error').textContent() === banner, 'kb-dayplan missing banner');
    assert.equal(await page.locator('#today-goal').count(), 0);
    assert.equal(await page.locator('#today-blocks').count(), 0);
    assert.equal(await page.locator('#today-plan').isDisabled(), true);
    await page.screenshot({ path: path.join(OUT, 'today-error.png'), fullPage: true });
    evidence.cases.D6 = { banner };
    evidence.steps.push(`D6 kb-dayplan removed: red "${banner}", no plan on the card, Plan my day disabled`);

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
    if (srv) await stopServer(srv.proc);
    fs.writeFileSync(path.join(OUT, 'result.json'), JSON.stringify(evidence, null, 2));
  }
})();
