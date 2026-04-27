"""Frontend Agent - Generates a Bootstrap 5 spec-driven web UI for the generated FastAPI app.

Uses a fixed HTML/JS template (frontend_template.html) that reads /openapi.json at runtime
and builds all forms, tables, and API calls dynamically. No LLM-generated JavaScript.
"""
import os
from pathlib import Path
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from .base import BaseAgent
from ..db.models import AgentRole, Project, UseCase, ArtifactType, Artifact

_TEMPLATE_PATH = Path(__file__).parent / "frontend_template.html"

_UNUSED = '''\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{app_title}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet"/>
<link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css" rel="stylesheet"/>
<style>
  body{{margin:0;background:#f8f9fa;}}
  #sidebar{{width:260px;min-height:100vh;background:{brand_color};color:#fff;position:fixed;top:0;left:0;overflow-y:auto;z-index:100;}}
  #sidebar .brand{{padding:1.2rem 1rem;border-bottom:1px solid rgba(255,255,255,.15);}}
  #sidebar .brand h5{{margin:0;font-weight:700;}}
  #sidebar .brand small{{opacity:.7;font-size:.75rem;}}
  #sidebar .nav-link{{color:rgba(255,255,255,.8);padding:.55rem 1rem;border-left:3px solid transparent;font-size:.875rem;}}
  #sidebar .nav-link:hover{{color:#fff;background:rgba(255,255,255,.1);}}
  #sidebar .nav-link.active{{color:#fff;border-left-color:#fff;background:rgba(255,255,255,.15);font-weight:600;}}
  #sidebar .section-label{{padding:.6rem 1rem .2rem;font-size:.65rem;text-transform:uppercase;letter-spacing:1px;opacity:.5;}}
  #main{{margin-left:260px;padding:1.5rem;}}
  .panel{{display:none;}}.panel.active{{display:block;}}
  .endpoint-card{{background:#fff;border:1px solid #dee2e6;border-radius:.5rem;margin-bottom:1rem;}}
  .endpoint-card .card-header{{border-radius:.5rem .5rem 0 0;padding:.6rem 1rem;display:flex;align-items:center;gap:.5rem;}}
  .method-badge{{font-size:.7rem;font-weight:700;padding:.2rem .45rem;border-radius:.25rem;text-transform:uppercase;}}
  .method-get{{background:#198754;color:#fff;}}.method-post{{background:#0d6efd;color:#fff;}}
  .method-delete{{background:#dc3545;color:#fff;}}.method-put{{background:#fd7e14;color:#fff;}}
  .method-patch{{background:#6f42c1;color:#fff;}}
  .response-box{{background:#1e1e2e;color:#a6e3a1;border-radius:.375rem;padding:.75rem;font-size:.78rem;white-space:pre-wrap;word-break:break-all;max-height:300px;overflow-y:auto;display:none;margin-top:.75rem;}}
  #health-badge{{font-size:.75rem;padding:.25rem .6rem;border-radius:1rem;}}
  .table-responsive table{{font-size:.85rem;}}
  #toast-container{{position:fixed;top:1rem;right:1rem;z-index:9999;}}
</style>
</head>
<body>

<!-- Sidebar -->
<nav id="sidebar">
  <div class="brand">
    <h5><i class="bi bi-grid-3x3-gap-fill me-2"></i>{app_title}</h5>
    <small>{app_desc}</small>
  </div>
  <div id="nav-links" class="mt-2"></div>
</nav>

<!-- Main -->
<div id="main">
  <div class="d-flex justify-content-between align-items-center mb-3">
    <h4 class="mb-0 fw-bold">{app_title}</h4>
    <span id="health-badge" class="badge bg-secondary"><i class="bi bi-circle-fill me-1"></i>Checking...</span>
  </div>
  <div id="panels"></div>
</div>

<!-- Toast container -->
<div id="toast-container"></div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
<script>
// ─── Utilities ────────────────────────────────────────────────────────────────

function toast(msg, ok) {{
  const id = 'toast_'+Date.now();
  const color = ok ? 'bg-success' : 'bg-danger';
  document.getElementById('toast-container').insertAdjacentHTML('beforeend',
    `<div id="${{id}}" class="toast align-items-center text-white ${{color}} border-0 show mb-2" role="alert">
       <div class="d-flex"><div class="toast-body">${{msg}}</div>
       <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div></div>`);
  setTimeout(() => document.getElementById(id)?.remove(), 3500);
}}

async function apiFetch(url, opts={{}}) {{
  try {{
    const r = await fetch(url, opts);
    const ct = r.headers.get('content-type') || '';
    const data = ct.includes('json') ? await r.json() : await r.text();
    return {{ok: r.ok, status: r.status, data}};
  }} catch(e) {{
    return {{ok: false, status: 0, data: {{detail: e.message}}}};
  }}
}}

function showResponse(boxId, data) {{
  const el = document.getElementById(boxId);
  if (!el) return;
  el.textContent = JSON.stringify(data, null, 2);
  el.style.display = 'block';
}}

function renderTable(tbodyId, rows) {{
  const el = document.getElementById(tbodyId);
  if (!el) return;
  if (!Array.isArray(rows)) rows = rows ? [rows] : [];
  if (rows.length === 0) {{ el.innerHTML = '<tr><td class="text-muted">No records found.</td></tr>'; return; }}
  const cols = Object.keys(rows[0]);
  // Build header in thead
  const thead = el.closest('table')?.querySelector('thead');
  if (thead) thead.innerHTML = '<tr>' + cols.map(c=>`<th>${{c}}</th>`).join('') + '</tr>';
  el.innerHTML = rows.map(r => '<tr>' + cols.map(c => `<td>${{r[c] ?? ''}}</td>`).join('') + '</tr>').join('');
}}

function showPanel(id) {{
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('#nav-links .nav-link').forEach(n => n.classList.remove('active'));
  const panel = document.getElementById('panel_' + id);
  if (panel) panel.classList.add('active');
  const link = document.querySelector(`[data-panel="${{id}}"]`);
  if (link) link.classList.add('active');
}}

// ─── Schema helpers ───────────────────────────────────────────────────────────

function resolveSchema(schema, components) {{
  if (!schema) return {{}};
  if (schema.$ref) {{
    const name = schema.$ref.split('/').pop();
    return components?.schemas?.[name] || {{}};
  }}
  return schema;
}}

function schemaProperties(schema, components) {{
  const resolved = resolveSchema(schema, components);
  const props = resolved.properties || {{}};
  const required = resolved.required || [];
  return Object.entries(props).map(([name, def]) => ({{
    name,
    type: def.type || 'string',
    format: def.format || '',
    description: def.description || '',
    required: required.includes(name),
    enum: def.enum || null,
  }}));
}}

function inputForProp(prop, fieldId) {{
  const req = prop.required ? 'required' : '';
  const label = prop.name.replace(/_/g,' ').replace(/\\b\\w/g,c=>c.toUpperCase());
  let input = '';
  if (prop.enum) {{
    const opts = prop.enum.map(v=>`<option value="${{v}}">${{v}}</option>`).join('');
    input = `<select class="form-select" id="${{fieldId}}" name="${{prop.name}}" ${{req}}><option value="">— select —</option>${{opts}}</select>`;
  }} else if (prop.type === 'boolean') {{
    input = `<select class="form-select" id="${{fieldId}}" name="${{prop.name}}"><option value="true">True</option><option value="false">False</option></select>`;
  }} else if (prop.type === 'integer' || prop.type === 'number') {{
    input = `<input type="number" class="form-control" id="${{fieldId}}" name="${{prop.name}}" placeholder="${{prop.description || prop.name}}" ${{req}}/>`;
  }} else if (prop.format === 'date-time' || prop.name.includes('_at') || prop.name.includes('date')) {{
    input = `<input type="datetime-local" class="form-control" id="${{fieldId}}" name="${{prop.name}}" ${{req}}/>`;
  }} else {{
    input = `<input type="text" class="form-control" id="${{fieldId}}" name="${{prop.name}}" placeholder="${{prop.description || prop.name}}" ${{req}}/>`;
  }}
  return `<div class="col-md-6 mb-2"><label class="form-label fw-semibold">${{label}}${{prop.required ? ' <span class=\\'text-danger\\'>*</span>' : ''}}</label>${{input}}</div>`;
}}

function collectFormData(formId) {{
  const form = document.getElementById(formId);
  if (!form) return {{}};
  const data = {{}};
  new FormData(form).forEach((v, k) => {{
    if (v === '') return;
    if (v === 'true') data[k] = true;
    else if (v === 'false') data[k] = false;
    else if (!isNaN(v) && v !== '') data[k] = +v;
    else data[k] = v;
  }});
  return data;
}}

// ─── Path parameter extraction ────────────────────────────────────────────────

function pathParams(path) {{
  return [...path.matchAll(/\\{{(\\w+)\\}}/g)].map(m => m[1]);
}}

function buildUrl(path, formId) {{
  let url = path;
  pathParams(path).forEach(p => {{
    const el = document.getElementById(formId + '_path_' + p);
    if (el) url = url.replace(`{{{{{p}}}}}`, encodeURIComponent(el.value));
  }});
  return url;
}}

// ─── Card builders ────────────────────────────────────────────────────────────

function makeCardId(method, path) {{
  return (method + path).replace(/[^a-zA-Z0-9]/g, '_');
}}

function buildPostCard(method, path, op, components) {{
  const cid = makeCardId(method, path);
  const formId = 'form_' + cid;
  const bodySchema = op.requestBody?.content?.['application/json']?.schema;
  const props = schemaProperties(bodySchema, components);
  const pathPs = pathParams(path);

  let pathInputs = pathPs.map(p =>
    `<div class="col-md-6 mb-2"><label class="form-label fw-semibold">${{p}} <span class="text-danger">*</span></label>` +
    `<input type="text" class="form-control" id="${{formId}}_path_${{p}}" placeholder="${{p}}" required/></div>`
  ).join('');

  let fieldInputs = props.map(p => inputForProp(p, formId + '_' + p.name)).join('');

  return `
<div class="endpoint-card">
  <div class="card-header bg-light">
    <span class="method-badge method-${{method}}">${{method}}</span>
    <code class="small">${{path}}</code>
    <span class="ms-2 text-muted small">${{op.summary || ''}}</span>
  </div>
  <div class="card-body">
    <div id="alert_${{cid}}"></div>
    <form id="${{formId}}" class="row">
      ${{pathInputs}}${{fieldInputs}}
      <div class="col-12 mt-2">
        <button type="submit" class="btn btn-primary btn-sm"><i class="bi bi-send me-1"></i>Submit</button>
      </div>
    </form>
    <div class="response-box" id="resp_${{cid}}"></div>
  </div>
</div>`;
}}

function buildGetCard(method, path, op, components) {{
  const cid = makeCardId(method, path);
  const formId = 'form_' + cid;
  const pathPs = pathParams(path);
  const queryParams = (op.parameters || []).filter(p => p.in === 'query');

  let pathInputs = pathPs.map(p =>
    `<div class="col-md-4 mb-2"><label class="form-label fw-semibold">${{p}} <span class="text-danger">*</span></label>` +
    `<input type="text" class="form-control form-control-sm" id="${{formId}}_path_${{p}}" placeholder="${{p}}"/></div>`
  ).join('');

  let queryInputs = queryParams.map(p =>
    `<div class="col-md-4 mb-2"><label class="form-label fw-semibold">${{p.name}}</label>` +
    `<input type="text" class="form-control form-control-sm" id="${{formId}}_q_${{p.name}}" placeholder="${{p.name}}"/></div>`
  ).join('');

  return `
<div class="endpoint-card">
  <div class="card-header bg-light">
    <span class="method-badge method-get">get</span>
    <code class="small">${{path}}</code>
    <span class="ms-2 text-muted small">${{op.summary || ''}}</span>
  </div>
  <div class="card-body">
    <div id="alert_${{cid}}"></div>
    ${{pathPs.length || queryParams.length ? `<form id="${{formId}}" class="row mb-2">${{pathInputs}}${{queryInputs}}</form>` : ''}}
    <button class="btn btn-success btn-sm" id="btn_${{cid}}"><i class="bi bi-arrow-clockwise me-1"></i>Load</button>
    <div class="table-responsive mt-2"><table class="table table-sm table-striped table-hover">
      <thead id="thead_${{cid}}"></thead><tbody id="tbody_${{cid}}"></tbody>
    </table></div>
    <div class="response-box" id="resp_${{cid}}"></div>
  </div>
</div>`;
}}

function buildDeleteCard(method, path, op) {{
  const cid = makeCardId(method, path);
  const formId = 'form_' + cid;
  const pathPs = pathParams(path);

  let pathInputs = pathPs.map(p =>
    `<div class="col-md-4 mb-2"><label class="form-label fw-semibold">${{p}} <span class="text-danger">*</span></label>` +
    `<input type="text" class="form-control form-control-sm" id="${{formId}}_path_${{p}}" placeholder="${{p}}" required/></div>`
  ).join('');

  return `
<div class="endpoint-card">
  <div class="card-header bg-light">
    <span class="method-badge method-delete">delete</span>
    <code class="small">${{path}}</code>
    <span class="ms-2 text-muted small">${{op.summary || ''}}</span>
  </div>
  <div class="card-body">
    <div id="alert_${{cid}}"></div>
    <form id="${{formId}}" class="row">${{pathInputs}}
      <div class="col-12 mt-2"><button type="submit" class="btn btn-danger btn-sm"><i class="bi bi-trash me-1"></i>Delete</button></div>
    </form>
    <div class="response-box" id="resp_${{cid}}"></div>
  </div>
</div>`;
}}

// ─── Event wiring ─────────────────────────────────────────────────────────────

function wireCard(method, path, op) {{
  const cid = makeCardId(method, path);
  const formId = 'form_' + cid;

  if (method === 'get') {{
    const btn = document.getElementById('btn_' + cid);
    if (!btn) return;
    btn.addEventListener('click', async () => {{
      btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
      let url = buildUrl(path, formId);
      // append query params
      const qInputs = document.querySelectorAll(`[id^="${{formId}}_q_"]`);
      const qs = [...qInputs].filter(e=>e.value).map(e=>`${{e.id.split('_q_')[1]}}=${{encodeURIComponent(e.value)}}`).join('&');
      if (qs) url += '?' + qs;
      const {{ok, data}} = await apiFetch(url);
      showResponse('resp_' + cid, data);
      const rows = Array.isArray(data) ? data : (data.items || data.results || (typeof data==='object'&&!data.detail ? [data] : []));
      const tbody = document.getElementById('tbody_' + cid);
      const thead = document.getElementById('thead_' + cid);
      if (tbody) renderTable('tbody_' + cid, rows);
      toast(ok ? `Loaded ${{rows.length}} record(s)` : (data.detail || 'Error'), ok);
      btn.disabled = false; btn.innerHTML = '<i class="bi bi-arrow-clockwise me-1"></i>Load';
    }});

  }} else if (method === 'delete') {{
    const form = document.getElementById(formId);
    if (!form) return;
    form.addEventListener('submit', async e => {{
      e.preventDefault();
      const url = buildUrl(path, formId);
      const {{ok, data}} = await apiFetch(url, {{method:'DELETE'}});
      showResponse('resp_' + cid, data);
      toast(ok ? 'Deleted successfully' : (data.detail || 'Error'), ok);
    }});

  }} else {{
    const form = document.getElementById(formId);
    if (!form) return;
    form.addEventListener('submit', async e => {{
      e.preventDefault();
      const url = buildUrl(path, formId);
      const body = collectFormData(formId);
      const {{ok, data}} = await apiFetch(url, {{
        method: method.toUpperCase(),
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify(body),
      }});
      showResponse('resp_' + cid, data);
      toast(ok ? 'Success!' : (data.detail || 'Error'), ok);
      if (ok) form.reset();
    }});
  }}
}}

// ─── Main bootstrap ───────────────────────────────────────────────────────────

async function init() {{
  // Health check
  const hb = document.getElementById('health-badge');
  const {{ok}} = await apiFetch('/health');
  hb.className = ok ? 'badge bg-success' : 'badge bg-danger';
  hb.innerHTML = `<i class="bi bi-circle-fill me-1"></i>${{ok ? 'API Online' : 'API Offline'}}`;

  // Load spec
  const {{data: spec}} = await apiFetch('/openapi.json');
  if (!spec || !spec.paths) {{ console.error('Could not load OpenAPI spec'); return; }}

  const components = spec.components || {{}};
  const paths = spec.paths;

  // Group routes by tag (use first tag or 'General')
  const groups = {{}};
  for (const [path, methods] of Object.entries(paths)) {{
    if (path === '/' || path.includes('health') || path.includes('openapi') || path.includes('docs') || path.includes('redoc')) continue;
    for (const [method, op] of Object.entries(methods)) {{
      if (['get','post','put','patch','delete'].indexOf(method) === -1) continue;
      const tag = (op.tags && op.tags[0]) || 'General';
      if (!groups[tag]) groups[tag] = [];
      groups[tag].push({{method, path, op}});
    }}
  }}

  const nav = document.getElementById('nav-links');
  const panels = document.getElementById('panels');
  let firstPanel = null;

  for (const [tag, endpoints] of Object.entries(groups)) {{
    const panelId = tag.replace(/[^a-zA-Z0-9]/g,'_');
    if (!firstPanel) firstPanel = panelId;

    // Nav link
    nav.insertAdjacentHTML('beforeend',
      `<div class="section-label">${{tag}}</div>` +
      `<a class="nav-link" data-panel="${{panelId}}" href="#" onclick="showPanel('${{panelId}}');return false;">` +
      `<i class="bi bi-grid me-2"></i>${{tag}}</a>`);

    // Panel
    let cards = '';
    for (const {{method, path, op}} of endpoints) {{
      if (method === 'get') cards += buildGetCard(method, path, op, components);
      else if (method === 'delete') cards += buildDeleteCard(method, path, op);
      else cards += buildPostCard(method, path, op, components);
    }}

    panels.insertAdjacentHTML('beforeend',
      `<div class="panel" id="panel_${{panelId}}">
         <h5 class="mb-3 fw-bold"><i class="bi bi-layers me-2"></i>${{tag}}</h5>
         ${{cards}}
       </div>`);

    // Wire events
    for (const {{method, path, op}} of endpoints) {{
      wireCard(method, path, op);
    }}
  }}

  if (firstPanel) showPanel(firstPanel);
}}

document.addEventListener('DOMContentLoaded', init);
</script>
</body>
</html>
'''


class FrontendAgent(BaseAgent):

    def __init__(self, db_session: Optional[Session] = None, project_id: Optional[int] = None):
        system_prompt = "You generate web frontends for FastAPI apps."
        super().__init__(
            name="FrontendAgent",
            system_prompt=system_prompt,
            agent_role=AgentRole.FRONTEND,
            db_session=db_session,
            project_id=project_id,
        )

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        project_id = context.get("project_id", self.project_id)
        if not project_id:
            raise ValueError("project_id required")

        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project {project_id} not found")

        if context.get("skip_existing", False):
            existing = self.db.query(Artifact).filter(
                Artifact.project_id == project_id,
                Artifact.artifact_type == ArtifactType.FRONTEND,
            ).count()
            if existing > 0:
                print(f"[FrontendAgent] Skipping - frontend artifacts already exist")
                arts = self.db.query(Artifact).filter(
                    Artifact.project_id == project_id,
                    Artifact.artifact_type == ArtifactType.FRONTEND,
                ).all()
                return {"project_id": project_id, "generated_frontend": [
                    {"id": a.id, "name": a.name, "file_path": a.file_path} for a in arts
                ]}

        output_dir = f"output/project_{project_id}/code"
        os.makedirs(output_dir, exist_ok=True)

        print(f"[FrontendAgent] Generating spec-driven frontend for: {project.name}")

        brand_color = self._pick_brand_color(project.name)
        template = _TEMPLATE_PATH.read_text(encoding="utf-8")
        html_content = (
            template
            .replace("__APP_TITLE__", project.name)
            .replace("__APP_DESC__", project.description or project.domain or "")
            .replace("__BRAND_COLOR__", brand_color)
        )

        html_path = os.path.join(output_dir, "static", "index.html")
        os.makedirs(os.path.dirname(html_path), exist_ok=True)
        artifact = self.save_artifact(
            filepath=html_path,
            content=html_content,
            artifact_type=ArtifactType.FRONTEND,
            metadata={"filename": "index.html", "project_name": project.name},
        )

        main_path = os.path.join(output_dir, "main.py")
        if os.path.exists(main_path):
            self._patch_main(main_path)

        generated = []
        if artifact:
            generated.append({"id": artifact.id, "name": artifact.name, "file_path": artifact.file_path})

        self.log_activity("generate_frontend", {
            "project_id": project_id,
            "files": ["static/index.html"],
        })
        return {"project_id": project_id, "project_name": project.name, "generated_frontend": generated}

    def _pick_brand_color(self, name: str) -> str:
        colors = ["#0d6efd", "#198754", "#6f42c1", "#0dcaf0", "#d63384", "#fd7e14", "#20c997"]
        return colors[sum(ord(c) for c in name) % len(colors)]

    def _patch_main(self, main_path: str) -> None:
        content = Path(main_path).read_text(encoding="utf-8")
        if "StaticFiles" in content:
            return

        patch = '''
# ── Frontend static files ──────────────────────────────────────────────────
import os as _os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

_static_dir = _os.path.join(_os.path.dirname(__file__), "static")
if _os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

    @app.get("/", include_in_schema=False)
    def serve_frontend():
        return FileResponse(_os.path.join(_static_dir, "index.html"))
'''
        with open(main_path, "a", encoding="utf-8") as f:
            f.write(patch)
        print(f"[FrontendAgent] Patched main.py to serve static/index.html at /")
