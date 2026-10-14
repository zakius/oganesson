# Uninstalls oganesson (Chromium's setup.exe), then starts the installer with its GUI in the
# signed-in desktop session.
Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force
$setup = Get-ChildItem "$env:LOCALAPPDATA\oganesson\Application\*\Installer\setup.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($setup) { Start-Process $setup.FullName -ArgumentList '--uninstall','--force-uninstall' -Wait }
"installed after uninstall: " + (Test-Path "$env:LOCALAPPDATA\oganesson\Application\chrome.exe")
Copy-Item \\host.lan\Data\oganesson-installer.exe $env:TEMP\og-installer.exe -Force
Unblock-File $env:TEMP\og-installer.exe
$action = New-ScheduledTaskAction -Execute "$env:TEMP\og-installer.exe"
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
Register-ScheduledTask -TaskName OganessonInstaller -Action $action -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName OganessonInstaller
