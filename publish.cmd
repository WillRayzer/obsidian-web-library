@echo off
setlocal
cd /d C:\WINDOWS\system32\obsidian-web-library
if exist C:\Python314\python.exe (
  C:\Python314\python.exe publish.py %*
  exit /b %errorlevel%
)
py -3.14 publish.py %*
