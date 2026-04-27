#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET


AUTO_INGEST_PREFIX = "<!-- AUTO-INGEST:"
AUTO_INGEST_SUFFIX = "-->"
SKIP_DIRS = {".obsidian", "00-backups", "00-templates"}


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-")


def title_case_from_stem(stem: str) -> str:
    text = stem.replace("_", " ").replace("-", " ").strip()
    return text[:1].upper() + text[1:] if text else "Documento importado"


def should_skip(path: Path) -> bool:
    return any(part.lower() in SKIP_DIRS for part in path.parts)


def clean_text(text: str) -> str:
    text = text.replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines).strip()


def extract_docx_text(path: Path) -> str:
    paragraphs: list[str] = []
    with zipfile.ZipFile(path) as zf:
        xml_bytes = zf.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    for paragraph in root.findall(".//w:p", ns):
        parts = [node.text or "" for node in paragraph.findall(".//w:t", ns)]
        text = "".join(parts).strip()
        if text:
            paragraphs.append(text)
    return clean_text("\n".join(paragraphs))


def extract_pdf_text(path: Path) -> str:
    result = subprocess.run(
        ["strings", "-n", "6", str(path)],
        check=True,
        capture_output=True,
        text=True,
        errors="replace",
    )
    lines: list[str] = []
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("%PDF") or line.startswith("/Type") or line.startswith("endobj"):
            continue
        if re.fullmatch(r"[\d\W_]+", line):
            continue
        if len(line) < 6:
            continue
        lines.append(line)
    return clean_text("\n".join(lines))


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return extract_docx_text(path)
    if suffix == ".pdf":
        return extract_pdf_text(path)
    raise ValueError(f"Formato nao suportado: {path.suffix}")


def auto_marker(source: Path) -> str:
    stat = source.stat()
    signature = f"{source.name}|{int(stat.st_mtime)}|{stat.st_size}"
    return f"{AUTO_INGEST_PREFIX}{signature}{AUTO_INGEST_SUFFIX}"


def current_marker(text: str) -> str:
    match = re.search(r"<!-- AUTO-INGEST:.*?-->", text)
    return match.group(0) if match else ""


def guess_area(source: Path) -> str:
    lower = source.stem.lower()
    if any(word in lower for word in ["relatorio", "trabalho", "projeto"]):
        return "Business"
    return "Studies"


def build_markdown(source: Path, extracted_text: str) -> str:
    title = title_case_from_stem(source.stem)
    date = datetime.fromtimestamp(source.stat().st_mtime).strftime("%Y-%m-%d")
    area = guess_area(source)
    topic = clean_text(extracted_text[:180]) or f"Documento importado de {source.name}"
    summary = clean_text(extracted_text[:320]) or f"Resumo extraido automaticamente de {source.name}"
    body = extracted_text[:18000].strip() or "Nao foi possivel extrair texto legivel deste documento."
    marker = auto_marker(source)
    lines = [
        "---",
        f'title: "{title}"',
        f"date: {date}",
        'ia: "AutoImport"',
        'model: "Local Ingestion"',
        f'source: "{source.name}"',
        'conversation_type: "document-import"',
        f'area: "{area}"',
        'folder: "04-Studies/importados"',
        "tags:",
        "  - ia",
        "  - obsidian",
        "  - documento",
        "  - importado",
        f'topic: "{topic.replace(chr(34), chr(39))}"',
        "summary: >",
        f"  {summary.replace(chr(34), chr(39))}",
        "status: complete",
        "related:",
        '  - "[[00-Dashboard - Biblioteca]]"',
        "---",
        "",
        "## Objective",
        "",
        f"Registrar o conteudo extraido automaticamente do documento `{source.name}` para uso no Obsidian e na biblioteca web.",
        "",
        "## Conversation",
        "",
        marker,
        "",
        body,
        "",
        "## Conclusions & Deliverables",
        "",
        "- [ ] Revisar a extração automática",
        "- [ ] Ajustar título, resumo e tags se necessário",
        "",
        "## Next Steps",
        "",
        "- [ ] Relacionar esta nota com outras do vault",
        "",
    ]
    return "\n".join(lines)


def target_markdown_path(source: Path) -> Path:
    return source.with_suffix(".md")


def ingest_document(source: Path) -> tuple[bool, str]:
    target = target_markdown_path(source)
    marker = auto_marker(source)

    if target.exists():
        current = target.read_text(encoding="utf-8", errors="replace")
        existing_marker = current_marker(current)
        if existing_marker == marker:
            return False, f"sem mudanca: {source.name}"
        if existing_marker and existing_marker != marker:
            extracted = extract_text(source)
            target.write_text(build_markdown(source, extracted), encoding="utf-8")
            return True, f"atualizado: {target.name}"
        return False, f"ignorado por nota existente: {target.name}"

    extracted = extract_text(source)
    target.write_text(build_markdown(source, extracted), encoding="utf-8")
    return True, f"gerado: {target.name}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("vault_path", type=Path)
    args = parser.parse_args()

    vault_path = args.vault_path.expanduser()
    changed = 0
    scanned = 0
    for path in sorted(vault_path.rglob("*")):
        if not path.is_file() or should_skip(path):
            continue
        if path.suffix.lower() not in {".pdf", ".docx"}:
            continue
        scanned += 1
        try:
            did_change, status = ingest_document(path)
            if did_change:
                changed += 1
            print(status)
        except Exception as exc:
            print(f"erro: {path.name}: {exc}")
    print(f"Documentos analisados: {scanned}")
    print(f"Notas geradas/atualizadas: {changed}")


if __name__ == "__main__":
    main()
