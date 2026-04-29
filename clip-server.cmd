@echo off
setlocal
cd /d C:\WINDOWS\system32\obsidian-web-library
if exist C:\Python314\python.exe (
  C:\Python314\python.exe clip_server.py --host 127.0.0.1 --port 8787 %*
  exit /b %errorlevel%
)
py -3.14 clip_server.py --host 127.0.0.1 --port 8787 %*
