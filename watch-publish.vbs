Set shell = CreateObject("WScript.Shell")
shell.Run "wsl.exe bash -lc ""cd /mnt/c/WINDOWS/system32/obsidian-web-library && python3 publish.py --watch --interval 30 >> /tmp/obsidian-web-library-watch.log 2>&1""", 0, False
