#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
BANNED_TAGS = {
    "ia", "conversa", "obsidian", "web", "clip", "inbox", "local", "capture", "captura",
    "documento", "pagina", "article", "post", "news", "site",
    "page", "featured", "summary", "source", "content", "report", "blog",
}
STOPWORDS = {
    "de", "da", "do", "das", "dos", "e", "em", "na", "no", "para", "com", "um", "uma",
    "o", "a", "os", "as", "por", "sobre", "ao", "aos", "que", "como", "mais", "menos",
    "se", "ou", "sem", "sua", "seu", "suas", "seus", "the", "and", "for", "with",
    "from", "into", "this", "that", "was", "are", "been", "can", "will", "not", "too",
}


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def resolve_cross_platform_path(value: str) -> Path:
    text = str(value).strip()
    if os.name == "nt" and text.startswith("/mnt/") and len(text) > 6:
        drive = text[5]
        rest = text[7:].replace("/", "\\")
        return Path(f"{drive.upper()}:\\{rest}")
    if os.name != "nt" and len(text) > 2 and text[1] == ":" and text[2] in {"\\", "/"}:
        drive = text[0].lower()
        rest = text[3:].replace("\\", "/")
        return Path(f"/mnt/{drive}/{rest}")
    return Path(text)


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-")


def normalize_text(text: str) -> str:
    text = unescape(text or "")
    text = text.replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    parts = re.findall(r"[a-z0-9]{3,}", text)
    return [part for part in parts if part not in STOPWORDS and part not in BANNED_TAGS]


class PageExtractor(HTMLParser):
    block_tags = {"p", "div", "section", "article", "main", "header", "footer", "aside", "nav", "blockquote", "pre", "ul", "ol", "table", "tr"}
    heading_tags = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}

    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.blocks: list[str] = []
        self.current_parts: list[str] = []
        self.links: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._link_href: str | None = None
        self._heading_prefix = ""
        self._in_li = False

    def flush(self) -> None:
        if not self.current_parts:
            return
        text = "".join(self.current_parts)
        text = normalize_text(text)
        if text:
            self.blocks.append(text)
        self.current_parts = []

    def append_text(self, text: str) -> None:
        if not text:
            return
        if self.current_parts and not self.current_parts[-1].endswith((" ", "\n")):
            self.current_parts.append(" ")
        self.current_parts.append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return

        attr_map = {key.lower(): (value or "") for key, value in attrs}
        if tag == "title":
            self._in_title = True
            return
        if tag == "meta":
            key = attr_map.get("name") or attr_map.get("property")
            content = attr_map.get("content", "").strip()
            if key and content:
                self.meta[key.lower()] = content
            return
        if tag in self.block_tags:
            self.flush()
        if tag in self.heading_tags:
            self.flush()
            self.current_parts.append(f"{'#' * self.heading_tags[tag]} ")
        elif tag == "li":
            self.flush()
            self.current_parts.append("- ")
            self._in_li = True
        elif tag == "br":
            self.current_parts.append("\n")
        elif tag == "a":
            self._link_href = attr_map.get("href", "").strip() or None

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = False
            return
        if tag == "a":
            if self._link_href and not self._link_href.startswith(("mailto:", "javascript:", "#")):
                if self._link_href not in self.links:
                    self.links.append(self._link_href)
            self._link_href = None
            return
        if tag == "li":
            self._in_li = False
        if tag in self.block_tags or tag in self.heading_tags:
            self.flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = normalize_text(data)
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
            return
        self.append_text(text)


def fetch_url(url: str) -> tuple[str, str, list[str], str]:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 ObsidianClipper/1.0"})
    with urlopen(request, timeout=30) as response:  # nosec - local utility for trusted use
        charset = response.headers.get_content_charset() or "utf-8"
        html = response.read().decode(charset, errors="replace")

    parser = PageExtractor()
    parser.feed(html)
    parser.close()

    title = " ".join(parser.title_parts).strip()
    if not title:
        title = parser.meta.get("og:title", "") or parser.meta.get("twitter:title", "")
    if not title:
        parsed = urlparse(url)
        title = parsed.netloc or "Pagina capturada"

    description = parser.meta.get("description", "") or parser.meta.get("og:description", "")
    body = "\n\n".join(parser.blocks)
    body = normalize_text(body)

    if description and description not in body:
        body = f"{description}\n\n{body}" if body else description

    return title.strip(), description.strip(), parser.links, body.strip()


def extract_tags(title: str, description: str, body: str) -> list[str]:
    title_tokens = tokenize(title)
    body_tokens = tokenize(f"{description} {body[:4000]}")
    body_counts = Counter(body_tokens)
    counts: dict[str, int] = {}
    for token in title_tokens:
        counts[token] = counts.get(token, 0) + 3
    for token in body_tokens:
        counts[token] = counts.get(token, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    tags: list[str] = []
    for token, _score in ordered:
        if token in tags:
            continue
        if len(token) < 4:
            continue
        if body_counts.get(token, 0) < 2:
            continue
        tags.append(token)
        if len(tags) >= 8:
            break
    return tags


def build_markdown(url: str, title: str, description: str, links: list[str], body: str) -> str:
    parsed = urlparse(url)
    source_domain = parsed.netloc
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    date = datetime.now().strftime("%Y-%m-%d")
    slug = slugify(title or source_domain or "captura-web")
    summary = normalize_text((description or body or "")[:320])
    tags = extract_tags(title, description, body)
    lines = [
        "---",
        f'title: "{title.replace(chr(34), chr(39))}"',
        f"date: {date}",
        'ia: "Clipper Local"',
        'model: "Local HTTP Capture"',
        f'source_url: "{url.replace(chr(34), chr(39))}"',
        f'source_domain: "{source_domain.replace(chr(34), chr(39))}"',
        'conversation_type: "web-clip"',
        'area: "Inbox"',
        'folder: "00-Inbox/Web Clips/Pending"',
        "tags:",
    ]
    lines.extend(f"  - {tag}" for tag in tags)
    lines.extend([
        f'summary: >\n  {summary.replace(chr(34), chr(39)) or "Captura de pagina web."}',
        "status: review",
        "related:",
        '  - "[[00-Dashboard - Biblioteca]]"',
        "---",
        "",
        "## Source",
        "",
        f"- URL: {url}",
        f"- Domain: {source_domain}",
        f"- Fetched at: {fetched_at}",
        "",
        "## Summary",
        "",
        summary or "Captura de pagina web.",
        "",
        "## Extracted Content",
        "",
        body or "Nao foi possivel extrair conteudo legivel desta pagina.",
    ])

    if links:
        lines.extend([
            "",
            "## Links",
            "",
        ])
        for href in links[:24]:
            lines.append(f"- {href}")

    lines.extend([
        "",
        "## Next Steps",
        "",
        "- [ ] Revisar o titulo e as tags se necessario",
        "- [ ] Deixar o vault processar a nota automaticamente",
        "",
    ])
    return "\n".join(lines), slug


def unique_target(folder: Path, date_prefix: str, slug: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    candidate = folder / f"{date_prefix}-{slug}.md"
    counter = 1
    while candidate.exists():
        candidate = folder / f"{date_prefix}-{slug}-{counter}.md"
        counter += 1
    return candidate


def write_clip_note(source_vault: Path, url: str) -> dict:
    title, description, links, body = fetch_url(url)
    markdown, slug = build_markdown(url, title, description, links, body)
    date_prefix = datetime.now().strftime("%Y-%m-%d")
    target_folder = source_vault / "00-Inbox" / "Web Clips"
    target = unique_target(target_folder, date_prefix, slug)
    target.write_text(markdown, encoding="utf-8")
    preview = markdown[:4000]
    return {
        "ok": True,
        "status": "saved",
        "title": title,
        "source_url": url,
        "saved_path": str(target),
        "relative_path": str(target.relative_to(source_vault)).replace("\\", "/"),
        "area": "Inbox",
        "preview": preview,
        "markdown": markdown,
    }


class ClipHandler(BaseHTTPRequestHandler):
    server_version = "ObsidianClipServer/1.0"

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def send_cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in {"", "/health"}:
            config = load_config()
            payload = {
                "status": "ok",
                "service": "obsidian-clip-server",
                "vault_path": str(resolve_cross_platform_path(config.get("source_vault_path", ""))),
            }
            self.send_json(HTTPStatus.OK, payload)
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/clip":
            self.send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_json"})
            return

        url = str(payload.get("url") or "").strip()
        if not url:
            self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "url_missing"})
            return
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_url"})
            return

        try:
            config = load_config()
            source_vault = resolve_cross_platform_path(config["source_vault_path"]).expanduser()
            result = write_clip_note(source_vault, url)
        except HTTPError as exc:
            self.send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": f"http_error: {exc.code}"})
            return
        except URLError as exc:
            self.send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": f"url_error: {exc.reason}"})
            return
        except Exception as exc:  # pragma: no cover - local service should report errors cleanly
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})
            return

        self.send_json(HTTPStatus.OK, result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), ClipHandler)
    print(f"Clip server listening on http://{args.host}:{args.port}")
    print("Use 'tailscale serve --bg 8787' to expose it privately over HTTPS.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
