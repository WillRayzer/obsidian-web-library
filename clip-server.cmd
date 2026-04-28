@echo off
wsl.exe bash -lc "cd /mnt/c/WINDOWS/system32/obsidian-web-library && python3 clip_server.py --host 127.0.0.1 --port 8787"
