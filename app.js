/* ============================================================
   CodenamesAgent — GitHub Pages app
   Fetches leaderboard.json and games.json from the main branch
   and renders leaderboard, ELO chart, H2H matrix, game log,
   and interactive game reviewer.
   ============================================================ */

const REPO       = 'donbowen/CodenamesAgent';
const RAW        = `https://raw.githubusercontent.com/${REPO}/main/game_logs`;
const LB_URL     = `${RAW}/leaderboard.json`;
const GAMES_URL  = `${RAW}/games.json`;
const PROMPT_URL = (id) => `${RAW}/full_records/${id}_prompts.txt`;

// ELO constants (must match codenames/elo.py)
const DEFAULT_ELO = 1000;
const K_FACTOR    = 32;

// ── Model color palette for chart lines ──────────────────────
const PALETTE = [
  '#2471a3', '#c0392b', '#27ae60', '#8e44ad',
  '#e67e22', '#16a085', '#d35400', '#7f8c8d', '#2c3e50'
];

// ── Helpers ───────────────────────────────────────────────────
function expectedScore(ratingA, ratingB) {
  return 1 / (1 + Math.pow(10, (ratingB - ratingA) / 400));
}

function updatedElo(rating, score, expected) {
  return rating + K_FACTOR * (score - expected);
}

function fmtDate(isoStr) {
  const d = new Date(isoStr);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function winPct(wins, games) {
  if (!games) return '—';
  return (wins / games * 100).toFixed(1) + '%';
}

// ── Main entry point ──────────────────────────────────────────
(async function init() {
  try {
    const [lbRes, gamesRes] = await Promise.all([
      fetch(LB_URL),
      fetch(GAMES_URL)
    ]);
    if (!lbRes.ok || !gamesRes.ok) throw new Error('Failed to fetch data.');
    const leaderboard = await lbRes.json();
    const games       = await gamesRes.json();

    renderLeaderboard(leaderboard);
    renderEloChart(games);
    renderH2HMatrix(games);
    renderGameTable(games);
  } catch (err) {
    const msg = `<tr><td colspan="8" class="loading">⚠ Could not load data: ${err.message}</td></tr>`;
    document.getElementById('lb-body').innerHTML = msg;
    document.getElementById('h2h-container').innerHTML =
      `<p class="loading">⚠ Could not load data.</p>`;
    document.getElementById('games-body').innerHTML =
      `<tr><td colspan="6" class="loading">⚠ Could not load data.</td></tr>`;
  }
})();

// ── Leaderboard ───────────────────────────────────────────────
function renderLeaderboard(data) {
  const sorted = [...data].sort((a, b) => b.elo - a.elo);
  const tbody = document.getElementById('lb-body');
  tbody.innerHTML = sorted.map((t, i) => {
    const rank = i + 1;
    const rankClass = rank <= 3 ? ` class="rank-${rank}"` : '';
    return `<tr${rankClass}>
      <td>${rank}</td>
      <td>${t.name}</td>
      <td><code>${t.model}</code></td>
      <td class="elo-val">${t.elo.toFixed(1)}</td>
      <td>${t.wins}</td>
      <td>${t.losses}</td>
      <td>${t.games}</td>
      <td class="win-pct">${winPct(t.wins, t.games)}</td>
    </tr>`;
  }).join('');
}

// ── ELO Over Time chart ───────────────────────────────────────
function renderEloChart(games) {
  const sorted = [...games].sort((a, b) => a.timestamp.localeCompare(b.timestamp));

  const agentNames = [...new Set(sorted.flatMap(g => [g.red_name, g.blue_name]))].sort();
  const eloState   = {};
  agentNames.forEach(name => { eloState[name] = DEFAULT_ELO; });

  const labels    = sorted.map((_, i) => i + 1);
  const chartData = {};
  agentNames.forEach(name => { chartData[name] = Array(sorted.length).fill(null); });

  sorted.forEach((game, i) => {
    const w = game.winner_name;
    const l = game.winner_color === 'red' ? game.blue_name : game.red_name;

    const wElo = eloState[w] ?? DEFAULT_ELO;
    const lElo = eloState[l] ?? DEFAULT_ELO;
    const expW = expectedScore(wElo, lElo);
    const expL = expectedScore(lElo, wElo);

    eloState[w] = updatedElo(wElo, 1, expW);
    eloState[l] = updatedElo(lElo, 0, expL);

    chartData[w][i] = Math.round(eloState[w] * 10) / 10;
    chartData[l][i] = Math.round(eloState[l] * 10) / 10;
  });

  const datasets = agentNames.map((name, idx) => ({
    label: name,
    data: chartData[name],
    borderColor: PALETTE[idx % PALETTE.length],
    backgroundColor: PALETTE[idx % PALETTE.length] + '22',
    borderWidth: 2,
    pointRadius: 0,
    pointHoverRadius: 4,
    tension: 0.3,
    spanGaps: true,
  }));

  const ctx = document.getElementById('elo-chart').getContext('2d');
  new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y !== null ? ctx.parsed.y.toFixed(1) : '—'}`
          }
        }
      },
      scales: {
        x: { title: { display: true, text: 'Game #', color: '#6b7280', font: { size: 11 } }, ticks: { maxTicksLimit: 10, font: { size: 10 } } },
        y: { title: { display: true, text: 'ELO',    color: '#6b7280', font: { size: 11 } }, ticks: { font: { size: 10 } } }
      }
    }
  });
}

// ── Head-to-Head Matrix ───────────────────────────────────────
function renderH2HMatrix(games) {
  const names = [...new Set(games.flatMap(g => [g.red_name, g.blue_name]))].sort();
  const h2h   = {};
  names.forEach(r => { h2h[r] = {}; names.forEach(c => { h2h[r][c] = { w: 0, l: 0 }; }); });

  games.forEach(({ red_name, blue_name, winner_color }) => {
    if (winner_color === 'red') { h2h[red_name][blue_name].w++; }
    else                        { h2h[red_name][blue_name].l++; }
  });

  let html = '<table class="h2h-table"><thead><tr><th class="row-header">Red ╲ Blue</th>';
  names.forEach(c => { html += `<th>${c}</th>`; });
  html += '</tr></thead><tbody>';

  names.forEach(row => {
    html += `<tr><th class="row-header">${row}</th>`;
    names.forEach(col => {
      if (row === col) { html += '<td class="h2h-cell-empty">—</td>'; return; }
      const { w, l } = h2h[row][col];
      const total    = w + l;
      if (total === 0) { html += '<td class="h2h-cell-empty">–</td>'; return; }
      const rate = w / total;
      const r255 = Math.round((1 - rate) * 200);
      const g255 = Math.round(rate * 200);
      const bg   = `rgba(${r255},${g255},80,0.25)`;
      const cls  = rate >= 0.5 ? 'h2h-cell-win' : '';
      html += `<td class="${cls}" style="background:${bg}" title="${row} as Red vs ${col} as Blue">${w}–${l}</td>`;
    });
    html += '</tr>';
  });

  html += '</tbody></table>';
  document.getElementById('h2h-container').innerHTML = html;
}

// ── Game Log Table ────────────────────────────────────────────
let allGames   = [];
let sortCol    = 'timestamp';
let sortDir    = 'desc';
let filterStr  = '';
let filterStr2 = '';

function renderGameTable(games) {
  allGames = games;
  attachGameTableEvents();
  rebuildGameTable();
}

function attachGameTableEvents() {
  document.getElementById('games-filter').addEventListener('input', e => {
    filterStr = e.target.value.trim().toLowerCase();
    rebuildGameTable();
  });

  document.getElementById('games-filter2').addEventListener('input', e => {
    filterStr2 = e.target.value.trim().toLowerCase();
    rebuildGameTable();
  });

  document.querySelectorAll('#games-table th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      if (sortCol === col) { sortDir = sortDir === 'asc' ? 'desc' : 'asc'; }
      else { sortCol = col; sortDir = col === 'timestamp' ? 'desc' : 'asc'; }
      document.querySelectorAll('#games-table th.sortable').forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
      th.classList.add(sortDir === 'asc' ? 'sort-asc' : 'sort-desc');
      rebuildGameTable();
    });
  });

  const defaultTh = document.querySelector(`#games-table th[data-col="${sortCol}"]`);
  if (defaultTh) defaultTh.classList.add('sort-desc');
}

function rebuildGameTable() {
  const matchesFilter = (g, f) =>
    g.red_name.toLowerCase().includes(f) ||
    g.blue_name.toLowerCase().includes(f) ||
    g.winner_name.toLowerCase().includes(f);

  let rows = allGames.filter(g => {
    if (filterStr  && !matchesFilter(g, filterStr))  return false;
    if (filterStr2 && !matchesFilter(g, filterStr2)) return false;
    return true;
  });

  rows.sort((a, b) => {
    let va = a[sortCol], vb = b[sortCol];
    if (sortCol === 'total_turns') { va = +va; vb = +vb; }
    if (va < vb) return sortDir === 'asc' ? -1 : 1;
    if (va > vb) return sortDir === 'asc' ?  1 : -1;
    return 0;
  });

  const tbody = document.getElementById('games-body');
  if (rows.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="loading">No matching games.</td></tr>';
    document.getElementById('games-count').textContent = '0 games';
    return;
  }

  tbody.innerHTML = rows.map(g => {
    const winClass = g.winner_color === 'red' ? 'winner-red' : 'winner-blue';
    return `<tr>
      <td>${fmtDate(g.timestamp)}</td>
      <td class="winner-red" style="opacity:0.85">${g.red_name}</td>
      <td class="winner-blue" style="opacity:0.85">${g.blue_name}</td>
      <td class="${winClass}">${g.winner_name}</td>
      <td>${g.total_turns}</td>
      <td><button class="btn-review" data-id="${g.game_id}" data-red="${g.red_name}" data-blue="${g.blue_name}" data-winner-color="${g.winner_color}" data-date="${g.timestamp}">&#9654; Review</button></td>
    </tr>`;
  }).join('');

  // Wire up Review buttons
  tbody.querySelectorAll('.btn-review').forEach(btn => {
    btn.addEventListener('click', () => {
      loadReviewer({
        game_id:      btn.dataset.id,
        red_name:     btn.dataset.red,
        blue_name:    btn.dataset.blue,
        winner_color: btn.dataset.winnerColor,
        timestamp:    btn.dataset.date,
      });
    });
  });

  const total = allGames.length;
  const shown = rows.length;
  document.getElementById('games-count').textContent =
    shown === total ? `${total} games` : `${shown} of ${total} games`;
}

// ═══════════════════════════════════════════════════════════════
// GAME REVIEWER
// ═══════════════════════════════════════════════════════════════

let reviewSteps   = [];
let reviewStepIdx = 0;
let reasoningVisible = false;

// ── Load a game into the reviewer ─────────────────────────────
async function loadReviewer(game) {
  const content = document.getElementById('reviewer-content');
  const placeholder = document.getElementById('reviewer-placeholder');

  // Show loading state
  placeholder.hidden = true;
  content.hidden = false;
  document.getElementById('reviewer-header').innerHTML =
    `<strong>${game.red_name}</strong> <span style="color:var(--red)">(Red)</span>
     vs <strong>${game.blue_name}</strong> <span style="color:var(--blue)">(Blue)</span>
     &nbsp;·&nbsp; ${fmtDate(game.timestamp)}
     &nbsp;&nbsp;<span style="color:var(--muted);font-size:0.85em">Loading…</span>`;

  document.getElementById('reviewer').scrollIntoView({ behavior: 'smooth' });

  try {
    const res = await fetch(PROMPT_URL(game.game_id));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const text = await res.text();

    const { board, turns } = parsePromptFile(text);
    reviewSteps   = buildSteps(board, turns, game.winner_color);
    reviewStepIdx = 0;
    reasoningVisible = false;

    // Rebuild header without "Loading…"
    document.getElementById('reviewer-header').innerHTML =
      `<strong>${game.red_name}</strong> <span style="color:var(--red)">(Red)</span>
       vs <strong>${game.blue_name}</strong> <span style="color:var(--blue)">(Blue)</span>
       &nbsp;·&nbsp; ${fmtDate(game.timestamp)}`;

    buildBoardDOM(board);
    attachReviewerControls();
    renderStep();
  } catch (err) {
    document.getElementById('reviewer-header').innerHTML =
      `⚠ Could not load game log: ${err.message}`;
  }
}

// ── Parse the prompt file ─────────────────────────────────────
function parsePromptFile(text) {
  const lines = text.split('\n');

  // 1. Board: find "Board (all colors visible to you):" and parse next 25 non-blank lines
  const board = {};   // { word: "RED"|"BLUE"|"NEUTRAL"|"ASSASSIN" }
  const boardWords = []; // ordered list for grid layout
  const boardMarker = 'Board (all colors visible to you):';
  let boardIdx = lines.findIndex(l => l.includes(boardMarker));
  if (boardIdx !== -1) {
    let count = 0;
    for (let i = boardIdx + 1; i < lines.length && count < 25; i++) {
      const m = lines[i].match(/^\s+(\S[\S ]*\S|\S)\s+(RED|BLUE|NEUTRAL|ASSASSIN)/);
      if (m) {
        const word  = m[1].trim();
        const color = m[2];
        board[word.toUpperCase()] = color;
        boardWords.push(word.toUpperCase());
        count++;
      }
    }
  }

  // 2. Game history: find the LAST "Game history:" block
  let lastHistoryIdx = -1;
  for (let i = lines.length - 1; i >= 0; i--) {
    if (lines[i].trim() === 'Game history:') { lastHistoryIdx = i; break; }
  }

  const turns = [];
  if (lastHistoryIdx !== -1) {
    let curTurnKey = null;
    for (let i = lastHistoryIdx + 1; i < lines.length; i++) {
      const line = lines[i];
      // Stop at blank line not followed by another history entry, or non-matching content
      const m = line.match(/^\s+\[(RED|BLUE)\] (\S+) (\d+)\s+#\d+: (\S+)(?: → (\w+))?/);
      if (!m) {
        // Stop if we hit a non-indented non-blank line (end of history block)
        if (line.trim() && !line.startsWith('  ')) break;
        continue;
      }
      const [, team, clue, numStr, guessWord, outcome] = m;
      const turnKey = `${team}|${clue}|${numStr}`;

      if (turnKey !== curTurnKey) {
        turns.push({ team, clue, number: parseInt(numStr), guesses: [] });
        curTurnKey = turnKey;
      }

      if (guessWord === 'PASS') {
        turns[turns.length - 1].guesses.push({ word: 'PASS', outcome: null });
      } else {
        turns[turns.length - 1].guesses.push({ word: guessWord.toUpperCase(), outcome: outcome ? outcome.toLowerCase() : null });
      }
    }
  }

  // 3. Reasoning: split by "PROMPT  model=" blocks, take last JSON per block
  const blocks = text.split(/PROMPT\s+model=/);
  const clueReasonings  = [];
  const guessReasonings = [];
  let lastGuessObj = null; // tracks the very last guesser response in the file

  for (const block of blocks) {
    // Find all lines that look like a top-level JSON object
    const jsonLines = block.split('\n').filter(l => /^\{.*\}$/.test(l.trim()));
    if (jsonLines.length === 0) continue;
    // Take the last one (handles retries)
    const raw = jsonLines[jsonLines.length - 1].trim();
    try {
      const obj = JSON.parse(raw);
      if ('clue'  in obj && 'reasoning' in obj) clueReasonings.push(obj.reasoning);
      if ('guess' in obj && 'reasoning' in obj) {
        guessReasonings.push(obj.reasoning);
        lastGuessObj = obj;
      }
    } catch (_) { /* skip malformed */ }
  }

  // Attach reasoning to turns / guesses
  let ci = 0, gi = 0;
  for (const turn of turns) {
    turn.spymasterReasoning = clueReasonings[ci++] || null;
    for (const guess of turn.guesses) {
      guess.reasoning = guessReasonings[gi++] || null;
    }
  }

  // The game-ending guess never appears in any "Game history:" block because
  // no further prompt is generated after the game ends. Detect it by checking
  // whether one guesser reasoning remains unassigned, then append the missing guess.
  if (gi < guessReasonings.length && lastGuessObj && turns.length > 0) {
    const word    = lastGuessObj.guess.toUpperCase();
    const outcome = (board[word] || 'neutral').toLowerCase();
    turns[turns.length - 1].guesses.push({
      word,
      outcome,
      reasoning: guessReasonings[gi],
    });
  }

  return { board, boardWords, turns };
}

// ── Build flat steps array ────────────────────────────────────
function buildSteps(board, turns, winnerColor) {
  const steps = [];
  const revealed = {}; // word -> color string (lower case for CSS class)

  steps.push({ type: 'start', revealed: {} });

  for (const turn of turns) {
    // Clue step
    steps.push({
      type: 'clue',
      team: turn.team,
      clue: turn.clue,
      number: turn.number,
      spymasterReasoning: turn.spymasterReasoning,
      revealed: { ...revealed },
    });

    let guessNum = 0;
    for (const guess of turn.guesses) {
      guessNum++;
      if (guess.word === 'PASS') {
        steps.push({
          type: 'pass',
          team: turn.team,
          clue: turn.clue,
          number: turn.number,
          guessNum,
          revealed: { ...revealed },
        });
      } else {
        // Flip the card
        const color = board[guess.word] || guess.outcome || 'neutral';
        revealed[guess.word] = color.toLowerCase();
        steps.push({
          type: 'guess',
          team: turn.team,
          clue: turn.clue,
          number: turn.number,
          guessNum,
          guess: guess.word,
          outcome: guess.outcome,
          guesserReasoning: guess.reasoning || null,
          revealed: { ...revealed },
        });
      }
    }
  }

  // Determine end reason
  const lastGuessStep = [...steps].reverse().find(s => s.type === 'guess');
  const assassinWord  = lastGuessStep && lastGuessStep.outcome === 'assassin'
    ? lastGuessStep.guess : null;

  steps.push({
    type: 'end',
    winnerColor,
    reason: assassinWord ? 'assassin' : 'normal',
    assassinWord,
    revealed: { ...revealed },
  });

  return steps;
}

// ── Build board DOM (once per game load) ─────────────────────
function buildBoardDOM(board) {
  const wrap = document.getElementById('board-wrap');
  // Collect words in order (from board object — insertion order)
  const words = Object.keys(board);
  wrap.innerHTML = words.map(word => {
    const color = board[word].toLowerCase().replace('assassin', 'assassin');
    return `<div class="card" data-word="${word}" data-color="${color}">
      <div class="card-inner">
        <div class="card-back">${word}</div>
        <div class="card-front color-${color}">${word}</div>
      </div>
    </div>`;
  }).join('');
}

// ── Attach keyboard + button controls ────────────────────────
function attachReviewerControls() {
  document.getElementById('prev-btn').onclick = () => stepTo(reviewStepIdx - 1);
  document.getElementById('next-btn').onclick = () => stepTo(reviewStepIdx + 1);

  // Keyboard arrows (only when reviewer is visible)
  document.onkeydown = (e) => {
    if (document.getElementById('reviewer-content').hidden) return;
    if (e.key === 'ArrowRight') stepTo(reviewStepIdx + 1);
    if (e.key === 'ArrowLeft')  stepTo(reviewStepIdx - 1);
  };

  const toggle = document.getElementById('reasoning-toggle');
  const panel  = document.getElementById('reasoning-panel');
  toggle.onclick = () => {
    reasoningVisible = !reasoningVisible;
    panel.hidden = !reasoningVisible;
    toggle.textContent = reasoningVisible ? 'Hide reasoning ▲' : 'Show reasoning ▾';
    if (reasoningVisible) updateReasoningText();
  };
}

// ── Navigate to a step ────────────────────────────────────────
function stepTo(idx) {
  if (idx < 0 || idx >= reviewSteps.length) return;
  reviewStepIdx = idx;
  renderStep();
}

// ── Render current step ───────────────────────────────────────
function renderStep() {
  const step    = reviewSteps[reviewStepIdx];
  const isFirst = reviewStepIdx === 0;
  const isLast  = reviewStepIdx === reviewSteps.length - 1;

  document.getElementById('prev-btn').disabled = isFirst;
  document.getElementById('next-btn').disabled = isLast;

  // Update board card flip states
  const cards = document.querySelectorAll('#board-wrap .card');
  cards.forEach(card => {
    const word  = card.dataset.word;
    const color = card.dataset.color; // e.g. "red", "blue", "neutral", "assassin"

    if (step.revealed[word]) {
      card.classList.add('revealed');
    } else {
      card.classList.remove('revealed');
    }

    // Subtle color hint on unrevealed cards at game end
    card.classList.remove('hint-red', 'hint-blue', 'hint-neutral', 'hint-assassin');
    if (step.type === 'end' && !step.revealed[word]) {
      card.classList.add(`hint-${color}`);
    }

    // Assassin hit highlight on end step
    const front = card.querySelector('.card-front');
    front.classList.remove('assassin-hit');
    if (step.type === 'end' && step.assassinWord === word) {
      front.classList.add('assassin-hit');
    }
  });

  // Board active-team styling
  const boardWrap = document.getElementById('board-wrap');
  boardWrap.classList.remove('team-red', 'team-blue', 'end-red', 'end-blue');
  if (step.type === 'end') {
    boardWrap.classList.add(`end-${step.winnerColor}`);
  } else if (step.type !== 'start') {
    boardWrap.classList.add(`team-${step.team.toLowerCase()}`);
  }

  // Clue bar
  const clueBadge    = document.getElementById('clue-team-badge');
  const clueWord     = document.getElementById('clue-word');
  const clueNum      = document.getElementById('clue-number');
  const guessDisplay = document.getElementById('guess-display');
  const turnInd      = document.getElementById('turn-indicator');

  if (step.type === 'start') {
    clueBadge.innerHTML    = '';
    clueWord.textContent   = '';
    clueNum.textContent    = '';
    guessDisplay.innerHTML = '';
    turnInd.textContent    = 'Press → to begin';
  } else if (step.type === 'end') {
    clueBadge.innerHTML    = '';
    clueWord.textContent   = '';
    clueNum.textContent    = '';
    guessDisplay.innerHTML = '';
    turnInd.textContent    = '';
  } else {
    const teamLower = step.team.toLowerCase();
    clueBadge.innerHTML = `<span class="clue-team-badge ${teamLower}">${step.team}</span>`;
    clueWord.textContent = step.clue;
    clueNum.textContent  = `(${step.number})`;

    if (step.type === 'guess' || step.type === 'pass') {
      const word = step.type === 'pass' ? 'PASS' : step.guess;
      guessDisplay.innerHTML =
        `Field Agent ${step.guessNum}/${step.number + 1} Choice: <strong>${word}</strong>`;
    } else {
      guessDisplay.innerHTML = '';
    }

    const clueSteps     = reviewSteps.filter(s => s.type === 'clue');
    const clueStepsCurr = reviewSteps.slice(0, reviewStepIdx + 1).filter(s => s.type === 'clue');
    turnInd.textContent = `Turn ${clueStepsCurr.length} of ${clueSteps.length}`;
  }

  document.getElementById('pass-banner').hidden = true;

  // End banner
  const endBanner = document.getElementById('end-banner');
  if (step.type === 'end') {
    endBanner.hidden = false;
    endBanner.className = `end-${step.winnerColor}`;
    const winTeam = step.winnerColor === 'red' ? 'Red' : 'Blue';
    const loseTeam = step.winnerColor === 'red' ? 'Blue' : 'Red';
    if (step.reason === 'assassin') {
      endBanner.innerHTML = `💀 ${loseTeam} team hit the assassin — <strong>${winTeam} team wins!</strong>`;
    } else {
      endBanner.innerHTML = `🏆 <strong>${winTeam} team wins!</strong>`;
    }
  } else {
    endBanner.hidden = true;
  }

  // Reasoning panel
  if (reasoningVisible) updateReasoningText();
}

// ── Update reasoning text for current step ────────────────────
function updateReasoningText() {
  const step = reviewSteps[reviewStepIdx];
  const el   = document.getElementById('reasoning-text');

  if (step.type === 'clue' && step.spymasterReasoning) {
    el.innerHTML = `<strong>Spymaster reasoning:</strong><br>${escHtml(step.spymasterReasoning)}`;
  } else if (step.type === 'guess' && step.guesserReasoning) {
    el.innerHTML = `<strong>Guesser reasoning for "${step.guess}":</strong><br>${escHtml(step.guesserReasoning)}`;
  } else if (step.type === 'start' || step.type === 'end') {
    el.innerHTML = `<em style="color:var(--muted)">No reasoning at this step.</em>`;
  } else {
    el.innerHTML = `<em style="color:var(--muted)">No reasoning recorded for this step.</em>`;
  }
}

function escHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
