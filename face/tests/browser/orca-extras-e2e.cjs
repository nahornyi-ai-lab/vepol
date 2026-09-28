/* One real-app E2E for the Orca extras: project tree, knowledge panel, column "+", agent exit and Start, usage bar. */
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
const OUT = fs.mkdtempSync(path.join(evidenceBase, 'vepol-orca-evidence-'));
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function waitUntil(fn, label, timeout = 10000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (await fn()) return; await sleep(100); }
  throw new Error(`Timed out: ${label}`);
}

// mtime of every entry under the fixture knowledge/ root, directories included.
function mtimes(root) {
  const out = {};
  const walk = (dir, rel) => {
    out[rel || '.'] = fs.lstatSync(dir).mtimeMs;
    for (const name of fs.readdirSync(dir).sort()) {
      const full = path.join(dir, name);
      const r = rel ? `${rel}/${name}` : name;
      if (fs.lstatSync(full).isDirectory()) walk(full, r); else out[r] = fs.lstatSync(full).mtimeMs;
    }
  };
  walk(root, '');
  return out;
}

// The sidebar tree as { project: [{ id, dot, active }] }, in page order.
async function treeShape(page) {
  return page.locator('#tree').evaluate(tree => {
    const out = [];
    for (const el of tree.children) {
      if (el.classList.contains('tree-project')) out.push({ slug: el.dataset.slug, active: el.classList.contains('active'), sessions: [] });
      else if (el.classList.contains('tree-sessions') && out.length) {
        out[out.length - 1].sessions = [...el.querySelectorAll('.tree-session')].map(s => {
          const dot = s.querySelector('.dot');
          return { id: s.dataset.id, dot: dot ? [...dot.classList].find(c => c.startsWith('agent-')) : null, active: s.classList.contains('active') };
        });
      }
    }
    return out;
  });
}

// tmux on the fixture's own socket only; without TMUX/TMUX_PANE it cannot reach a caller's server.
function fixtureTmux(socket, ...args) {
  const env = { ...process.env };
  delete env.TMUX;
  delete env.TMUX_PANE;
  const r = spawnSync('tmux', ['-S', socket, ...args], { encoding: 'utf8', env });
  assert.equal(r.status, 0, `tmux ${args.join(' ')}: ${r.stderr}`);
  return r.stdout.trim();
}

function processOf(pid) {
  const cmd = spawnSync('ps', ['-o', 'command=', '-p', String(pid)], { encoding: 'utf8' }).stdout.trim();
  const ppid = spawnSync('ps', ['-o', 'ppid=', '-p', String(pid)], { encoding: 'utf8' }).stdout.trim();
  const parent = ppid ? spawnSync('ps', ['-o', 'command=', '-p', ppid], { encoding: 'utf8' }).stdout.trim() : '';
  return { cmd, parent };
}

(async () => {
  let browser, server;
  const evidence = { status: 'running', app: APP, fixture: OUT, steps: [], cases: {}, pageErrors: [], httpErrors: [], runtimeCalls: [] };
  try {
    server = spawn(PYTHON, [path.join(ROOT, 'fixture_server.py'), APP, OUT], {
      stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, VEPOL_FIXTURE_ORCA: '1' },
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
    const orca = fixture.orca;
    const base = `http://127.0.0.1:${boot.port}`;
    const api = async (url, method = 'GET', data) => {
      const res = await fetch(base + url, { method, headers: { 'X-Vepol-Token': boot.token, 'Content-Type': 'application/json' }, body: data === undefined ? undefined : JSON.stringify(data) });
      assert(res.ok, `${method} ${url}: ${res.status} ${res.ok ? '' : await res.text()}`);
      return res.json();
    };
    await waitUntil(async () => { try { return (await api('/api/health')).ok; } catch { return false; } }, 'fixture health');
    const mtimesBefore = mtimes(orca.knowledge);

    // Two projects with sessions: alpha/claude started (the /bin/cat stand-in), beta/codex never started.
    const a1 = await api('/api/conversations', 'POST', { target: 'alpha', runtime: 'claude', transport: 'terminal' });
    await api(`/api/conversations/${a1.id}/terminal/start`, 'POST');
    const b1 = await api('/api/conversations', 'POST', { target: 'beta', runtime: 'codex', transport: 'terminal' });
    const listed = Object.fromEntries((await api('/api/conversations')).map(c => [c.id, c.agent]));
    assert.equal(listed[a1.id], 'alive');
    assert.equal(listed[b1.id], 'not_running');
    evidence.steps.push('Fixture: alpha/claude terminal started (stand-in), beta/codex terminal created, not started');

    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
    await context.addInitScript(token => { window.__VEPOL_TOKEN__ = token; }, boot.token);
    const page = await context.newPage();
    page.on('pageerror', e => evidence.pageErrors.push(e.message));
    page.on('response', r => { if (r.status() >= 400) evidence.httpErrors.push({ url: new URL(r.url()).pathname, status: r.status() }); });
    page.on('request', r => { const p = new URL(r.url()).pathname; if (r.method() === 'POST' && /\/(messages|retry|stop)$/.test(p)) evidence.runtimeCalls.push(p); });
    await page.goto(base);
    await page.locator('#board-view').waitFor({ state: 'visible' });
    await page.locator('[data-board-view="sessions"]').click();
    await waitUntil(async () => await page.locator('#board-view [data-conversation-id]').count() === 2, 'two cards');

    // O1. Tree: every project, newest activity first (beta's session is the newest, projects without
    // activity keep discovery order), sessions nested with the board's liveness dot; a session opens.
    await page.locator(`[data-open-conversation="${a1.id}"]`).click();
    await page.locator('#board-view').waitFor({ state: 'hidden' });
    const wantTree = [
      { slug: 'beta', active: false, sessions: [{ id: b1.id, dot: 'agent-not_running', active: false }] },
      { slug: 'alpha', active: true, sessions: [{ id: a1.id, dot: 'agent-alive', active: true }] },
      { slug: 'hub', active: false, sessions: [] },
      { slug: 'delta', active: false, sessions: [] },
      { slug: 'gamma', active: false, sessions: [] },
    ];
    await waitUntil(async () => JSON.stringify(await treeShape(page)) === JSON.stringify(wantTree), 'every project in the tree, sessions with dots')
      .catch(async (e) => { throw new Error(`${e.message}; tree: ${JSON.stringify(await treeShape(page))}`); });
    const node = async (slug) => (await treeShape(page)).find(p => p.slug === slug);
    await page.screenshot({ path: path.join(OUT, 'tree.png'), fullPage: true });
    const opened = page.waitForResponse(r => r.request().method() === 'GET' && new URL(r.url()).pathname === `/api/conversations/${b1.id}`);
    await page.locator(`#tree .tree-session[data-id="${b1.id}"]`).click();
    assert.equal((await (await opened).json()).id, b1.id);
    await waitUntil(async () => {
      const [a, b] = [await node('alpha'), await node('beta')];
      return b.sessions[0].active && !a.sessions[0].active && b.active;
    }, 'beta session selected in the tree');
    assert.equal((await api(`/api/conversations/${b1.id}`)).agent, 'not_running', 'opening never starts an agent');
    await page.locator('#tree .tree-project[data-slug="alpha"]').click();
    await waitUntil(async () => (await node('alpha')).active, 'alpha project selected');
    assert.equal(await page.locator('#routing').textContent(), '→ codex · alpha');
    // «+ New session» asks for the project; the agent choice carries over.
    const created = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/conversations');
    await page.locator('#newconv').click();
    await page.locator('#picker').waitFor({ state: 'visible' });
    assert.equal(await page.locator('#picker-runtimes [aria-pressed="true"]').textContent(), 'codex');
    await page.locator('#picker-list [data-pick="alpha"]').click();
    const c1 = await (await created).json();
    assert.equal(c1.target, 'alpha');
    assert.equal(c1.runtime, 'codex');
    assert.equal(c1.existing, false);
    await waitUntil(async () => (await node('alpha')).sessions.some(s => s.id === c1.id && s.active), 'new alpha session in the tree');
    evidence.cases.O1 = { tree: wantTree, newConversation: c1 };
    evidence.steps.push('O1 tree lists every project newest first and nests sessions with alive/not-running dots; a session row opens it; «+ New session» → picker → alpha');

    // O2. Knowledge panel: read-only tree of alpha's knowledge/, filter, exact file text, no escape, nothing written.
    await page.locator('[data-panel="knowledge"]').click();
    const kbPaths = () => page.locator('#kb-tree .kb-entry').evaluateAll(els => els.map(e => e.title));
    const kbEntries = ['decisions', 'decisions/a.md', 'huge.md', 'log.md'];
    // Folders start collapsed; a click expands one, a second click collapses it again.
    await waitUntil(async () => JSON.stringify(await kbPaths()) === JSON.stringify(['decisions', 'huge.md', 'log.md']), 'knowledge tree lists the top level with decisions/ collapsed');
    await page.locator('#kb-tree [data-kb-dir="decisions"]').click();
    await waitUntil(async () => JSON.stringify(await kbPaths()) === JSON.stringify(kbEntries), 'expanded decisions/ lists every fixture file');
    assert.equal(await page.locator('#kb-tree [data-kb-dir="decisions"]').getAttribute('aria-expanded'), 'true');
    await page.locator('#kb-tree [data-kb-dir="decisions"]').click();
    await waitUntil(async () => JSON.stringify(await kbPaths()) === JSON.stringify(['decisions', 'huge.md', 'log.md']), 'decisions/ collapses again');
    // The filter searches inside collapsed folders.
    await page.locator('#kb-filter').fill('a.md');
    assert.deepEqual(await kbPaths(), ['decisions/a.md']);
    await page.locator('#kb-tree [data-kb-path="decisions/a.md"]').click();
    // Markdown is rendered: the heading and paragraph of decisions/a.md are elements, no raw '#'.
    await waitUntil(async () => await page.locator('#kb-file-text h1').count() === 1, 'decisions/a.md rendered');
    assert.equal(await page.locator('#kb-file-text h1').textContent(), 'Decision A');
    assert.equal(await page.locator('#kb-file-text p').textContent(), 'Keep the knowledge panel read-only.');
    assert(!(await page.locator('#kb-file-text').textContent()).includes('#'), 'no raw markdown heading');
    await page.screenshot({ path: path.join(OUT, 'knowledge.png'), fullPage: true });
    const escape = await fetch(`${base}/api/knowledge/file?target=alpha&path=${encodeURIComponent('../../etc/hosts')}`, { headers: { 'X-Vepol-Token': boot.token } });
    assert.equal(escape.status, 404);
    assert.deepEqual(mtimes(orca.knowledge), mtimesBefore);
    // ORCA-06b: a file over the read limit is 413 and the panel says so in grey.
    await page.locator('#kb-filter').fill('');
    const huge = page.waitForResponse(r => new URL(r.url()).pathname === '/api/knowledge/file' && new URL(r.url()).searchParams.get('path') === 'huge.md');
    await page.locator('#kb-tree [data-kb-path="huge.md"]').click();
    assert.equal((await huge).status(), 413);
    await waitUntil(async () => await page.locator('#kb-file-text.hint').count() === 1 && await page.locator('#kb-file-text').textContent() === 'too large to show', 'huge.md too large to show');
    const hugeError = evidence.httpErrors.findIndex(e => e.url === '/api/knowledge/file' && e.status === 413);
    assert(hugeError >= 0, 'the 413 was recorded');
    evidence.httpErrors.splice(hugeError, 1);
    // ORCA-06f: a failed list poll in the chat view keeps the last tree and says "Could not refresh"; the next good list clears it.
    const treeBefore = await treeShape(page);
    await page.route('**/api/conversations', route => route.request().method() === 'GET' ? route.abort() : route.continue());
    await waitUntil(async () => await page.locator('#tree-error').isVisible(), 'tree "Could not refresh" notice', 6000);
    assert.equal(await page.locator('#tree-error').textContent(), 'Could not refresh');
    assert.deepEqual(await treeShape(page), treeBefore);
    await page.unroute('**/api/conversations');
    await waitUntil(async () => !(await page.locator('#tree-error').isVisible()), 'notice cleared by the next good list', 7000);
    assert.deepEqual(await treeShape(page), treeBefore);
    evidence.cases.O2 = { entries: kbEntries, filtered: ['decisions/a.md'], escapeStatus: escape.status, hugeStatus: 413, treeRefreshError: 'Could not refresh', mtimes: mtimesBefore };
    evidence.steps.push('O2 knowledge tree lists the fixture files, filter narrows to one, click shows it rendered (heading and paragraph); ../../etc/hosts is 404; huge.md is 413 "too large to show"; a failed list poll keeps the tree with "Could not refresh"; mtimes unchanged');

    // O3. Column "+": gamma has no terminal; "+" in Research asks for the project, then creates, starts and places it there.
    await page.locator('[data-board-view="sessions"]').click();
    await page.locator('#board-view').waitFor({ state: 'visible' });
    const countBefore = (await api('/api/conversations')).length;
    const createdG = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/conversations');
    await page.locator('#board-columns [data-new-in="research"]').click();
    await page.locator('#picker').waitFor({ state: 'visible' });
    await page.locator('#picker-list [data-pick="gamma"]').click();
    const g1 = await (await createdG).json();
    assert.equal(g1.target, 'gamma');
    assert.equal(g1.existing, false);
    await page.locator('#board-view').waitFor({ state: 'hidden' });
    let g1Detail;
    await waitUntil(async () => (g1Detail = await api(`/api/conversations/${g1.id}`)).agent === 'alive', 'gamma agent alive');
    assert.equal(g1Detail.board_stage, 'research');
    await waitUntil(async () => processOf(g1Detail.pid).cmd === '/bin/cat', `pid ${g1Detail.pid} is /bin/cat`, 5000);
    const proc = processOf(g1Detail.pid);
    assert.equal(proc.parent, '/bin/zsh -f', 'the agent runs inside the pane shell');
    assert.equal((await api('/api/conversations')).length, countBefore + 1);
    // TERM-09 (Orca-style): the agent exits → the shell holds the pane and works as a terminal; Start types the
    // agent in again; closing the terminal says so, and Start opens a new one.
    const gSession = `kb-gamma-${g1.runtime}`;
    const startOf = () => page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === `/api/conversations/${g1.id}/terminal/start`);
    const rows = async () => await page.locator('#terminal .xterm-rows').textContent();
    await waitUntil(async () => await page.locator('#agent-state').textContent() === `Agent running · PID ${g1Detail.pid}`, 'header shows the first PID');
    const panePid = fixtureTmux(boot.tmux_socket, 'display-message', '-p', '-t', gSession, '#{pane_pid}');
    fixtureTmux(boot.tmux_socket, 'send-keys', '-t', gSession, 'C-d');
    await waitUntil(async () => await page.locator('#agent-state').textContent() === 'Agent not running · shell open' && await page.locator('#terminal-start').isVisible(), 'shell open + Start', 8000);
    assert.equal((await api(`/api/conversations/${g1.id}`)).agent, 'shell', 'no auto-restart');
    await page.locator('#terminal').click();
    await page.keyboard.type('echo vepol-shell-$((20+22))');
    await page.keyboard.press('Enter');
    await waitUntil(async () => (await rows()).includes('vepol-shell-42'), 'the shell runs a command typed in the window', 5000);
    // The owner's 2026-09-28 path: another project is clicked while the session is on screen; Start still acts on it.
    await page.locator('#tree .tree-project[data-slug="delta"]').click();
    await waitUntil(async () => (await node('delta')).active, 'delta project selected');
    const restart = startOf();
    await page.locator('#terminal-start').click();
    assert((await restart).ok(), 'Start succeeded');
    let restarted;
    await waitUntil(async () => (restarted = await api(`/api/conversations/${g1.id}`)).agent === 'alive', 'gamma agent alive again');
    assert.notEqual(restarted.pid, g1Detail.pid);
    assert.equal(processOf(restarted.pid).cmd, '/bin/cat');
    assert.equal(fixtureTmux(boot.tmux_socket, 'display-message', '-p', '-t', gSession, '#{pane_pid}'), panePid, 'same shell, same terminal');
    await waitUntil(async () => await page.locator('#agent-state').textContent() === `Agent running · PID ${restarted.pid}` && !(await page.locator('#terminal-start').isVisible()), 'header shows the new PID');
    // Closing the terminal (the shell's session ends) is said in the pane; Start opens a new shell with the agent.
    await waitUntil(async () => fixtureTmux(boot.tmux_socket, 'list-clients', '-t', gSession) !== '', 'the reopened page is attached');
    fixtureTmux(boot.tmux_socket, 'kill-session', '-t', gSession);
    await waitUntil(async () => await page.locator('#agent-state').textContent() === 'Agent not running' && await page.locator('#terminal-start').isVisible(), 'Agent not running + Start', 3000);
    await waitUntil(async () => (await rows()).includes('The terminal has closed. Press Start above to open a new one.'), 'the terminal says it closed', 3000);
    const reopen = startOf();
    await page.locator('#terminal-start').click();
    assert((await reopen).ok(), 'Start reopened the terminal');
    let reopened;
    await waitUntil(async () => (reopened = await api(`/api/conversations/${g1.id}`)).agent === 'alive', 'a new terminal with the agent');
    assert.notEqual(fixtureTmux(boot.tmux_socket, 'display-message', '-p', '-t', gSession, '#{pane_pid}'), panePid, 'a new shell');
    evidence.cases.TERM09 = { session: gSession, panePid, firstPid: g1Detail.pid, restartedPid: restarted.pid, reopenedPid: reopened.pid };
    evidence.steps.push(`TERM-09 agent exit → "shell open", echo ran in the pane; Start in the same shell → PID ${restarted.pid} (was ${g1Detail.pid}); kill-session → "terminal has closed"; Start → new shell, PID ${reopened.pid}`);
    await page.locator('[data-board-view="sessions"]').click();
    await page.locator(`#board-columns [data-stage="research"] [data-conversation-id="${g1.id}"]`).waitFor();
    // "+" again for gamma/codex (from another column): the existing card opens, its stage stays, a note says so.
    const again = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/conversations');
    await page.locator('#board-columns [data-new-in="working"]').click();
    await page.locator('#picker').waitFor({ state: 'visible' });
    await page.locator('#picker-list [data-pick="gamma"]').click();
    const g2 = await (await again).json();
    assert.equal(g2.id, g1.id);
    assert.equal(g2.existing, true);
    await page.locator('#board-view').waitFor({ state: 'hidden' });
    const note = `A terminal for gamma · ${g1.runtime} already exists — opened it.`;
    await waitUntil(async () => await page.locator('#session-note').isVisible() && await page.locator('#session-note').textContent() === note, 'existing-terminal note');
    assert.equal((await api(`/api/conversations/${g1.id}`)).board_stage, 'research');
    assert.equal((await api('/api/conversations')).length, countBefore + 1);
    await page.screenshot({ path: path.join(OUT, 'column-plus-existing.png'), fullPage: true });
    await page.locator('[data-board-view="sessions"]').click();
    await page.locator(`#board-columns [data-stage="research"] [data-conversation-id="${g1.id}"]`).waitFor();
    evidence.cases.O3 = { conversation: g1.id, stage: 'research', pid: g1Detail.pid, command: proc.cmd, parent: proc.parent.split(' /usr/bin/env')[0], note };
    evidence.steps.push('O3 "+" in Research makes a gamma card in Research with a live /bin/cat under tmux; "+" again opens it, stage unchanged, note shown');

    // TABS. Every tabsOpened session is a tab; a tab switches the terminal, "×" selects the neighbour, sections keep
    // the tabs, reload restores them. A terminal session has no Send box.
    const tabIds = () => page.locator('#tabstrip .tab').evaluateAll(t => t.map(x => x.dataset.tab));
    const activeTab = () => page.locator('#tabstrip .tab[aria-selected="true"]').evaluateAll(t => t.map(x => x.dataset.tab));
    await page.locator(`[data-open-conversation="${a1.id}"]`).click();
    await page.locator('#board-view').waitFor({ state: 'hidden' });
    await page.locator('[data-board-view="sessions"]').click();
    await page.locator(`[data-open-conversation="${g1.id}"]`).click();
    await waitUntil(async () => (await activeTab())[0] === g1.id, 'gamma tab selected');
    const tabsOpened = await tabIds();
    assert(tabsOpened.includes(a1.id) && tabsOpened.includes(g1.id), JSON.stringify(tabsOpened));
    await page.locator(`#tabstrip .tab[data-tab="${a1.id}"]`).click();
    await waitUntil(async () => (await activeTab())[0] === a1.id && / · alpha · claude$/.test(await page.locator('#conversation-title').textContent()), 'alpha tab shows alpha');
    assert(await page.locator('#terminal').isVisible(), 'terminal shown');
    assert(await page.locator('#composer').isHidden(), 'no Send box under a terminal session');
    assert.equal(await page.locator('.nav [aria-selected="true"]').count(), 0, 'no section selected while a tab is');
    await page.reload();
    await waitUntil(async () => (await activeTab())[0] === a1.id && JSON.stringify(await tabIds()) === JSON.stringify(tabsOpened), 'tabs restored after reload');
    await page.locator('#board-view').waitFor({ state: 'hidden' });
    const ti = tabsOpened.indexOf(a1.id);
    const neighbour = tabsOpened[ti - 1] || tabsOpened[ti + 1];
    await page.locator(`#tabstrip [data-tab-close="${a1.id}"]`).click();
    await waitUntil(async () => (await activeTab())[0] === neighbour && !(await tabIds()).includes(a1.id), 'closing selects the neighbour');
    assert.equal((await api('/api/conversations')).find(c => c.id === a1.id).agent, 'alive', 'closing a tab stops nothing');
    await page.locator('[data-board-view="tasks"]').click();
    await page.locator('#tasks-pane').waitFor({ state: 'visible' });
    assert.deepEqual(await activeTab(), []);
    assert.deepEqual(await tabIds(), tabsOpened.filter(id => id !== a1.id));
    await page.screenshot({ path: path.join(OUT, 'tabs.png'), fullPage: true });
    await page.locator('[data-board-view="sessions"]').click();
    await page.locator('#board-view').waitFor({ state: 'visible' });
    evidence.cases.TABS = { tabsOpened, neighbour, afterClose: await tabIds() };
    evidence.steps.push('TABS sessions open as tabs; a tab switches the terminal (no Send box); reload restores tabs and the selected one; "×" selects the neighbour and leaves the agent alive; Tasks keeps the tabs');

    // O4. Status bar from the fixture files; with the Claude file malformed and the Codex rollout removed, "no data" for both.
    const usageText = async (key) => (await page.locator(`#usage-${key}`).textContent()) || '';
    await waitUntil(async () => (await usageText('codex')).startsWith('Codex 7d 14%') && (await usageText('claude')).startsWith('Claude 5h 12% · 7d 40%'), 'usage numbers');
    assert.match(await usageText('codex'), / · as of \d\d:\d\d$/);
    assert.match(await usageText('claude'), / · as of \d\d:\d\d$/);
    assert.equal(await page.locator('#usage-codex.stale').count(), 0);
    assert.equal(await page.locator('#usage-claude.stale').count(), 0);
    const withData = { claude: await usageText('claude'), codex: await usageText('codex') };
    await page.screenshot({ path: path.join(OUT, 'usage.png'), fullPage: true });
    // A just-started Codex session has no numbers yet: the bar keeps the newest file that has them.
    const freshRollout = path.join(path.dirname(orca.codex_rollout), 'rollout-fixture-new-session.jsonl');
    fs.writeFileSync(freshRollout, JSON.stringify({ timestamp: new Date().toISOString(), type: 'session_meta', payload: { id: 'fixture-new' } }) + '\n');
    await page.reload();
    await page.locator('#board-view').waitFor({ state: 'visible' });
    await waitUntil(async () => (await usageText('codex')).startsWith('Codex 7d 14%'), 'usage keeps the newest rollout with numbers');
    fs.unlinkSync(freshRollout);
    fs.unlinkSync(orca.codex_rollout);
    fs.writeFileSync(orca.claude_usage, '{not json');
    await page.reload();
    await page.locator('#board-view').waitFor({ state: 'visible' });
    await waitUntil(async () => await usageText('claude') === 'Claude — no data' && await usageText('codex') === 'Codex — no data', 'usage no data');
    evidence.cases.O4 = { withData, malformedOrRemoved: { claude: await usageText('claude'), codex: await usageText('codex') } };
    evidence.steps.push(`O4 status bar "${withData.claude} | ${withData.codex}"; Claude file "{not json" and Codex rollout removed: "no data" for both`);

    assert.deepEqual(mtimes(orca.knowledge), mtimesBefore);
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
