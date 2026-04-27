#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import shutil
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
SYNC_STATUS_PATH = ROOT / "sync-status.json"
NORMALIZE_SCRIPT = ROOT / "normalize_conversations.py"
ENRICH_SCRIPT = ROOT / "enrich_vault_metadata.py"
WEAK_NOTES_REPORT_SCRIPT = ROOT / "report_weak_notes.py"
AUDIT_SCRIPT = ROOT / "audit_vault_coherence.py"
INGEST_SCRIPT = ROOT / "ingest_documents.py"
CONTEXT_LINKS_SCRIPT = ROOT / "add_context_links.py"
REPORTS_DIR = ROOT / "reports"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd or ROOT, check=True)


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def write_sync_status(timestamp: str, source: Path, commit_message: str) -> None:
    payload = {
        "last_sync_local": timestamp,
        "source_vault_path": str(source),
        "last_commit": commit_message,
    }
    SYNC_STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def repo_clean() -> bool:
    result = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, check=True, capture_output=True, text=True)
    return not result.stdout.strip()


def handle_remove_readonly(func, path, exc_info) -> None:
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
    func(path)


def copy_tree(source: Path, target: Path) -> None:
    temp_target = ROOT / f"{target.name}.tmp"
    if temp_target.exists():
        shutil.rmtree(temp_target, onexc=handle_remove_readonly)

    shutil.copytree(
        source,
        temp_target,
        ignore=shutil.ignore_patterns(
            "workspace.json",
            "00-Backups",
            "00-Templates",
            "99-Archive",
            ".obsidian",
            "*.docx",
            "*.pdf",
            "*.canvas",
        ),
    )

    target.mkdir(parents=True, exist_ok=True)
    for child in list(target.iterdir()):
        if child.name == ".obsidian":
            continue
        if child.is_dir():
            shutil.rmtree(child, onexc=handle_remove_readonly)
        else:
            child.unlink()

    for child in temp_target.iterdir():
        shutil.move(str(child), str(target / child.name))

    shutil.rmtree(temp_target, onexc=handle_remove_readonly)


def ingest_documents(source: Path) -> None:
    run(["python3", str(INGEST_SCRIPT), str(source)])


def prepare_vault(target: Path) -> None:
    run(["python3", str(NORMALIZE_SCRIPT), str(target), "--write", "--rename-lowercase-ext"])
    run(["python3", str(ENRICH_SCRIPT), str(target), "--write"])
    run(["python3", str(CONTEXT_LINKS_SCRIPT), str(target), "--write", "--limit", "20"])


def update_reports(target: Path) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    run(
        [
            "python3",
            str(WEAK_NOTES_REPORT_SCRIPT),
            str(target),
            "--output",
            str(REPORTS_DIR / "weak-notes-report.md"),
        ]
    )
    run(
        [
            "python3",
            str(AUDIT_SCRIPT),
            str(target),
            "--output",
            str(REPORTS_DIR / "vault-coherence-audit.md"),
        ]
    )


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def sync_and_publish(message: str | None = None) -> bool:
    config = load_config()
    source = Path(config["source_vault_path"]).expanduser()
    target = ROOT / config["vault_path"]
    ingest_documents(source)
    before = tree_hash(target) if target.exists() else ""
    copy_tree(source, target)
    prepare_vault(target)
    update_reports(target)
    after = tree_hash(target)

    if before == after and repo_clean():
        print("Nenhuma mudanca no vault.")
        return False

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    commit_message = message or f"Update vault {timestamp}"
    write_sync_status(timestamp, source, commit_message)
    run(["python3", "build.py"])
    run(["git", "add", "."])

    if repo_clean():
        print("Nenhuma mudanca para commit.")
        return False

    run(["git", "commit", "-m", commit_message])
    run(["git", "push"])
    print("Publicado com sucesso.")
    return True


def watch(interval: int) -> None:
    config = load_config()
    source = Path(config["source_vault_path"]).expanduser()
    last_hash = tree_hash(source)
    print(f"Monitorando: {source}")
    while True:
        time.sleep(interval)
        current_hash = tree_hash(source)
        if current_hash == last_hash:
            continue
        print("Mudanca detectada. Publicando...")
        sync_and_publish()
        last_hash = current_hash


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--message", default=None)
    args = parser.parse_args()

    if args.watch:
        watch(args.interval)
        return

    sync_and_publish(args.message)


if __name__ == "__main__":
    main()
