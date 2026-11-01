<#
  Get-Digest.ps1 - downloads the latest digest page from GitHub Pages into a local folder.
  Keeps files for N days and deletes older ones. Opens the new digest in the default browser.
  ASCII only on purpose (Windows PowerShell 5.1 reads BOM-less files as ANSI).
#>
param(
    [Parameter(Mandatory = $true)][string]$Url,
    [string]$Dir = "C:\Digests",
    [int]$KeepDays = 30,
    [switch]$Open
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

New-Item -ItemType Directory -Force -Path $Dir | Out-Null
$log = Join-Path $Dir "log.txt"
function Log($m) { Add-Content -Path $log -Value ("{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m) }

$tmp = Join-Path $env:TEMP "digest_download.html"
$ok = $false
for ($i = 1; $i -le 5 -and -not $ok; $i++) {
    try {
        $bust = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        Invoke-WebRequest -UseBasicParsing -Uri ($Url.TrimEnd("/") + "/?t=$bust") -OutFile $tmp -TimeoutSec 60
        $ok = $true
    } catch {
        Log ("Attempt $i failed: " + $_.Exception.Message)
        if ($i -lt 5) { Start-Sleep -Seconds 30 }
    }
}
if (-not $ok) { Log "Giving up, no network or site unavailable."; exit 1 }

$text = [IO.File]::ReadAllText($tmp, [Text.Encoding]::UTF8)
if ($text -notmatch '<meta name="digest-date" content="(\d{4}-\d{2}-\d{2})"') {
    Log "Downloaded page has no digest-date, skipped."
    exit 1
}
$date = $Matches[1]
$target = Join-Path $Dir ("digest-{0}.html" -f $date)
$isNew = -not (Test-Path $target)
[IO.File]::WriteAllText($target, $text, (New-Object Text.UTF8Encoding($false)))
Remove-Item $tmp -ErrorAction SilentlyContinue
Log ("Saved {0} (new: {1})" -f $target, $isNew)

# cleanup of old digests
Get-ChildItem -Path $Dir -Filter "digest-*.html" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepDays) } |
    ForEach-Object { Log ("Deleted old file " + $_.Name); Remove-Item $_.FullName -Force }

if ($Open -and $isNew) { Start-Process $target }
