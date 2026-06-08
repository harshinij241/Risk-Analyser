let currentJobId  = null;
let currentData   = null;
let pollTimer     = null;
let chartsLoaded  = { treemap: false, network: false };

const PLOTLY_LAYOUT = {
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor:  'rgba(0,0,0,0)',
  font: { family: 'DM Mono, monospace', color: '#555555', size: 13 },
  margin: { t: 8, r: 8, b: 32, l: 40 },
};

function riskClass(score) {
  return score >= 75 ? 'high' : score >= 40 ? 'medium' : 'low';
}

function riskColor(score) {
  return score >= 75 ? '#ff4444' : score >= 40 ? '#ff9900' : '#00cc66';
}

async function startAnalysis() {
  const owner = document.getElementById('owner').value.trim();
  const repo  = document.getElementById('repo').value.trim();
  const token = document.getElementById('token').value.trim();
  const model = document.getElementById('model').value.trim();

  if (!owner || !repo || !token) {
    setStatus('error', 'Fill in owner, repo and token');
    return;
  }

  setStatus('running', 'Starting analysis…');
  document.getElementById('analyze-btn').disabled = true;
  document.getElementById('progress-wrap').classList.remove('hidden');
  setProgress(5);

  chartsLoaded = { treemap: false, network: false };

  try {
    const res = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ owner, repo, token, model,
                             top_n: 20, max_files: 1000,
                             max_commits: 300 })
    });
    const data = await res.json();
    currentJobId = data.job_id;
    pollTimer = setInterval(poll, 2000);
  } catch(e) {
    setStatus('error', e.message);
    document.getElementById('analyze-btn').disabled = false;
  }
}

async function poll() {
  if (!currentJobId) return;
  try {
    const res  = await fetch(`/api/status/${currentJobId}`);
    const data = await res.json();

    setStatus(data.status === 'complete' ? 'complete'
              : data.status === 'failed'  ? 'error'
              : 'running', data.message);
    setProgress(data.progress || 0);

    if (data.status === 'complete') {
      clearInterval(pollTimer);
      await loadResults();
      document.getElementById('analyze-btn').disabled = false;
    } else if (data.status === 'failed') {
      clearInterval(pollTimer);
      document.getElementById('analyze-btn').disabled = false;
    }
  } catch(e) { console.error(e); }
}

async function loadResults() {
  const res  = await fetch(`/api/results/${currentJobId}`);
  currentData = await res.json();

  document.getElementById('stat-high').textContent   = currentData.high_risk;
  document.getElementById('stat-medium').textContent = currentData.medium_risk;
  document.getElementById('stat-low').textContent    = currentData.low_risk;
  document.getElementById('stat-avg').textContent    = currentData.avg_score.toFixed(1);

  document.getElementById('stats-section').classList.remove('hidden');
  document.getElementById('empty-state').classList.add('hidden');
  document.getElementById('results-view').classList.remove('hidden');

  buildFileList(currentData.files);
  buildHistogram(currentData.files);
  buildScatter(currentData.files);
}

function buildFileList(files) {
  const list = document.getElementById('file-list');
  list.innerHTML = '';

  files.forEach(f => {
    const rc   = riskClass(f.score);
    const name = f.file_path.split('/').pop();
    const dir  = f.file_path.includes('/')
                 ? f.file_path.split('/').slice(0,-1).join('/') + '/'
                 : '';

    const item = document.createElement('div');
    item.className = 'file-item fade-in';
    item.onclick   = () => openDetail(f);
    item.innerHTML = `
      <div class="risk-bar ${rc}"></div>
      <div class="file-info">
        <div class="file-name">${name}</div>
        <div class="file-meta">${dir || f.top_authors?.[0]?.author || '—'}</div>
      </div>
      <div class="file-score ${rc}">${f.score.toFixed(0)}</div>
    `;
    list.appendChild(item);
  });
}

function buildHistogram(files) {
  const scores = files.map(f => f.score);
  const colors = scores.map(s => riskColor(s));

  Plotly.newPlot('histogram-chart', [{
    type: 'histogram',
    x: scores,
    nbinsx: 15,
    marker: {
      color: colors,
      line: { color: '#0a0a0a', width: 1 }
    }
  }], {
    ...PLOTLY_LAYOUT,
    margin: { t: 8, r: 8, b: 32, l: 36 },
    xaxis: {
      title: { text: 'risk score', font: { size: 13 } },
      color: '#555',
      gridcolor: '#1a1a1a',
      range: [0, 100],
    },
    yaxis: {
      title: { text: 'files', font: { size: 13 } },
      color: '#555',
      gridcolor: '#1a1a1a',
    },
    bargap: 0.08,
  }, { responsive: true, displayModeBar: false });
}

function buildScatter(files) {
  Plotly.newPlot('scatter-chart', [{
    type: 'scatter',
    mode: 'markers',
    x: files.map(f => f.hhi),
    y: files.map(f => f.decayed_recency),
    text: files.map(f => f.file_path.split('/').pop()),
    marker: {
      color: files.map(f => f.score),
      colorscale: [
        [0,   '#00cc66'],
        [0.4, '#ff9900'],
        [1,   '#ff4444']
      ],
      size: files.map(f => 8 + f.complexity * 12),
      line: { color: '#0a0a0a', width: 1 },
      showscale: false,
    },
    hovertemplate: '<b>%{text}</b><br>HHI: %{x:.2f}<br>Staleness: %{y:.2f}<extra></extra>',
  }], {
    ...PLOTLY_LAYOUT,
    margin: { t: 8, r: 8, b: 40, l: 44 },
    xaxis: {
      title: { text: 'ownership concentration (HHI)', font: { size: 13 } },
      color: '#555', gridcolor: '#1a1a1a', range: [0, 1.05],
    },
    yaxis: {
      title: { text: 'knowledge staleness', font: { size: 13 } },
      color: '#555', gridcolor: '#1a1a1a', range: [0, 1.05],
    },
  }, { responsive: true, displayModeBar: false });
}

async function loadTreemap() {
  if (chartsLoaded.treemap) return;
  try {
    const res  = await fetch(`/api/charts/${currentJobId}`);
    const data = await res.json();
    const fig  = JSON.parse(data.treemap_json);
    Plotly.newPlot('treemap-chart', fig.data, {
      ...fig.layout, ...PLOTLY_LAYOUT,
      margin: { t: 8, r: 8, b: 8, l: 8 }
    }, { responsive: true, displayModeBar: false });
    chartsLoaded.treemap = true;
  } catch(e) { console.error(e); }
}

async function loadNetwork() {
  if (chartsLoaded.network) return;
  try {
    const res  = await fetch(`/api/charts/${currentJobId}`);
    const data = await res.json();
    const fig  = JSON.parse(data.network_json);
    Plotly.newPlot('network-chart', fig.data, {
      ...fig.layout, ...PLOTLY_LAYOUT,
      margin: { t: 8, r: 8, b: 8, l: 8 }
    }, { responsive: true, displayModeBar: false });
    chartsLoaded.network = true;
  } catch(e) { console.error(e); }
}

function showTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));

  if (typeof event !== 'undefined' && event && event.target && event.target.classList) {
    if (event.target.classList.contains('tab')) {
      event.target.classList.add('active');
    }
  } else {
    document.querySelectorAll('.tab').forEach(t => {
      if (t.getAttribute('onclick') && t.getAttribute('onclick').includes(name)) {
        t.classList.add('active');
      }
    });
  }

  const tabElement = document.getElementById(`tab-${name}`);
  if (tabElement) {
    tabElement.classList.add('active');
  }

  if (name === 'treemap') loadTreemap();
  if (name === 'network') loadNetwork();
}

function openDetail(f) {
  const rc = riskClass(f.score);
  const primaryAuthor = f.top_authors?.[0]?.author || 'unknown';
  const primaryShare  = f.top_authors?.[0]?.share  || 0;
  const backupCount   = Math.max((f.top_authors?.length || 1) - 1, 0);
  const busFactor     = f.top_authors?.length || 1;

  let authorsHtml = (f.top_authors || []).map(a => `
    <div class="author-row">
      <div class="author-avatar">${a.author[0].toUpperCase()}</div>
      <div class="author-name">${a.author}</div>
      <div class="author-share-bar">
        <div class="author-share-fill" style="width:${(a.share*100).toFixed(0)}%"></div>
      </div>
      <div class="author-pct">${(a.share*100).toFixed(0)}%</div>
    </div>
  `).join('');

  let knowledgeHtml = (f.knowledge_areas || []).map(k =>
    `<li class="knowledge-item">${k}</li>`
  ).join('') || '<li class="knowledge-item" style="color:var(--gray-5)">No data</li>';

  let driversHtml = (f.risk_drivers || []).map(d => {
    const cls = d.startsWith('+') ? 'pos' : 'neg';
    const txt = d.replace(/^[+\-] ?/, '');
    return `<li class="driver-item ${cls}">${txt}</li>`;
  }).join('') || '';

  let actionsHtml = (f.recommended_actions || []).map((a, i) => `
    <li class="action-item">
      <span class="action-num">${String(i+1).padStart(2,'0')}</span>
      <span class="action-text">${a}</span>
    </li>
  `).join('') || '';

  let flagsHtml = (f.confidence_flags || []).map(flag =>
    `<div class="flag-item">${flag}</div>`
  ).join('') || '<div class="flag-item" style="color:var(--gray-5)">No flags</div>';

  const fragility = (0.45 * f.hhi + 0.25 * f.decayed_recency);
  const ownerPts  = (0.45 * f.hhi * 100 * f.amplifier).toFixed(1);
  const stalePts  = (0.25 * f.decayed_recency * 100 * f.amplifier).toFixed(1);

  const criticBadge = f.business_criticality
    ? `<span class="badge criticality-${(f.business_criticality||'').toLowerCase()}">${f.business_criticality} criticality</span>`
    : '';

  document.getElementById('file-detail-content').innerHTML = `
    <!-- Header -->
    <div class="detail-header">
      <div class="detail-filepath">${f.file_path}</div>
      <div class="detail-title">${f.file_path.split('/').pop()}</div>
      <div class="detail-badges">
        <span class="badge ${rc}">${f.score.toFixed(1)} / 100</span>
        ${criticBadge}
        <span class="badge">${f.confidence} confidence</span>
        <span class="badge">bus factor ${busFactor}</span>
      </div>
    </div>

    <div class="detail-body">

      <!-- Score breakdown -->
      <div class="detail-section">
        <div class="section-label">Risk score</div>
        <div class="score-display">
          <span class="score-number ${rc}">${f.score.toFixed(0)}</span>
          <span class="score-denom">/ 100</span>
        </div>
        <div class="breakdown-row">
          <span class="breakdown-label">Ownership (HHI ${f.hhi.toFixed(2)})</span>
          <div class="breakdown-bar-wrap">
            <div class="breakdown-bar" style="width:${f.hhi*100}%;background:var(--danger)"></div>
          </div>
          <span class="breakdown-value pos">+${ownerPts}</span>
        </div>
        <div class="breakdown-row">
          <span class="breakdown-label">Staleness (${(f.decayed_recency*100).toFixed(0)}%)</span>
          <div class="breakdown-bar-wrap">
            <div class="breakdown-bar" style="width:${f.decayed_recency*100}%;background:var(--warn)"></div>
          </div>
          <span class="breakdown-value pos">+${stalePts}</span>
        </div>
        <div class="breakdown-row">
          <span class="breakdown-label">Complexity amplifier</span>
          <div class="breakdown-bar-wrap">
            <div class="breakdown-bar" style="width:${f.complexity*100}%"></div>
          </div>
          <span class="breakdown-value">${f.complexity.toFixed(2)}×</span>
        </div>
        <div class="breakdown-row">
          <span class="breakdown-label">Living knowledge</span>
          <div class="breakdown-bar-wrap">
            <div class="breakdown-bar" style="width:${f.living_knowledge*100}%;background:var(--ok)"></div>
          </div>
          <span class="breakdown-value neg">${(f.living_knowledge*100).toFixed(0)}%</span>
        </div>
      </div>

      <!-- Ownership -->
      <div class="detail-section">
        <div class="section-label">Ownership</div>
        <div class="ownership-grid">
          <div class="ownership-stat">
            <div class="ownership-value">${primaryAuthor.split(/[^a-zA-Z]/)[0]}</div>
            <div class="ownership-label">Primary owner</div>
          </div>
          <div class="ownership-stat">
            <div class="ownership-value">${(primaryShare*100).toFixed(0)}%</div>
            <div class="ownership-label">Ownership share</div>
          </div>
          <div class="ownership-stat">
            <div class="ownership-value ${backupCount === 0 ? 'danger' : ''}">${backupCount}</div>
            <div class="ownership-label">Backup maintainers</div>
          </div>
          <div class="ownership-stat">
            <div class="ownership-value ${busFactor === 1 ? 'danger' : ''}">${busFactor}</div>
            <div class="ownership-label">Bus factor</div>
          </div>
        </div>
        ${authorsHtml}
        <div style="margin-top:12px;font-family:var(--font-mono);font-size:13px;font-weight:bold;color:var(--gray-6)">
          Last commit: ${f.last_meaningful_commit || 'unknown'}
        </div>
      </div>

      <!-- Business impact -->
      <div class="detail-section">
        <div class="section-label">Business impact</div>
        <div class="impact-text">${f.business_impact || 'Analysis pending.'}</div>
      </div>

      <!-- Onboarding -->
      <div class="detail-section">
        <div class="section-label">Onboarding notes</div>
        <div class="onboarding-text">${f.onboarding_notes || 'No onboarding data.'}</div>
      </div>

      <!-- Knowledge areas -->
      <div class="detail-section">
        <div class="section-label">Knowledge areas required</div>
        <ul class="knowledge-list">${knowledgeHtml}</ul>
      </div>

      <!-- Risk drivers -->
      <div class="detail-section">
        <div class="section-label">Risk drivers</div>
        <ul class="driver-list">${driversHtml}</ul>
      </div>

      <!-- Recommended actions -->
      <div class="detail-section full" style="border-bottom:var(--border)">
        <div class="section-label">Recommended actions</div>
        <ul class="action-list">${actionsHtml}</ul>
      </div>

      <!-- Confidence flags -->
      <div class="detail-section full">
        <div class="section-label">Confidence flags</div>
        <div class="flag-list">${flagsHtml}</div>
      </div>

    </div>
  `;

  document.getElementById('file-detail').classList.remove('hidden');
  document.getElementById('file-detail').scrollTop = 0;
}

function closeDetail() {
  document.getElementById('file-detail').classList.add('hidden');
}

function setStatus(state, message) {
  const dot  = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  dot.className  = `status-dot ${state}`;
  text.textContent = message || state;
}

function setProgress(pct) {
  document.getElementById('progress-fill').style.width = `${pct}%`;
}
