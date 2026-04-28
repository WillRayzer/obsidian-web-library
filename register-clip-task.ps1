$ErrorActionPreference = "Stop"

$taskName = "ObsidianClipServer"
$scriptPath = "C:\WINDOWS\system32\obsidian-web-library\clip-autostart.vbs"
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$scriptPath`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Description "Start local Obsidian clip server and expose it via Tailscale at logon" -Force | Out-Null
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
