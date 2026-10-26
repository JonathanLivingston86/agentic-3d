#!/bin/bash
# Agentic 3D: disinstallazione su macOS. Toglie Skill e server MCP dagli agenti e il programma; i lavori restano.

BIN="$HOME/.local/bin"
UV="$BIN/uv"
[ -x "$UV" ] || UV=$(command -v uv)
chiudi_server() {
    # un agente aperto tiene acceso il server di Agentic 3D: si chiude (l'agente lo riapre al prossimo avvio)
    if pgrep -f "uv/tools/agentic3d/" >/dev/null 2>&1; then
        echo "Chiudo il server di Agentic 3D aperto da un agente AI (si riapre quando riavvii l'agente)."
        pkill -f "uv/tools/agentic3d/" 2>/dev/null
        sleep 1
    fi
}

echo "Agentic 3D: disinstallazione"
if [ -x "$BIN/agentic3d" ]; then
    echo ""; echo "[1/2] Scollego Agentic 3D dagli agenti AI"
    "$BIN/agentic3d" scollega
else
    echo "Agentic 3D non risulta installato in $BIN."
fi
if [ -n "$UV" ] && [ -x "$UV" ]; then
    echo ""; echo "[2/2] Tolgo il programma"
    chiudi_server
    "$UV" tool uninstall agentic3d
fi
echo ""
echo "Fatto. I lavori sono rimasti nella loro cartella (di solito Documenti/Agentic 3D)."
echo "L'estensione di SketchUp si toglie da SketchUp: Estensioni > Gestione estensioni > Agentic 3D > Disinstalla."
echo ""
read -r -p "Premi Invio per chiudere " _
