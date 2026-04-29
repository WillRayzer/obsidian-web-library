#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import unicodedata
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-")


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
    for key in ["title", "date", "ia", "model", "source_url", "source_domain", "conversation_type", "area", "folder", "tags", "summary", "status", "related"]:
        if key not in data:
            continue
        value = data[key]
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


def call_openai(prompt: str) -> dict[str, object]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY nao configurada")

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
        f"{OPENAI_BASE_URL}/chat/completions",
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

    prompt = f"""
Traduza e reescreva a captura web abaixo para portugues do Brasil.

Regras:
- Retorne apenas JSON valido.
- Use chaves exatas: title, summary, tags, area, folder, content, related, status.
- title: titulo final em portugues.
- summary: resumo em portugues com no maximo 2 frases.
- tags: lista curta com ate 6 tags tematicas, somente assuntos do conteudo.
- area: use "Studies" ou "Business" conforme o assunto.
- folder: escolha uma pasta coerente dentro de 04-Studies/ ou 05-Projects/.
- content: nota final em portugues, com sections markdown curtas e claras.
- related: liste wikilinks relevantes do vault quando houver certeza.
- status: use "complete".
- Ignore metadados de captura na traducao.

Metadados da captura:
Title: {frontmatter.get('title', path.stem)}
URL: {frontmatter.get('source_url', '')}
Domain: {frontmatter.get('source_domain', '')}

Conteudo bruto:
{body[:12000]}
"""

    translated = call_openai(prompt)
    title = str(translated.get("title") or frontmatter.get("title") or path.stem).strip()
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

    vault_path = args.vault_path.expanduser()
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
