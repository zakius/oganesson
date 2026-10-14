# Starts the installed oganesson in the signed-in desktop session (SSH runs outside it).
$exe = "$env:LOCALAPPDATA\oganesson\Application\chrome.exe"
$action = New-ScheduledTaskAction -Execute $exe -Argument '--enable-logging --v=0'
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
Register-ScheduledTask -TaskName OganessonRun -Action $action -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName OganessonRun
Start-Sleep 15
Get-Process chrome -ErrorAction SilentlyContinue | Select-Object Id, SessionId, MainWindowTitle | Format-Table -AutoSize
