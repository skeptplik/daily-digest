<#
  Install-Task.ps1 - registers a Windows scheduled task "DailyDigest".
  Runs every day at 08:30 and at every logon. If the PC was off at 08:30,
  the task runs as soon as possible after the PC is turned on.
  Usage:  powershell -ExecutionPolicy Bypass -File .\Install-Task.ps1 -Owner YOUR_GITHUB_LOGIN
#>
param(
    [Parameter(Mandatory = $true)][string]$Owner,
    [string]$Repo = "daily-digest",
    [string]$Dir = "C:\Digests",
    [int]$KeepDays = 30,
    [string]$Time = "08:30"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $Dir | Out-Null

$script = Join-Path $Dir "Get-Digest.ps1"
Copy-Item -Path (Join-Path $PSScriptRoot "Get-Digest.ps1") -Destination $script -Force

$url = "https://$($Owner.ToLower()).github.io/$Repo/"
$args = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`" -Url `"$url`" -Dir `"$Dir`" -KeepDays $KeepDays -Open"

$action   = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $args
$triggers = @(
    (New-ScheduledTaskTrigger -Daily -At $Time),
    (New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME")
)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -RunOnlyIfNetworkAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName "DailyDigest" -Action $action -Trigger $triggers `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "Done. Task 'DailyDigest' created."
Write-Host "Page URL : $url"
Write-Host "Folder   : $Dir  (files older than $KeepDays days are deleted automatically)"
Write-Host "Test now : Start-ScheduledTask -TaskName DailyDigest"
