"""
ccc workspace serve — launch a browser UI for workspace exploration.

Serves a single-page HTML app that reads service-index.json and lets
anyone (including non-coders) browse services, query by tag, explore
dependencies, and export results.

Zero dependencies — uses Python's built-in http.server.
"""

import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional

from ..utils.files import safe_read_text
from .manifest import WorkspaceManifest
from .index import build_service_index


# ── HTML UI ───────────────────────────────────────────────────────────────────

def _build_html(index_data: dict) -> str:
    """Build the single-page workspace explorer UI."""
    index_json = json.dumps(index_data) 
    workspace_name = index_data.get("workspace", "Workspace")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{workspace_name} — CCC Workspace</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

  :root {{
    --bg: #0f1117;
    --surface: #1a1d27;
    --surface2: #22263a;
    --border: #2e3350;
    --accent: #4f9cf9;
    --accent2: #7c6af7;
    --green: #3ecf8e;
    --yellow: #f5a623;
    --red: #e05252;
    --text: #e2e8f0;
    --muted: #8892a4;
    --mono: 'IBM Plex Mono', monospace;
    --sans: 'IBM Plex Sans', sans-serif;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    font-size: 14px;
    line-height: 1.6;
    min-height: 100vh;
  }}

  /* ── Layout ── */
  .app {{ display: flex; flex-direction: column; min-height: 100vh; }}

  header {{
    border-bottom: 1px solid var(--border);
    padding: 16px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--surface);
    position: sticky; top: 0; z-index: 100;
  }}

  .logo {{ display: flex; align-items: center; gap: 12px; }}
  .logo-mark {{
    width: 32px; height: 32px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-family: var(--mono); font-weight: 500; font-size: 13px;
    color: #fff;
  }}
  .logo-name {{ font-weight: 600; font-size: 15px; letter-spacing: -0.3px; }}
  .logo-ws {{ color: var(--muted); font-weight: 300; margin-left: 4px; }}

  .header-meta {{
    font-family: var(--mono);
    font-size: 11px;
    color: var(--muted);
    text-align: right;
  }}

  .main {{ display: flex; flex: 1; }}

  /* ── Sidebar ── */
  .sidebar {{
    width: 280px;
    min-width: 280px;
    border-right: 1px solid var(--border);
    background: var(--surface);
    padding: 24px 0;
    overflow-y: auto;
    position: sticky;
    top: 57px;
    height: calc(100vh - 57px);
  }}

  .sidebar-section {{ padding: 0 20px 24px; }}
  .sidebar-label {{
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 10px;
  }}

  .search-input {{
    width: 100%;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 9px 12px;
    color: var(--text);
    font-family: var(--sans);
    font-size: 13px;
    outline: none;
    transition: border-color 0.15s;
  }}
  .search-input:focus {{ border-color: var(--accent); }}
  .search-input::placeholder {{ color: var(--muted); }}

  .tag-cloud {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .tag-chip {{
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 500;
    cursor: pointer;
    border: 1px solid var(--border);
    background: var(--surface2);
    color: var(--muted);
    transition: all 0.15s;
    user-select: none;
  }}
  .tag-chip:hover {{ border-color: var(--accent); color: var(--accent); }}
  .tag-chip.active {{
    background: rgba(79,156,249,0.15);
    border-color: var(--accent);
    color: var(--accent);
  }}

  .service-list {{ padding: 0 12px; }}
  .service-item {{
    padding: 10px 10px;
    border-radius: 8px;
    cursor: pointer;
    margin-bottom: 2px;
    transition: background 0.12s;
    display: flex;
    align-items: center;
    gap: 10px;
  }}
  .service-item:hover {{ background: var(--surface2); }}
  .service-item.active {{ background: rgba(79,156,249,0.12); }}

  .service-dot {{
    width: 8px; height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }}
  .dot-frontend  {{ background: var(--accent); }}
  .dot-backend-api {{ background: var(--green); }}
  .dot-data      {{ background: var(--yellow); }}
  .dot-gateway   {{ background: var(--accent2); }}
  .dot-library   {{ background: var(--muted); }}
  .dot-worker    {{ background: var(--red); }}
  .dot-unknown   {{ background: var(--border); }}

  .service-name {{ font-size: 13px; font-weight: 500; flex: 1; min-width: 0; }}
  .service-name-text {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .service-context-badge {{
    font-size: 9px;
    padding: 2px 5px;
    border-radius: 4px;
    flex-shrink: 0;
  }}
  .badge-ready {{ background: rgba(62,207,142,0.15); color: var(--green); }}
  .badge-missing {{ background: rgba(224,82,82,0.1); color: var(--red); }}

  /* ── Content ── */
  .content {{ flex: 1; padding: 32px; overflow-y: auto; max-width: 900px; }}

  .view {{ display: none; }}
  .view.active {{ display: block; }}

  /* Overview cards */
  .stats-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 32px; }}
  .stat-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
  }}
  .stat-number {{ font-size: 32px; font-weight: 600; font-family: var(--mono); color: var(--accent); }}
  .stat-label {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}

  /* Service detail */
  .detail-header {{ margin-bottom: 28px; }}
  .detail-name {{
    font-size: 26px; font-weight: 600;
    letter-spacing: -0.5px;
    margin-bottom: 6px;
  }}
  .detail-meta {{ display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }}
  .type-badge {{
    padding: 4px 12px; border-radius: 20px;
    font-size: 11px; font-weight: 600;
    letter-spacing: 0.3px;
  }}
  .type-frontend  {{ background: rgba(79,156,249,0.15); color: var(--accent); }}
  .type-backend-api {{ background: rgba(62,207,142,0.15); color: var(--green); }}
  .type-data      {{ background: rgba(245,166,35,0.15); color: var(--yellow); }}
  .type-gateway   {{ background: rgba(124,106,247,0.15); color: var(--accent2); }}
  .type-library   {{ background: rgba(136,146,164,0.15); color: var(--muted); }}

  .detail-tags {{ display: flex; gap: 6px; flex-wrap: wrap; }}
  .detail-tag {{
    padding: 3px 9px; border-radius: 12px;
    font-size: 11px;
    background: var(--surface2);
    color: var(--muted);
    border: 1px solid var(--border);
  }}

  .section-title {{
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 14px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
  }}

  .info-block {{ margin-bottom: 28px; }}

  .dep-list {{ display: flex; flex-direction: column; gap: 8px; }}
  .dep-item {{
    display: flex; align-items: center; gap: 10px;
    padding: 10px 14px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    cursor: pointer;
    transition: border-color 0.15s;
  }}
  .dep-item:hover {{ border-color: var(--accent); }}
  .dep-arrow {{ color: var(--accent); font-family: var(--mono); font-size: 13px; }}
  .dep-name {{ font-weight: 500; }}
  .dep-type {{ color: var(--muted); font-size: 11px; margin-left: auto; }}

  .api-list {{ display: flex; flex-direction: column; gap: 4px; }}
  .api-item {{
    font-family: var(--mono);
    font-size: 12px;
    padding: 6px 12px;
    background: var(--surface2);
    border-radius: 6px;
    display: flex; gap: 10px; align-items: center;
  }}
  .method {{
    font-weight: 600; font-size: 10px;
    padding: 2px 6px; border-radius: 4px;
    min-width: 46px; text-align: center;
  }}
  .method-GET    {{ background: rgba(62,207,142,0.2); color: var(--green); }}
  .method-POST   {{ background: rgba(79,156,249,0.2); color: var(--accent); }}
  .method-PUT    {{ background: rgba(245,166,35,0.2); color: var(--yellow); }}
  .method-DELETE {{ background: rgba(224,82,82,0.2); color: var(--red); }}
  .method-PATCH  {{ background: rgba(124,106,247,0.2); color: var(--accent2); }}
  .method-OTHER  {{ background: var(--border); color: var(--muted); }}

  /* Export panel */
  .export-bar {{
    display: flex; gap: 10px; margin-bottom: 28px; flex-wrap: wrap;
  }}
  .btn {{
    padding: 9px 18px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    border: 1px solid var(--border);
    background: var(--surface2);
    color: var(--text);
    transition: all 0.15s;
    font-family: var(--sans);
  }}
  .btn:hover {{ border-color: var(--accent); color: var(--accent); }}
  .btn-primary {{
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }}
  .btn-primary:hover {{ background: #3a87e8; border-color: #3a87e8; color: #fff; }}

  .copy-area {{
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px;
    font-family: var(--mono);
    font-size: 12px;
    line-height: 1.7;
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 400px;
    overflow-y: auto;
    color: var(--text);
  }}

  /* Tag query view */
  .query-result {{
    margin-top: 20px;
  }}
  .query-result-header {{
    font-size: 13px; color: var(--muted); margin-bottom: 16px;
  }}
  .service-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 18px 20px;
    margin-bottom: 12px;
    cursor: pointer;
    transition: border-color 0.15s;
  }}
  .service-card:hover {{ border-color: var(--accent); }}
  .service-card-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }}
  .service-card-name {{ font-size: 15px; font-weight: 600; }}
  .service-card-desc {{ color: var(--muted); font-size: 12px; }}
  .service-card-footer {{
    display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px;
    padding-top: 12px; border-top: 1px solid var(--border);
    font-size: 11px; color: var(--muted);
  }}

  .change-sequence {{
    margin-top: 24px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px;
  }}
  .change-sequence h3 {{
    font-size: 12px; font-weight: 600;
    letter-spacing: 0.8px; text-transform: uppercase;
    color: var(--muted); margin-bottom: 16px;
  }}
  .seq-item {{
    display: flex; align-items: flex-start; gap: 14px;
    padding: 10px 0;
    border-bottom: 1px solid var(--border);
  }}
  .seq-item:last-child {{ border-bottom: none; }}
  .seq-num {{
    width: 26px; height: 26px;
    border-radius: 50%;
    background: rgba(79,156,249,0.15);
    color: var(--accent);
    font-family: var(--mono); font-size: 11px; font-weight: 600;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0; margin-top: 1px;
  }}
  .seq-content {{ flex: 1; }}
  .seq-name {{ font-weight: 600; margin-bottom: 2px; }}
  .seq-hint {{ font-size: 11px; color: var(--muted); }}

  .empty-state {{
    text-align: center; padding: 60px 20px; color: var(--muted);
  }}
  .empty-icon {{ font-size: 40px; margin-bottom: 12px; }}
  .empty-text {{ font-size: 14px; }}

  /* Toast */
  .toast {{
    position: fixed; bottom: 24px; right: 24px;
    background: var(--surface);
    border: 1px solid var(--green);
    border-radius: 8px;
    padding: 10px 18px;
    font-size: 13px; color: var(--green);
    opacity: 0; pointer-events: none;
    transition: opacity 0.2s;
    z-index: 1000;
  }}
  .toast.show {{ opacity: 1; }}

  .path-text {{
    font-family: var(--mono); font-size: 11px;
    color: var(--muted); word-break: break-all;
  }}

  .desc-text {{ color: var(--muted); font-size: 13px; margin-top: 4px; }}

  .no-context-notice {{
    background: rgba(245,166,35,0.08);
    border: 1px solid rgba(245,166,35,0.25);
    border-radius: 8px; padding: 12px 16px;
    font-size: 12px; color: var(--yellow); margin-bottom: 20px;
  }}
</style>
</head>
<body>
<div class="app">

<header>
  <div class="logo">
    <div class="logo-mark">ccc</div>
    <div>
      <span class="logo-name">{workspace_name}</span>
      <span class="logo-ws">/ workspace</span>
    </div>
  </div>
  <div class="header-meta" id="header-meta"></div>
</header>

<div class="main">
  <!-- Sidebar -->
  <aside class="sidebar">
    <div class="sidebar-section">
      <div class="sidebar-label">Search</div>
      <input type="text" class="search-input" id="search" placeholder="Find a service...">
    </div>

    <div class="sidebar-section">
      <div class="sidebar-label">Filter by tag</div>
      <div class="tag-cloud" id="tag-cloud"></div>
    </div>

    <div class="sidebar-section">
      <div class="sidebar-label">Services</div>
    </div>
    <div class="service-list" id="service-list"></div>
  </aside>

  <!-- Main content -->
  <main class="content">

    <!-- Overview view -->
    <div class="view active" id="view-overview">
      <div class="stats-grid" id="stats-grid"></div>
      <div class="info-block">
        <div class="section-title">All Tags</div>
        <div class="tag-cloud" id="overview-tags"></div>
      </div>
      <div class="info-block">
        <div class="section-title">Services Overview</div>
        <div id="overview-services"></div>
      </div>
    </div>

    <!-- Tag query view -->
    <div class="view" id="view-query">
      <div class="export-bar" id="query-export-bar"></div>
      <div class="query-result" id="query-result"></div>
    </div>

    <!-- Service detail view -->
    <div class="view" id="view-detail">
      <div class="export-bar" id="detail-export-bar"></div>
      <div id="detail-content"></div>
    </div>

  </main>
</div>
</div>

<div class="toast" id="toast">Copied to clipboard</div>

<script>
const INDEX = {index_json};

// ── State ─────────────────────────────────────────────────────────────────────
let activeTags = [];
let activeService = null;
let currentView = 'overview';

// ── Helpers ───────────────────────────────────────────────────────────────────

function dot(type) {{
  const cls = 'dot-' + (type || 'unknown').replace(/[^a-z-]/g, '');
  return `<span class="service-dot ${{cls}}"></span>`;
}}

function typeBadge(type) {{
  const t = (type || 'unknown');
  return `<span class="type-badge type-${{t}}">${{t}}</span>`;
}}

function methodBadge(route) {{
  const parts = route.trim().split(/ +/);
  if (parts.length >= 2) {{
    const m = parts[0].toUpperCase();
    const path = parts.slice(1).join(' ');
    const cls = ['GET','POST','PUT','DELETE','PATCH'].includes(m) ? m : 'OTHER';
    return `<div class="api-item"><span class="method method-${{cls}}">${{m}}</span><span>${{path}}</span></div>`;
  }}
  return `<div class="api-item">${{route}}</div>`;
}}

function topoSort(serviceNames) {{
  const services = serviceNames.map(n => INDEX.services[n]).filter(Boolean);
  const names = new Set(serviceNames);
  const inDeg = {{}};
  const graph = {{}};
  services.forEach(s => {{ inDeg[s.name] = 0; graph[s.name] = []; }});
  services.forEach(s => {{
    (s.depends_on || []).forEach(d => {{
      if (names.has(d)) {{ graph[d].push(s.name); inDeg[s.name]++; }}
    }});
  }});
  const q = Object.keys(inDeg).filter(n => inDeg[n] === 0);
  const result = [];
  while (q.length) {{
    const n = q.shift(); result.push(n);
    (graph[n] || []).forEach(nb => {{ if (--inDeg[nb] === 0) q.push(nb); }});
  }}
  return result.length === services.length ? result : serviceNames;
}}

function showToast(msg = 'Copied!') {{
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2000);
}}

function copyText(text) {{
  navigator.clipboard?.writeText(text).then(() => showToast())
    .catch(() => {{ const ta = document.createElement('textarea');
      ta.value = text; document.body.appendChild(ta);
      ta.select(); document.execCommand('copy');
      document.body.removeChild(ta); showToast(); }});
}}

function downloadFile(filename, content) {{
  const a = document.createElement('a');
  a.href = 'data:text/plain;charset=utf-8,' + encodeURIComponent(content);
  a.download = filename; a.click();
}}

function showView(name) {{
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById('view-' + name).classList.add('active');
  currentView = name;
}}

// ── Sidebar ───────────────────────────────────────────────────────────────────

function renderSidebar(filter = '') {{
  const list = document.getElementById('service-list');
  const filtered = Object.values(INDEX.services).filter(s => {{
    const matchSearch = !filter || s.name.toLowerCase().includes(filter.toLowerCase())
      || (s.description || '').toLowerCase().includes(filter.toLowerCase());
    const matchTags = activeTags.length === 0
      || activeTags.every(t => (s.tags || []).includes(t));
    return matchSearch && matchTags;
  }});

  list.innerHTML = filtered.map(s => `
    <div class="service-item ${{activeService === s.name ? 'active' : ''}}"
         onclick="selectService('${{s.name}}')">
      ${{dot(s.type)}}
      <div class="service-name">
        <div class="service-name-text">${{s.name}}</div>
      </div>
      <span class="service-context-badge ${{s.has_context ? 'badge-ready' : 'badge-missing'}}">
        ${{s.has_context ? 'ctx' : 'no ctx'}}
      </span>
    </div>
  `).join('');
}}

function renderTagCloud() {{
  const cloud = document.getElementById('tag-cloud');
  cloud.innerHTML = INDEX.all_tags.map(tag => `
    <span class="tag-chip ${{activeTags.includes(tag) ? 'active' : ''}}"
          onclick="toggleTag('${{tag}}')">${{tag}}</span>
  `).join('');
}}

function toggleTag(tag) {{
  const idx = activeTags.indexOf(tag);
  if (idx >= 0) activeTags.splice(idx, 1);
  else activeTags.push(tag);
  renderTagCloud();
  renderSidebar(document.getElementById('search').value);
  if (activeTags.length > 0) showQueryView();
  else showOverview();
}}

// ── Overview ──────────────────────────────────────────────────────────────────

function showOverview() {{
  activeService = null; activeTags = [];
  renderTagCloud(); renderSidebar();
  showView('overview');

  const services = Object.values(INDEX.services);
  const withCtx = services.filter(s => s.has_context).length;
  const allTags = INDEX.all_tags;

  document.getElementById('stats-grid').innerHTML = `
    <div class="stat-card">
      <div class="stat-number">${{services.length}}</div>
      <div class="stat-label">Services</div>
    </div>
    <div class="stat-card">
      <div class="stat-number">${{allTags.length}}</div>
      <div class="stat-label">Tags</div>
    </div>
    <div class="stat-card">
      <div class="stat-number">${{withCtx}}</div>
      <div class="stat-label">With generated context</div>
    </div>
  `;

  document.getElementById('overview-tags').innerHTML =
    allTags.map(t => `<span class="tag-chip" onclick="toggleTag('${{t}}')">${{t}}</span>`).join('');

  document.getElementById('overview-services').innerHTML = services.map(s => `
    <div class="service-card" onclick="selectService('${{s.name}}')">
      <div class="service-card-header">
        ${{dot(s.type)}} ${{typeBadge(s.type)}}
        <span class="service-card-name">${{s.name}}</span>
      </div>
      <div class="service-card-desc">${{s.description || 'No description'}}</div>
      <div class="service-card-footer">
        ${{(s.tags||[]).map(t => `<span class="detail-tag">${{t}}</span>`).join('')}}
        ${{s.has_context ? '<span style="color:var(--green)">✓ context ready</span>' : '<span style="color:var(--yellow)">⚠ run ccc first</span>'}}
      </div>
    </div>
  `).join('');

  document.getElementById('header-meta').innerHTML =
    `${{INDEX.workspace}} &nbsp;·&nbsp; v${{INDEX.version}} &nbsp;·&nbsp; generated ${{INDEX.generated?.split('T')[0] || ''}}`;
}}

// ── Tag query view ────────────────────────────────────────────────────────────

function showQueryView() {{
  showView('query');
  const services = Object.values(INDEX.services).filter(s =>
    activeTags.every(t => (s.tags || []).includes(t))
  );
  const ordered = topoSort(services.map(s => s.name));

  // Export buttons
  document.getElementById('query-export-bar').innerHTML = `
    <button class="btn" onclick="copyQueryMarkdown()">Copy as Markdown</button>
    <button class="btn" onclick="downloadQueryJson()">Download JSON</button>
  `;

  // Results
  const res = document.getElementById('query-result');
  if (services.length === 0) {{
    res.innerHTML = `<div class="empty-state">
      <div class="empty-icon">🔍</div>
      <div class="empty-text">No services match tags: ${{activeTags.join(', ')}}</div>
    </div>`;
    return;
  }}

  res.innerHTML = `
    <div class="query-result-header">
      Found <strong>${{services.length}} service${{services.length !== 1 ? 's' : ''}}</strong>
      tagged <strong>${{activeTags.join(' + ')}}</strong>
    </div>
    ${{services.map(s => `
      <div class="service-card" onclick="selectService('${{s.name}}')">
        <div class="service-card-header">
          ${{dot(s.type)}} ${{typeBadge(s.type)}}
          <span class="service-card-name">${{s.name}}</span>
          ${{!s.has_context ? '<span style="font-size:11px;color:var(--yellow)">⚠ no context</span>' : ''}}
        </div>
        <div class="service-card-desc">${{s.description || '—'}}</div>
        ${{(s.exposes?.api?.length) ? `<div style="margin-top:8px;font-size:11px;color:var(--muted)">${{s.exposes.api.length}} API endpoint${{s.exposes.api.length !== 1 ? 's' : ''}}</div>` : ''}}
        <div class="service-card-footer">
          ${{(s.tags||[]).map(t => `<span class="detail-tag">${{t}}</span>`).join('')}}
          ${{(s.depends_on||[]).length ? `<span>depends on: ${{s.depends_on.join(', ')}}</span>` : ''}}
        </div>
      </div>
    `).join('')}}

    <div class="change-sequence">
      <h3>Suggested Change Sequence</h3>
      ${{ordered.map((name, i) => {{
        const s = INDEX.services[name];
        const hint = {{ 'data':'Update schema/config first', 'frontend':'Update UI last',
          'gateway':'Update routing', 'library':'Update shared types first',
          'backend-api':'Implement business logic', 'worker':'Update processing logic' }}[s?.type] || 'Review and update';
        return `<div class="seq-item">
          <div class="seq-num">${{i+1}}</div>
          <div class="seq-content">
            <div class="seq-name">${{name}}</div>
            <div class="seq-hint">${{hint}}${{(s?.depends_on||[]).length ? ` · depends on: ${{s.depends_on.join(', ')}}` : ''}}</div>
          </div>
        </div>`;
      }}).join('')}}
    </div>
  `;
}}

function copyQueryMarkdown() {{
  const services = Object.values(INDEX.services).filter(s =>
    activeTags.every(t => (s.tags || []).includes(t))
  );
  const ordered = topoSort(services.map(s => s.name));
  let md = `# Workspace Query: ${{activeTags.join(' + ')}}\n\n`;
  md += `**${{services.length}} service${{services.length !== 1 ? 's' : ''}} found**\n\n`;
  services.forEach(s => {{
    md += `## ${{s.name}}\n`;
    md += `- **Type**: ${{s.type}}\n`;
    md += `- **Tags**: ${{(s.tags||[]).join(', ')}}\n\n`;
    if (s.description) md += `- **Description**: ${{s.description}}\n\n`;
    if (s.depends_on?.length) md += `- **Depends on**: ${{s.depends_on.join(', ')}}\n\n`;
    if (s.exposes?.api?.length) {{
      md += `- **Exposes**:\n\n`;
      s.exposes.api.slice(0,10).forEach(a => md += '  - `' + a + '\n\n\n');
    }}
    md += '\n\n';
  }});
  md += `## Change Sequence\n\n`;
  ordered.forEach((n, i) => md += `${{i+1}}. **${{n}}**\n`);
  copyText(md);
}}

function downloadQueryJson() {{
  const services = Object.values(INDEX.services).filter(s =>
    activeTags.every(t => (s.tags || []).includes(t))
  );
  const ordered = topoSort(services.map(s => s.name));
  const data = {{ query: activeTags, services, change_sequence: ordered }};
  downloadFile(`workspace-query-${{activeTags.join('-')}}.json`, JSON.stringify(data, null, 2));
}}

// ── Service detail ────────────────────────────────────────────────────────────

function selectService(name) {{
  activeService = name;
  renderSidebar(document.getElementById('search').value);
  showView('detail');
  const s = INDEX.services[name];
  if (!s) return;

  const deps = (s.depends_on || []).map(d => INDEX.services[d]).filter(Boolean);
  const dependents = Object.values(INDEX.services).filter(sv => (sv.depends_on||[]).includes(name));

  document.getElementById('detail-export-bar').innerHTML = `
    <button class="btn btn-primary" onclick="copyServiceMarkdown('${{name}}')">Copy for LLM</button>
    <button class="btn" onclick="copyServiceJson('${{name}}')">Copy JSON</button>
    <button class="btn" onclick="downloadServiceJson('${{name}}')">Download JSON</button>
  `;

  const apis = s.exposes?.api || [];
  const events = s.exposes?.events || [];
  const types = s.exposes?.types || [];

  document.getElementById('detail-content').innerHTML = `
    ${{!s.has_context ? `<div class="no-context-notice">
      ⚠ Context not generated for this service. Run <code>ccc</code> in <code>${{s.path}}</code> for richer data.
    </div>` : ''}}

    <div class="detail-header">
      <div class="detail-name">${{s.name}}</div>
      <div class="detail-meta">
        ${{typeBadge(s.type)}}
        <div class="detail-tags">
          ${{(s.tags||[]).map(t => `<span class="detail-tag" style="cursor:pointer" onclick="toggleTag('${{t}}')">${{t}}</span>`).join('')}}
        </div>
      </div>
      ${{s.description ? `<div class="desc-text">${{s.description}}</div>` : ''}}
    </div>

    ${{s.path ? `<div class="info-block">
      <div class="section-title">Path</div>
      <div class="path-text">${{s.path}}</div>
    </div>` : ''}}

    ${{deps.length ? `<div class="info-block">
      <div class="section-title">Depends On</div>
      <div class="dep-list">
        ${{deps.map(d => `<div class="dep-item" onclick="selectService('${{d.name}}')">
          <span class="dep-arrow">→</span>
          ${{dot(d.type)}}
          <span class="dep-name">${{d.name}}</span>
          <span class="dep-type">${{d.type}}</span>
        </div>`).join('')}}
      </div>
    </div>` : ''}}

    ${{dependents.length ? `<div class="info-block">
      <div class="section-title">Used By</div>
      <div class="dep-list">
        ${{dependents.map(d => `<div class="dep-item" onclick="selectService('${{d.name}}')">
          <span class="dep-arrow">←</span>
          ${{dot(d.type)}}
          <span class="dep-name">${{d.name}}</span>
          <span class="dep-type">${{d.type}}</span>
        </div>`).join('')}}
      </div>
    </div>` : ''}}

    ${{apis.length ? `<div class="info-block">
      <div class="section-title">Exposes — API Endpoints (${{apis.length}})</div>
      <div class="api-list">${{apis.map(methodBadge).join('')}}</div>
    </div>` : ''}}

    ${{events.length ? `<div class="info-block">
      <div class="section-title">Exposes — Events</div>
      <div class="api-list">
        ${{events.map(e => `<div class="api-item"><span class="method method-OTHER">EVT</span>${{e}}</div>`).join('')}}
      </div>
    </div>` : ''}}

    ${{types.length ? `<div class="info-block">
      <div class="section-title">Exposes — Types</div>
      <div class="api-list">
        ${{types.map(t => `<div class="api-item"><span class="method method-OTHER">TYPE</span>${{t}}</div>`).join('')}}
      </div>
    </div>` : ''}}
  `;
}}

function copyServiceMarkdown(name) {{
  const s = INDEX.services[name];
  if (!s) return;
  let md = `# ${{s.name}}\n\n`;
  md += `- **Type**: ${{s.type}}\n`;
  md += `- **Tags**: ${{(s.tags||[]).join(', ')}}\n`;
  if (s.description) md += `- **Description**: ${{s.description}}\n`;
  if (s.path) md += '- **Path**: `' + s.path + '`\n';
  const deps = s.depends_on || [];
  if (deps.length) md += `- **Depends on**: ${{deps.join(', ')}}\n`;
  const dependents = Object.values(INDEX.services).filter(sv => (sv.depends_on||[]).includes(name));
  if (dependents.length) md += `- **Used by**: ${{dependents.map(d=>d.name).join(', ')}}\n`;
  if (s.exposes?.api?.length) {{
    md += `\n## API Endpoints\n\n`;
    s.exposes.api.forEach(a => md += '- `' + a + '`\n');
  }}
  if (s.exposes?.events?.length) {{
    md += `\n## Events\n\n`;
    s.exposes.events.forEach(e => md += `- ${{e}}\n`);
  }}
  if (s.exposes?.types?.length) {{
    md += `\n## Types\n\n`;
    s.exposes.types.forEach(t => md += `- ${{t}}\n`);
  }}
  copyText(md);
}}

function copyServiceJson(name) {{
  const s = INDEX.services[name];
  if (s) copyText(JSON.stringify(s, null, 2));
}}

function downloadServiceJson(name) {{
  const s = INDEX.services[name];
  if (s) downloadFile(`${{name}}.json`, JSON.stringify(s, null, 2));
}}

// ── Search ────────────────────────────────────────────────────────────────────

document.getElementById('search').addEventListener('input', e => {{
  renderSidebar(e.target.value);
}});

// ── Init ──────────────────────────────────────────────────────────────────────

renderTagCloud();
renderSidebar();
showOverview();
</script>
</body>
</html>"""


# ── HTTP server ───────────────────────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    html: str = ""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(self.html.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # silence request logs


def serve_workspace(
    manifest: WorkspaceManifest,
    port: int = 7842,
    open_browser: bool = True,
    rebuild_index: bool = True,
) -> None:
    """
    Launch the workspace browser UI.

    Args:
        manifest:       Loaded WorkspaceManifest
        port:           Port to serve on (default 7842)
        open_browser:   Auto-open in default browser
        rebuild_index:  Rebuild service-index.json before serving
    """
    # Build/refresh service index
    index_path = manifest.root / "workspace-context" / "service-index.json"

    if rebuild_index or not index_path.exists():
        print("  Building service index...")
        index_path = build_service_index(manifest)
        print(f"  Index written to: {index_path}")

    content = safe_read_text(index_path)
    if not content:
        raise ValueError(f"Could not read service index at {index_path}")

    try:
        index_data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid service-index.json: {e}")

    html = _build_html(index_data)

    _Handler.html = html

    server = HTTPServer(("localhost", port), _Handler)
    url = f"http://localhost:{port}"

    print(f"\n{'=' * 60}")
    print(f"  CCC Workspace Explorer")
    print(f"  Serving: {url}")
    print(f"  Workspace: {manifest.name} ({len(manifest.services)} services)")
    print(f"{'=' * 60}")
    print(f"  Press Ctrl+C to stop")
    print(f"")

    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        server.server_close()
