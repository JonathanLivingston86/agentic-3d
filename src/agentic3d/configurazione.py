"""Impostazioni dell'utente: dove stanno i lavori, i file temporanei e Blender, su Windows e su macOS.

Ogni percorso si decide in quest'ordine: variabile d'ambiente, file delle impostazioni, valore predefinito.

| Cosa        | Variabile          | Chiave nel file | Predefinito                                                   |
|-------------|--------------------|-----------------|---------------------------------------------------------------|
| Lavori      | AGENTIC3D_LAVORI   | lavori          | `lavori/` nel repository di sviluppo, altrimenti Documenti/Agentic 3D |
| Temporanei  | AGENTIC3D_TEMP     | temporanei      | cartella temporanea del sistema / Agentic 3D                  |
| Blender     | AGENTIC3D_BLENDER  | blender         | Blender più recente installato nel posto standard             |

Il file delle impostazioni è `impostazioni.toml` in `%APPDATA%\\Agentic 3D` (Windows) o in
`~/Library/Application Support/Agentic 3D` (macOS).
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import tomllib
from pathlib import Path

NOME = "Agentic 3D"
CHIAVI = ("lavori", "temporanei", "blender", "dopo_render", "modalita")
# dopo i render: aprire il .blend in Blender solo se manca SketchUp (automatico), sempre (apri) o mai (chiudi)
# modalita: risposte brevi a ogni modifica (veloce) o complete, con file e dettagli dei controlli (diagnostica)
SCELTE = {"dopo_render": ("automatico", "apri", "chiudi"), "modalita": ("veloce", "diagnostica")}


def modalita() -> str:
    valore = str(leggi_impostazioni().get("modalita", "veloce")).strip().lower()
    return valore if valore in SCELTE["modalita"] else "veloce"
RADICE_PACCHETTO = Path(__file__).resolve().parent


def cartella_configurazione() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / NOME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / NOME
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "agentic-3d"


def file_impostazioni() -> Path:
    return Path(os.environ.get("AGENTIC3D_IMPOSTAZIONI", cartella_configurazione() / "impostazioni.toml"))


def leggi_impostazioni() -> dict:
    f = file_impostazioni()
    if not f.is_file():
        return {}
    with f.open("rb") as h:
        return tomllib.load(h)


def scrivi_impostazione(chiave: str, valore: str) -> Path:
    """Salva una impostazione (testo) nel file, conservando le altre."""
    if chiave not in CHIAVI:
        raise ValueError(f"impostazione sconosciuta: {chiave!r} (ammesse: {', '.join(CHIAVI)})")
    if chiave in SCELTE:
        valore = str(valore).strip().lower()
        if valore not in SCELTE[chiave]:
            raise ValueError(f"{chiave}: valore {valore!r} non valido (ammessi: {', '.join(SCELTE[chiave])})")
    dati = leggi_impostazioni()
    dati[chiave] = str(valore)
    f = file_impostazioni()
    f.parent.mkdir(parents=True, exist_ok=True)
    righe = ["# Impostazioni di Agentic 3D: cartelle, Blender e cosa fare dopo i render."]
    for k in CHIAVI:
        if k in dati:
            righe.append(f"{k} = {_stringa_toml(dati[k])}")
    f.write_text("\n".join(righe) + "\n", encoding="utf-8")
    return f


def _stringa_toml(s: str) -> str:
    return "'" + s + "'" if "'" not in s and "\n" not in s else '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _scelta(variabile: str, chiave: str) -> Path | None:
    valore = os.environ.get(variabile) or leggi_impostazioni().get(chiave)
    return Path(valore).expanduser() if valore else None


def radice_sviluppo() -> Path | None:
    """La cartella del repository quando il motore gira dai sorgenti (non installato): ha `pyproject.toml` e `lavori/`."""
    radice = RADICE_PACCHETTO.parents[1]
    return radice if (radice / "pyproject.toml").is_file() and (radice / "lavori").is_dir() else None


def cartella_documenti() -> Path:
    if sys.platform == "win32":
        try:                                     # la cartella Documenti vera, anche se spostata (per esempio in OneDrive)
            import ctypes
            from ctypes import wintypes
            guid = (ctypes.c_byte * 16).from_buffer_copy(
                bytes.fromhex("D0 9A D3 FD 8F 23 AF 46 AD B4 6C 85 48 03 69 C7".replace(" ", "")))
            percorso = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(percorso)) == 0:
                risultato = Path(percorso.value)
                ctypes.windll.ole32.CoTaskMemFree(percorso)
                return risultato
        except (AttributeError, OSError):
            pass
    return Path.home() / "Documents"


def cartella_lavori() -> Path:
    scelta = _scelta("AGENTIC3D_LAVORI", "lavori")
    if scelta:
        return scelta
    sviluppo = radice_sviluppo()
    return sviluppo / "lavori" if sviluppo else cartella_documenti() / NOME


FILE_REGOLE = {"AGENTS.md": None, "CLAUDE.md": "@AGENTS.md\n", "GEMINI.md": "@AGENTS.md\n"}


def prepara_cartella_lavori(cartella: Path | None = None) -> list[Path]:
    """Mette nella cartella dei lavori le regole per gli agenti (`AGENTS.md`, con `CLAUDE.md` e `GEMINI.md` che lo
    richiamano): un agente che lavora lì le legge anche se Agentic 3D non è collegato, e non improvvisa. Nel
    repository di sviluppo non si scrive nulla. Restituisce i file scritti o aggiornati."""
    if cartella is None:
        if radice_sviluppo() and not _scelta("AGENTIC3D_LAVORI", "lavori"):
            return []
        cartella = cartella_lavori()
    regole = (RADICE_PACCHETTO / "regole_agenti.md").read_text(encoding="utf-8")
    scritti = []
    try:
        cartella.mkdir(parents=True, exist_ok=True)
        for nome, testo in FILE_REGOLE.items():
            f = cartella / nome
            contenuto = regole if testo is None else testo
            if not f.is_file() or f.read_text(encoding="utf-8") != contenuto:
                f.write_text(contenuto, encoding="utf-8")
                scritti.append(f)
    except OSError:
        pass
    return scritti


def cartella_temporanea() -> Path:
    p = _scelta("AGENTIC3D_TEMP", "temporanei") or Path(tempfile.gettempdir()) / NOME
    p.mkdir(parents=True, exist_ok=True)
    return p


def _versione(p: Path) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", p.name)) or (0,)


def eseguibile_blender() -> Path | None:
    """Blender scelto dall'utente o il più recente installato nel posto standard. None se non c'è."""
    scelta = _scelta("AGENTIC3D_BLENDER", "blender")
    candidati: list[Path] = []
    if scelta:
        candidati += [scelta] if scelta.is_file() else [
            scelta / "blender-launcher.exe", scelta / "blender.exe", scelta / "Contents" / "MacOS" / "Blender"]
    elif sys.platform == "win32":
        base = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Blender Foundation"
        for cartella in sorted(base.glob("Blender*"), key=_versione, reverse=True):
            candidati += [cartella / "blender-launcher.exe", cartella / "blender.exe"]
    elif sys.platform == "darwin":
        candidati += [Path(a) / "Contents" / "MacOS" / "Blender"
                      for a in ("/Applications/Blender.app", str(Path.home() / "Applications" / "Blender.app"))]
    else:
        candidati += [Path("/usr/bin/blender"), Path("/snap/bin/blender")]
    return next((c for c in candidati if c.is_file()), None)
