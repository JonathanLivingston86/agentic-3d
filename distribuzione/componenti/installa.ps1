# Installazione di Agentic 3D su Windows (lanciata da Windows\Installa.cmd).
# Non servono diritti di amministratore: tutto va nella cartella dell'utente. Si rilancia per aggiornare.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$cartella = Split-Path -Parent $MyInvocation.MyCommand.Path
$configurazione = Join-Path $env:APPDATA "Agentic 3D"
New-Item -ItemType Directory -Force -Path $configurazione | Out-Null
$rapporto = Join-Path $configurazione "Rapporto installazione.txt"
Start-Transcript -Path $rapporto -Force | Out-Null
# Python scrive in UTF-8 e PowerShell legge in UTF-8 (senza: "perche'" diventa "perch├®")
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

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
function Passo($n, $testo) { Write-Host ""; Write-Host "[$n/5] $testo" -ForegroundColor Cyan }
function Fine($ok) {
    Write-Host ""
    Write-Host "Rapporto completo: $rapporto"
    Stop-Transcript | Out-Null
    Write-Host ""
    if ($env:AGENTIC3D_PROVA_INSTALLATORE -ne "1") { Read-Host "Premi Invio per chiudere" }
    if ($ok) { exit 0 } else { exit 1 }
}

try {
    Write-Host "Agentic 3D: installazione" -ForegroundColor Green
    Write-Host ("Windows " + [Environment]::OSVersion.Version + ", cartella: " + $cartella)

    $pacchetto = Get-ChildItem -Path $cartella -Filter "agentic3d-*.whl" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $pacchetto) { throw "Non trovo il file agentic3d-*.whl nella cartella componenti. Estrai tutto lo ZIP in una cartella e riprova." }

    Passo 1 "uv (installa Agentic 3D e il suo Python senza toccare il resto del computer)"
    $bin = Join-Path $env:USERPROFILE ".local\bin"
    $uv = Join-Path $bin "uv.exe"
    if (-not (Test-Path $uv)) {
        $trovato = Get-Command uv -ErrorAction SilentlyContinue
        if ($trovato) { $uv = $trovato.Source }
    }
    if (-not (Test-Path $uv)) {
        Write-Host "uv non c'e': lo scarico dal sito ufficiale (astral.sh)."
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
        $uv = Join-Path $bin "uv.exe"
        if (-not (Test-Path $uv)) { throw "uv non si e' installato: controlla la connessione a internet e riprova." }
    }
    & $uv --version

    Passo 2 ("Agentic 3D " + $pacchetto.Name)
    Chiudi-Server
    & $uv tool install --reinstall --python 3.13 $pacchetto.FullName
    if ($LASTEXITCODE -ne 0) { throw "installazione del pacchetto non riuscita (vedi le righe sopra)." }
    if ($env:AGENTIC3D_PROVA_INSTALLATORE -ne "1") { & $uv tool update-shell | Out-Null }   # la prova automatica non tocca il PATH
    $agentic = Join-Path $bin "agentic3d.exe"

    Passo 3 "Collegamento agli agenti AI installati (Skill e server MCP, con copia di sicurezza)"
    $collegamento = & $agentic collega
    if ($LASTEXITCODE -ne 0) { $collegamento; throw "collegamento agli agenti non riuscito (vedi le righe sopra)." }
    foreach ($riga in $collegamento) {
        if ($riga -like "COLLEGATO A:*") { Write-Host $riga -ForegroundColor Green }
        elseif ($riga -like "NON TROVATI:*" -or $riga -like "ATTENZIONE*") { Write-Host $riga -ForegroundColor Yellow }
        else { Write-Host $riga }
    }

    Passo 4 "Estensione per SketchUp"
    # PowerShell 5.1 non registra nel rapporto l'output dei programmi esterni: passa da Write-Host
    & $agentic installa-estensione | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) { Write-Host "SketchUp non trovato: se lo usi, aprilo e chiudilo una volta, poi rilancia questo installatore." -ForegroundColor Yellow }

    Passo 5 "Verifica"
    & $agentic verifica | ForEach-Object { Write-Host $_ }

    Write-Host ""
    Write-Host "Installazione completata." -ForegroundColor Green
    Write-Host "Ora: chiudi e riapri il tuo agente AI e SketchUp. Al primo avvio SketchUp puo' chiedere di approvare l'estensione Agentic 3D: approvala."
    Write-Host "Se una riga sopra dice ERRORE o ATTENZIONE, chiedi al tuo agente: Verifica l'installazione di Agentic 3D."
    Fine $true
}
catch {
    Write-Host ""
    Write-Host ("Installazione interrotta: " + $_.Exception.Message) -ForegroundColor Red
    Write-Host "Chiedi al tuo agente AI di leggere il rapporto qui sotto e di seguire la guida."
    Fine $false
}
