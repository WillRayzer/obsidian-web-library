#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


THEMES = [
    {
        "name": "psicologia",
        "area": "Studies",
        "folder": "04-Studies/psicologia",
        "tags": ["psicologia", "mente", "comportamento"],
        "keywords": ["psicologia", "psicanalise", "freud", "trauma", "emocional", "ansiedade", "terapia", "neurose"],
    },
    {
        "name": "espiritualidade",
        "area": "Studies",
        "folder": "04-Studies/autoconhecimento-e-espiritualidade",
        "tags": ["espiritualidade", "autoconhecimento", "consciencia"],
        "keywords": ["espiritualidade", "alma", "holistica", "meditacao", "oracao", "energia", "interiorizacao", "deusas"],
    },
    {
        "name": "astrologia",
        "area": "Studies",
        "folder": "04-Studies/astrologia-e-autoconhecimento",
        "tags": ["astrologia", "mapa-natal", "simbolismo"],
        "keywords": ["astrologia", "mapa natal", "signos", "escorpiao", "virgem", "zodiaco", "mapa astral"],
    },
    {
        "name": "neurociencia",
        "area": "Studies",
        "folder": "04-Studies/neurociencia-psicologia",
        "tags": ["neurociencia", "cerebro", "cognicao"],
        "keywords": ["neurociencia", "sinapse", "sinaptica", "cerebro", "mente humana", "autismo", "plasticidade"],
    },
    {
        "name": "saude",
        "area": "Studies",
        "folder": "04-Studies/saude",
        "tags": ["saude", "bem-estar", "estudos"],
        "keywords": ["saude", "doencas", "infecciosas", "psilocybe", "herbal", "herbalismo", "holistica"],
    },
    {
        "name": "direito-previdenciario",
        "area": "Studies",
        "folder": "04-Studies/previdencia-publica",
        "tags": ["previdencia", "direito-previdenciario", "administracao-publica"],
        "keywords": ["aposentadoria", "previdencia", "iprem", "rpps", "decreto", "servidor", "municipal"],
    },
    {
        "name": "governanca-publica",
        "area": "Studies",
        "folder": "04-Studies/governanca-publica",
        "tags": ["governanca-publica", "administracao-publica", "gestao-publica"],
        "keywords": ["governanca", "politicas publicas", "gestao publica", "administracao publica", "accountability"],
    },
    {
        "name": "projetos",
        "area": "Business",
        "folder": "05-Projects/projetos",
        "tags": ["projeto", "organizacao", "business"],
        "keywords": ["projeto", "codinome", "workplace", "trabalho flexivel", "organizacional"],
    },
]

STOPWORDS = {
    "de", "da", "do", "das", "dos", "e", "em", "na", "no", "para", "com", "um", "uma",
    "o", "a", "os", "as", "por", "sobre", "ao", "aos", "que", "como", "mais", "menos",
    "se", "ou", "sem", "sua", "seu", "suas", "seus", "del", "la", "el", "the",
    "with", "from", "into", "this", "that", "was", "are", "been", "can", "will",
    "not", "too", "by", "at", "on", "of", "as", "is", "it", "its", "an", "or",
    "if", "to", "in", "for", "and", "about", "after", "before", "during", "over",
    "under", "between", "through", "toward", "towards", "up", "down", "out",
}

BANNED_TAGS = {
    "ia",
    "conversa",
    "obsidian",
    "web",
    "clip",
    "inbox",
    "news",
    "article",
    "post",
    "page",
    "site",
    "featured",
    "summary",
    "source",
    "content",
}

AUTO_RELATED_START = "<!-- AUTO-RELATED-LINKS:START -->"
AUTO_RELATED_END = "<!-- AUTO-RELATED-LINKS:END -->"
DEFAULT_MODEL = os.environ.get("MOONSHOT_MODEL") or os.environ.get("OPENAI_MODEL") or "kimi-k2.5"
MOONSHOT_BASE_URL = os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.ai/v1").rstrip("/")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


@dataclass
class Note:
    path: Path
    title: str
    frontmatter: dict[str, object]
    body: str
    tokens: set[str]
    tags: list[str]


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-")


def tokenize(text: str) -> set[str]:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    parts = re.findall(r"[a-z0-9]{3,}", text)
    return {part for part in parts if part not in STOPWORDS}


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---\n"):
        return {}, text
    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, text
    raw = parts[0][4:]
    body = parts[1]
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
            data[key] = " ".join(part.strip() for part in block if part.strip()).strip()
            continue
        if value == "":
            block: list[str] = []
            j = i + 1
            while j < len(lines):
                candidate = lines[j]
                if candidate.strip().startswith("- "):
                    block.append(candidate.strip()[2:].strip().strip('"'))
                    j += 1
                    continue
                if not candidate.strip():
                    j += 1
                    continue
                break
            data[key] = block
            i = j
            continue
        data[key] = value.strip('"')
        i += 1
    return data, body


def dump_frontmatter(data: dict[str, object]) -> str:
    lines = ["---"]
    order = [
        "title", "aliases", "date", "ia", "model", "source", "conversation_type", "area", "folder",
        "tags", "topic", "summary", "status", "related"
    ]
    for key in order:
        if key not in data:
            continue
        value = data[key]
        if key in {"aliases", "tags", "related"}:
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
        if key in {"date", "status"}:
            lines.append(f"{key}: {value}")
            continue
        lines.append(f'{key}: "{value}"')
    lines.append("---")
    return "\n".join(lines)


def read_notes(vault_path: Path) -> list[Note]:
    notes: list[Note] = []
    for path in sorted(vault_path.rglob("*.md")):
        lower_parts = {part.lower() for part in path.parts}
        if ".obsidian" in lower_parts or "00-backups" in lower_parts or "00-templates" in lower_parts or "99-archive" in lower_parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        frontmatter, body = parse_frontmatter(text)
        title = str(frontmatter.get("title") or path.stem)
        tags = [slugify(tag) for tag in frontmatter.get("tags", [])] if isinstance(frontmatter.get("tags", []), list) else []
        tokens = tokenize(f"{title}\n{body}\n{' '.join(tags)}")
        notes.append(Note(path=path, title=title, frontmatter=frontmatter, body=body, tokens=tokens, tags=tags))
    return notes


def infer_theme(note: Note) -> dict[str, object] | None:
    scores = []
    haystack = " ".join(note.tokens)
    for theme in THEMES:
        score = 0
        for keyword in theme["keywords"]:
            normalized = slugify(keyword).replace("-", " ")
            if normalized in haystack or slugify(keyword) in haystack:
                score += 1
        if score:
            scores.append((score, theme))
    if not scores:
        return None
    scores.sort(key=lambda item: item[0], reverse=True)
    return scores[0][1]


def infer_tags(note: Note, theme: dict[str, object] | None, strict: bool = False) -> list[str]:
    body_counter = Counter(tokenize(note.body))
    theme_tags = set(theme["tags"]) if theme else set()
    tags = []
    if not strict:
        tags.extend(
            tag for tag in note.tags
            if tag
            and tag not in BANNED_TAGS
            and (tag in theme_tags or body_counter.get(tag, 0) >= 2)
        )
    if theme:
        tags.extend(theme["tags"])
        for keyword in theme["keywords"][:6]:
            slug = slugify(keyword)
            if slug and (slug in note.tokens and body_counter.get(slug, 0) >= 2):
                tags.append(slug)
    title_words = [slugify(word) for word in re.findall(r"[A-Za-zÀ-ÿ0-9-]{4,}", note.title)]
    tags.extend(
        word for word in title_words
        if word and word not in STOPWORDS and body_counter.get(word, 0) >= 2
    )
    unique: list[str] = []
    for tag in tags:
        if not tag or tag in unique:
            continue
        if tag in BANNED_TAGS:
            continue
        unique.append(tag)
    return unique[:12]


def infer_related(note: Note, notes: list[Note], tags: list[str]) -> list[str]:
    tag_set = set(tags)
    candidates: list[tuple[int, str]] = []
    for other in notes:
        if other.path == note.path:
            continue
        overlap = len(tag_set.intersection(other.tags)) + len(note.tokens.intersection(other.tokens))
        if overlap < 3:
            continue
        candidates.append((overlap, other.title))
    candidates.sort(key=lambda item: (-item[0], item[1].lower()))
    related = [f"[[{title}]]" for _, title in candidates[:4]]
    if "[[00-Dashboard - Biblioteca]]" not in related:
        related.append("[[00-Dashboard - Biblioteca]]")
    return related[:5]


def normalize_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def merge_unique(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for item in group:
            if item and item not in merged:
                merged.append(item)
    return merged


def has_ai_key() -> bool:
    return bool(os.environ.get("MOONSHOT_API_KEY", "").strip() or os.environ.get("OPENAI_API_KEY", "").strip())


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
                    "Voce sugere metadados para um segundo cerebro em Obsidian. "
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
        raise RuntimeError("resposta invalida do modelo")
    return json.loads(match.group(0))


def ensure_aliases(frontmatter: dict[str, object], title: str) -> list[str]:
    aliases: list[str] = []
    existing = frontmatter.get("aliases")
    if isinstance(existing, list):
        aliases.extend(str(item).strip() for item in existing if str(item).strip())
    elif isinstance(existing, str) and existing.strip():
        aliases.append(existing.strip())

    if title and title not in aliases:
        aliases.insert(0, title)
    return aliases[:8]


def read_candidate_titles(vault_root: Path, note: Note, limit: int = 24) -> list[str]:
    source_tokens = note.tokens.union(tokenize(note.title))
    candidates: list[tuple[int, str]] = []
    for path in sorted(vault_root.rglob("*.md")):
        lower_parts = {part.lower() for part in path.parts}
        if ".obsidian" in lower_parts or "00-backups" in lower_parts or "00-templates" in lower_parts or "99-archive" in lower_parts:
            continue
        if "pending" in lower_parts:
            continue
        if path == note.path:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        frontmatter, body = parse_frontmatter(text)
        title = str(frontmatter.get("title") or path.stem).strip()
        candidate_tokens = tokenize(f"{title}\n{body[:2400]}")
        overlap = len(source_tokens.intersection(candidate_tokens))
        if overlap:
            candidates.append((overlap, title))
    candidates.sort(key=lambda item: (-item[0], item[1].lower()))
    ordered: list[str] = []
    for _, title in candidates:
        if title not in ordered:
            ordered.append(title)
        if len(ordered) >= limit:
            break
    return ordered


def infer_aliases_ai(note: Note, candidates: list[str]) -> list[str]:
    aliases = ensure_aliases(dict(note.frontmatter), note.title)
    if not has_ai_key():
        return aliases

    candidate_block = "\n".join(f"- {title}" for title in candidates) if candidates else "- (nenhuma candidata encontrada)"
    prompt = f"""
Sugira aliases para uma nota em portugues do Brasil.

Regras:
- Retorne apenas JSON valido.
- Use chaves exatas: aliases, related.
- aliases: lista curta de nomes alternativos uteis para o Obsidian.
- related: lista curta de wikilinks, mas somente para notas que existam na lista de candidatas.
- Nao invente notas fora da lista.

Titulo atual:
{note.title}

Conteudo resumido:
{note.body[:6000]}

Notas candidatas do vault:
{candidate_block}
"""
    try:
        result = call_model(prompt)
    except Exception:
        return aliases

    ai_aliases = [str(item).strip() for item in result.get("aliases", []) if str(item).strip()]
    for alias in ai_aliases:
        if alias not in aliases:
            aliases.append(alias)
    return aliases[:8]


def infer_related_ai(note: Note, candidates: list[str], fallback: list[str]) -> list[str]:
    if not has_ai_key():
        return fallback

    candidate_block = "\n".join(f"- {title}" for title in candidates) if candidates else "- (nenhuma candidata encontrada)"
    prompt = f"""
Sugira conexoes para uma nota em portugues do Brasil.

Regras:
- Retorne apenas JSON valido.
- Use chaves exatas: related.
- related: lista curta com wikilinks.
- Escolha somente entre as notas candidatas fornecidas.
- Priorize notas realmente relacionadas ao conteudo e nao so por tema amplo.

Titulo atual:
{note.title}

Conteudo resumido:
{note.body[:7000]}

Notas candidatas do vault:
{candidate_block}
"""
    try:
        result = call_model(prompt)
    except Exception:
        return fallback

    allowed = {title.lower(): title for title in candidates}
    related: list[str] = []
    for item in result.get("related", []):
        text = str(item).strip().strip('"')
        if not text:
            continue
        cleaned = text
        if cleaned.startswith("[[") and cleaned.endswith("]]"):
            cleaned = cleaned[2:-2]
        if "|" in cleaned:
            cleaned = cleaned.split("|", 1)[0]
        title = allowed.get(cleaned.lower()) or allowed.get(text.lower())
        if not title:
            continue
        wikilink = f"[[{title}]]"
        if wikilink not in related:
            related.append(wikilink)
    if "[[00-Dashboard - Biblioteca]]" not in related:
        related.append("[[00-Dashboard - Biblioteca]]")
    return related[:5]


def ensure_body_related_links(body: str, related: list[str]) -> str:
    cleaned = body.strip()
    pattern = re.compile(
        rf"\n?{re.escape(AUTO_RELATED_START)}.*?{re.escape(AUTO_RELATED_END)}\n?",
        re.S,
    )
    cleaned = re.sub(pattern, "\n", cleaned).strip()

    links = [link for link in related if link and link != "[[00-Dashboard - Biblioteca]]"]
    if not links:
        return cleaned + "\n"

    section_lines = [
        AUTO_RELATED_START,
        "## Related Notes",
        "",
        *[f"- {link}" for link in links],
        AUTO_RELATED_END,
    ]
    section = "\n".join(section_lines)
    if cleaned:
        return cleaned + "\n\n" + section + "\n"
    return section + "\n"


def backup_file(path: Path, backup_root: Path, vault_root: Path) -> None:
    destination = backup_root / path.relative_to(vault_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("vault_path", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--backup-dir", type=Path, default=None)
    args = parser.parse_args()

    vault_path = args.vault_path.expanduser()
    notes = read_notes(vault_path)
    backup_root = args.backup_dir.expanduser() if args.backup_dir else None
    if backup_root:
        backup_root.mkdir(parents=True, exist_ok=True)

    changed = 0
    for note in notes:
        is_web_clip = str(note.frontmatter.get("conversation_type") or "").strip().lower() == "web-clip"
        is_inbox_note = str(note.frontmatter.get("area") or "").strip().lower() == "inbox" or str(note.frontmatter.get("folder") or "").strip().startswith("00-Inbox")
        theme = None if (is_web_clip or is_inbox_note) else infer_theme(note)
        front = dict(note.frontmatter)
        existing_aliases = normalize_list(front.get("aliases"))
        existing_tags = normalize_list(front.get("tags"))
        existing_related = normalize_list(front.get("related"))

        if theme:
            front["area"] = theme["area"]
            front["folder"] = theme["folder"]
        else:
            front["area"] = str(front.get("area") or "Studies")
            front["folder"] = str(front.get("folder") or "04-Studies/tema")
        candidate_titles = read_candidate_titles(vault_path, note)
        aliases = merge_unique(existing_aliases, infer_aliases_ai(note, candidate_titles))
        if note.title not in aliases:
            aliases.insert(0, note.title)
        front["aliases"] = aliases[:8]

        inferred_tags = infer_tags(note, theme, strict=is_web_clip or is_inbox_note)
        if is_web_clip:
            tags = merge_unique(existing_tags, inferred_tags)
        else:
            tags = inferred_tags
        front["tags"] = tags

        inferred_related = infer_related(note, notes, tags)
        ai_related = infer_related_ai(note, candidate_titles, inferred_related)
        if existing_related:
            related = merge_unique(existing_related, ai_related)
        else:
            related = ai_related
        front["related"] = related
        enriched_body = ensure_body_related_links(note.body, related)
        serialized = dump_frontmatter(front).strip() + "\n\n" + enriched_body.strip() + "\n"
        current = note.path.read_text(encoding="utf-8", errors="replace")
        if serialized == current:
            continue
        changed += 1
        print(f"- {note.path.name}")
        if not args.write:
            continue
        if backup_root:
            backup_file(note.path, backup_root, vault_path)
        note.path.write_text(serialized, encoding="utf-8")
    print(f"Arquivos enriquecidos: {changed}")


if __name__ == "__main__":
    main()
