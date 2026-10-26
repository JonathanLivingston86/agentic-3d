#!/bin/bash
# Agentic 3D: installazione su macOS. Doppio clic su questo file (dopo aver estratto tutto lo ZIP).
# Non servono diritti di amministratore: tutto va nella cartella dell'utente. Si rilancia per aggiornare.

cd "$(dirname "$0")/../componenti" || exit 1
# il Mac mette in quarantena i file scaricati e blocca ogni .command: approvato questo, si toglie la quarantena al
# resto della cartella, così Disinstalla e gli altri file non vengono più bloccati
xattr -dr com.apple.quarantine "$(cd .. && pwd)" 2>/dev/null
CONFIGURAZIONE="$HOME/Library/Application Support/Agentic 3D"
mkdir -p "$CONFIGURAZIONE"
RAPPORTO="$CONFIGURAZIONE/Rapporto installazione.txt"
BIN="$HOME/.local/bin"

fine() {
    echo ""
    echo "Rapporto completo: $RAPPORTO"
    echo ""
    read -r -p "Premi Invio per chiudere " _
    exit "$1"
}

errore() {
    echo ""
    echo "Installazione interrotta: $1"
    echo "Chiedi al tuo agente AI di leggere il rapporto qui sotto e di seguire la guida."
    exit 1                  # esce dal blocco registrato nel rapporto; "fine" chiude dopo
}

chiudi_server() {
    # un agente aperto tiene acceso il server di Agentic 3D: si chiude (l'agente lo riapre al prossimo avvio)
    if pgrep -f "uv/tools/agentic3d/" >/dev/null 2>&1; then
        echo "Chiudo il server di Agentic 3D aperto da un agente AI (si riapre quando riavvii l'agente)."
        pkill -f "uv/tools/agentic3d/" 2>/dev/null
        sleep 1
    fi
}

passo() { echo ""; echo "[$1/5] $2"; }

{
echo "Agentic 3D: installazione"
echo "macOS $(sw_vers -productVersion), cartella: $(pwd)"

PACCHETTO=$(ls -t agentic3d-*.whl 2>/dev/null | head -n 1)
[ -n "$PACCHETTO" ] || errore "non trovo il file agentic3d-*.whl. Estrai tutto lo ZIP in una cartella e riprova."

passo 1 "uv (installa Agentic 3D e il suo Python senza toccare il resto del computer)"
UV="$BIN/uv"
[ -x "$UV" ] || UV=$(command -v uv)
if [ -z "$UV" ] || [ ! -x "$UV" ]; then
    echo "uv non c'è: lo scarico dal sito ufficiale (astral.sh)."
    curl -LsSf https://astral.sh/uv/install.sh | sh || errore "uv non si è installato: controlla la connessione a internet e riprova."
    UV="$BIN/uv"
fi
"$UV" --version || errore "uv non risponde."

passo 2 "Agentic 3D $PACCHETTO"
chiudi_server
"$UV" tool install --reinstall --python 3.13 "$(pwd)/$PACCHETTO" || errore "installazione del pacchetto non riuscita (vedi le righe sopra)."
"$UV" tool update-shell >/dev/null 2>&1
AGENTIC="$BIN/agentic3d"

passo 3 "Collegamento agli agenti AI installati (Skill e server MCP, con copia di sicurezza)"
"$AGENTIC" collega || errore "collegamento agli agenti non riuscito (vedi le righe sopra)."

passo 4 "Estensione per SketchUp"
"$AGENTIC" installa-estensione || echo "SketchUp non trovato: se lo usi, aprilo e chiudilo una volta, poi rilancia questo installatore. Senza SketchUp, dopo i render il modello si apre in Blender."

passo 5 "Verifica"
"$AGENTIC" verifica

echo ""
echo "Installazione completata."
echo "Ora: chiudi e riapri il tuo agente AI (e SketchUp, se lo usi). Al primo avvio SketchUp può chiedere di approvare l'estensione Agentic 3D: approvala."
echo "Se una riga sopra dice ERRORE o ATTENZIONE, chiedi al tuo agente: Verifica l'installazione di Agentic 3D."
} 2>&1 | tee "$RAPPORTO"
fine "${PIPESTATUS[0]}"
