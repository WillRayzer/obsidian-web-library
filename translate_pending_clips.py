#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = (
    os.environ.get("MOONSHOT_MODEL")
    or os.environ.get("OPENAI_MODEL")
    or "kimi-k2.5"
)
MOONSHOT_BASE_URL = os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.ai/v1").rstrip("/")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-")


def tokenize(text: str) -> set[str]:
    cleaned = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    return set(re.findall(r"[a-z0-9]{3,}", cleaned))


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


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---\n"):
        return {}, text
    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, text
    raw = parts[0][4:]
    body = parts[1]
    data: dict[str, object] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"')
    return data, body


def dump_frontmatter(data: dict[str, object]) -> str:
    lines = ["---"]
    for key in ["title", "aliases", "date", "ia", "model", "source_url", "source_domain", "conversation_type", "area", "folder", "tags", "summary", "status", "related"]:
        if key not in data:
            continue
        value = data[key]
        if key == "aliases" and isinstance(value, list):
            lines.append("aliases:")
            for alias in value:
                lines.append(f'  - "{alias}"')
            continue
        if key == "tags" and isinstance(value, list):
            lines.append("tags:")
            for tag in value:
                lines.append(f"  - {tag}")
            continue
        if key == "related" and isinstance(value, list):
            lines.append("related:")
            for item in value:
                lines.append(f'  - "{item}"')
            continue
        if key == "summary":
            lines.append("summary: >")
            lines.append(f"  {str(value)}")
            continue
        lines.append(f'{key}: "{value}"' if key not in {"date", "status"} else f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def read_candidate_titles(vault_root: Path, source_path: Path) -> list[str]:
    titles: list[tuple[int, str]] = []
    source_text = ""
    try:
        source_text = source_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        source_text = ""
    source_tokens = tokenize(source_text[:12000])

    for path in sorted(vault_root.rglob("*.md")):
        lower_parts = {part.lower() for part in path.parts}
        if ".obsidian" in lower_parts or "00-backups" in lower_parts or "00-templates" in lower_parts or "99-archive" in lower_parts:
            continue
        if "pending" in lower_parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        frontmatter, body = parse_frontmatter(text)
        title = str(frontmatter.get("title") or path.stem).strip()
        title_tokens = tokenize(f"{title}\n{body[:2000]}")
        score = len(source_tokens.intersection(title_tokens))
        if score:
            titles.append((score, title))
    titles.sort(key=lambda item: (-item[0], item[1].lower()))
    ordered: list[str] = []
    for _, title in titles:
        if title not in ordered:
            ordered.append(title)
        if len(ordered) >= 24:
            break
    return ordered


def call_model(prompt: str) -> dict[str, object]:
    api_key = os.environ.get("MOONSHOT_API_KEY", "").strip()
    base_url = MOONSHOT_BASE_URL
    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        base_url = OPENAI_BASE_URL
    if not api_key:
        raise RuntimeError("Nenhuma chave API configurada")

    payload = {
        "model": DEFAULT_MODEL,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Voce traduz e reescreve capturas web para o segundo cerebro. "
                    "Responda apenas em JSON valido, sem markdown, sem bloco de codigo."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    request = Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=120) as response:  # nosec - local utility
        data = json.loads(response.read().decode("utf-8"))

    content = data["choices"][0]["message"]["content"]
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        raise RuntimeError("resposta invalida do tradutor")
    return json.loads(match.group(0))


def translate_note(path: Path, vault_root: Path) -> tuple[bool, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    frontmatter, body = parse_frontmatter(text)
    if str(frontmatter.get("status") or "").strip().lower() not in {"review", "pending"}:
        return False, "ignorada"
    if str(frontmatter.get("conversation_type") or "").strip().lower() != "web-clip":
        return False, "ignorada"

    candidates = read_candidate_titles(vault_root, path)
    candidate_block = "\n".join(f"- {title}" for title in candidates) if candidates else "- (nenhuma candidata encontrada)"

    prompt = f"""
Traduza e reescreva a captura web abaixo para portugues do Brasil.

Regras:
- Retorne apenas JSON valido.
- Use chaves exatas: title, aliases, summary, tags, area, folder, content, related, status.
- title: titulo final em portugues.
- aliases: lista curta com o titulo original e eventuais variantes uteis para o Obsidian.
- summary: resumo em portugues com no maximo 2 frases.
- tags: lista curta com ate 6 tags tematicas, somente assuntos do conteudo.
- area: use "Studies" ou "Business" conforme o assunto.
- folder: escolha uma pasta coerente dentro de 04-Studies/ ou 05-Projects/.
- content: nota final em portugues, com sections markdown curtas e claras.
- related: liste apenas wikilinks de notas que existam nesta lista de candidatas quando houver certeza.
- status: use "complete".
- Ignore metadados de captura na traducao.

Metadados da captura:
Title: {frontmatter.get('title', path.stem)}
URL: {frontmatter.get('source_url', '')}
Domain: {frontmatter.get('source_domain', '')}

Notas candidatas do vault:
{candidate_block}

Conteudo bruto:
{body[:12000]}
"""

    translated = call_model(prompt)
    title = str(translated.get("title") or frontmatter.get("title") or path.stem).strip()
    aliases = [str(item).strip() for item in translated.get("aliases", []) if str(item).strip()]
    if title and title not in aliases:
        aliases.insert(0, title)
    source_title = str(frontmatter.get("title") or "").strip()
    if source_title and source_title not in aliases:
        aliases.append(source_title)
    summary = str(translated.get("summary") or "").strip()
    tags = [slugify(str(tag)) for tag in translated.get("tags", []) if str(tag).strip()]
    area = str(translated.get("area") or "Studies").strip()
    folder = str(translated.get("folder") or "04-Studies/tema").strip()
    content = str(translated.get("content") or "").strip()
    related = [str(item).strip() for item in translated.get("related", []) if str(item).strip()]
    status = str(translated.get("status") or "complete").strip().lower()

    if not content:
        raise RuntimeError("traducao sem content")

    dest_name = f"{path.stem.split('-', 3)[0]}-{slugify(title)[:80]}.md"
    dest = vault_root / folder / dest_name
    dest.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "title": title,
        "aliases": aliases,
        "date": frontmatter.get("date") or path.stem[:10],
        "ia": "Revisão manual",
        "model": "Reescrita em português",
        "source_url": frontmatter.get("source_url") or "",
        "source_domain": frontmatter.get("source_domain") or "",
        "conversation_type": "web-clip",
        "area": area,
        "folder": folder,
        "tags": tags,
        "summary": summary or "Captura web reescrita em portugues.",
        "status": status,
        "related": related or ["[[00-Dashboard - Biblioteca]]"],
    }
    serialized = dump_frontmatter(payload).strip() + "\n\n" + content.strip() + "\n"
    dest.write_text(serialized, encoding="utf-8")
    path.unlink()
    return True, f"promovida: {dest.relative_to(vault_root)}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("vault_path", type=Path)
    args = parser.parse_args()

    vault_path = resolve_cross_platform_path(args.vault_path).expanduser()
    pending = sorted((vault_path / "00-Inbox" / "Web Clips" / "Pending").rglob("*.md"))
    if not pending:
        print("Nenhuma captura pendente para traduzir.")
        return

    changed = 0
    for path in pending:
        try:
            did_change, message = translate_note(path, vault_path)
            if did_change:
                changed += 1
                print(f"- {message}")
        except Exception as exc:
            print(f"- falha em {path.name}: {exc}")
    print(f"Capturas promovidas: {changed}")


if __name__ == "__main__":
    main()
