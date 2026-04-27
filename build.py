#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
import re
import shutil
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
DIST = ROOT / "dist"
SYNC_STATUS_PATH = ROOT / "sync-status.json"


@dataclass
class Note:
    source_path: Path
    relative_path: str
    file_stem: str
    slug: str
    title: str
    area: str
    date: str
    summary: str
    topic: str
    folder: str
    tags: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    raw_body: str = ""
    content_html: str = ""
    excerpt: str = ""


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_sync_status() -> dict[str, Any]:
    if not SYNC_STATUS_PATH.exists():
        return {}
    return json.loads(SYNC_STATUS_PATH.read_text(encoding="utf-8"))


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = value.strip().lower()
    value = re.sub(r"\[\[|\]\]", "", value)
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE)
    value = re.sub(r"[-\s]+", "-", value)
    return value.strip("-") or "nota"


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    return value


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text

    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, text

    raw = parts[0][4:]
    body = parts[1]
    lines = raw.splitlines()
    data: dict[str, Any] = {}
    i = 0

    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        if ":" not in line:
            i += 1
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        if value in {"|", ">"}:
            block: list[str] = []
            i += 1
            while i < len(lines):
                candidate = lines[i]
                if candidate.startswith("  ") or not candidate.strip():
                    block.append(candidate[2:] if candidate.startswith("  ") else "")
                    i += 1
                    continue
                break
            if value == ">":
                data[key] = " ".join(part.strip() for part in block if part.strip()).strip()
            else:
                data[key] = "\n".join(block).strip()
            continue

        if value == "":
            items: list[str] = []
            j = i + 1
            while j < len(lines):
                candidate = lines[j]
                stripped = candidate.strip()
                if stripped.startswith("- "):
                    items.append(parse_scalar(stripped[2:]))
                    j += 1
                    continue
                if not stripped:
                    j += 1
                    continue
                break
            data[key] = items
            i = j
            continue

        data[key] = parse_scalar(value)
        i += 1

    return data, body


def strip_wikilink_markup(value: str) -> str:
    cleaned = value.strip()
    if cleaned.startswith("[[") and cleaned.endswith("]]"):
        cleaned = cleaned[2:-2]
    if "|" in cleaned:
        cleaned = cleaned.split("|", 1)[0]
    return cleaned.strip()


def extract_wikilinks(text: str) -> list[str]:
    found: list[str] = []
    for match in re.findall(r"\[\[([^\]]+)\]\]", text):
        found.append(strip_wikilink_markup(match))
    return found


def inline_markdown(text: str, note_lookup: dict[str, str]) -> str:
    escaped = html.escape(text)

    def replace_wikilink(match: re.Match[str]) -> str:
        raw_target = match.group(1)
        label = match.group(2) or raw_target
        target = strip_wikilink_markup(raw_target).lower()
        href = note_lookup.get(target)
        safe_label = html.escape(label)
        if href:
            return f'<a href="{href}">{safe_label}</a>'
        return f'<span class="broken-link">{safe_label}</span>'

    escaped = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", replace_wikilink, escaped)
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>',
        escaped,
    )
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
    return escaped


def render_markdown(body: str, note_lookup: dict[str, str]) -> str:
    lines = body.splitlines()
    out: list[str] = []
    paragraph: list[str] = []
    in_list = False
    in_quote = False

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            joined = " ".join(part.strip() for part in paragraph).strip()
            out.append(f"<p>{inline_markdown(joined, note_lookup)}</p>")
            paragraph = []

    def close_blocks() -> None:
        nonlocal in_list, in_quote
        if in_list:
            out.append("</ul>")
            in_list = False
        if in_quote:
            out.append("</blockquote>")
            in_quote = False

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            close_blocks()
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            flush_paragraph()
            close_blocks()
            level = len(heading.group(1))
            out.append(f"<h{level}>{inline_markdown(heading.group(2), note_lookup)}</h{level}>")
            continue

        if stripped == ">" or stripped.startswith("> "):
            flush_paragraph()
            if in_list:
                out.append("</ul>")
                in_list = False
            if not in_quote:
                out.append("<blockquote>")
                in_quote = True
            quote_text = stripped[1:].strip()
            if quote_text:
                out.append(f"<p>{inline_markdown(quote_text, note_lookup)}</p>")
            continue

        if in_quote:
            out.append("</blockquote>")
            in_quote = False

        if re.match(r"^- ", stripped):
            flush_paragraph()
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{inline_markdown(stripped[2:], note_lookup)}</li>")
            continue

        if in_list:
            out.append("</ul>")
            in_list = False

        paragraph.append(stripped)

    flush_paragraph()
    close_blocks()
    return "\n".join(out)


def read_notes(vault_path: Path) -> list[Note]:
    notes: list[Note] = []

    for path in sorted(vault_path.rglob("*.md")):
        if ".obsidian" in path.parts:
            continue

        text = path.read_text(encoding="utf-8")
        frontmatter, body = parse_frontmatter(text)
        title = str(frontmatter.get("title") or path.stem)
        summary = str(frontmatter.get("summary") or "")
        topic = str(frontmatter.get("topic") or "")
        excerpt_source = summary or topic or body.strip().split("\n", 1)[0]
        excerpt_source = re.sub(r"^\s*>\s*", "", excerpt_source)
        excerpt_source = re.sub(r"\s+", " ", excerpt_source).strip()
        relative_path = str(path.relative_to(vault_path)).replace("\\", "/")

        notes.append(
            Note(
                source_path=path,
                relative_path=relative_path,
                file_stem=path.stem,
                slug=slugify(path.stem),
                title=title,
                area=str(frontmatter.get("area") or "Sem area"),
                date=str(frontmatter.get("date") or ""),
                summary=summary,
                topic=topic,
                folder=str(frontmatter.get("folder") or ""),
                tags=[str(tag) for tag in frontmatter.get("tags", [])],
                related=[strip_wikilink_markup(str(item)) for item in frontmatter.get("related", [])],
                links=extract_wikilinks(body),
                raw_body=body,
                excerpt=excerpt_source[:260],
            )
        )

    return notes


def build_lookup(notes: list[Note]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for note in notes:
        href = f"notes/{note.slug}.html"
        lookup[note.file_stem.lower()] = href
        lookup[note.title.lower()] = href
    return lookup


def page_template(title: str, content: str) -> str:
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Serif:wght@400;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../assets/styles.css">
</head>
<body>
<div class="grain"></div>
{content}
</body>
</html>
"""


def index_template(content: str, site_name: str) -> str:
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(site_name)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Serif:wght@400;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="assets/styles.css">
</head>
<body>
<div class="grain"></div>
{content}
<script src="assets/app.js"></script>
</body>
</html>
"""


def note_card(note: Note) -> str:
    tags = "".join(f'<span class="tag">#{html.escape(tag)}</span>' for tag in note.tags[:6])
    summary = html.escape(note.summary or note.excerpt)
    return f"""
    <article class="card note-card" data-title="{html.escape(note.title.lower())}" data-area="{html.escape(note.area.lower())}" data-tags="{html.escape(' '.join(note.tags).lower())}">
      <div class="card-meta">
        <span>{html.escape(note.area)}</span>
        <span>{html.escape(note.date)}</span>
      </div>
      <h3><a href="notes/{note.slug}.html">{html.escape(note.title)}</a></h3>
      <p>{summary}</p>
      <div class="tags">{tags}</div>
    </article>
    """


def build_graph_data(notes: list[Note], lookup: dict[str, str]) -> dict[str, Any]:
    node_ids = {note.title.lower(): note.slug for note in notes}
    nodes = []
    edges: set[tuple[str, str]] = set()

    for note in notes:
        nodes.append(
            {
                "id": note.slug,
                "title": note.title,
                "area": note.area,
                "url": f"notes/{note.slug}.html",
                "tags": note.tags[:8],
            }
        )

        targets = note.related + note.links
        for raw_target in targets:
            target_slug = node_ids.get(raw_target.lower())
            if not target_slug or target_slug == note.slug:
                continue
            edge = tuple(sorted((note.slug, target_slug)))
            edges.add(edge)

    return {
        "nodes": nodes,
        "edges": [{"source": source, "target": target} for source, target in sorted(edges)],
    }


def build_graph_page(site_name: str) -> None:
    content = f"""
<main class="app-shell">
  <aside class="sidebar">
    <div class="sidebar-block brand-block">
      <span class="sidebar-label">Vault</span>
      <h1>{html.escape(site_name)}</h1>
      <p>Visualizacao de conexoes entre notas, em um grafo interativo inspirado no Obsidian.</p>
    </div>
    <div class="sidebar-block">
      <span class="sidebar-label">Navegacao</span>
      <a class="nav-link" href="index.html">Biblioteca</a>
      <a class="nav-link" href="notes/00-dashboard-biblioteca.html">Dashboard</a>
    </div>
    <div class="sidebar-block">
      <span class="sidebar-label">Uso</span>
      <p class="sidebar-text">Arraste os nos, use a busca para destacar uma nota e clique para abrir.</p>
    </div>
  </aside>
  <section class="main-column">
    <header class="hero">
      <div class="hero-copy">
        <span class="eyebrow">Graph View</span>
        <h1>Mapa de conexoes</h1>
        <p>As ligacoes sao geradas a partir de links `[[...]]` e do campo `related:` do frontmatter.</p>
      </div>
    </header>
    <section class="toolbar card">
      <label for="graph-search">Buscar no grafo</label>
      <input id="graph-search" type="search" placeholder="Digite o nome da nota">
      <p class="helper">A busca destaca o no correspondente e suas ligacoes.</p>
    </section>
    <section class="card graph-card">
      <div class="graph-meta">
        <strong>Graph View</strong>
        <div class="graph-controls">
          <button type="button" class="graph-button" data-graph-action="fit">Centralizar</button>
          <button type="button" class="graph-button" data-graph-action="labels">Rotulos</button>
          <span id="graph-stats">Carregando...</span>
        </div>
      </div>
      <div id="graph-view" class="graph-view"></div>
    </section>
  </section>
</main>
"""
    graph_page = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(site_name)} - Graph</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Serif:wght@400;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="assets/styles.css">
</head>
<body>
<div class="grain"></div>
{content}
<script src="https://unpkg.com/cytoscape@3.30.2/dist/cytoscape.min.js"></script>
<script>window.OBSIDIAN_GRAPH = true;</script>
<script src="assets/app.js"></script>
</body>
</html>
"""
    (DIST / "graph.html").write_text(graph_page, encoding="utf-8")


def build_note_pages(notes: list[Note], lookup: dict[str, str], site_name: str) -> None:
    notes_dir = DIST / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)

    for note in notes:
        note.content_html = render_markdown(note.raw_body, lookup)
        related_links = []
        for item in note.related:
            href = lookup.get(item.lower())
            if href:
                related_links.append(f'<li><a href="../{href}">{html.escape(item)}</a></li>')
        related_html = ""
        if related_links:
            related_html = "<section class=\"related\"><h2>Relacionadas</h2><ul>" + "".join(related_links) + "</ul></section>"

        tags = "".join(f'<span class="tag">#{html.escape(tag)}</span>' for tag in note.tags)
        summary_html = f"<p class=\"lead\">{html.escape(note.summary)}</p>" if note.summary else ""
        topic_html = f"<p class=\"topic\"><strong>Tema:</strong> {html.escape(note.topic)}</p>" if note.topic else ""
        folder_html = f"<p class=\"topic\"><strong>Pasta lógica:</strong> {html.escape(note.folder)}</p>" if note.folder else ""

        content = f"""
<main class="app-shell">
  <aside class="sidebar">
    <div class="sidebar-block brand-block">
      <span class="sidebar-label">Vault</span>
      <h1>{html.escape(site_name)}</h1>
      <p>Versao web inspirada no Obsidian.</p>
      <a class="button primary" href="../index.html">Biblioteca</a>
    </div>
    <div class="sidebar-block">
      <span class="sidebar-label">Navegacao</span>
      <a class="nav-link" href="../index.html">Inicio</a>
      <a class="nav-link" href="../notes/00-dashboard-biblioteca.html">Dashboard</a>
    </div>
    <div class="sidebar-block">
      <span class="sidebar-label">Nota atual</span>
      <p class="sidebar-text">{html.escape(note.title)}</p>
      <p class="sidebar-text">{html.escape(note.area)}</p>
    </div>
  </aside>
  <section class="main-column">
  <a class="back-link" href="../index.html">← Voltar para a biblioteca</a>
  <article class="note-shell">
    <header class="hero note-hero">
      <div class="hero-copy">
        <span class="eyebrow">{html.escape(note.area)}</span>
        <h1>{html.escape(note.title)}</h1>
        <div class="hero-meta">
          <span>{html.escape(note.date)}</span>
          <span>{html.escape(note.relative_path)}</span>
        </div>
        {summary_html}
        {topic_html}
        {folder_html}
        <div class="tags">{tags}</div>
      </div>
    </header>
    <section class="note-content">
      {note.content_html}
    </section>
    {related_html}
  </article>
  </section>
</main>
"""
        (notes_dir / f"{note.slug}.html").write_text(page_template(note.title, content), encoding="utf-8")


def build_index(notes: list[Note], site_name: str, sync_status: dict[str, Any]) -> None:
    by_area: dict[str, list[Note]] = defaultdict(list)
    all_tags: dict[str, int] = defaultdict(int)

    for note in notes:
        by_area[note.area].append(note)
        for tag in note.tags:
            all_tags[tag] += 1

    area_sections = []
    for area, area_notes in sorted(by_area.items()):
        cards = "".join(note_card(note) for note in sorted(area_notes, key=lambda n: n.title.lower()))
        area_sections.append(
            f"""
            <section class="section-block" id="area-{slugify(area)}">
              <div class="section-head">
                <h2>{html.escape(area)}</h2>
                <span>{len(area_notes)} notas</span>
              </div>
              <div class="card-grid">
                {cards}
              </div>
            </section>
            """
        )

    top_tags = sorted(all_tags.items(), key=lambda item: (-item[1], item[0]))[:18]
    tag_cloud = "".join(f'<span class="tag large">#{html.escape(tag)} <small>{count}</small></span>' for tag, count in top_tags)
    quick_links = "".join(
        f'<a class="nav-link" href="#area-{slugify(area)}">{html.escape(area)} <span>{len(area_notes)}</span></a>'
        for area, area_notes in sorted(by_area.items())
    )
    last_sync = str(sync_status.get("last_sync_local") or "Ainda não publicado automaticamente")
    last_commit = str(sync_status.get("last_commit") or "—")

    content = f"""
<main class="app-shell">
  <aside class="sidebar">
    <div class="sidebar-block brand-block">
      <span class="sidebar-label">Vault</span>
      <h1>{html.escape(site_name)}</h1>
      <p>Acesso web ao seu cofre do Obsidian, pensado para consulta fora de casa.</p>
    </div>
    <div class="sidebar-block">
      <span class="sidebar-label">Atalhos</span>
      <a class="nav-link" href="notes/00-dashboard-biblioteca.html">Dashboard principal</a>
      <a class="nav-link" href="graph.html">Graph View</a>
      {quick_links}
    </div>
    <div class="sidebar-block metrics-stack">
      <div class="metric"><strong>{len(notes)}</strong><span>notas</span></div>
      <div class="metric"><strong>{len(by_area)}</strong><span>areas</span></div>
      <div class="metric"><strong>{sum(1 for _ in all_tags)}</strong><span>tags</span></div>
    </div>
    <div class="sidebar-block">
      <span class="sidebar-label">Sincronizacao</span>
      <p class="sidebar-text"><strong>Ultima publicacao:</strong> {html.escape(last_sync)}</p>
      <p class="sidebar-text"><strong>Commit:</strong> {html.escape(last_commit)}</p>
    </div>
  </aside>
  <section class="main-column">
  <header class="hero">
    <div class="hero-copy">
      <span class="eyebrow">Biblioteca Web</span>
      <h1>Leitura, busca e conexoes</h1>
      <p>Versao web do vault do Obsidian com visual mais proximo de workspace, organizacao por area, busca no navegador e paginas individuais para cada nota.</p>
      <div class="hero-actions">
        <a class="button primary" href="#colecao">Explorar biblioteca</a>
        <a class="button" href="notes/00-dashboard-biblioteca.html">Abrir dashboard</a>
        <a class="button" href="graph.html">Abrir grafo</a>
      </div>
    </div>
  </header>

  <section class="toolbar card">
    <label for="search">Buscar</label>
    <input id="search" type="search" placeholder="Título, área ou tag">
    <p class="helper">Filtra os cartões em tempo real. Ideal para uso no celular.</p>
  </section>

  <section class="card">
    <div class="section-head">
      <h2>Tags em destaque</h2>
      <span>{len(top_tags)} mais usadas</span>
    </div>
    <div class="tags">{tag_cloud}</div>
  </section>

  <section id="colecao">
    {''.join(area_sections)}
  </section>
  </section>
</main>
"""

    html_output = index_template(content, site_name)
    (DIST / "index.html").write_text(html_output, encoding="utf-8")
    (DIST / "404.html").write_text(html_output, encoding="utf-8")


def write_assets() -> None:
    assets = DIST / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    styles = r"""
:root {
  --bg: #101418;
  --bg-alt: #171e24;
  --surface: rgba(24, 31, 39, 0.84);
  --surface-strong: #1c242d;
  --sidebar: rgba(16, 20, 24, 0.92);
  --text: #d9e1ea;
  --muted: #93a1b2;
  --accent: #7caa6d;
  --accent-2: #8fb5ff;
  --border: rgba(217, 225, 234, 0.08);
  --shadow: 0 18px 48px rgba(0, 0, 0, 0.34);
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  color: var(--text);
  background:
    radial-gradient(circle at top left, rgba(143, 181, 255, 0.1), transparent 25%),
    radial-gradient(circle at top right, rgba(124, 170, 109, 0.08), transparent 25%),
    linear-gradient(180deg, #0d1217 0%, var(--bg) 100%);
  font-family: "IBM Plex Sans", sans-serif;
}
.grain {
  position: fixed;
  inset: 0;
  pointer-events: none;
  opacity: 0.05;
  background-image: radial-gradient(#ffffff 0.6px, transparent 0.6px);
  background-size: 8px 8px;
}
a { color: inherit; }
.app-shell {
  width: min(1440px, calc(100% - 28px));
  margin: 0 auto;
  padding: 22px 0 42px;
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 18px;
}
.main-column {
  min-width: 0;
}
.hero, .card, .note-shell, .sidebar {
  background: var(--surface);
  backdrop-filter: blur(12px);
  border: 1px solid var(--border);
  border-radius: 20px;
  box-shadow: var(--shadow);
}
.sidebar {
  position: sticky;
  top: 18px;
  align-self: start;
  padding: 18px;
  background: var(--sidebar);
}
.sidebar h1 {
  margin: 6px 0 8px;
  font: 600 1.4rem "IBM Plex Serif", serif;
}
.sidebar p {
  color: var(--muted);
  line-height: 1.55;
}
.sidebar-block + .sidebar-block {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid var(--border);
}
.sidebar-label {
  display: inline-block;
  margin-bottom: 8px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 0.75rem;
  font-weight: 700;
}
.nav-link {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 12px;
  color: var(--text);
  text-decoration: none;
}
.nav-link:hover {
  background: rgba(255, 255, 255, 0.04);
}
.nav-link span {
  color: var(--muted);
}
.sidebar-text {
  margin: 0 0 8px;
}
.hero {
  padding: 28px;
  margin-bottom: 24px;
}
.hero-copy h1, .note-hero h1 {
  margin: 8px 0 14px;
  font: 600 clamp(2rem, 5vw, 3.6rem) "IBM Plex Serif", serif;
  line-height: 1.02;
}
.hero-copy p, .lead {
  color: var(--muted);
  font-size: 1.05rem;
  line-height: 1.65;
}
.eyebrow {
  display: inline-block;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(124, 170, 109, 0.12);
  color: #bfe1b3;
  font-size: 0.82rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.hero-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 20px;
}
.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  padding: 0 18px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface-strong);
  text-decoration: none;
  font-weight: 600;
}
.button.primary {
  background: var(--accent);
  color: #102016;
}
.metrics-stack { display: grid; gap: 12px; }
.metric {
  padding: 16px;
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.02));
  border: 1px solid var(--border);
}
.metric strong {
  display: block;
  font-size: 1.8rem;
  line-height: 1;
}
.metric span, .helper, .card-meta, .hero-meta, .section-head span, .topic {
  color: var(--muted);
}
.toolbar, .card {
  padding: 20px;
  margin-bottom: 18px;
}
.toolbar label {
  display: block;
  margin-bottom: 10px;
  font-weight: 700;
}
.toolbar input {
  width: 100%;
  min-height: 52px;
  border-radius: 16px;
  border: 1px solid var(--border);
  padding: 0 16px;
  font-size: 1rem;
  color: var(--text);
  background: rgba(10, 14, 18, 0.55);
}
.section-block { margin-bottom: 24px; }
.section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin: 0 0 14px;
}
.section-head h2 {
  margin: 0;
  font-size: 1.5rem;
}
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 18px;
}
.note-card {
  padding: 18px;
  transition: transform 180ms ease, border-color 180ms ease;
  background: rgba(18, 24, 31, 0.78);
}
.note-card:hover {
  transform: translateY(-3px);
  border-color: rgba(143, 181, 255, 0.28);
}
.note-card h3 {
  margin: 10px 0;
  font-size: 1.15rem;
  line-height: 1.25;
}
.note-card h3 a {
  text-decoration: none;
}
.note-card p {
  color: var(--muted);
  line-height: 1.55;
}
.card-meta, .hero-meta {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 0.9rem;
}
.tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 14px;
}
.tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(124, 170, 109, 0.12);
  color: #c4e7b8;
  font-size: 0.84rem;
}
.tag.large {
  min-height: 36px;
  padding: 0 14px;
}
.tag small {
  font-size: 0.76rem;
  opacity: 0.7;
}
.back-link {
  display: inline-block;
  margin: 0 0 16px;
  text-decoration: none;
  color: #b7d0ff;
  font-weight: 700;
}
.note-shell { overflow: hidden; }
.note-hero {
  border-radius: 0;
  box-shadow: none;
  border: 0;
  padding: 32px;
  margin: 0;
  background:
    linear-gradient(135deg, rgba(124, 170, 109, 0.08), rgba(143, 181, 255, 0.08)),
    rgba(12, 17, 22, 0.25);
}
.note-content, .related {
  padding: 0 32px 32px;
}
.note-content h2, .note-content h3 {
  margin-top: 28px;
  font-family: "IBM Plex Serif", serif;
}
.note-content p, .note-content li, .note-content blockquote {
  line-height: 1.75;
}
.note-content blockquote {
  margin: 18px 0;
  padding: 4px 0 4px 18px;
  border-left: 3px solid var(--accent-2);
  color: var(--muted);
}
.note-content code {
  padding: 2px 6px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.08);
}
.broken-link {
  color: #ffb480;
  text-decoration: underline dotted;
}
.graph-card {
  min-height: 72vh;
}
.graph-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 14px;
}
.graph-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.graph-button {
  border: 1px solid var(--border);
  background: rgba(255,255,255,0.04);
  color: var(--text);
  border-radius: 999px;
  min-height: 34px;
  padding: 0 12px;
  cursor: pointer;
}
.graph-button:hover {
  background: rgba(255,255,255,0.08);
}
.graph-view {
  width: 100%;
  height: 68vh;
  border-radius: 16px;
  border: 1px solid var(--border);
  background:
    radial-gradient(circle at center, rgba(143, 181, 255, 0.06), transparent 40%),
    rgba(8, 12, 16, 0.82);
  overflow: hidden;
  position: relative;
}
@media (max-width: 980px) {
  .app-shell {
    grid-template-columns: 1fr;
  }
  .sidebar {
    position: static;
  }
}
@media (max-width: 640px) {
  .app-shell { width: min(100% - 16px, 1440px); padding-top: 14px; }
  .sidebar, .hero, .toolbar, .card, .note-hero, .note-content, .related { padding-left: 16px; padding-right: 16px; }
  .hero-copy h1, .note-hero h1 { line-height: 1.04; }
}
"""
    script = r"""
const search = document.querySelector("#search");
const cards = [...document.querySelectorAll(".note-card")];

if (search) {
  search.addEventListener("input", (event) => {
    const term = event.target.value.trim().toLowerCase();
    for (const card of cards) {
      const haystack = [
        card.dataset.title || "",
        card.dataset.area || "",
        card.dataset.tags || ""
      ].join(" ");
      card.style.display = haystack.includes(term) ? "" : "none";
    }
  });
}

async function initGraph() {
  if (!window.OBSIDIAN_GRAPH || !window.cytoscape) return;

  const container = document.querySelector("#graph-view");
  const stats = document.querySelector("#graph-stats");
  const searchInput = document.querySelector("#graph-search");
  if (!container) return;

  const response = await fetch("assets/graph.json");
  const graph = await response.json();
  const actionButtons = [...document.querySelectorAll("[data-graph-action]")];
  let showLabels = true;
  const areaPalette = {
    studies: "#8fb5ff",
    business: "#ffb480",
    system: "#7caa6d",
    "sem area": "#b9b9b9",
  };

  stats.textContent = `${graph.nodes.length} notas, ${graph.edges.length} conexoes`;
  const elements = [
    ...graph.nodes.map((node) => ({
      data: {
        id: node.id,
        label: node.title,
        area: node.area,
        url: node.url,
        areaKey: (node.area || "").toLowerCase(),
        color: areaPalette[(node.area || "").toLowerCase()] || "#7caa6d",
      },
    })),
    ...graph.edges.map((edge) => ({
      data: {
        id: `${edge.source}__${edge.target}`,
        source: edge.source,
        target: edge.target,
      },
    })),
  ];

  const cy = window.cytoscape({
    container,
    elements,
    layout: {
      name: "cose",
      animate: false,
      padding: 50,
      nodeRepulsion: 900000,
      idealEdgeLength: 130,
      edgeElasticity: 0.2,
      gravity: 0.2,
    },
    style: [
      {
        selector: "node",
        style: {
          "background-color": "data(color)",
          "border-width": 1,
          "border-color": "rgba(255,255,255,0.18)",
          "width": 12,
          "height": 12,
          "label": showLabels ? "data(label)" : "",
          "color": "#d9e1ea",
          "font-size": 10,
          "text-wrap": "wrap",
          "text-max-width": 120,
          "text-valign": "bottom",
          "text-halign": "center",
          "text-margin-y": 8,
        },
      },
      {
        selector: "edge",
        style: {
          "width": 1,
          "line-color": "rgba(143,181,255,0.14)",
          "curve-style": "bezier",
          "opacity": 0.9,
        },
      },
      {
        selector: ".active",
        style: {
          "background-color": "#8fb5ff",
          "width": 16,
          "height": 16,
          "line-color": "#c4e7b8",
          "width": 2,
          "opacity": 1,
          "z-index": 999,
        },
      },
      {
        selector: ".neighbor",
        style: {
          "background-color": "#c4e7b8",
          "opacity": 1,
        },
      },
      {
        selector: ".dimmed",
        style: {
          "opacity": 0.12,
          "text-opacity": 0.08,
        },
      },
    ],
    wheelSensitivity: 0.18,
    minZoom: 0.2,
    maxZoom: 3,
  });

  function applyLabels() {
    cy.style().selector("node").style("label", showLabels ? "data(label)" : "").update();
  }

  function clearState() {
    cy.elements().removeClass("active neighbor dimmed");
  }

  function focusNode(node) {
    clearState();
    const neighborhood = node.closedNeighborhood();
    cy.elements().difference(neighborhood).addClass("dimmed");
    node.addClass("active");
    node.neighborhood("node").addClass("neighbor");
    node.connectedEdges().addClass("active");
    cy.animate({ fit: { eles: neighborhood, padding: 90 }, duration: 220 });
  }

  function filterByText(term) {
    clearState();
    const normalized = term.trim().toLowerCase();
    if (!normalized) return;
    const matches = cy.nodes().filter((node) => node.data("label").toLowerCase().includes(normalized));
    if (!matches.length) {
      cy.elements().addClass("dimmed");
      return;
    }
    const keep = matches.union(matches.neighborhood());
    cy.elements().difference(keep).addClass("dimmed");
    matches.addClass("active");
    matches.neighborhood("node").addClass("neighbor");
    matches.connectedEdges().addClass("active");
    cy.animate({ fit: { eles: keep, padding: 100 }, duration: 220 });
  }

  cy.on("tap", "node", (event) => {
    const node = event.target;
    if (node.hasClass("active")) {
      window.location.href = node.data("url");
      return;
    }
    focusNode(node);
  });

  cy.on("tap", (event) => {
    if (event.target === cy) clearState();
  });

  actionButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const action = button.dataset.graphAction;
      if (action === "fit") {
        clearState();
        cy.fit(cy.elements(), 80);
      }
      if (action === "labels") {
        showLabels = !showLabels;
        applyLabels();
      }
    });
  });

  searchInput?.addEventListener("input", (event) => filterByText(event.target.value));
  cy.ready(() => cy.fit(cy.elements(), 80));
}

initGraph();
"""

    (assets / "styles.css").write_text(styles.strip() + "\n", encoding="utf-8")
    (assets / "app.js").write_text(script.strip() + "\n", encoding="utf-8")


def main() -> None:
    config = load_config()
    vault_path = Path(config["vault_path"])
    site_name = str(config.get("site_name") or "Biblioteca Luanda")

    if not vault_path.exists():
        raise SystemExit(f"Vault nao encontrado: {vault_path}")

    if DIST.exists():
        shutil.rmtree(DIST)

    DIST.mkdir(parents=True, exist_ok=True)
    notes = read_notes(vault_path)
    lookup = build_lookup(notes)
    build_note_pages(notes, lookup, site_name)
    write_assets()
    sync_status = load_sync_status()
    build_index(notes, site_name, sync_status)
    build_graph_page(site_name)
    graph_data = build_graph_data(notes, lookup)
    (DIST / "assets" / "graph.json").write_text(json.dumps(graph_data, ensure_ascii=False, indent=2), encoding="utf-8")
    (DIST / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Site gerado em: {DIST}")
    print(f"Total de notas: {len(notes)}")


if __name__ == "__main__":
    main()
