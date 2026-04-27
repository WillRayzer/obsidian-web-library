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
    if target.exists():
        shutil.rmtree(target, onexc=handle_remove_readonly)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("workspace.json"))


def prepare_vault(target: Path) -> None:
    run(["python3", str(NORMALIZE_SCRIPT), str(target), "--write", "--rename-lowercase-ext"])
    run(["python3", str(ENRICH_SCRIPT), str(target), "--write"])


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
    before = tree_hash(target) if target.exists() else ""
    copy_tree(source, target)
    prepare_vault(target)
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
