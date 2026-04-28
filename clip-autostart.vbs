Set shell = CreateObject("WScript.Shell")
shell.Run "wsl.exe bash -lc ""cd /mnt/c/WINDOWS/system32/obsidian-web-library && python3 clip_server.py --host 127.0.0.1 --port 8787""", 0, False
WScript.Sleep 5000
shell.Run "cmd.exe /c ""cd /d C:\WINDOWS\system32\obsidian-web-library && clip-expose.cmd""", 0, False
