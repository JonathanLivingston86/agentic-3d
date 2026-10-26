# Disinstallazione di Agentic 3D su Windows (lanciata da Windows\Disinstalla.cmd).
# Toglie Skill e server MCP dagli agenti e il programma. I lavori restano dove sono.

$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$bin = Join-Path $env:USERPROFILE ".local\bin"
$agentic = Join-Path $bin "agentic3d.exe"
$uv = Join-Path $bin "uv.exe"
if (-not (Test-Path $uv)) { $trovato = Get-Command uv -ErrorAction SilentlyContinue; if ($trovato) { $uv = $trovato.Source } }

function Chiudi-Server {
    # un agente aperto tiene acceso il server di Agentic 3D: Windows non lascia sostituire i file in uso.
    # Si chiude (l'agente lo riapre da solo al prossimo avvio).
    $aperti = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*\uv\tools\agentic3d\*" }
    if ($aperti) {
        Write-Host "Chiudo il server di Agentic 3D aperto da un agente AI (si riapre quando riavvii l'agente)."
        $aperti | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
}
Write-Host "Agentic 3D: disinstallazione" -ForegroundColor Green
if (Test-Path $agentic) {
    Write-Host ""
    Write-Host "[1/2] Scollego Agentic 3D dagli agenti AI" -ForegroundColor Cyan
    & $agentic scollega
} else {
    Write-Host "Agentic 3D non risulta installato in $bin."
}
if (Test-Path $uv) {
    Write-Host ""
    Write-Host "[2/2] Tolgo il programma" -ForegroundColor Cyan
    Chiudi-Server
    & $uv tool uninstall agentic3d
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "Non sono riuscito a togliere il programma: chiudi tutti gli agenti AI e rilancia la disinstallazione." -ForegroundColor Red
        Write-Host ""
        Read-Host "Premi Invio per chiudere"
        exit 1
    }
}
Write-Host ""
Write-Host "Fatto. I lavori sono rimasti nella loro cartella (di solito Documenti\Agentic 3D)."
Write-Host "L'estensione di SketchUp si toglie da SketchUp: Estensioni > Gestione estensioni > Agentic 3D > Disinstalla."
Write-Host ""
Read-Host "Premi Invio per chiudere"
