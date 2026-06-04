let currentJobId = null;
let pollInterval = null;
let allFiles     = [];

// ── Analysis trigger ───────────────────────────────────────────────────────

async function startAnalysis() {
  const owner = document.getElementById("input-owner").value.trim();
  const repo  = document.getElementById("input-repo").value.trim();
  const token = document.getElementById("input-token").value.trim();
  const model = document.getElementById("input-model").value.trim();

  if (!owner || !repo || !token) {
    alert("Please fill in owner, repo, and token.");
    return;
  }

  // Reset UI
  hideAll();
  showProgress(0, "Starting analysis...");

  const resp = await fetch("/api/analyze", {
    method:  "POST",
    headers: {"Content-Type": "application/json"},
    body:    JSON.stringify({ owner, repo, token, model })
  });

  const { job_id } = await resp.json();
  currentJobId = job_id;

  // Poll for progress
  pollInterval = setInterval(() => pollStatus(job_id), 2000);
}


// ── Polling ────────────────────────────────────────────────────────────────

async function pollStatus(jobId) {
  const resp = await fetch(`/api/status/${jobId}`);
  const data = await resp.json();

  showProgress(data.progress, data.message);

  if (data.status === "complete") {
    clearInterval(pollInterval);
    await loadResults(jobId);
  }

  if (data.status === "failed") {
    clearInterval(pollInterval);
    showError(data.message);
  }
}


// ── Load and render results ────────────────────────────────────────────────

async function loadResults(jobId) {
  const [resultsResp, chartsResp] = await Promise.all([
    fetch(`/api/results/${jobId}`),
    fetch(`/api/charts/${jobId}`)
  ]);

  const results = await resultsResp.json();
  const charts  = await chartsResp.json();

  allFiles = results.files;

  renderSummaryCards(results);
  renderTreemap(charts.treemap_json);
  renderNetwork(charts.network_json);
  renderTable(results.files);

  hideProgress();
}


// ── Summary cards ──────────────────────────────────────────────────────────

function renderSummaryCards(data) {
  document.getElementById("stat-high").textContent   = data.high_risk;
  document.getElementById("stat-medium").textContent = data.medium_risk;
  document.getElementById("stat-low").textContent    = data.low_risk;
  document.getElementById("stat-avg").textContent    =
    data.avg_score.toFixed(1);

  show("summary-section");
}


// ── Treemap ────────────────────────────────────────────────────────────────

function renderTreemap(chartJson) {
  const fig = JSON.parse(chartJson);
  Plotly.newPlot("treemap-chart", fig.data, fig.layout,
    { responsive: true, displayModeBar: false }
  );

  // Click handler — open file detail
  document.getElementById("treemap-chart")
    .on("plotly_click", (data) => {
      const point = data.points[0];
      if (point.id && point.id.includes(".")) {
        openModal(point.id);
      }
    });

  show("treemap-section");
}


// ── Network graph ──────────────────────────────────────────────────────────

function renderNetwork(chartJson) {
  const fig = JSON.parse(chartJson);
  Plotly.newPlot("network-chart", fig.data, fig.layout,
    { responsive: true, displayModeBar: false }
  );
  show("network-section");
}


// ── File table ─────────────────────────────────────────────────────────────

function renderTable(files) {
  const tbody = document.getElementById("table-body");
  tbody.innerHTML = "";

  files.forEach(f => {
    const row = document.createElement("tr");
    row.className = riskClass(f.score);
    row.innerHTML = `
      <td class="file-path">${f.file_path}</td>
      <td><span class="score-badge ${riskClass(f.score)}">
        ${f.score.toFixed(1)}
      </span></td>
      <td>${confidenceBadge(f.confidence)}</td>
      <td>${f.top_author}</td>
      <td>${(f.living_knowledge * 100).toFixed(0)}%</td>
      <td>${f.last_meaningful_commit || "—"}</td>
      <td>
        <button onclick="openModal('${f.file_path}')">
          Details
        </button>
      </td>
    `;
    tbody.appendChild(row);
  });

  show("table-section");
}


// ── File detail modal ──────────────────────────────────────────────────────

function openModal(filePath) {
  const f = allFiles.find(f => f.file_path === filePath);
  if (!f) return;

  document.getElementById("modal-file").textContent  = f.file_path;
  document.getElementById("modal-score").textContent = f.score.toFixed(1);
  document.getElementById("modal-what").textContent  = f.what_it_does;
  document.getElementById("modal-domain").textContent= f.domain_knowledge;
  document.getElementById("modal-onboarding").textContent =
    f.onboarding_notes;
  document.getElementById("modal-action").textContent =
    f.recommended_action;

  const flagsEl = document.getElementById("modal-flags");
  if (f.confidence_flags && f.confidence_flags.length > 0) {
    flagsEl.innerHTML = `
      <div class="flags">
        <strong>⚠ Confidence flags:</strong>
        <ul>${f.confidence_flags.map(
          fl => `<li>${fl}</li>`
        ).join("")}</ul>
      </div>`;
  } else {
    flagsEl.innerHTML = "";
  }

  document.getElementById("modal").classList.remove("hidden");
}

function closeModal() {
  document.getElementById("modal").classList.add("hidden");
}


// ── Helpers ────────────────────────────────────────────────────────────────

function riskClass(score) {
  if (score >= 75) return "high";
  if (score >= 40) return "medium";
  return "low";
}

function confidenceBadge(level) {
  const colors = {
    high: "🟢", medium: "🟡", low: "🔴"
  };
  return `${colors[level] || "⚪"} ${level}`;
}

function showProgress(pct, message) {
  document.getElementById("progress-bar")
    .classList.remove("hidden");
  document.getElementById("progress-fill")
    .style.width = `${pct}%`;
  document.getElementById("progress-message")
    .textContent = message;
}

function hideProgress() {
  document.getElementById("progress-bar")
    .classList.add("hidden");
}

function showError(msg) {
  hideProgress();
  alert(`Analysis failed: ${msg}`);
}

function show(id) {
  document.getElementById(id).classList.remove("hidden");
}

function hideAll() {
  ["summary-section", "treemap-section",
   "network-section", "table-section"].forEach(id => {
    document.getElementById(id).classList.add("hidden");
  });
}