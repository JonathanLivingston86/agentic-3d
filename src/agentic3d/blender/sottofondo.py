"""Render senza finestra: Blender in sottofondo, una vista alla volta, con avanzamento e galleria.

Blender parte con `-b` (nessuna finestra, nessun ponte, nessun componente aggiuntivo) e `--factory-startup` (le
impostazioni di fabbrica: il risultato non dipende dal profilo di chi lo usa). Esegue lo script generato dal
costruttore, che a scena pronta stampa `AGENTIC3D_VISTA 0 <totale> -` e dopo ogni vista
`AGENTIC3D_VISTA <fatte> <totale> <nome>`; i secondi di ogni vista li misura il motore tra una riga e l'altra. Da qui nascono
il messaggio di avanzamento, la stima del tempo che manca e la galleria nel browser. A fine lavoro il processo
termina da solo; se si blocca oltre il tempo massimo viene chiuso, così non restano istanze aperte.

Dopo i render, l'impostazione `dopo_render` decide se aprire il file .blend in un Blender normale (con il profilo e
le preferenze dell'utente): `automatico` (predefinito) lo apre solo se sul computer non c'è SketchUp, `apri` sempre,
`chiudi` mai. Un .blend modificato dall'utente non viene mai sovrascritto: il nuovo va accanto con "(nuovo)".
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from ..configurazione import cartella_configurazione, cartella_temporanea, eseguibile_blender, leggi_impostazioni
from .. import galleria

SEGNALE = "AGENTIC3D_VISTA"
CREATE_NO_WINDOW = 0x08000000
SCELTE_DOPO_RENDER = ("automatico", "apri", "chiudi")


def blender_da_console(exe: Path | None = None) -> Path | None:
    """Su Windows `blender-launcher.exe` apre la finestra e non passa l'uscita: in sottofondo serve `blender.exe`."""
    exe = exe or eseguibile_blender()
    if exe is None:
        return None
    if exe.name.lower() == "blender-launcher.exe" and (exe.parent / "blender.exe").is_file():
        return exe.parent / "blender.exe"
    return exe


def leggi_segnale(riga: str) -> tuple[int, int, str] | None:
    """(fatte, totale, nome della vista) da una riga di avanzamento, altrimenti None."""
    if not riga.startswith(SEGNALE + " "):
        return None
    parti = riga.rstrip("\r\n").split(" ", 3)
    try:
        return int(parti[1]), int(parti[2]), parti[3]
    except (IndexError, ValueError):
        return None


# ------------------------------------------------------------------ stime dei tempi
def _file_tempi() -> Path:
    return cartella_configurazione() / "tempi dei render.json"


def tempi_precedenti(lavoro: str) -> dict[str, float]:
    """Secondi dell'ultimo render di ogni vista di questo lavoro (vuoto se mai renderizzato)."""
    try:
        return json.loads(_file_tempi().read_text(encoding="utf-8")).get(lavoro, {})
    except (OSError, ValueError):
        return {}


def salva_tempi(lavoro: str, tempi: dict[str, float]) -> None:
    f = _file_tempi()
    try:
        dati = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dati = {}
    dati[lavoro] = {k: round(v, 1) for k, v in tempi.items()}
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(dati, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def stima_rimanente(viste: list[str], fatte: dict[str, float], precedenti: dict[str, float]) -> float | None:
    """Secondi che mancano: per ogni vista da fare il tempo della volta scorsa, altrimenti la media delle viste già
    fatte in questo giro (o di quelle della volta scorsa). None se non c'è ancora nessun dato."""
    da_fare = [v for v in viste if v not in fatte]
    noti = list(fatte.values()) or list(precedenti.values())
    if not da_fare:
        return 0.0
    if not noti:
        return None
    media = sum(noti) / len(noti)
    return sum(precedenti.get(v, media) for v in da_fare)


def testo_durata(secondi: float | None) -> str:
    if secondi is None:
        return "stima dopo la prima vista"
    secondi = max(0, round(secondi))
    if secondi < 58:
        return f"circa {max(5, round(secondi / 5) * 5)} secondi"
    minuti = round(secondi / 60)
    return "circa 1 minuto" if minuti == 1 else f"circa {minuti} minuti"


# ------------------------------------------------------------------ esecuzione
IN_CORSO: set = set()                # processi Blender in corso, da chiudere se l'agente annulla il render


def ferma_tutti() -> int:
    """Chiude i Blender in sottofondo ancora aperti (render annullato dall'agente). Restituisce quanti."""
    n = 0
    for pr in list(IN_CORSO):
        try:
            pr.kill()
            n += 1
        except Exception:
            pass
        IN_CORSO.discard(pr)
    return n


def esegui(codice: str, viste: list[str], cartella_render: Path, lavoro: str, al_progresso=None,
           apri_galleria: bool = True, tempo_massimo: float = 3600.0, avvia=subprocess.Popen) -> dict:
    """Esegue lo script in un Blender senza finestra. `al_progresso(fatte, totale, messaggio)` viene chiamata
    all'avvio e dopo ogni vista. Restituisce esito, viste fatte con i secondi e le ultime righe di Blender."""
    exe = blender_da_console()
    if exe is None or not exe.exists():
        raise FileNotFoundError("Blender non trovato: installalo oppure indica dove si trova con "
                                "`agentic3d impostazioni blender <percorso>`")
    script = cartella_temporanea() / f"Render {lavoro}.py"
    script.write_text(codice, encoding="utf-8")
    precedenti = tempi_precedenti(lavoro)
    fatte: dict[str, float] = {}
    totale = len(viste)
    inizio = time.time()

    def aggiorna(finito=False, errore=None):
        resta = stima_rimanente(viste, fatte, precedenti)
        galleria.scrivi(cartella_render, lavoro, viste, fatte, testo_durata(resta) if not finito else "",
                        finito=finito, errore=errore)
        return resta

    resta = aggiorna()
    pagina = galleria.percorso(cartella_render)
    if apri_galleria and os.environ.get("AGENTIC3D_SENZA_GALLERIA") != "1":
        try:
            webbrowser.open(pagina.as_uri())
        except Exception:
            pass
    if al_progresso:
        al_progresso(0, totale, f"render di {totale} viste avviato, {testo_durata(resta)}; galleria: {pagina}")

    opzioni = {"creationflags": CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    comando = [str(exe), "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(script)]
    processo = avvia(comando, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                     text=True, encoding="utf-8", errors="replace", bufsize=1, **opzioni)
    IN_CORSO.add(processo)
    ultime: list[str] = []
    errore = None
    scaduto = threading.Event()

    def scadenza():                  # Blender bloccato senza scrivere nulla: si chiude comunque
        scaduto.set()
        processo.kill()
    sveglia = threading.Timer(tempo_massimo, scadenza)
    sveglia.daemon = True
    sveglia.start()
    ultimo_segnale = time.time()
    try:
        for riga in processo.stdout:
            segnale = leggi_segnale(riga)
            if segnale is None:
                testo = riga.rstrip()
                if testo and not testo.startswith(("Fra:", "Saved:", " Time:")):
                    ultime = (ultime + [testo])[-12:]
                continue
            n, totale_blender, nome = segnale
            adesso = time.time()
            secondi, ultimo_segnale = adesso - ultimo_segnale, adesso
            if n == 0:               # scena pronta: da qui partono i tempi delle viste
                continue
            fatte[nome] = secondi
            resta = aggiorna()
            if al_progresso:
                seguito = f", mancano {testo_durata(resta)}" if n < totale_blender else ""
                al_progresso(n, totale_blender, f"render {n} di {totale_blender}: {nome} ({secondi:.0f} s){seguito}")
        codice_uscita = processo.wait(timeout=60)
        if scaduto.is_set():
            errore = f"Blender non ha finito entro {tempo_massimo / 60:.0f} minuti: chiuso"
        elif codice_uscita != 0:
            errore = "Blender si è fermato con un errore: " + " | ".join(ultime[-4:])
    except subprocess.TimeoutExpired:
        errore = "Blender non si è chiuso dopo l'ultima vista"
    finally:
        sveglia.cancel()
        IN_CORSO.discard(processo)
        if processo.poll() is None:
            processo.kill()
            processo.wait()
        script.unlink(missing_ok=True)
    if errore is None and len(fatte) < totale:
        errore = f"fatte {len(fatte)} viste su {totale}: " + " | ".join(ultime[-4:])
    aggiorna(finito=True, errore=errore)
    if fatte:
        salva_tempi(lavoro, {**precedenti, **fatte})
    durata = time.time() - inizio
    return {"esito": "errore" if errore else "ok", "errore": errore, "viste": fatte, "secondi": round(durata),
            "galleria": str(pagina), "righe": ultime}


# ------------------------------------------------------------------ il file .blend dopo i render
def _file_blend_scritti() -> Path:
    return cartella_configurazione() / "file blend scritti.json"


def _impronta(p: Path) -> list[int]:
    s = p.stat()
    return [s.st_mtime_ns, s.st_size]


def destinazione_blend(desiderato: Path) -> Path:
    """Dove salvare il .blend: il file solito, a meno che l'utente l'abbia modificato dopo l'ultimo salvataggio del
    motore; allora accanto, con "(nuovo)" nel nome (che il motore può riscrivere, perché è suo)."""
    if not desiderato.exists():
        return desiderato
    try:
        scritti = json.loads(_file_blend_scritti().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        scritti = {}
    noto = scritti.get(str(desiderato))
    if noto is None or noto == _impronta(desiderato):
        return desiderato           # scritto dal motore (o da una versione che non lo annotava) e non toccato
    return desiderato.with_name(f"{desiderato.stem} (nuovo){desiderato.suffix}")


def annota_blend(p: Path) -> None:
    """Ricorda l'impronta del .blend appena scritto dal motore: se poi cambia, l'ha modificato l'utente."""
    if not p.exists():
        return
    f = _file_blend_scritti()
    try:
        scritti = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        scritti = {}
    scritti[str(p)] = _impronta(p)
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(scritti, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def dopo_render() -> str:
    scelta = str(leggi_impostazioni().get("dopo_render", "automatico")).strip().lower()
    return scelta if scelta in SCELTE_DOPO_RENDER else "automatico"


def da_aprire(scelta: str, sketchup_presente: bool) -> bool:
    return scelta == "apri" or (scelta == "automatico" and not sketchup_presente)


def apri_in_blender(blend: Path, avvia=subprocess.Popen) -> None:
    """Apre il .blend in un Blender normale, con la finestra e le preferenze dell'utente (nessun ponte)."""
    exe = eseguibile_blender()
    if exe is None:
        raise FileNotFoundError("Blender non trovato")
    opzioni = {}
    if sys.platform == "win32":
        opzioni["creationflags"] = 0x00000008 | 0x00000200      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        opzioni["start_new_session"] = True
    avvia([str(exe), str(blend)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
          close_fds=True, **opzioni)
