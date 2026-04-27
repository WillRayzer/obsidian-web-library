#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


AUTO_RELATED_PATTERN = re.compile(
    r"\n?<!-- AUTO-RELATED-LINKS:START -->.*?<!-- AUTO-RELATED-LINKS:END -->\n?",
    re.S,
)


@dataclass
class NoteStats:
    path: Path
    title: str
    area: str
    tags: list[str]
    wikilinks: int
    related: int
    score: int


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---\n") or "\n---\n" not in text:
        return {}, text
    raw, body = text[4:].split("\n---\n", 1)
    data: dict[str, object] = {}
    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or ":" not in line:
            i += 1
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            items: list[str] = []
            j = i + 1
            while j < len(lines):
                candidate = lines[j].strip()
                if candidate.startswith("- "):
                    items.append(candidate[2:].strip().strip('"'))
                    j += 1
                    continue
                if not candidate:
                    j += 1
                    continue
                break
            data[key] = items
            i = j
            continue
        data[key] = value.strip('"')
        i += 1
    return data, body


def count_manual_wikilinks(body: str) -> int:
    cleaned = re.sub(AUTO_RELATED_PATTERN, "\n", body)
    return len(re.findall(r"\[\[([^\]]+)\]\]", cleaned))


def should_skip(path: Path) -> bool:
    lower_parts = {part.lower() for part in path.parts}
    return ".obsidian" in lower_parts or "00-backups" in lower_parts or "00-templates" in lower_parts or "99-archive" in lower_parts


def analyze(vault_path: Path) -> list[NoteStats]:
    results: list[NoteStats] = []
    for path in sorted(vault_path.rglob("*.md")):
        if should_skip(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        frontmatter, body = parse_frontmatter(text)
        title = str(frontmatter.get("title") or path.stem)
        area = str(frontmatter.get("area") or "Sem area")
        tags = [str(tag) for tag in frontmatter.get("tags", [])] if isinstance(frontmatter.get("tags"), list) else []
        related = [str(item) for item in frontmatter.get("related", [])] if isinstance(frontmatter.get("related"), list) else []
        wikilinks = count_manual_wikilinks(body)
        score = wikilinks * 2 + len(related) + min(len(tags), 4)
        results.append(
            NoteStats(
                path=path,
                title=title,
                area=area,
                tags=tags,
                wikilinks=wikilinks,
                related=len(related),
                score=score,
            )
        )
    return results


def render_report(notes: list[NoteStats], vault_path: Path) -> str:
    total = len(notes)
    weak = sorted(notes, key=lambda note: (note.score, note.wikilinks, note.related, note.title.lower()))
    weakest = weak[:20]
    lines = [
        "# Relatorio - Notas com Conexao Fraca",
        "",
        f"- Total de notas analisadas: {total}",
        f"- Notas com 0 links manuais: {sum(1 for note in notes if note.wikilinks == 0)}",
        f"- Notas com 1 ou menos links manuais: {sum(1 for note in notes if note.wikilinks <= 1)}",
        "",
        "## Prioridade de reforco",
        "",
        "| Nota | Area | Links manuais | Related | Tags | Score |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for note in weakest:
        lines.append(
            f"| {note.title} | {note.area} | {note.wikilinks} | {note.related} | {len(note.tags)} | {note.score} |"
        )
    lines.extend(
        [
            "",
            "## Criterio",
            "",
            "- `Links manuais`: wikilinks reais no corpo da nota, sem contar a secao automatica.",
            "- `Related`: conexoes inferidas no frontmatter.",
            "- `Score`: medida simples de densidade semantica para priorizar reforco.",
            "",
            "## Recomendacao",
            "",
            "- Adicionar 2 a 5 wikilinks manuais nas notas mais fracas.",
            "- Conectar cada nota ao menos a uma nota-hub da mesma area.",
            "- Revisar titulos muito vagos ou duplicados.",
            "",
            f"_Vault analisado: `{vault_path}`_",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("vault_path", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    vault_path = args.vault_path.expanduser()
    notes = analyze(vault_path)
    report = render_report(notes, vault_path)
    args.output.write_text(report, encoding="utf-8")
    print(f"Relatorio salvo em: {args.output}")
    print(f"Notas analisadas: {len(notes)}")


if __name__ == "__main__":
    main()
