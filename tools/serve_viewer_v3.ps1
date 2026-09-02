<#
Viewer v3 sunucusunu, RAG Console'un .env dosyasindaki anahtarlari BU surece
yukleyerek baslatir.

Neden var: amsc.viewer_server anahtari calisma aninda os.environ'dan okur ve
(bilerek) hicbir .env dosyasi yuklemez. chat_rag/.env'i yalnizca konsolun
kendi sureci (python-dotenv ile) okur; viewer sunucusu ayri bir surec oldugu
icin anahtari goremez. Bu script degerleri yalnizca baslattigi surecin
ortamina koyar - hicbir sey yazdirmaz, kaydetmez, kalici yapmaz.

Kullanim (chunk klasorunden):
    powershell -ExecutionPolicy Bypass -File tools\serve_viewer_v3.ps1
    tools\serve_viewer_v3.ps1 -Viewer artifacts\viewer-v3\index.html -Port 8765
    tools\serve_viewer_v3.ps1 -NoServe        # yalnizca env yuklemeyi test et
#>
param(
    [string]$EnvFile = (Join-Path $PSScriptRoot "..\..\chat_rag\.env"),
    [string]$Viewer = "artifacts\viewer-v3\index.html",
    [string]$Config = "configs\rag-poc.yaml",
    [int]$Port = 8765,
    [string]$ConsoleUrl = "http://127.0.0.1:5005",
    [switch]$Warm,
    [switch]$NoServe
)

$EnvFile = [System.IO.Path]::GetFullPath($EnvFile)
if (-not (Test-Path $EnvFile)) {
    Write-Error ".env bulunamadi: $EnvFile"
    exit 1
}

$loaded = @()
foreach ($line in Get-Content $EnvFile) {
    $line = $line.Trim()
    if ($line -eq "" -or $line.StartsWith("#")) { continue }
    $eq = $line.IndexOf("=")
    if ($eq -lt 1) { continue }
    $name = $line.Substring(0, $eq).Trim()
    $value = $line.Substring($eq + 1).Trim()
    # python-dotenv gibi: sarmalayan tek/cift tirnaklari at
    if ($value.Length -ge 2 -and (
        ($value.StartsWith('"') -and $value.EndsWith('"')) -or
        ($value.StartsWith("'") -and $value.EndsWith("'")))) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    # -cmatch (case-sensitive/ordinal) sart: kulture duyarli -match, tr-TR
    # altinda 'I' harfini 'i'ya degil 'ı'ya indirdigi icin [A-Za-z] sinifina
    # sokmaz ve I iceren her degisken adini (OPENROUTER_API_KEY dahil) eler.
    if ($name -cmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
        $loaded += $name
    }
}
Write-Host ("env yuklendi ({0} degisken): {1}" -f $loaded.Count, ($loaded -join ", "))

$key = $env:OPENROUTER_API_KEY
if ($key) { Write-Host ("OPENROUTER_API_KEY: SET (len={0})" -f $key.Length) }
else { Write-Warning "OPENROUTER_API_KEY bu .env'de yok - canli cevap calismayacak." }

if ($NoServe) { exit 0 }

$chunkRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
Set-Location $chunkRoot
$serverArgs = @("-3.11", "-m", "amsc.viewer_server",
    "--viewer", $Viewer, "--config", $Config, "--port", $Port)
# PowerShell bos stringi native cagrida dusurur; --console-url degersiz
# kalmasin diye yalnizca dolu bir deger varsa eklenir.
if ($ConsoleUrl) { $serverArgs += @("--console-url", $ConsoleUrl) }
if ($Warm) { $serverArgs += "--warm" }
& py @serverArgs
