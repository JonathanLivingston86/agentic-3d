"""SketchUp installati, estensione Agentic 3D al loro interno, rapporto dell'estensione e verifica dell'installazione.

L'estensione si installa copiando i suoi file nella cartella Plugins di ogni SketchUp trovato (come fa Gestione
estensioni con un .rbz): `%APPDATA%\\SketchUp\\SketchUp 20xx\\SketchUp\\Plugins` su Windows,
`~/Library/Application Support/SketchUp 20xx/SketchUp/Plugins` su macOS.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from . import configurazione as conf
from .estensione import SORGENTE as SORGENTE_ESTENSIONE

FILE_REGISTRO = "Agentic 3D registro.txt"
FILE_CONTROLLO = "Agentic 3D controllo.json"
CARICATORE = "agentic3d_sketchup.rb"


def _versione_in(testo: str) -> str | None:
    m = re.search(r"ESTENSIONE\.version\s*=\s*'([^']+)'", testo)
    return m.group(1) if m else None


def versione_estensione_pacchetto() -> str:
    return _versione_in((SORGENTE_ESTENSIONE / CARICATORE).read_text(encoding="utf-8")) or "?"


def _base_sketchup() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "SketchUp"
    return Path.home() / "Library" / "Application Support"


@dataclass
class SketchUp:
    anno: int
    plugins: Path

    @property
    def versione_estensione(self) -> str | None:
        f = self.plugins / CARICATORE
        return _versione_in(f.read_text(encoding="utf-8")) if f.is_file() else None


def sketchup_installati() -> list[SketchUp]:
    """SketchUp desktop che hanno già creato la loro cartella utente (cioè aperti almeno una volta), dal più recente."""
    trovati = []
    for cartella in _base_sketchup().glob("SketchUp 20[0-9][0-9]"):
        plugins = cartella / "SketchUp" / "Plugins"
        if (cartella / "SketchUp").is_dir():
            trovati.append(SketchUp(int(cartella.name[-4:]), plugins))
    return sorted(trovati, key=lambda s: -s.anno)


def installa_estensione(su: SketchUp) -> str:
    """Copia l'estensione nella cartella Plugins (sostituisce una versione precedente). Restituisce un riepilogo."""
    su.plugins.mkdir(parents=True, exist_ok=True)
    prima = su.versione_estensione
    shutil.copy2(SORGENTE_ESTENSIONE / CARICATORE, su.plugins / CARICATORE)
    destinazione = su.plugins / "agentic3d_sketchup"
    destinazione.mkdir(exist_ok=True)
    for f in (SORGENTE_ESTENSIONE / "agentic3d_sketchup").glob("*.rb"):
        shutil.copy2(f, destinazione / f.name)
    dopo = su.versione_estensione
    azione = "installata" if prima is None else ("aggiornata da " + prima if prima != dopo else "già aggiornata")
    return f"SketchUp {su.anno}: estensione {dopo} {azione}. Riavvia SketchUp se era aperto."


# ------------------------------------------------------------------ rapporto dell'estensione
def cartella_rapporti() -> Path:
    """Dove l'estensione scrive registro e controllo: la cartella temporanea del sistema (Ruby `Dir.tmpdir`)."""
    return Path(tempfile.gettempdir())


def rapporto_sketchup(dopo: float | None = None, attesa: float = 0.0) -> str:
    """Esito dell'ultimo aggiornamento in SketchUp. Con `dopo` (istante, secondi) aspetta fino a `attesa` secondi un
    controllo scritto dopo quell'istante, cioè dopo l'esportazione appena fatta."""
    controllo = cartella_rapporti() / FILE_CONTROLLO
    registro = cartella_rapporti() / FILE_REGISTRO
    fine = time.time() + attesa
    while dopo is not None and time.time() < fine and not (controllo.is_file() and controllo.stat().st_mtime >= dopo):
        time.sleep(0.5)
    righe = []
    if dopo is not None and not (controllo.is_file() and controllo.stat().st_mtime >= dopo):
        righe.append("SketchUp non ha ancora applicato l'ultima esportazione. Cause possibili: l'estensione non è "
                     "collegata a questo lavoro (Estensioni > Agentic 3D > Collega modello...), è aperto un gruppo "
                     "dell'utente, oppure SketchUp è chiuso.")
    if controllo.is_file():
        try:
            dati = json.loads(controllo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            dati = {}
        oggetti = dati.get("oggetti", [])
        problemi = [f"- {o['nome']}: {'; '.join(o['problemi'])}" for o in oggetti if o.get("problemi")]
        riserve = [o["nome"] for o in oggetti if o.get("riserve")]
        righe.append(f"Ultimo controllo: {dati.get('quando', '?')}, SketchUp {dati.get('sketchup', '?')}, "
                     f"file {dati.get('file', '?')}")
        righe.append(dati.get("riepilogo", ""))
        righe.append(f"{len(oggetti)} oggetti controllati, {len(problemi)} con problemi"
                     + (f", facce di riserva in: {', '.join(riserve)}" if riserve else ""))
        righe += problemi
    else:
        righe.append("Nessun rapporto dell'estensione: in SketchUp non è ancora stato collegato un modello.")
    if registro.is_file():
        ultime = registro.read_text(encoding="utf-8", errors="replace").splitlines()[-8:]
        errori = [r for r in ultime if "ERRORE" in r]
        if errori:
            righe.append("Errori recenti nel registro dell'estensione:")
            righe += errori
    return "\n".join(r for r in righe if r)


def collegato_a(file_sketchup: str | Path) -> bool:
    """Vero se l'ultimo rapporto dell'estensione riguarda proprio questo file: allora vale la pena aspettare
    l'aggiornamento. Con SketchUp chiuso o collegato a un altro lavoro si risponde subito."""
    controllo = cartella_rapporti() / FILE_CONTROLLO
    try:
        dati = json.loads(controllo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    try:
        return Path(dati.get("file", "")).resolve() == Path(file_sketchup).resolve()
    except OSError:
        return False


def non_collegato(file_sketchup: str | Path) -> str:
    return (f"SketchUp non è collegato a questo lavoro: in SketchUp Estensioni > Agentic 3D > Collega modello... e "
            f"scegliere {Path(file_sketchup).name} (cartella Esportazioni del lavoro). Da lì ogni modifica compare da sola.")


def rapporto_sketchup_breve(dopo: float, attesa: float) -> str:
    """Una riga se l'aggiornamento in SketchUp è andato bene; il rapporto completo se c'è qualcosa da vedere."""
    completo = rapporto_sketchup(dopo=dopo, attesa=attesa)
    righe = completo.splitlines()
    pulito = (not completo.startswith("SketchUp non ha") and not completo.startswith("Nessun rapporto")
              and any(r.endswith(", 0 con problemi") for r in righe)
              and not any("Errori recenti" in r or "facce di riserva" in r for r in righe))
    if not pulito:
        return completo
    riepilogo = next((r for r in righe if r and not r.startswith(("Ultimo controllo", "-"))
                      and "oggetti controllati" not in r), "")
    return f"SketchUp aggiornato, nessun problema ({riepilogo})" if riepilogo else "SketchUp aggiornato, nessun problema"


# ------------------------------------------------------------------ verifica dell'installazione
def verifica_installazione() -> str:
    """Controlla motore, cartelle, SketchUp, estensione e Blender. Ogni riga: OK, ATTENZIONE o ERRORE, con il rimedio."""
    from .informazioni import versione
    righe = [f"OK  Agentic 3D {versione()}, Python {sys.version.split()[0]}, {sys.platform}"]
    for nome, funzione in (("lavori", conf.cartella_lavori), ("temporanei", conf.cartella_temporanea)):
        try:
            p = funzione()
            p.mkdir(parents=True, exist_ok=True)
            prova = p / ".agentic3d-prova"
            prova.write_text("ok", encoding="utf-8")
            prova.unlink()
            righe.append(f"OK  cartella dei {nome}: {p}")
        except OSError as e:
            righe.append(f"ERRORE  cartella dei {nome} non scrivibile ({e}). Rimedio: "
                         f"`agentic3d impostazioni {nome} <altra cartella>`")
    attesa = versione_estensione_pacchetto()
    installati = sketchup_installati()
    if not installati:
        righe.append("ATTENZIONE  nessun SketchUp desktop trovato (o mai aperto). Rimedio: apri SketchUp una volta, "
                     "poi rilancia l'installazione.")
    for su in installati:
        v = su.versione_estensione
        if v is None:
            righe.append(f"ATTENZIONE  SketchUp {su.anno}: estensione non installata. Rimedio: strumento "
                         "`installa_estensione_sketchup` (poi riavvia SketchUp).")
        elif v != attesa:
            righe.append(f"ATTENZIONE  SketchUp {su.anno}: estensione {v}, il motore porta la {attesa}. Rimedio: "
                         "`installa_estensione_sketchup`, poi riavvia SketchUp.")
        else:
            righe.append(f"OK  SketchUp {su.anno}: estensione {v}")
    blender = conf.eseguibile_blender()
    righe.append(f"OK  Blender: {blender}" if blender else
                 "OK  Blender non trovato: serve solo per i render (facoltativo). Se è installato altrove: "
                 "`agentic3d impostazioni blender <percorso>`")
    from .collegamenti import stato_collegamenti
    righe += stato_collegamenti()
    registro = cartella_rapporti() / FILE_REGISTRO
    if registro.is_file():
        errori = [r for r in registro.read_text(encoding="utf-8", errors="replace").splitlines()[-30:] if "ERRORE" in r]
        if errori:
            righe.append("ATTENZIONE  errori recenti dell'estensione SketchUp:\n    " + "\n    ".join(errori[-3:]))
    return "\n".join(righe)
