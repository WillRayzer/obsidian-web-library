#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path


SECTION_TITLES = {
    "objective": "## Objective",
    "conversation": "## Conversation",
    "conclusions": "## Conclusions & Deliverables",
    "next_steps": "## Next Steps",
}


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-")


def title_case_from_filename(path: Path) -> str:
    stem = path.stem.replace("-", " ").replace("_", " ").strip()
    return stem[:1].upper() + stem[1:] if stem else "Titulo da conversa"


def parse_list_block(value: str) -> list[str]:
    value = value.strip()
    if not value:
        return []
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1]
        parts = [part.strip().strip('"').strip("'") for part in inner.split(",")]
        return [part for part in parts if part]
    parts = re.split(r",\s*|\n+", value)
    return [part.strip().strip('"').strip("'").lstrip("- ").strip() for part in parts if part.strip()]


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---"):
        return {}, text
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", text, re.S)
    if not match:
        return {}, text
    raw = match.group(1)
    body = match.group(2)
    data: dict[str, object] = {}
    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
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
            block: list[str] = []
            j = i + 1
            while j < len(lines):
                candidate = lines[j]
                if not candidate.strip():
                    j += 1
                    continue
                if candidate.lstrip().startswith("- "):
                    block.append(candidate)
                    j += 1
                    continue
                if ":" in candidate:
                    break
                block.append(candidate)
                j += 1
            parsed = parse_list_block("\n".join(block))
            data[key] = parsed
            i = j
            continue
        data[key] = value.strip('"').strip("'")
        i += 1
    return data, body


def normalize_related(value: object) -> list[str]:
    items = value if isinstance(value, list) else parse_list_block(str(value or ""))
    out = []
    for item in items:
        text = str(item).strip().strip('"').strip("'")
        if not text:
            continue
        if not text.startswith("[["):
            text = f"[[{text}]]"
        out.append(text)
    return out


def normalize_tags(value: object) -> list[str]:
    items = value if isinstance(value, list) else parse_list_block(str(value or ""))
    out = []
    for item in items:
        tag = slugify(str(item).replace("#", " "))
        if tag:
            out.append(tag)
    return list(dict.fromkeys(out))


def extract_sections(body: str) -> dict[str, str]:
    text = body.strip().replace("\r\n", "\n")
    replacements = {
        r"(?m)^Objective\s*$": SECTION_TITLES["objective"],
        r"(?m)^Conversation\s*$": SECTION_TITLES["conversation"],
        r"(?m)^Conclusions\s*&\s*Deliverables\s*$": SECTION_TITLES["conclusions"],
        r"(?m)^Next\s*Steps\s*$": SECTION_TITLES["next_steps"],
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)
    matches = list(re.finditer(r"(?m)^## (Objective|Conversation|Conclusions & Deliverables|Next Steps)\s*$", text))
    if not matches:
        return {
            "objective": "Registrar a conversa com estrutura padronizada para uso no Obsidian, dashboard web e Graph View.",
            "conversation": text.strip(),
            "conclusions": "- [ ] Revisar e resumir os principais pontos",
            "next_steps": "- [ ] Relacionar com outras notas",
        }
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        title = match.group(1).lower().replace(" & deliverables", "").replace(" ", "_")
        if title == "conclusions":
            key = "conclusions"
        elif title == "next_steps":
            key = "next_steps"
        else:
            key = title
        sections[key] = text[start:end].strip()
    sections.setdefault("objective", "Registrar a conversa com estrutura padronizada para uso no Obsidian, dashboard web e Graph View.")
    sections.setdefault("conversation", text.strip())
    sections.setdefault("conclusions", "- [ ] Revisar e resumir os principais pontos")
    sections.setdefault("next_steps", "- [ ] Relacionar com outras notas")
    return sections


def infer_date(frontmatter: dict[str, object], path: Path) -> str:
    raw = str(frontmatter.get("date") or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")


def infer_title(frontmatter: dict[str, object], body: str, path: Path) -> str:
    raw = str(frontmatter.get("title") or "").strip().strip('"')
    if raw:
        return raw
    heading = re.search(r"(?m)^#\s+(.+)$", body)
    if heading:
        return heading.group(1).strip()
    return title_case_from_filename(path)


def infer_topic(frontmatter: dict[str, object], title: str, body: str) -> str:
    raw = str(frontmatter.get("topic") or "").strip().strip('"')
    if raw:
        return raw
    text = re.sub(r"\s+", " ", body).strip()
    return text[:180] if text else f"Conversa sobre {title}."


def infer_summary(frontmatter: dict[str, object], body: str) -> str:
    raw = str(frontmatter.get("summary") or "").strip().strip('"')
    if raw:
        return raw
    text = re.sub(r"\s+", " ", body).strip()
    return text[:320] if text else "Conversa padronizada para uso no Obsidian."


def normalize_content(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    frontmatter, body = parse_frontmatter(text)
    sections = extract_sections(body)

    title = infer_title(frontmatter, body, path)
    date = infer_date(frontmatter, path)
    ia = str(frontmatter.get("ia") or "ChatGPT").strip('"')
    model = str(frontmatter.get("model") or "GPT-5.4").strip('"')
    source = str(frontmatter.get("source") or "OpenAI").strip('"')
    conversation_type = str(frontmatter.get("conversation_type") or "chat").strip('"')
    area = str(frontmatter.get("area") or "Studies").strip('"')
    folder = str(frontmatter.get("folder") or "04-Studies/tema").strip('"')
    topic = infer_topic(frontmatter, title, sections["conversation"])
    summary = infer_summary(frontmatter, sections["conversation"])
    status = str(frontmatter.get("status") or "complete").strip('"')
    tags = normalize_tags(frontmatter.get("tags"))
    if not tags:
        tags = ["ia", "conversa", "obsidian", slugify(title)[:48] or "tema"]
    related = normalize_related(frontmatter.get("related"))

    yaml_lines = [
        "---",
        f'title: "{title}"',
        f"date: {date}",
        f'ia: "{ia}"',
        f'model: "{model}"',
        f'source: "{source}"',
        f'conversation_type: "{conversation_type}"',
        f'area: "{area}"',
        f'folder: "{folder}"',
        "tags:",
    ]
    yaml_lines.extend(f"  - {tag}" for tag in tags)
    yaml_lines.extend(
        [
            f'topic: "{topic.replace(chr(34), chr(39))}"',
            "summary: >",
            f"  {summary.replace(chr(34), chr(39))}",
            f"status: {status}",
            "related:",
        ]
    )
    if related:
        yaml_lines.extend(f'  - "{item}"' for item in related)
    else:
        yaml_lines.append('  - "[[00-Dashboard - Biblioteca]]"')
    yaml_lines.append("---")

    normalized = "\n".join(
        yaml_lines
        + [
            "",
            SECTION_TITLES["objective"],
            "",
            sections["objective"].strip(),
            "",
            SECTION_TITLES["conversation"],
            "",
            sections["conversation"].strip(),
            "",
            SECTION_TITLES["conclusions"],
            "",
            sections["conclusions"].strip(),
            "",
            SECTION_TITLES["next_steps"],
            "",
            sections["next_steps"].strip(),
            "",
        ]
    )
    return normalized


def backup_file(path: Path, backup_root: Path, vault_root: Path) -> None:
    destination = backup_root / path.relative_to(vault_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)


def should_skip(path: Path) -> bool:
    lower_parts = {part.lower() for part in path.parts}
    return ".obsidian" in lower_parts or "00-templates" in lower_parts or "00-backups" in lower_parts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("vault_path", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--rename-lowercase-ext", action="store_true")
    args = parser.parse_args()

    vault_path = args.vault_path.expanduser()
    files = [path for path in vault_path.rglob("*") if path.is_file() and path.suffix.lower() == ".md" and not should_skip(path)]
    print(f"Arquivos encontrados: {len(files)}")

    changed = 0
    backup_root = args.backup_dir.expanduser() if args.backup_dir else None
    if backup_root:
      backup_root.mkdir(parents=True, exist_ok=True)

    for path in files:
        normalized = normalize_content(path)
        current = path.read_text(encoding="utf-8", errors="replace")
        target_path = path.with_suffix(".md") if args.rename_lowercase_ext else path
        if current == normalized and target_path == path:
            continue
        changed += 1
        print(f"- {path.name}")
        if not args.write:
            continue
        if backup_root:
            backup_file(path, backup_root, vault_path)
        path.write_text(normalized, encoding="utf-8")
        if target_path != path:
            path.rename(target_path)

    print(f"Arquivos a padronizar: {changed}")


if __name__ == "__main__":
    main()
