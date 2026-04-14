"""`keel view` — read-only HTML project viewer.

Generates a single static HTML page with the concept graph, issues,
and critical path, then serves it on localhost. This is the human
brief-in surface — agents use the CLI, humans get a 30-second visual.

Read-only by design. No forms, no state mutations, no backend.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import click

from keel.core.concept_graph import build_full_graph
from keel.core.dependency_graph import build_dependency_graph
from keel.core.store import (
    ProjectNotFoundError,
    list_issues,
    load_project,
)


def _build_page(project_dir: Path) -> str:
    """Generate the full HTML page as a string."""
    project = load_project(project_dir)
    issues = list_issues(project_dir)
    graph = build_full_graph(project_dir)
    dep_graph = build_dependency_graph(issues)

    graph_json = json.dumps(graph.model_dump(mode="json", by_alias=True), indent=2)
    issues_json = json.dumps(
        [
            {
                "id": i.id,
                "title": i.title,
                "status": i.status,
                "priority": i.priority,
                "executor": i.executor,
                "blocked_by": i.blocked_by,
            }
            for i in issues
        ],
        indent=2,
    )
    critical_path_json = json.dumps(dep_graph.critical_path)

    return (
        _HTML_TEMPLATE.replace("{{PROJECT_NAME}}", project.name)
        .replace("{{GRAPH_DATA}}", graph_json)
        .replace("{{ISSUES_DATA}}", issues_json)
        .replace("{{CRITICAL_PATH}}", critical_path_json)
    )


class _SinglePageHandler(SimpleHTTPRequestHandler):
    """Serve one HTML page for any request path."""

    html_content: bytes = b""

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(self.html_content)))
        self.end_headers()
        self.wfile.write(self.html_content)

    def log_message(self, format: str, *args: object) -> None:
        pass  # suppress request logs


@click.command(name="view")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
    help="Path to the project root.",
)
@click.option("--port", default=7777, show_default=True, help="Port to serve on.")
@click.option(
    "--open", "open_browser", is_flag=True, help="Open browser automatically."
)
def view_cmd(project_dir: Path, port: int, open_browser: bool) -> None:
    """Serve a read-only HTML view of the project.

    Shows the concept graph, issues by status, and critical path in a
    single static page. Ctrl+C to stop.
    """
    resolved = project_dir.expanduser().resolve()
    click.echo("Building project view…")
    try:
        html = _build_page(resolved)
    except ProjectNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    handler = type(
        "Handler",
        (_SinglePageHandler,),
        {"html_content": html.encode("utf-8")},
    )

    server = HTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}"
    click.echo(f"Serving project view at {url}")
    click.echo("Press Ctrl+C to stop.")

    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=[url]).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        click.echo("\nStopped.")
    finally:
        server.server_close()


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{PROJECT_NAME}} — Keel View</title>
<script src="https://unpkg.com/cytoscape@3.28.1/dist/cytoscape.min.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0d1117; color: #c9d1d9; padding: 24px; }
  h1 { font-size: 1.5rem; margin-bottom: 8px; color: #58a6ff; }
  h2 { font-size: 1.1rem; margin: 24px 0 8px; color: #8b949e; }
  .subtitle { color: #8b949e; font-size: 0.85rem; margin-bottom: 24px; }
  #cy { width: 100%; height: 400px; background: #161b22; border-radius: 8px;
         border: 1px solid #30363d; margin-bottom: 24px; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 24px; }
  th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid #21262d; }
  th { color: #8b949e; font-size: 0.8rem; text-transform: uppercase; }
  .status { display: inline-block; padding: 2px 8px; border-radius: 12px;
            font-size: 0.75rem; font-weight: 600; }
  .status-todo { background: #1f6feb33; color: #58a6ff; }
  .status-in_progress { background: #d29922; color: #0d1117; }
  .status-done { background: #238636; color: #fff; }
  .status-blocked { background: #f8514933; color: #f85149; }
  .status-backlog { background: #30363d; color: #8b949e; }
  .critical-path { color: #d2a8ff; font-size: 0.9rem; margin: 12px 0; }
  .footer { color: #484f58; font-size: 0.75rem; margin-top: 40px; text-align: center; }
</style>
</head>
<body>
<h1>{{PROJECT_NAME}}</h1>
<p class="subtitle">Keel project view — read-only</p>

<h2>Concept Graph</h2>
<div id="cy"></div>

<h2>Issues</h2>
<table>
<thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Priority</th><th>Executor</th></tr></thead>
<tbody id="issues-body"></tbody>
</table>

<div id="critical-path-section"></div>

<p class="footer">Generated by <code>keel view</code>. Read-only.</p>

<script>
const graphData = {{GRAPH_DATA}};
const issuesData = {{ISSUES_DATA}};
const criticalPath = {{CRITICAL_PATH}};

// Render Cytoscape graph
const elements = [];
(graphData.nodes || []).forEach(n => {
  elements.push({ data: { id: n.id, label: n.label || n.id, kind: n.kind } });
});
(graphData.edges || []).forEach(e => {
  const fromId = e['from'] || e.from_id;
  const toId = e['to'] || e.to_id;
  elements.push({ data: { source: fromId, target: toId, label: e.type } });
});

if (elements.length > 0) {
  cytoscape({
    container: document.getElementById('cy'),
    elements: elements,
    style: [
      { selector: 'node', style: {
        'label': 'data(label)', 'color': '#c9d1d9', 'font-size': '10px',
        'background-color': '#238636', 'text-valign': 'bottom',
        'text-margin-y': 4, 'width': 20, 'height': 20
      }},
      { selector: 'node[kind="node"]', style: { 'background-color': '#1f6feb', 'shape': 'diamond' }},
      { selector: 'edge', style: {
        'width': 1, 'line-color': '#30363d', 'target-arrow-color': '#30363d',
        'target-arrow-shape': 'triangle', 'curve-style': 'bezier',
        'label': 'data(label)', 'font-size': '8px', 'color': '#484f58'
      }}
    ],
    layout: { name: 'cose', animate: false, nodeDimensionsIncludeLabels: true }
  });
} else {
  document.getElementById('cy').innerHTML = '<p style="padding:40px;color:#8b949e">No graph data.</p>';
}

// Render issues table
const tbody = document.getElementById('issues-body');
issuesData.forEach(i => {
  const cls = 'status-' + i.status.replace(/ /g, '_');
  const row = `<tr>
    <td><strong>${i.id}</strong></td>
    <td>${i.title}</td>
    <td><span class="status ${cls}">${i.status}</span></td>
    <td>${i.priority}</td>
    <td>${i.executor}</td>
  </tr>`;
  tbody.innerHTML += row;
});
if (issuesData.length === 0) {
  tbody.innerHTML = '<tr><td colspan="5" style="color:#484f58">No issues yet.</td></tr>';
}

// Critical path
if (criticalPath.length > 0) {
  const section = document.getElementById('critical-path-section');
  section.innerHTML = '<h2>Critical Path</h2><p class="critical-path">' +
    criticalPath.join(' → ') + '</p>';
}
</script>
</body>
</html>
"""
