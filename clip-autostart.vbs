Set shell = CreateObject("WScript.Shell")
shell.Run "cmd.exe /c ""cd /d C:\WINDOWS\system32\obsidian-web-library && clip-server.cmd""", 0, False
WScript.Sleep 5000
shell.Run "cmd.exe /c ""cd /d C:\WINDOWS\system32\obsidian-web-library && clip-expose.cmd""", 0, False
