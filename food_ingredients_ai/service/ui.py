"""Demo web UI: single-page app served at ``GET /``.

Plain HTML+JS, no build step. This page is the Playwright UI-test target
(stable element ids: #scenario-select, #token-input, #run-button,
#results, #status) and the primary demo surface.
"""

from __future__ import annotations

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Clean-Label Reformulation Demo</title>
<style>
  body { font-family: system-ui, -apple-system, sans-serif; max-width: 960px;
         margin: 0 auto; padding: 24px; color: #1a1a1a; }
  .banner { background: #fff8e1; border: 1px solid #f0d060; padding: 12px;
            border-radius: 8px; font-size: 0.9em; margin-bottom: 20px; }
  .card { border: 1px solid #ddd; border-radius: 8px; padding: 16px;
          margin: 12px 0; }
  label { display: block; margin: 8px 0 4px; font-weight: 600; }
  select, input[type=text], input[type=password] { width: 100%; padding: 8px;
          border: 1px solid #bbb; border-radius: 6px; box-sizing: border-box; }
  button { background: #0b5fff; color: #fff; border: 0; border-radius: 6px;
           padding: 10px 20px; font-size: 1em; cursor: pointer; margin-top: 12px; }
  button:disabled { background: #999; cursor: wait; }
  #status { margin-top: 12px; font-style: italic; }
  .flag { color: #b00020; } .ok { color: #0a7a2f; }
  pre { background: #f6f6f6; padding: 12px; border-radius: 6px;
        overflow-x: auto; font-size: 0.85em; }
  table { border-collapse: collapse; width: 100%; margin-top: 8px; }
  th, td { border: 1px solid #ddd; padding: 6px 10px; text-align: left;
           font-size: 0.9em; }
  th { background: #f0f0f0; }
  .hint { font-size: 0.85em; color: #555; }
  code { background: #f0f0f0; padding: 2px 6px; border-radius: 4px; }
</style>
</head>
<body>
<h1>Clean-Label Reformulation Demo</h1>
<div class="banner">
  <strong>Independent portfolio demo.</strong> All ingredients, formulas and
  numbers are <em>synthetic and fictional</em>. Not affiliated with any real company.
  Agents run on Microsoft Agent Framework 1.0 (offline, deterministic).
</div>

<div class="card">
  <label for="scenario-select">Scenario</label>
  <select id="scenario-select"></select>

  <label for="token-input">Bearer <redacted> (demo auth)</label>
  <input type="password" id="token-input" placeholder="paste demo token here">
  <div class="hint">Mint one with:
    <code>python -m food_ingredients_ai.service.mint_token --scopes formulation:write,supply:read,esg:read,proposal:read</code>
  </div>

  <button id="run-button">Run reformulation</button>
  <div id="status" role="status"></div>
</div>

<div id="results"></div>
<div id="analytics"></div>

<script>
const $ = (id) => document.getElementById(id);

async function loadScenarios() {
  const res = await fetch('/api/scenarios');
  const data = await res.json();
  const sel = $('scenario-select');
  data.scenarios.forEach((s) => {
    const opt = document.createElement('option');
    opt.value = s.id; opt.textContent = s.id + ' — ' + s.formula_id;
    sel.appendChild(opt);
  });
}

function esc(s) {
  return String(s).replace(/[&<>"'`]/g, (c) =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;','`':'&#96;'}[c]));
}

function renderResults(bb) {
  const el = $('results');
  let html = '<div class="card"><h2>Results</h2>';

  const analysis = bb.analyze_ingredients || {};
  html += '<h3>1. Flagged ingredients (' + (analysis.flagged_count || 0) + ')</h3><ul>';
  (analysis.flagged || []).forEach((f) => {
    html += '<li class="flag">' + esc(f.name) + ' (' + f.pct + '%): ' +
            esc((f.reasons || []).join('; ')) + '</li>';
  });
  html += '</ul>';

  const subs = bb.suggest_substitutes || {};
  html += '<h3>2. Substitutions</h3><table><tr><th>Old</th><th>New / action</th><th>Reason</th></tr>';
  (subs.substitutions || []).forEach((s) => {
    html += '<tr><td>' + esc(s.old_name) + '</td><td>' +
            esc(s.action === 'remove' ? 'REMOVED' : s.new_name) + '</td><td>' +
            esc(s.reason) + '</td></tr>';
  });
  html += '</table>';

  const pred = (bb.predict_texture_shelf_life || {}).prediction || {};
  html += '<h3>3. Texture &amp; shelf-life</h3><p>Texture match: <strong>' +
          pred.texture_match_pct + '%</strong> · Shelf-life: <strong>' +
          pred.shelf_life_days + ' days</strong></p>';
  if ((pred.risk_flags || []).length) {
    html += '<ul>' + pred.risk_flags.map((r) => '<li class="flag">' + esc(r) + '</li>').join('') + '</ul>';
  }

  const claims = (bb.validate_claims || {}).claims || [];
  html += '<h3>4. Claim validation</h3><ul>';
  claims.forEach((c) => {
    html += '<li class="' + (c.valid ? 'ok' : 'flag') + '">[' +
            (c.valid ? 'VALID' : 'INVALID') + '] ' + esc(c.claim) + '</li>';
  });
  html += '</ul>';

  const pricing = (bb.estimate_pricing || {}).pricing || {};
  html += '<h3>5. Pricing</h3><p>Cost $' + pricing.cost_per_kg_usd + '/kg · Band $' +
          pricing.price_low_usd + '–$' + pricing.price_high_usd + '/kg</p>';

  html += '<h3>Raw blackboard</h3><pre id="raw-json">' +
          esc(JSON.stringify(bb, null, 2)) + '</pre></div>';
  el.innerHTML = html;
}

function barChart(rows, unit) {
  // rows: [{label, value, color}]; dependency-free SVG horizontal bars.
  const max = Math.max.apply(null, rows.map((r) => r.value).concat([1]));
  const W = 420, BH = 26, gap = 8;
  const H = rows.length * (BH + gap) + 30;
  let svg = '<svg width="' + W + '" height="' + H + '" role="img" aria-label="bar chart">';
  rows.forEach((r, i) => {
    const y = 24 + i * (BH + gap);
    const w = Math.max(2, (r.value / max) * (W - 190));
    svg += '<text x="0" y="' + (y + 17) + '" font-size="12">' + esc(r.label) + '</text>';
    svg += '<rect x="150" y="' + y + '" width="' + w + '" height="' + BH +
           '" fill="' + r.color + '" rx="4"/>';
    svg += '<text x="' + (160 + w) + '" y="' + (y + 17) + '" font-size="12">' +
           r.value + (unit ? ' ' + esc(unit) : '') + '</text>';
  });
  return svg + '</svg>';
}

function donut(pct, label) {
  // pct 0-100; dependency-free SVG ring.
  const c = Math.max(0, Math.min(100, pct));
  const R = 54, CIRC = 2 * Math.PI * R;
  const color = c >= 80 ? '#0a7a2f' : (c >= 50 ? '#d9930d' : '#b00020');
  return '<svg width="140" height="140" role="img" aria-label="' + esc(label) + '">' +
    '<circle cx="70" cy="70" r="' + R + '" fill="none" stroke="#eee" stroke-width="16"/>' +
    '<circle cx="70" cy="70" r="' + R + '" fill="none" stroke="' + color +
    '" stroke-width="16" stroke-dasharray="' + (CIRC * c / 100).toFixed(1) + ' ' + CIRC.toFixed(1) +
    '" transform="rotate(-90 70 70)" stroke-linecap="round"/>' +
    '<text x="70" y="76" text-anchor="middle" font-size="20" font-weight="bold">' +
    c.toFixed(0) + '%</text></svg>';
}

function renderAnalytics(data) {
  const el = $('analytics');
  let html = '<div class="card"><h2>Analytics</h2>';
  html += '<p class="hint">' + esc(data.synthetic_data_note || '') + '</p>';

  const flags = data.anomaly_flags || [];
  html += '<h3>Proactive flags (' + flags.length + ')</h3>';
  if (!flags.length) {
    html += '<p class="ok">No anomalies detected in this run.</p>';
  } else {
    html += '<ul>' + flags.map((f) =>
      '<li class="' + (f.severity === 'critical' ? 'flag' : '') + '"><strong>[' +
      esc(f.severity.toUpperCase()) + ']</strong> ' + esc(f.message) + '</li>').join('') + '</ul>';
  }

  const bench = {};
  (data.peer_benchmarks || []).forEach((b) => { bench[b.metric] = b; });

  html += '<h3>Cost vs synthetic peers</h3>';
  if (bench.cost_per_kg_usd) {
    const b = bench.cost_per_kg_usd;
    html += barChart([
      { label: 'Your run', value: b.value, color: '#0b5fff' },
      { label: 'Peer p50', value: b.peer_p50, color: '#9e9e9e' },
      { label: 'Peer p90', value: b.peer_p90, color: '#cfcfcf' },
    ], b.unit) + '<p class="hint">Verdict: ' + esc(b.verdict) + ' · ' + esc(b.data_label) + '</p>';
  }

  html += '<h3>Shelf-life projection vs peers</h3>';
  if (bench.shelf_life_days) {
    const b = bench.shelf_life_days;
    html += barChart([
      { label: 'Your run', value: b.value, color: '#0b5fff' },
      { label: 'Peer p50', value: b.peer_p50, color: '#9e9e9e' },
    ], b.unit) + '<p class="hint">Verdict: ' + esc(b.verdict) + '</p>';
  }

  html += '<h3>Claim coverage</h3>';
  const agg = data.aggregates || {};
  if (agg.avg_claim_coverage_pct != null) {
    html += donut(agg.avg_claim_coverage_pct, 'claim coverage');
  }
  html += '<p class="hint">Runs recorded: ' + (agg.run_count || 0) +
          (agg.avg_cost_per_kg_usd != null ? ' · Avg cost $' + agg.avg_cost_per_kg_usd + '/kg' : '') +
          (agg.avg_cycle_weeks != null ? ' · Avg cycle ' + agg.avg_cycle_weeks + ' weeks' : '') + '</p>';

  el.innerHTML = html + '</div>';
}

async function loadAnalytics(token) {
  try {
    const res = await fetch('/api/analytics/summary', {
      headers: { 'Authorization': 'Bearer ' + token },
    });
    if (!res.ok) { return; }
    renderAnalytics(await res.json());
  } catch (e) { /* analytics is best-effort in the demo UI */ }
}

async function runDemo() {
  const btn = $('run-button'), status = $('status'), results = $('results');
  const token = $('token-input').value.trim();
  if (!token) { status.textContent = 'Please paste a demo bearer token first.'; return; }
  btn.disabled = true; results.innerHTML = '';
  status.textContent = 'Running 4 agents (offline workflow)…';
  const headers = { 'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + token };
  if (window._sessionId) { headers['X-Session-Id'] = window._sessionId; }
  try {
    const res = await fetch('/api/reformulate', {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({ scenario: $('scenario-select').value }),
    });
    const sid = res.headers.get('X-Session-Id');
    if (sid) { window._sessionId = sid; }
    const data = await res.json();
    if (!res.ok) {
      status.textContent = 'Error ' + res.status + ': ' + esc(data.detail || JSON.stringify(data));
    } else {
      status.textContent = 'Done in ' + data.elapsed_ms + ' ms (offline, deterministic).' +
        ' Session: ' + esc(data.session_id) +
        (data.grounding && data.grounding.length ? ' · grounded on ' + data.grounding.length + ' knowledge chunks.' : '');
      renderResults(data.blackboard);
      loadAnalytics(token);
    }
  } catch (e) {
    status.textContent = 'Request failed: ' + e.message;
  } finally {
    btn.disabled = false;
  }
}

$('run-button').addEventListener('click', runDemo);
loadScenarios();
</script>
</body>
</html>
"""
