#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


SKIP_DIRS = {".obsidian", "00-backups", "00-templates", "99-archive"}


@dataclass
class Note:
    path: Path
    title: str
    stem_slug: str
    title_slug: str
    area: str
    tags: list[str]
    related: list[str]
    links: list[str]
    frontmatter: bool
    conversation_type: str
    body: str


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"\[\[|\]\]", "", value)
    value = re.sub(r"[^\w\s-]", "", value)
    return re.sub(r"[-\s]+", "-", value).strip("-")


def canonical_stem(stem: str) -> str:
    return slugify(re.sub(r"\s*\(\d+\)\s*$", "", stem).strip())


def should_skip(path: Path) -> bool:
    return any(part.lower() in SKIP_DIRS for part in path.parts)


def parse_frontmatter(text: str) -> tuple[dict[str, object], str, bool]:
    if not text.startswith("---\n") or "\n---\n" not in text:
        return {}, text, False
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
    return data, body, True


def extract_links(body: str) -> list[str]:
    return [match.split("|", 1)[0].strip() for match in re.findall(r"\[\[([^\]]+)\]\]", body)]


def likely_bad_import(note: Note) -> bool:
    if note.conversation_type != "document-import":
        return False
    lowered = note.body.lower()
    artifact_hits = sum(
        lowered.count(token)
        for token in [
            "/bitspercomponent",
            "/colorspace",
            "/filter",
            "/dctdecode",
            "/subtype",
            "endstream",
            "endobj",
            "stream",
            " obj",
        ]
    )
    natural_phrases = len(re.findall(r"[a-zà-ÿ]{4,}\s+[a-zà-ÿ]{4,}", lowered))
    return artifact_hits >= 6 or natural_phrases < 12


def read_notes(vault_path: Path) -> list[Note]:
    notes: list[Note] = []
    for path in sorted(vault_path.rglob("*.md")):
        if should_skip(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        frontmatter, body, has_frontmatter = parse_frontmatter(text)
        title = str(frontmatter.get("title") or path.stem)
        notes.append(
            Note(
                path=path,
                title=title,
                stem_slug=slugify(path.stem),
                title_slug=slugify(title),
                area=str(frontmatter.get("area") or ""),
                tags=[str(tag) for tag in frontmatter.get("tags", [])] if isinstance(frontmatter.get("tags"), list) else [],
                related=[str(item) for item in frontmatter.get("related", [])] if isinstance(frontmatter.get("related"), list) else [],
                links=extract_links(body),
                frontmatter=has_frontmatter,
                conversation_type=str(frontmatter.get("conversation_type") or ""),
                body=body,
            )
        )
    return notes


def render_report(vault_path: Path, notes: list[Note]) -> str:
    lookup: dict[str, Note] = {}
    for note in notes:
        lookup[note.stem_slug] = note
        lookup[note.title_slug] = note

    inbound: defaultdict[str, set[str]] = defaultdict(set)
    outbound: defaultdict[str, set[str]] = defaultdict(set)
    for note in notes:
        for raw in note.links + note.related:
            target = lookup.get(slugify(raw))
            if not target or target.path == note.path:
                continue
            outbound[note.stem_slug].add(target.stem_slug)
            inbound[target.stem_slug].add(note.stem_slug)

    no_frontmatter = [note for note in notes if not note.frontmatter]
    no_area = [note for note in notes if not note.area]
    orphans = [note for note in notes if not inbound[note.stem_slug] and not outbound[note.stem_slug]]
    weak = [note for note in notes if len(inbound[note.stem_slug]) + len(outbound[note.stem_slug]) <= 1]
    bad_imports = [note for note in notes if likely_bad_import(note)]

    duplicate_groups: defaultdict[str, list[Note]] = defaultdict(list)
    for note in notes:
        duplicate_groups[canonical_stem(note.path.stem)].append(note)
    copy_variants = [group for group in duplicate_groups.values() if len(group) > 1]

    lines = [
        "# Auditoria de Coerencia do Vault",
        "",
        f"- Vault: `{vault_path}`",
        f"- Total de notas analisadas: {len(notes)}",
        f"- Sem frontmatter: {len(no_frontmatter)}",
        f"- Sem area: {len(no_area)}",
        f"- Orfas reais: {len(orphans)}",
        f"- Notas fracas (0 ou 1 conexao): {len(weak)}",
        f"- Importacoes com baixa qualidade: {len(bad_imports)}",
        f"- Grupos com variantes por copia: {len(copy_variants)}",
        "",
    ]

    def section(title: str, rows: list[str]) -> None:
        lines.append(f"## {title}")
        lines.append("")
        if not rows:
            lines.append("- Nenhum")
            lines.append("")
            return
        lines.extend(rows)
        lines.append("")

    section("Sem Frontmatter", [f"- {note.path.name}" for note in no_frontmatter])
    section("Sem Area", [f"- {note.path.name}" for note in no_area])
    section(
        "Orfas Reais",
        [
            f"- {note.path.name} | area={note.area or 'Sem area'} | tipo={note.conversation_type or 'n/a'}"
            for note in orphans
        ],
    )
    section(
        "Importacoes com Baixa Qualidade",
        [f"- {note.path.name}" for note in bad_imports],
    )

    variant_rows: list[str] = []
    for group in sorted(copy_variants, key=lambda grp: grp[0].path.name.lower()):
        variant_rows.append(f"- Grupo: {canonical_stem(group[0].path.stem)}")
        for note in sorted(group, key=lambda n: n.path.name.lower()):
            variant_rows.append(f"  - {note.path.name}")
    section("Variantes por Copia", variant_rows)

    weak_rows = []
    for note in sorted(weak, key=lambda n: (len(inbound[n.stem_slug]) + len(outbound[n.stem_slug]), n.path.name.lower()))[:25]:
        weak_rows.append(
            f"- {note.path.name} | in={len(inbound[n.stem_slug])} | out={len(outbound[n.stem_slug])} | area={note.area or 'Sem area'}"
        )
    section("Notas para Reforcar Primeiro", weak_rows)

    lines.extend(
        [
            "## Leitura",
            "",
            "- `Orfas reais`: sem links de entrada e sem links de saida reconhecidos por titulo ou nome do arquivo.",
            "- `Importacoes com baixa qualidade`: notas geradas de documento com texto provavelmente corrompido ou pouco legivel.",
            "- `Variantes por copia`: arquivos que parecem ser o mesmo documento com sufixos como `(1)` ou `(2)`.",
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
    notes = read_notes(vault_path)
    report = render_report(vault_path, notes)
    args.output.write_text(report, encoding="utf-8")
    print(f"Relatorio salvo em: {args.output}")
    print(f"Notas analisadas: {len(notes)}")


if __name__ == "__main__":
    main()
