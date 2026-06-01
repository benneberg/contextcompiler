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

def _build_html(index_data: dict, auto_refresh: int = 0) -> str:
    """Build the single-page workspace explorer UI."""
    index_json = json.dumps(index_data)
    workspace_name = index_data.get("workspace", "Workspace")

    # Auto-refresh snippet — injected before </body> if enabled
    auto_refresh_js = ""
    if auto_refresh > 0:
        auto_refresh_js_raw = f"""
<script>
(function() {{
  var lastGenerated = {json.dumps(index_data.get('generated', ''))};
  var interval = {auto_refresh * 1000};
  var indicator = document.createElement('div');
  indicator.id = 'refresh-indicator';
  indicator.style.cssText = 'position:fixed;bottom:12px;right:16px;font-size:11px;color:var(--muted);z-index:999';
  document.body.appendChild(indicator);

  function updateIndicator(msg) {{
    indicator.textContent = msg;
  }}

  function pollIndex() {{
    fetch('/api/index')
      .then(r => r.json())
      .then(data => {{
        if (data.generated && data.generated !== lastGenerated) {{
          lastGenerated = data.generated;
          updateIndicator('Refreshing...');
          setTimeout(() => window.location.reload(), 300);
        }} else {{
          var now = new Date().toLocaleTimeString();
          updateIndicator('Last checked: ' + now);
        }}
      }})
      .catch(() => updateIndicator('Refresh unavailable'));
  }}

  setInterval(pollIndex, interval);
  updateIndicator('Auto-refresh: every {auto_refresh}s');
}})();
</script>"""
        auto_refresh_js = auto_refresh_js_raw.replace("{", "{{").replace("}", "}}")

    return ("""<!DOCTYPE html>
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
      <div class="sidebar-label">Views</div>
      <div style="padding:0 4px">
        <div class="sidebar-item" onclick="showOverview()" style="cursor:pointer;padding:6px 8px;border-radius:4px;font-size:12px;margin-bottom:2px">Overview</div>
        <div class="sidebar-item" onclick="showDepsView()" style="cursor:pointer;padding:6px 8px;border-radius:4px;font-size:12px;margin-bottom:2px">Dependencies</div>
      </div>
    </div>

    <div class="sidebar-section">
      <div class="sidebar-label">Reports</div>
      <div style="padding:0 4px">
        <div class="sidebar-item" onclick="showCoverageView()" style="cursor:pointer;padding:6px 8px;border-radius:4px;font-size:12px;margin-bottom:2px">Coverage Map</div>
        <div class="sidebar-item" onclick="showStaleView()" style="cursor:pointer;padding:6px 8px;border-radius:4px;font-size:12px;margin-bottom:2px">Stale Context</div>
        <div class="sidebar-item" onclick="showImpactPrompt()" style="cursor:pointer;padding:6px 8px;border-radius:4px;font-size:12px;margin-bottom:2px">Change Impact</div>
      </div>
    </div>

    <div class="sidebar-section">
      <div class="sidebar-label">Task Intent</div>
      <input type="text" class="search-input" id="intent-input"
             placeholder="e.g. add webm support..."
             title="Describe a task — CCC will find relevant services">
      <div id="intent-hint" style="font-size:10px;color:var(--muted);padding:4px 2px 0;display:none">
        Press Enter to find relevant services
      </div>
    </div>

    <div class="sidebar-section">
      <div class="sidebar-label">Find Service</div>
      <input type="text" class="search-input" id="search" placeholder="Filter by name...">
    </div>

    <div class="sidebar-section">
      <div class="sidebar-label">Filter by tag</div>
      <div class="tag-cloud" id="tag-cloud"></div>
    </div>

    <div class="sidebar-section" id="saved-views-section" style="display:none">
      <div class="sidebar-label" style="display:flex;align-items:center;justify-content:space-between">
        <span>Saved Views</span>
        <span onclick="clearAllSavedViews()" style="font-size:10px;color:var(--muted);cursor:pointer" title="Clear all saved views">clear</span>
      </div>
      <div id="saved-views-list" style="padding:0 4px"></div>
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
      <div id="stale-banner" style="display:none;margin-bottom:16px;padding:12px 16px;background:var(--surface);border:1px solid var(--yellow);border-radius:6px;font-size:13px;color:var(--yellow)"></div>
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

    <!-- Dependencies view -->
    <div class="view" id="view-deps">
      <div id="deps-content"></div>
    </div>

    <!-- Intent query view -->
    <div class="view" id="view-intent">
      <div id="intent-content"></div>
    </div>

    <!-- Coverage map view -->
    <div class="view" id="view-coverage">
      <div id="coverage-content"></div>
    </div>

    <!-- Stale context view -->
    <div class="view" id="view-stale">
      <div id="stale-content"></div>
    </div>

    <!-- Change impact view -->
    <div class="view" id="view-impact">
      <div id="impact-content"></div>
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
  const chips = INDEX.all_tags.map(tag => `
    <span class="tag-chip ${{activeTags.includes(tag) ? 'active' : ''}}"
          onclick="toggleTag('${{tag}}')">${{tag}}</span>
  `).join('');
  const saveBtn = activeTags.length > 0
    ? `<span onclick="promptSaveView()"
             style="display:inline-block;margin-top:8px;font-size:10px;color:var(--accent);cursor:pointer;padding:2px 6px;border:1px solid var(--accent);border-radius:3px">
         + save view
       </span>`
    : '';
  cloud.innerHTML = chips + saveBtn;
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

// ── Saved views (localStorage) ────────────────────────────────────────────────

const SAVED_VIEWS_KEY = 'ccc_saved_views_' + INDEX.workspace;

function loadSavedViews() {{
  try {{
    return JSON.parse(localStorage.getItem(SAVED_VIEWS_KEY) || '[]');
  }} catch(e) {{ return []; }}
}}

function saveSavedViews(views) {{
  try {{ localStorage.setItem(SAVED_VIEWS_KEY, JSON.stringify(views)); }} catch(e) {{}}
}}

function renderSavedViewsSidebar() {{
  const views = loadSavedViews();
  const section = document.getElementById('saved-views-section');
  const list = document.getElementById('saved-views-list');
  if (!section || !list) return;
  if (views.length === 0) {{ section.style.display = 'none'; return; }}
  section.style.display = 'block';
  list.innerHTML = views.map((v, i) => `
    <div style="display:flex;align-items:center;gap:4px;margin-bottom:2px">
      <span onclick="applySavedView(${{i}})"
            style="flex:1;padding:5px 8px;border-radius:4px;font-size:12px;cursor:pointer;
                   color:var(--fg);background:${{JSON.stringify(v.tags) === JSON.stringify(activeTags) ? 'var(--surface)' : 'transparent'}}"
            onmouseover="this.style.background='var(--surface)'"
            onmouseout="this.style.background='${{JSON.stringify(v.tags) === JSON.stringify(activeTags) ? 'var(--surface)' : 'transparent'}}'">
        ${{v.name}}
        <span style="font-size:10px;color:var(--muted)"> (${{v.tags.join(', ')}})</span>
      </span>
      <span onclick="deleteSavedView(${{i}})" style="font-size:11px;color:var(--muted);cursor:pointer;padding:2px 4px" title="Delete">x</span>
    </div>
  `).join('');
}}

function promptSaveView() {{
  const name = prompt('Name this view (e.g. "Auth stack", "My team"):');
  if (!name || !name.trim()) return;
  const views = loadSavedViews();
  // Check for duplicate name
  const existing = views.findIndex(v => v.name === name.trim());
  if (existing >= 0) views.splice(existing, 1);
  views.push({{ name: name.trim(), tags: [...activeTags] }});
  saveSavedViews(views);
  renderSavedViewsSidebar();
  renderTagCloud();
}}

function applySavedView(idx) {{
  const views = loadSavedViews();
  if (!views[idx]) return;
  activeTags = [...views[idx].tags];
  renderTagCloud();
  renderSidebar(document.getElementById('search').value);
  renderSavedViewsSidebar();
  if (activeTags.length > 0) showQueryView();
  else showOverview();
}}

function deleteSavedView(idx) {{
  const views = loadSavedViews();
  views.splice(idx, 1);
  saveSavedViews(views);
  renderSavedViewsSidebar();
}}

function clearAllSavedViews() {{
  if (!confirm('Delete all saved views?')) return;
  saveSavedViews([]);
  renderSavedViewsSidebar();
}}

// ── Overview ──────────────────────────────────────────────────────────────────

function showOverview() {{
  activeService = null; activeTags = [];
  renderTagCloud(); renderSidebar();
  showView('overview');

  const services = Object.values(INDEX.services);
  const withCtx = services.filter(s => s.has_context).length;
  const allTags = INDEX.all_tags;

  // ── Stale context banner ──
  const noCtx = services.filter(s => !s.has_context);
  const staleCtx = services.filter(s => {{
    if (!s.has_context || !s.context_generated || !s.last_commit) return false;
    const ctxDate = new Date(s.context_generated);
    const commitDate = new Date(s.last_commit);
    return commitDate > ctxDate;
  }});

  const bannerEl = document.getElementById('stale-banner');
  const bannerParts = [];
  if (noCtx.length > 0) {{
    bannerParts.push('[!] ' + noCtx.length + ' service' + (noCtx.length > 1 ? 's' : '') + ' missing context (run ccc in: ' + noCtx.map(s => s.name).join(', ') + ')');
  }}
  if (staleCtx.length > 0) {{
    bannerParts.push('[!] ' + staleCtx.length + ' service' + (staleCtx.length > 1 ? 's' : '') + ' have commits newer than generated context: ' + staleCtx.map(s => s.name).join(', '));
  }}
  if (bannerParts.length > 0) {{
    bannerEl.innerHTML = bannerParts.join('<br>');
    bannerEl.style.display = 'block';
  }} else {{
    bannerEl.style.display = 'none';
  }}

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
    `${{INDEX.workspace}} &nbsp;&middot;&nbsp; v${{INDEX.version}} &nbsp;&middot;&nbsp; generated ${{INDEX.generated?.split('T')[0] || ''}}` +
    ` &nbsp;<span style="font-size:10px;color:var(--muted)" title="Share: commit workspace-context/ and teammates can run ccc workspace serve without cloning all repos">[share: ccc workspace generate --commit-index]</span>`;
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
const hint = {{
  'data':'Update schema/config first',
  'frontend':'Update UI last',
  'gateway':'Update routing',
  'library':'Update shared types first',
  'backend-api':'Implement business logic',
  'worker':'Update processing logic'
}}[s?.type] || 'Review and update';
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
      s.exposes.api.slice(0,10).forEach(a => md += '  - `' + a + '`\\n');
    }}
    md += '\\n\\n';
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
  md += `- **Type**: ${{s.type}}\\n`;
  md += `- **Tags**: ${{(s.tags||[]).join(', ')}}\\n`;
  if (s.description) md += `- **Description**: ${{s.description}}\\n`;
  if (s.path) md += '- **Path**: `' + s.path + '`\\n';
  const deps = s.depends_on || [];
  if (deps.length) md += `- **Depends on**: ${{deps.join(', ')}}\\n`;
  const dependents = Object.values(INDEX.services).filter(sv => (sv.depends_on||[]).includes(name));
  if (dependents.length) md += `- **Used by**: ${{dependents.map(d=>d.name).join(', ')}}\\n`;
  if (s.exposes?.api?.length) {{
    md += `\\n## API Endpoints\\n\\n`;
    s.exposes.api.forEach(a => md += '- `' + a + '`\\n');
  }}
  if (s.exposes?.events?.length) {{
    md += `\n## Events\n\n`;
    s.exposes.events.forEach(e => md += `- ${{e}}\\n`);
  }}
  if (s.exposes?.types?.length) {{
    md += `\n## Types\n\n`;
    s.exposes.types.forEach(t => md += `- ${{t}}\\n`);
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

// ── Report views ────────────────────────────────────────────────────────────


function showCoverageView() {{
  activeService = null; activeTags = [];
  renderTagCloud(); renderSidebar();
  showView('coverage');

  const services = Object.values(INDEX.services);

  function coverageTier(s) {{
    if (!s.has_context) return 'none';
    const hasRoutes = (s.exposes?.api || []).length > 0;
    const hasTypes  = (s.exposes?.types || []).length > 0;
    const hasEvents = (s.exposes?.events || []).length > 0;
    const score = (hasRoutes?1:0) + (hasTypes?1:0) + (hasEvents?1:0);
    if (score === 3) return 'full';
    if (score >= 1) return 'partial';
    return 'basic';
  }}

  const tiers = {{
    full:    {{ label: 'Full',    color: 'var(--green)',  desc: 'routes + types + events' }},
    partial: {{ label: 'Partial', color: 'var(--accent)', desc: 'some context extracted' }},
    basic:   {{ label: 'Basic',   color: 'var(--muted)',  desc: 'context exists but sparse' }},
    none:    {{ label: 'None',    color: 'var(--yellow)', desc: 'run ccc first' }},
  }};

  const byTier = {{ full: [], partial: [], basic: [], none: [] }};
  services.forEach(s => byTier[coverageTier(s)].push(s));

  const totalWithCtx = services.filter(s => s.has_context).length;
  const pct = services.length > 0 ? Math.round((totalWithCtx / services.length) * 100) : 0;

  const barHtml = '<div style="margin-bottom:24px">' +
    '<div style="display:flex;justify-content:space-between;margin-bottom:6px;font-size:12px">' +
    '<span>Context coverage</span>' +
    '<span style="color:var(--muted)">' + totalWithCtx + ' / ' + services.length + ' services</span></div>' +
    '<div style="height:8px;background:var(--surface);border-radius:4px;overflow:hidden">' +
    '<div style="height:100%;width:' + pct + '%;background:var(--green)"></div></div>' +
    '<div style="font-size:11px;color:var(--muted);margin-top:4px">' + pct + '% coverage</div></div>';

  const tierOrder = ['full', 'partial', 'basic', 'none'];
  const sectionsHtml = tierOrder.map(tier => {{
    const svcs = byTier[tier];
    if (!svcs.length) return '';
    const t = tiers[tier];
    const cards = svcs.map(s =>
      '<div onclick="selectService(" + JSON.stringify(s.name) + ")" ' +
      'style="padding:10px 12px;background:var(--surface);border:1px solid var(--border);' +
      'border-radius:6px;cursor:pointer" ' +
      '>' +
      '<div style="font-size:12px;font-weight:600;margin-bottom:4px">' + s.name + '</div>' +
      '<div style="font-size:10px;color:var(--muted)">' + (s.tags||[]).join(', ') + '</div>' +
      (tier !== 'none' ?
        '<div style="font-size:10px;color:var(--muted);margin-top:4px">' +
        (s.exposes?.api||[]).length + ' routes \u00b7 ' +
        (s.exposes?.types||[]).length + ' types \u00b7 ' +
        (s.exposes?.events||[]).length + ' events</div>'
        : '<div style="font-size:10px;color:var(--yellow);margin-top:4px">run ccc in ' + s.path + '</div>') +
      '</div>'
    ).join('');
    return '<div style="margin-bottom:20px">' +
      '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">' +
      '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + t.color + '"></span>' +
      '<span style="font-size:12px;font-weight:600">' + t.label + '</span>' +
      '<span style="font-size:11px;color:var(--muted)">' + t.desc + '</span>' +
      '<span style="font-size:11px;color:var(--muted);margin-left:auto">' + svcs.length + ' service' + (svcs.length !== 1 ? 's' : '') + '</span></div>' +
      '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px">' + cards + '</div></div>';
  }}).join('');

  document.getElementById('coverage-content').innerHTML =
    '<div class="info-block"><div class="section-title">Coverage Map</div>' + barHtml + sectionsHtml + '</div>';
}}

function showStaleView() {{
  activeService = null; activeTags = [];
  renderTagCloud(); renderSidebar();
  showView('stale');

  const services = Object.values(INDEX.services);
  const now = Date.now();

  function staleDays(s) {{
    if (!s.has_context || !s.context_generated || !s.last_commit) return null;
    const diff = new Date(s.last_commit) - new Date(s.context_generated);
    return diff > 0 ? Math.round(diff / 86400000) : 0;
  }}

  function ageDays(s) {{
    if (!s.context_generated) return null;
    return Math.round((now - new Date(s.context_generated)) / 86400000);
  }}

  const noCtx = services.filter(s => !s.has_context);
  const stale = services.filter(s => (staleDays(s) || 0) > 0)
                        .sort((a,b) => (staleDays(b)||0) - (staleDays(a)||0));
  const fresh = services.filter(s => s.has_context && (staleDays(s) || 0) === 0);

  function svcRow(s, badge, badgeColor) {{
    const age = ageDays(s);
    const sd  = staleDays(s);
    return '<div style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border)">' +
      '<span style="min-width:100px;font-size:11px;font-weight:600;color:' + badgeColor + '">' + badge + '</span>' +
      '<span style="font-size:13px;cursor:pointer;flex:1" onclick="selectService(" + JSON.stringify(s.name) + ")">' + s.name + '</span>' +
      '<span style="font-size:11px;color:var(--muted)">' +
      (age !== null ? 'context ' + age + 'd old' : '') +
      (sd ? ' \u00b7 ' + sd + 'd behind commits' : '') + '</span></div>';
  }}

  const label = (txt, color) => '<div style="font-size:11px;font-weight:600;text-transform:uppercase;' +
    'letter-spacing:.05em;color:var(--muted);margin:16px 0 8px">' + txt + '</div>';

  let html = '<div class="info-block"><div class="section-title">Stale Context</div>' +
    '<div style="font-size:12px;color:var(--muted);margin-bottom:20px">Services where generated context is out of date with recent commits.</div>';

  if (noCtx.length)  html += label('No context') + noCtx.map(s => svcRow(s, 'missing', 'var(--yellow)')).join('');
  if (stale.length)  html += label('Stale \u2014 commits newer than context') + stale.map(s => svcRow(s, staleDays(s) + 'd stale', 'var(--accent)')).join('');
  if (fresh.length)  html += label('Up to date') + fresh.map(s => svcRow(s, 'current', 'var(--green)')).join('');
  if (!noCtx.length && !stale.length) html += '<div style="color:var(--green);font-size:13px;padding:20px 0">All services have current context.</div>';

  html += '</div>';
  document.getElementById('stale-content').innerHTML = html;
}}

function showImpactPrompt() {{
  activeService = null; activeTags = [];
  renderTagCloud(); renderSidebar();
  showView('impact');

  const opts = Object.keys(INDEX.services).sort()
    .map(n => '<option value="' + n + '">' + n + '</option>').join('');

  document.getElementById('impact-content').innerHTML =
    '<div class="info-block"><div class="section-title">Change Impact</div>' +
    '<div style="font-size:12px;color:var(--muted);margin-bottom:16px">Select a service to see its dependency fan-out.</div>' +
    '<select id="impact-select" style="width:100%;padding:8px 12px;background:var(--surface);' +
    'border:1px solid var(--border);border-radius:6px;color:var(--fg);font-size:13px;margin-bottom:12px">' +
    '<option value="">-- choose a service --</option>' + opts + '</select>' +
    '<div id="impact-result"></div></div>';

  document.getElementById('impact-select').addEventListener('change', e => {{
    const name = e.target.value;
    if (!name) {{ document.getElementById('impact-result').innerHTML = ''; return; }}
    showImpactFor(name);
  }});
}}

function showImpactFor(name) {{
  const services = Object.values(INDEX.services);
  const svc = INDEX.services[name];
  if (!svc) return;

  const dependents = services.filter(s => (s.depends_on || []).includes(name));
  const transSet = new Set();
  dependents.forEach(d => {{
    services.filter(s => (s.depends_on || []).includes(d.name) && s.name !== name)
            .forEach(t => transSet.add(t.name));
  }});
  const deps = (svc.depends_on || []).map(n => INDEX.services[n]).filter(Boolean);

  function chip(s, note) {{
    return '<span onclick="selectService(" + JSON.stringify(s.name) + ")" title="' + note + '" ' +
      'style="display:inline-block;padding:4px 10px;margin:3px;background:var(--surface);' +
      'border:1px solid var(--border);border-radius:4px;font-size:12px;cursor:pointer" ' +
      '>' +
      s.name + '</span>';
  }}

  const secLabel = txt => '<div style="font-size:11px;font-weight:600;text-transform:uppercase;' +
    'letter-spacing:.05em;color:var(--muted);margin:16px 0 8px">' + txt + '</div>';
  const none = '<span style="font-size:12px;color:var(--muted)">none declared</span>';

  let html = '<div style="margin-top:8px">';
  html += secLabel('Direct dependents (' + dependents.length + ') \u2014 affected if ' + name + ' changes');
  html += dependents.length ? dependents.map(s => chip(s, 'directly depends on ' + name)).join('') : none;
  if (transSet.size) {{
    html += secLabel('Transitive (' + transSet.size + ') \u2014 depend on the dependents');
    html += [...transSet].map(n => INDEX.services[n]).filter(Boolean).map(s => chip(s, 'transitive')).join('');
  }}
  html += secLabel(name + ' depends on (' + deps.length + ')');
  html += deps.length ? deps.map(s => chip(s, name + ' depends on this')).join('') : none;
  html += '</div>';

  document.getElementById('impact-result').innerHTML = html;
}}


// ── Intent engine ────────────────────────────────────────────────────────────
// Pure client-side scoring: no LLM, no network. Works entirely from INDEX data.

const INTENT_STOPWORDS = new Set([
  'a','an','the','and','or','in','on','at','to','for','of','with',
  'is','it','be','as','by','from','that','this','which','how','what',
  'we','i','my','our','need','want','would','should','can','will',
  'support','add','fix','change','update','remove','implement','create',
  'new','make','get','set','put','use','show','find','help','please',
]);

// Common tech → likely service tag or keyword mappings
const TECH_HINTS = {{
  'auth': ['auth','security','login','jwt','oauth','session'],
  'user': ['users','accounts','profiles','auth'],
  'payment': ['payments','billing','stripe','checkout'],
  'email': ['notifications','messaging','mail','smtp'],
  'file': ['storage','media','upload','files','s3','cdn'],
  'image': ['media','thumbnail','storage','cdn','s3'],
  'video': ['media','thumbnail','encoder','cdn','transcode'],
  'webm': ['media','thumbnail','encoder','codec','transcode','storage'],
  'mp4': ['media','encoder','codec','transcode'],
  'thumbnail': ['thumbnail','media','image','storage'],
  'notification': ['notifications','messaging','email','push','alerts'],
  'search': ['search','index','elastic','solr','query'],
  'cache': ['cache','redis','performance','session'],
  'database': ['database','data','models','schema','migrations'],
  'queue': ['queue','jobs','workers','async','messaging','rabbitmq'],
  'api': ['api','gateway','routing','backend'],
  'frontend': ['frontend','ui','web','react','vue'],
  'deploy': ['infrastructure','config','devops','docker'],
  'platform': ['platforms','devices','adapters','integration'],
  'websocket': ['realtime','ws','socket','streaming'],
  'webhook': ['integration','events','notifications','api'],
}};

function scoreIntent(query) {{
  const words = query.toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/)
    .filter(w => w.length > 2 && !INTENT_STOPWORDS.has(w));

  if (words.length === 0) return [];

  const services = Object.values(INDEX.services);
  const results = [];

  services.forEach(svc => {{
    let score = 0;
    const reasons = [];

    const svcText = [
      svc.name,
      ...(svc.tags || []),
      svc.description || '',
      svc.type || '',
      svc.framework || '',
      ...(svc.languages || []),
    ].join(' ').toLowerCase();

    const apiText = (svc.exposes?.api || []).join(' ').toLowerCase();
    const extDeps = ((svc.exposes?.types || []).concat(svc.exposes?.events || [])).join(' ').toLowerCase();

    words.forEach(word => {{
      // Direct name match — highest signal
      if (svc.name.toLowerCase().includes(word)) {{
        score += 40;
        reasons.push('name match: ' + word);
      }}

      // Tag match
      const matchedTags = (svc.tags || []).filter(t => t.toLowerCase().includes(word) || word.includes(t.toLowerCase()));
      if (matchedTags.length) {{
        score += 25 * matchedTags.length;
        reasons.push('tags: ' + matchedTags.join(', '));
      }}

      // API endpoint match
      if (apiText.includes(word)) {{
        score += 20;
        reasons.push('api endpoint: ' + word);
      }}

      // Description / type / framework match
      if ((svc.description || '').toLowerCase().includes(word)) {{
        score += 15;
        reasons.push('description: ' + word);
      }}
      if ((svc.type || '').toLowerCase().includes(word)) {{
        score += 10;
      }}

      // Tech hint expansion
      const hintTags = TECH_HINTS[word] || [];
      hintTags.forEach(hint => {{
        if (svcText.includes(hint)) {{
          score += 12;
          reasons.push('tech hint: ' + word + ' \u2192 ' + hint);
        }}
      }});
    }});

    // Boost services that already have context (more useful to include)
    if (svc.has_context) score += 5;

    if (score > 0) {{
      results.push({{ svc, score, reasons: [...new Set(reasons)] }});
    }}
  }});

  // Sort by score descending
  results.sort((a, b) => b.score - a.score);

  // Add transitive deps of top results (lower score)
  const topNames = new Set(results.slice(0, 3).map(r => r.svc.name));
  services.forEach(svc => {{
    if (topNames.has(svc.name)) return;
    const isDep = results.slice(0, 3).some(r =>
      (r.svc.depends_on || []).includes(svc.name) ||
      (svc.depends_on || []).some(d => topNames.has(d))
    );
    if (isDep) {{
      results.push({{ svc, score: 8, reasons: ['transitive dependency'] }});
    }}
  }});

  // Re-sort and dedupe
  const seen = new Set();
  return results
    .sort((a, b) => b.score - a.score)
    .filter(r => {{ if (seen.has(r.svc.name)) return false; seen.add(r.svc.name); return true; }})
    .slice(0, 8);
}}

function buildCopilotBlock(results) {{
  const primary = results.filter(r => r.score >= 20);
  const secondary = results.filter(r => r.score < 20 && r.score >= 8);

  let block = '';
  primary.forEach(r => {{
    if (r.svc.has_context) {{
      block += '#file:' + r.svc.path + '/.llm-context/LLM.md\\n';
    }}
  }});
  secondary.forEach(r => {{
    if (r.svc.has_context) {{
      block += '#file:' + r.svc.path + '/.llm-context/LLM.md\\n';
    }}
  }});
  return block;
}}

function showIntentView(query) {{
  showView('intent');
  const results = scoreIntent(query);
  const el = document.getElementById('intent-content');

  if (results.length === 0) {{
    el.innerHTML = `
      <div class="info-block">
        <div class="section-title">Task: "${{query}}"</div>
        <div style="color:var(--muted);font-size:13px">
          No services matched this query. Try different keywords,
          or check that services have tags and descriptions in ccc-workspace.yml.
        </div>
      </div>`;
    return;
  }}

  const primary = results.filter(r => r.score >= 20);
  const secondary = results.filter(r => r.score < 20 && r.score >= 8);
  const copilotBlock = buildCopilotBlock(results);

  const renderRow = (r, tier) => `
    <div style="display:flex;align-items:flex-start;gap:12px;padding:12px 0;border-bottom:1px solid var(--border)">
      <div style="min-width:48px;text-align:right">
        <span style="font-size:11px;font-weight:600;color:${{tier === 'primary' ? 'var(--accent)' : 'var(--muted)'}}">${{r.score}}</span>
      </div>
      <div style="flex:1">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
          <span style="font-weight:600;font-size:13px;cursor:pointer;color:var(--fg)"
                onclick="selectService('${{r.svc.name}}')">${{r.svc.name}}</span>
          <span class="dot dot-${{(r.svc.type||'unknown').replace(/[^a-z]/g,'-')}}"></span>
          ${{(r.svc.tags||[]).map(t=>'<span class="tag-chip">'+t+'</span>').join('')}}
          ${{!r.svc.has_context ? '<span style="font-size:10px;color:var(--yellow)">[no context]</span>' : ''}}
        </div>
        <div style="font-size:11px;color:var(--muted)">${{r.reasons.join(' · ')}}</div>
      </div>
    </div>`;

  const copilotHtml = copilotBlock ? `
    <div style="margin-top:20px">
      <div style="font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px">
        Copy for Copilot / Claude
      </div>
      <pre id="copilot-block" style="background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:12px;font-size:11px;color:var(--fg);white-space:pre-wrap;margin:0">${{copilotBlock.trim()}}</pre>
      <button onclick="copyIntentBlock()" style="margin-top:8px;padding:6px 14px;background:var(--accent);color:#fff;border:none;border-radius:4px;font-size:12px;cursor:pointer">
        Copy to clipboard
      </button>
      <span id="copy-confirm" style="font-size:11px;color:var(--green);margin-left:8px;display:none">Copied!</span>
    </div>` : `
    <div style="margin-top:16px;font-size:12px;color:var(--yellow)">
      No services with generated context found. Run <code>ccc</code> in matched service directories first.
    </div>`;

  el.innerHTML = `
    <div class="info-block">
      <div class="section-title">Task: "${{query}}"</div>
      <div style="font-size:12px;color:var(--muted);margin-bottom:16px">
        ${{results.length}} service${{results.length !== 1 ? 's' : ''}} matched &mdash;
        ${{primary.length}} primary, ${{secondary.length}} transitive
      </div>

      ${{primary.length ? `
        <div style="font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px">Primary</div>
        ${{primary.map(r => renderRow(r, 'primary')).join('')}}
      ` : ''}}

      ${{secondary.length ? `
        <div style="font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-top:16px;margin-bottom:4px">Also relevant</div>
        ${{secondary.map(r => renderRow(r, 'secondary')).join('')}}
      ` : ''}}

      ${{copilotHtml}}
    </div>`;
}}

function copyIntentBlock() {{
  const text = document.getElementById('copilot-block').textContent;
  if (navigator.clipboard) {{
    navigator.clipboard.writeText(text).then(() => {{
      const el = document.getElementById('copy-confirm');
      el.style.display = 'inline';
      setTimeout(() => {{ el.style.display = 'none'; }}, 2000);
    }});
  }}
}}

// ── Dependencies view ─────────────────────────────────────────────────────────

function showDepsView() {{
  activeService = null; activeTags = [];
  renderTagCloud(); renderSidebar();
  showView('deps');

  const services = Object.values(INDEX.services);

  // Build declared dep matrix
  const declared = [];
  services.forEach(s => {{
    (s.depends_on || []).forEach(dep => {{
      declared.push({{ from: s.name, to: dep, kind: 'declared' }});
    }});
  }});

  // Stale / missing context summary
  const noCtx = services.filter(s => !s.has_context);
  const staleCtx = services.filter(s => {{
    if (!s.has_context || !s.context_generated || !s.last_commit) return false;
    return new Date(s.last_commit) > new Date(s.context_generated);
  }});

  const staleHtml = (noCtx.length + staleCtx.length) > 0 ? `
    <div class="no-context-notice" style="margin-bottom:24px">
      ${{noCtx.length > 0 ? `<div>[!] No context: ${{noCtx.map(s=>'<code>'+s.name+'</code>').join(', ')}}</div>` : ''}}
      ${{staleCtx.length > 0 ? `<div>[!] Stale context (commits newer than last ccc run): ${{staleCtx.map(s=>'<code>'+s.name+'</code>').join(', ')}}</div>` : ''}}
    </div>` : '';

  // Declared deps table
  const depsHtml = declared.length > 0 ? `
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead>
        <tr style="border-bottom:1px solid var(--border);color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.05em">
          <th style="text-align:left;padding:8px 12px">Service</th>
          <th style="text-align:left;padding:8px 12px">Depends On</th>
          <th style="text-align:left;padding:8px 12px">Status</th>
        </tr>
      </thead>
      <tbody>
        ${{declared.map(d => `
          <tr style="border-bottom:1px solid var(--border)" onclick="selectService('${{d.from}}')" style="cursor:pointer">
            <td style="padding:8px 12px"><code>${{d.from}}</code></td>
            <td style="padding:8px 12px"><code>${{d.to}}</code></td>
            <td style="padding:8px 12px;color:var(--green);font-size:11px">declared</td>
          </tr>`).join('')}}
      </tbody>
    </table>` : '<div style="color:var(--muted);font-size:13px">No declared dependencies found. Add <code>depends_on</code> entries to ccc-workspace.yml.</div>';

  const discoverHint = `
    <div style="margin-top:24px;padding:12px 16px;background:var(--surface);border-radius:6px;font-size:12px;color:var(--muted)">
      Run <code>ccc workspace discover</code> to detect undeclared dependencies automatically.
      Results appear in <code>workspace-context/discovered-relationships.md</code>.
    </div>`;

  document.getElementById('deps-content').innerHTML = `
    <div class="info-block">
      <div class="section-title">Dependencies</div>
      ${{staleHtml}}
      <div style="margin-bottom:8px;font-size:12px;color:var(--muted)">${{declared.length}} declared relationship(s) across ${{services.length}} services</div>
      ${{depsHtml}}
      ${{discoverHint}}
    </div>`;
}}

// ── Init ──────────────────────────────────────────────────────────────────────

// Intent input
const intentEl = document.getElementById('intent-input');
intentEl.addEventListener('focus', () => {{
  document.getElementById('intent-hint').style.display = 'block';
}});
intentEl.addEventListener('blur', () => {{
  setTimeout(() => {{ document.getElementById('intent-hint').style.display = 'none'; }}, 200);
}});
intentEl.addEventListener('keydown', e => {{
  if (e.key === 'Enter') {{
    const q = intentEl.value.trim();
    if (q.length > 2) showIntentView(q);
  }}
}});
intentEl.addEventListener('input', e => {{
  // Live preview when enough text
  const q = e.target.value.trim();
  if (q.length >= 6) showIntentView(q);
  else if (q.length === 0) showOverview();
}});

renderTagCloud();
renderSidebar();
renderSavedViewsSidebar();
showOverview();
</script>
""" + auto_refresh_js + """
</body>
</html>""").format(workspace_name=workspace_name, index_json=index_json)


# ── HTTP server ───────────────────────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    html: str = ""
    index_json: str = ""
    token: Optional[str] = None

    def do_GET(self):
        # Optional token check
        if self.token:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            provided = qs.get("token", [""])[0]
            if provided != self.token and self.path.rstrip("/") != "/api/index":
                self.send_response(403)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"403 Forbidden - token required (?token=...)")
                return

        # /api/index — serve raw service-index.json for auto-refresh polling
        if self.path.rstrip("/") == "/api/index":
            data = self.index_json.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(self.html.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # silence stdlib request logs


def serve_workspace(
    manifest: WorkspaceManifest,
    port: int = 7842,
    open_browser: bool = True,
    rebuild_index: bool = True,
    bind: str = "127.0.0.1",
    token: Optional[str] = None,
    auto_refresh: int = 0,
) -> None:
    """
    Launch the workspace browser UI.

    Args:
        manifest:       Loaded WorkspaceManifest
        port:           Port to serve on (default 7842)
        open_browser:   Auto-open in default browser
        rebuild_index:  Rebuild service-index.json before serving
        bind:           Address to bind to (default: 127.0.0.1)
        token:          Optional access token required as ?token=<value>
        auto_refresh:   Poll interval in seconds (0 = disabled)
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

    html = _build_html(index_data, auto_refresh=auto_refresh)

    _Handler.html = html
    _Handler.index_json = content
    _Handler.token = token

    server = HTTPServer((bind, port), _Handler)
    url = f"http://{bind}:{port}"
    url_display = f"http://localhost:{port}" if bind == "127.0.0.1" else url
    if token:
        url_display += f"?token={token}"

    print(f"\n{'=' * 60}")
    print(f"  CCC Workspace Explorer")
    print(f"  Serving: {url_display}")
    print(f"  Workspace: {manifest.name} ({len(manifest.services)} services)")
    if bind != "127.0.0.1":
        print(f"  [!] Bound to {bind} -- accessible on network")
    if token:
        print(f"  [lock] Token protection enabled")
    print(f"{'=' * 60}")
    print(f"  Press Ctrl+C to stop")
    print(f"")

    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url_display)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        server.server_close()
