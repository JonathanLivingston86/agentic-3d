"""Apertura e chiusura di un lavoro 3D: `nuovo` crea la cartella con la struttura giusta, `chiudi` la riordina.

    python -m agentic3d nuovo "Camera da letto Via Appia" [--tipo stanza|edificio] [--disegno file ...]
    python -m agentic3d chiudi "Camera da letto Via Appia"

Regole del progetto (AGENTS.md): una cartella per progetto in `lavori/`, nome leggibile con spazi e senza trattini o
underscore; dentro `Riferimenti`, `Modello`, `Esportazioni`, `Render` e `Scheda del progetto.md`; i file in eccesso
vanno nel Cestino (si recuperano), i temporanei si svuotano.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import sys
from pathlib import Path

from .blender.ponte import ponte_acceso
from .configurazione import cartella_lavori
from .costruttore import cartella_temporanea

SOTTOCARTELLE = ("Riferimenti", "Modello", "Esportazioni", "Render")
ESTENSIONI_IN_ECCESSO = (".blend1", ".blend2", ".tmp", ".bak", ".log")

SCHEDA_STANZA = """# {nome}: scheda della stanza. Origine nell'angolo interno sud-ovest, X est, Y nord, Z alto, metri.
# Metti le misure che hai (dal disegno o dal brief): il resto lo completa il progetto con valori conformi alle norme
# e lo dichiara tra le ipotesi. Esempi completi: `agentic3d esempi`.

progetto: {nome}
comune: Roma
destinazione: abitazione        # abitazione, scuola...
intervento: nuova               # nuova, ristrutturazione, esistente

stanza:
  id: Stanza
  tipo: camera_singola          # camera_singola, camera_doppia, soggiorno, cucina, bagno, aula...
  lunghezza_m: 4.0              # asse X, ovest-est
  larghezza_m: 3.0              # asse Y, sud-nord
  aperture:
    - {{id: Finestra, tipo: finestra, parete: nord, da_m: 1.0}}
    - {{id: Porta, tipo: porta, parete: sud, da_m: 0.4, ingresso: true, cerniera: est}}
  arredi: []
"""

SCHEDA_EDIFICIO = """# {nome}: scheda dell'edificio (più stanze). Coordinate globali in metri: X est, Y nord.
# Le pareti sono linee d'asse con spessore; le stanze sono poligoni al filo interno delle pareti.
# Esempio completo: `agentic3d nuovo "<Nome>" --esempio "Appartamento di esempio"`.

progetto: {nome}
comune: Roma
destinazione: abitazione
intervento: nuova

edificio:
  soffitto: true
  piani:
    - id: Piano terra
      altezza_m: 2.70
      pareti:
        - {{id: A, da: [0.0, 0.0], a: [5.0, 0.0], spessore_m: 0.30}}
        - {{id: B, da: [5.0, 0.0], a: [5.0, 4.0], spessore_m: 0.30}}
        - {{id: C, da: [5.0, 4.0], a: [0.0, 4.0], spessore_m: 0.30}}
        - {{id: D, da: [0.0, 4.0], a: [0.0, 0.0], spessore_m: 0.30}}
      stanze:
        - {{id: Stanza, tipo: camera_doppia, poligono_m: [[0.15, 0.15], [4.85, 0.15], [4.85, 3.85], [0.15, 3.85]]}}
      aperture:
        - {{id: Finestra, tipo: finestra, stanza: Stanza, parete: nord, da_m: 1.5, larghezza_m: 1.4}}
        - {{id: Porta, tipo: porta, parete: A, lato: sinistra, da_m: 0.8, larghezza_m: 0.9, ingresso: true}}
      arredi: []
"""

SCHEDA_PROGETTO = """# {nome}

Progetto del {data}.

## Brief

(Che cosa va realizzato, per chi, con quali riferimenti.)

## Misure lette

(Da dove vengono le misure: vettori del PDF, quote di uno schizzo, brief. Scala e riscontri.)

## Ipotesi (da confermare)

(Tutto quello che non era scritto nel disegno e che hai scelto tu: dichiaralo qui.)

## Norme controllate

`agentic3d controlla "{nome}"`

## Risultato

- Modello: `Modello/`
- Render: `Render/`
- Esportazione per SketchUp: `Esportazioni/` (GLB e file "per SketchUp.json")
"""


def _nome_valido(nome: str) -> str | None:
    if not nome.strip() or nome != nome.strip():
        return "il nome non può essere vuoto né avere spazi all'inizio o alla fine"
    if any(c in nome for c in "_-"):
        return (f"il nome '{nome}' contiene trattini o underscore: usa spazi, "
                f"per esempio '{nome.replace('_', ' ').replace('-', ' ')}'")
    if any(c in nome for c in '\\/:*?"<>|'):
        return "il nome contiene caratteri non ammessi nei nomi di cartella"
    return None


CARTELLA_ESEMPI = Path(__file__).resolve().parent / "esempi"


def esempi() -> list[str]:
    """Nomi degli esempi compresi nel pacchetto (schede complete da cui partire)."""
    return sorted(p.stem for p in CARTELLA_ESEMPI.glob("*.yaml"))


def nuovo(nome: str, tipo: str = "stanza", disegni: list[str] | None = None, lavori: Path | None = None,
          esempio: str | None = None) -> list[str]:
    """Crea il lavoro `<nome>` nella cartella dei lavori, con sottocartelle, scheda stanze e scheda del progetto.
    Con `esempio` la scheda stanze è la copia di un esempio del pacchetto. Restituisce un riepilogo."""
    if esempio is not None and esempio not in esempi():
        raise ValueError(f"esempio sconosciuto: {esempio!r} (disponibili: {', '.join(esempi())})")
    errore = _nome_valido(nome)
    if errore:
        raise ValueError(errore)
    if tipo not in ("stanza", "edificio"):
        raise ValueError("tipo sconosciuto: usa 'stanza' o 'edificio'")
    base = (lavori or cartella_lavori()) / nome
    if base.exists():
        raise FileExistsError(f"esiste già: {base}")
    for s in SOTTOCARTELLE:
        (base / s).mkdir(parents=True)
    if esempio is not None:
        testo = (CARTELLA_ESEMPI / f"{esempio}.yaml").read_text(encoding="utf-8")
        testo = testo.replace(f"progetto: {esempio}", f"progetto: {nome}", 1)
    else:
        testo = (SCHEDA_STANZA if tipo == "stanza" else SCHEDA_EDIFICIO).format(nome=nome)
    (base / "Scheda stanze.yaml").write_text(testo, encoding="utf-8")
    from datetime import date
    mesi = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
            "novembre", "dicembre"]
    oggi = date.today()
    (base / "Scheda del progetto.md").write_text(
        SCHEDA_PROGETTO.format(nome=nome, data=f"{oggi.day} {mesi[oggi.month - 1]} {oggi.year}"), encoding="utf-8")
    righe = [f"Creata {base}"]
    for d in disegni or []:
        sorgente = Path(d)
        if not sorgente.is_file():
            righe.append(f"ATTENZIONE: il disegno {sorgente} non esiste, non copiato")
            continue
        shutil.copy2(sorgente, base / "Riferimenti" / sorgente.name)      # si copia, mai si sposta
        righe.append(f"Copiato in Riferimenti: {sorgente.name}")
    righe.append(f"Prossimo passo: scrivi le misure in 'Scheda stanze.yaml', poi `agentic3d controlla \"{nome}\"` "
                 f"e `agentic3d costruisci \"{nome}\" --esporta`.")
    return righe


# ------------------------------------------------------------------ cestino
def sposta_nel_cestino(percorso: Path) -> bool:
    """Sposta un file nel Cestino (recuperabile): Windows con la shell, macOS nella cartella ~/.Trash."""
    if sys.platform == "darwin":
        return _cestino_macos(percorso)
    if sys.platform != "win32":
        return False
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

    op = SHFILEOPSTRUCTW()
    op.wFunc = 3                                   # FO_DELETE
    op.pFrom = str(percorso.resolve()) + "\0"       # doppio terminatore: la stringa ctypes ne aggiunge uno
    op.fFlags = 0x40 | 0x10 | 0x4 | 0x400          # ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0 and not op.fAnyOperationsAborted


def _cestino_macos(percorso: Path) -> bool:
    cestino = Path.home() / ".Trash"
    if not cestino.is_dir():
        return False
    meta = cestino / percorso.name
    n = 2
    while meta.exists():                            # stesso nome già nel Cestino: come il Finder, si aggiunge un numero
        meta = cestino / f"{percorso.stem} {n}{percorso.suffix}"
        n += 1
    try:
        shutil.move(str(percorso), str(meta))
        return True
    except OSError:
        return False


_ponte_blender_aperto = ponte_acceso


def chiudi(nome: str, lavori: Path | None = None, cestino=sposta_nel_cestino, temporanei: Path | None = None,
           controlla_ponte=_ponte_blender_aperto) -> list[str]:
    """Riordina un lavoro: sposta i file in eccesso nel Cestino, svuota i temporanei, segnala ciò che non torna."""
    base = (lavori or cartella_lavori()) / nome
    if not base.is_dir():
        raise FileNotFoundError(f"cartella non trovata: {base}")
    righe: list[str] = []
    avvisi: list[str] = []

    for s in SOTTOCARTELLE:
        if not (base / s).is_dir():
            avvisi.append(f"manca la sottocartella {s}")
    for f in ("Scheda del progetto.md", "Scheda stanze.yaml"):
        if not (base / f).is_file():
            avvisi.append(f"manca {f}")

    eccesso = [p for p in sorted(base.rglob("*")) if p.is_file() and p.suffix.lower() in ESTENSIONI_IN_ECCESSO]
    spostati = 0
    for p in eccesso:
        if cestino(p):
            spostati += 1
            righe.append(f"nel Cestino: {p.relative_to(base)}")
        else:
            avvisi.append(f"da togliere a mano (Cestino non disponibile): {p.relative_to(base)}")

    sciolti = [p.name for p in base.iterdir() if p.is_file() and p.name not in ("Scheda del progetto.md", "Scheda stanze.yaml")]
    if sciolti:
        avvisi.append("file sciolti nella cartella del progetto (vanno in Riferimenti, Modello, Esportazioni o Render): "
                      + ", ".join(sciolti))
    extra = [p.name for p in base.iterdir() if p.is_dir() and p.name not in SOTTOCARTELLE]
    if extra:
        avvisi.append("sottocartelle senza scopo dichiarato: " + ", ".join(extra))

    non_leggibili = [str(p.relative_to(base)) for p in base.rglob("*")
                     if any(c in p.stem for c in "_") and p.suffix.lower() not in (".py", ".rb")]
    if non_leggibili:
        avvisi.append("nomi con underscore (usa spazi): " + ", ".join(non_leggibili[:5]))

    scheda = base / "Scheda stanze.yaml"
    if scheda.is_file():
        for e in sorted((base / "Esportazioni").glob("*")) if (base / "Esportazioni").is_dir() else []:
            if e.stat().st_mtime < scheda.stat().st_mtime - 1:
                avvisi.append(f"{e.name} è più vecchio della scheda: rigenera con `costruisci --esporta`")

    tmp = temporanei or cartella_temporanea()
    tolti = 0
    if tmp.is_dir():
        for p in list(tmp.iterdir()):
            try:
                shutil.rmtree(p) if p.is_dir() else p.unlink()
                tolti += 1
            except OSError as e:
                avvisi.append(f"temporaneo non rimosso: {p.name} ({e})")
    righe.append(f"temporanei svuotati: {tolti} elementi in {tmp}")

    if controlla_ponte():
        avvisi.append("Blender è ancora aperto con il ponte MCP: chiudilo (il ponte accetta codice da qualunque programma "
                      "del computer)")

    peso = sum(p.stat().st_size for p in base.rglob("*") if p.is_file()) / 1e6
    contenuto = {s: len([p for p in (base / s).iterdir()]) for s in SOTTOCARTELLE if (base / s).is_dir()}
    righe.append(f"resta in {base.name}: " + ", ".join(f"{k} {v}" for k, v in contenuto.items()) + f" ({peso:.1f} MB)")
    righe += [f"ATTENZIONE: {a}" for a in avvisi]
    if not avvisi:
        righe.append("Tutto in ordine.")
    return righe
