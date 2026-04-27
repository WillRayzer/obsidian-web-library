#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


SKIP_DIRS = {".obsidian", "00-backups", "00-templates", "99-archive"}
AUTO_RELATED_PATTERN = re.compile(
    r"\n?<!-- AUTO-RELATED-LINKS:START -->.*?<!-- AUTO-RELATED-LINKS:END -->\n?",
    re.S,
)
CONTEXT_START = "<!-- AUTO-CONTEXT-LINKS:START -->"
CONTEXT_END = "<!-- AUTO-CONTEXT-LINKS:END -->"


@dataclass
class Note:
    path: Path
    frontmatter: dict[str, object]
    body: str
    manual_links: int
    has_context_links: bool


def should_skip(path: Path) -> bool:
    return any(part.lower() in SKIP_DIRS for part in path.parts)


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---\n") or "\n---\n" not in text:
        return {}, text
    raw, body = text[4:].split("\n---\n", 1)
    data: dict[str, object] = {}
    key: str | None = None
    for line in raw.splitlines():
        if ":" in line and not line.startswith("  "):
            k, v = line.split(":", 1)
            key = k.strip()
            v = v.strip()
            data[key] = [] if v == "" else v.strip('"')
            continue
        if line.strip().startswith("- ") and key and isinstance(data.get(key), list):
            data[key].append(line.strip()[2:].strip().strip('"'))
    return data, body


def dump_frontmatter(data: dict[str, object]) -> str:
    order = [
        "title", "date", "ia", "model", "source", "conversation_type", "area", "folder",
        "tags", "topic", "summary", "status", "related",
    ]
    lines = ["---"]
    for key in order:
        if key not in data:
            continue
        value = data[key]
        if key in {"tags", "related"}:
            lines.append(f"{key}:")
            items = value if isinstance(value, list) else []
            for item in items:
                if key == "related":
                    lines.append(f'  - "{item}"')
                else:
                    lines.append(f"  - {item}")
            continue
        if key == "summary":
            lines.append("summary: >")
            lines.append(f"  {str(value)}")
            continue
        lines.append(f'{key}: "{value}"' if key not in {"date", "status"} else f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def count_manual_links(body: str) -> int:
    cleaned = re.sub(AUTO_RELATED_PATTERN, "\n", body)
    cleaned = re.sub(rf"\n?{re.escape(CONTEXT_START)}.*?{re.escape(CONTEXT_END)}\n?", "\n", cleaned, flags=re.S)
    return len(re.findall(r"\[\[([^\]]+)\]\]", cleaned))


def read_notes(vault_path: Path) -> list[Note]:
    notes: list[Note] = []
    for path in sorted(vault_path.rglob("*.md")):
        if should_skip(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        frontmatter, body = parse_frontmatter(text)
        notes.append(
            Note(
                path=path,
                frontmatter=frontmatter,
                body=body,
                manual_links=count_manual_links(body),
                has_context_links=CONTEXT_START in body and CONTEXT_END in body,
            )
        )
    return notes


def extract_context_links(related: object) -> list[str]:
    items = related if isinstance(related, list) else []
    links: list[str] = []
    for item in items:
        text = str(item).strip().strip('"')
        if not text or text == "[[00-Dashboard - Biblioteca]]":
            continue
        links.append(text if text.startswith("[[") else f"[[{text}]]")
    return links[:4]


def inject_context_section(body: str, links: list[str]) -> str:
    cleaned = re.sub(rf"\n?{re.escape(CONTEXT_START)}.*?{re.escape(CONTEXT_END)}\n?", "\n", body, flags=re.S).strip()
    if not links:
        return cleaned + "\n"
    section = "\n".join(
        [
            CONTEXT_START,
            "## Context Links",
            "",
            *[f"- {link}" for link in links],
            CONTEXT_END,
        ]
    )
    if "## Conclusions & Deliverables" in cleaned:
        return cleaned.replace("## Conclusions & Deliverables", section + "\n\n## Conclusions & Deliverables", 1).strip() + "\n"
    return cleaned + "\n\n" + section + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("vault_path", type=Path)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    vault_path = args.vault_path.expanduser()
    notes = read_notes(vault_path)
    candidates = [note for note in notes if note.manual_links == 0 and not note.has_context_links]
    candidates.sort(key=lambda note: note.path.name.lower())
    changed = 0

    for note in candidates[: args.limit]:
        links = extract_context_links(note.frontmatter.get("related", []))
        if not links:
            continue
        new_body = inject_context_section(note.body, links)
        frontmatter_text = dump_frontmatter(note.frontmatter)
        updated = frontmatter_text + "\n\n" + new_body.strip() + "\n"
        current = note.path.read_text(encoding="utf-8", errors="replace")
        if current == updated:
            continue
        changed += 1
        print(f"- {note.path.name}")
        if args.write:
            note.path.write_text(updated, encoding="utf-8")

    print(f"Notas com context links adicionados: {changed}")


if __name__ == "__main__":
    main()
