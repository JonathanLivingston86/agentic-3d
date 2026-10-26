"""Avvio e chiusura di Blender con il ponte MCP, senza finestre di terminale.

Blender si apre con il profilo dedicato all'agente e il server del ponte acceso sulla porta 9876 (solo su questo
computer). Sulle finestre nere: `blender.exe` apre sempre una console, mentre `blender-launcher.exe` (il programma
che usa anche il menu Start) no; il processo viene poi creato senza finestra (`CREATE_NO_WINDOW`).

`costruisci --render` usa queste funzioni da sola: apre Blender se è chiuso e lo richiude a fine lavoro, ma solo se
l'ha aperto lei (un Blender che stavi usando tu non si tocca). Il ponte accetta codice da qualunque programma del
computer: per questo non resta aperto più del necessario.

    python -m agentic3d blender avvia | chiudi | stato
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from ..configurazione import eseguibile_blender

PORTA = 9876
PROFILO = Path(os.environ.get("AGENTIC3D_PROFILO_BLENDER", str(Path.home() / ".blender-agentic")))
AVVIA_SERVER = ("import bpy; bpy.app.timers.register(lambda: (bpy.ops.blendermcp.start_server(), None)[1], "
                "first_interval=3.0)")
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


def ponte_acceso(porta: int = PORTA, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection(("localhost", porta), timeout=timeout):
            return True
    except OSError:
        return False


def comando_blender() -> tuple[list[str], dict[str, str]]:
    """Comando e ambiente con cui si avvia Blender per l'agente (launcher senza console, profilo dedicato)."""
    exe = eseguibile_blender() or Path("blender")
    ambiente = dict(os.environ)
    ambiente["BLENDER_USER_CONFIG"] = str(PROFILO / "config")
    ambiente["BLENDER_USER_SCRIPTS"] = str(PROFILO / "scripts")
    return [str(exe), "--python-expr", AVVIA_SERVER], ambiente


def avvia_blender(attesa: float = 90.0, aperto=ponte_acceso, avvia=subprocess.Popen) -> bool:
    """Apre Blender (senza finestre di terminale) e aspetta il ponte. True se l'ha aperto lei, False se era già aperto."""
    if aperto():
        return False
    comando, ambiente = comando_blender()
    if not Path(comando[0]).exists():
        raise FileNotFoundError("Blender non trovato: installalo oppure indica dove si trova con "
                                "`agentic3d impostazioni blender <percorso>`")
    opzioni = {}
    if sys.platform == "win32":
        opzioni["creationflags"] = CREATE_NO_WINDOW | DETACHED_PROCESS
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = 7                       # SW_SHOWMINNOACTIVE: finestra ridotta a icona, senza rubare il fuoco
        opzioni["startupinfo"] = info
    avvia(comando, env=ambiente, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
          close_fds=True, **opzioni)
    fine = time.time() + attesa
    while time.time() < fine:
        if aperto():
            return True
        time.sleep(1.0)
    raise TimeoutError(f"il ponte di Blender non risponde sulla porta {PORTA} dopo {attesa:.0f} s")


def pid_in_ascolto(testo_netstat: str, porta: int = PORTA) -> int | None:
    """PID del processo in ascolto sulla porta, dall'output di `netstat -ano -p tcp`."""
    for riga in testo_netstat.splitlines():
        parti = riga.split()
        if len(parti) >= 5 and parti[0].upper() == "TCP" and parti[1].endswith(f":{porta}") and parti[3].upper() in ("LISTENING", "IN"):
            try:
                return int(parti[4])
            except ValueError:
                continue
    return None


def chiudi_blender(esegui=subprocess.run) -> bool:
    """Chiude il Blender che ascolta sul ponte (solo se il processo è davvero Blender). True se l'ha chiuso."""
    if sys.platform != "win32":
        return _chiudi_blender_unix(esegui)
    senza = {"creationflags": CREATE_NO_WINDOW}
    net = esegui(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, **senza)
    pid = pid_in_ascolto(net.stdout or "")
    if pid is None:
        return False
    nome = esegui(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True, **senza).stdout or ""
    if "blender" not in nome.lower():
        return False
    esegui(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True, **senza)
    return True


def _chiudi_blender_unix(esegui) -> bool:
    """macOS e Linux: `lsof` trova il processo in ascolto sulla porta, `ps` ne dà il nome."""
    righe = (esegui(["lsof", "-nP", f"-iTCP:{PORTA}", "-sTCP:LISTEN", "-t"], capture_output=True, text=True).stdout or "")
    pid = next((int(r) for r in righe.split() if r.isdigit()), None)
    if pid is None:
        return False
    nome = esegui(["ps", "-p", str(pid), "-o", "comm="], capture_output=True, text=True).stdout or ""
    if "blender" not in nome.lower():
        return False
    esegui(["kill", str(pid)], capture_output=True, text=True)
    return True


def main(argv: list[str]) -> int:
    azione = argv[2] if len(argv) > 2 else "stato"
    if azione == "avvia":
        print("Blender aperto ora" if avvia_blender() else "Blender era già aperto")
        return 0
    if azione == "chiudi":
        print("Blender chiuso" if chiudi_blender() else "nessun Blender con il ponte da chiudere")
        return 0
    print("ponte acceso" if ponte_acceso() else "ponte spento (Blender chiuso)")
    return 0
