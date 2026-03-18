/* ============================================================
   CodenamesAgent — GitHub Pages app
   Fetches leaderboard.json and games.json from the main branch
   and renders leaderboard, ELO chart, H2H matrix, and game log.
   ============================================================ */

const REPO = 'donbowen/CodenamesAgent';
const RAW  = `https://raw.githubusercontent.com/${REPO}/main/game_logs`;
const LB_URL    = `${RAW}/leaderboard.json`;
const GAMES_URL = `${RAW}/games.json`;

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
      `<tr><td colspan="5" class="loading">⚠ Could not load data.</td></tr>`;
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
  // Sort by timestamp ascending
  const sorted = [...games].sort((a, b) => a.timestamp.localeCompare(b.timestamp));

  // Track current ELO per agent name
  const eloState = {};
  // Track data series: { agentName -> [elo after each game they played] }
  const series   = {};
  // Track x-axis labels per agent (game index within that agent's games)
  // We use a unified x-axis: cumulative game index for all games
  // Each agent gets a point only when they play; we'll use sparse data with null

  // First pass: collect all agent names
  const agentNames = [...new Set(sorted.flatMap(g => [g.red_name, g.blue_name]))].sort();
  agentNames.forEach(name => {
    eloState[name] = DEFAULT_ELO;
    series[name]   = [];
  });

  // Build data: for each game, record ELO snapshots for both participants
  // Use per-agent game count as x (cleaner than global index)
  const agentGameCount = {};
  agentNames.forEach(n => agentGameCount[n] = 0);

  // For Chart.js we'll use a single x-axis = game number (1-indexed) across ALL games
  // Each dataset will have nulls for games that agent didn't play
  const labels = sorted.map((_, i) => i + 1);

  // Initialize all series with nulls
  const chartData = {};
  agentNames.forEach(name => {
    chartData[name] = Array(sorted.length).fill(null);
  });

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
        legend: {
          position: 'bottom',
          labels: { boxWidth: 12, font: { size: 11 } }
        },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y !== null ? ctx.parsed.y.toFixed(1) : '—'}`
          }
        }
      },
      scales: {
        x: {
          title: { display: true, text: 'Game #', color: '#6b7280', font: { size: 11 } },
          ticks: { maxTicksLimit: 10, font: { size: 10 } }
        },
        y: {
          title: { display: true, text: 'ELO', color: '#6b7280', font: { size: 11 } },
          ticks: { font: { size: 10 } }
        }
      }
    }
  });
}

// ── Head-to-Head Matrix ───────────────────────────────────────
function renderH2HMatrix(games) {
  // Collect all agent names in leaderboard ELO order (use alphabetical as fallback)
  const names = [...new Set(games.flatMap(g => [g.red_name, g.blue_name]))].sort();

  // Build win/loss counts: h2h[rowName][colName] = { w, l }
  // Row = red team, Col = blue team
  const h2h = {};
  names.forEach(r => {
    h2h[r] = {};
    names.forEach(c => { h2h[r][c] = { w: 0, l: 0 }; });
  });

  games.forEach(g => {
    const red  = g.red_name;
    const blue = g.blue_name;
    if (g.winner_color === 'red') {
      h2h[red][blue].w++;
      h2h[blue][red].l++;  // blue's perspective when they played as red vs this blue
      // Actually: we track [red][blue] = red's record in this matchup
      // So red won: h2h[red][blue].w++; blue lost: this is h2h[blue][red] for reverse matchup? No.
      // Keep simple: cell[row][col] = row's record when row=red, col=blue
    } else {
      h2h[red][blue].l++;
    }
  });

  // Recompute cleanly
  names.forEach(r => names.forEach(c => { h2h[r][c] = { w: 0, l: 0 }; }));
  games.forEach(g => {
    const { red_name, blue_name, winner_color } = g;
    if (winner_color === 'red') {
      h2h[red_name][blue_name].w++;
    } else {
      h2h[red_name][blue_name].l++;
    }
  });

  // Build table HTML
  let html = '<table class="h2h-table"><thead><tr><th class="row-header">Red ╲ Blue</th>';
  names.forEach(c => { html += `<th>${c}</th>`; });
  html += '</tr></thead><tbody>';

  names.forEach(row => {
    html += `<tr><th class="row-header">${row}</th>`;
    names.forEach(col => {
      if (row === col) {
        html += '<td class="h2h-cell-empty">—</td>';
        return;
      }
      const { w, l } = h2h[row][col];
      const total = w + l;
      if (total === 0) {
        html += '<td class="h2h-cell-empty">–</td>';
        return;
      }
      const rate  = w / total;
      // Color: green-ish for high win rate, red-ish for low
      const alpha = Math.round(rate * 0.45 * 255).toString(16).padStart(2, '0');
      const r255  = Math.round((1 - rate) * 200);
      const g255  = Math.round(rate * 200);
      const bg    = `rgba(${r255},${g255},80,0.25)`;
      const cls   = rate >= 0.5 ? 'h2h-cell-win' : '';
      html += `<td class="${cls}" style="background:${bg}" title="${row} as Red vs ${col} as Blue">${w}–${l}</td>`;
    });
    html += '</tr>';
  });

  html += '</tbody></table>';
  document.getElementById('h2h-container').innerHTML = html;
}

// ── Game Log Table ────────────────────────────────────────────
let allGames     = [];
let sortCol      = 'timestamp';
let sortDir      = 'desc';
let filterStr    = '';

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

  document.querySelectorAll('#games-table th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      if (sortCol === col) {
        sortDir = sortDir === 'asc' ? 'desc' : 'asc';
      } else {
        sortCol = col;
        sortDir = col === 'timestamp' ? 'desc' : 'asc';
      }
      // Update header classes
      document.querySelectorAll('#games-table th.sortable').forEach(h => {
        h.classList.remove('sort-asc', 'sort-desc');
      });
      th.classList.add(sortDir === 'asc' ? 'sort-asc' : 'sort-desc');
      rebuildGameTable();
    });
  });

  // Set initial sort indicator
  const defaultTh = document.querySelector(`#games-table th[data-col="${sortCol}"]`);
  if (defaultTh) defaultTh.classList.add('sort-desc');
}

function rebuildGameTable() {
  let rows = allGames.filter(g => {
    if (!filterStr) return true;
    return g.red_name.toLowerCase().includes(filterStr) ||
           g.blue_name.toLowerCase().includes(filterStr) ||
           g.winner_name.toLowerCase().includes(filterStr);
  });

  rows.sort((a, b) => {
    let va = a[sortCol], vb = b[sortCol];
    if (sortCol === 'total_turns') { va = +va; vb = +vb; }
    if (va < vb) return sortDir === 'asc' ? -1 : 1;
    if (va > vb) return sortDir === 'asc' ? 1  : -1;
    return 0;
  });

  const tbody = document.getElementById('games-body');
  if (rows.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="loading">No matching games.</td></tr>';
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
    </tr>`;
  }).join('');

  const total = allGames.length;
  const shown = rows.length;
  document.getElementById('games-count').textContent =
    shown === total ? `${total} games` : `${shown} of ${total} games`;
}
