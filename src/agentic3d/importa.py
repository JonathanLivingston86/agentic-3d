"""Importazione di un disegno CAD in un lavoro: lettura del DXF, scheda, tavola di lettura da confermare.

Usato dallo strumento MCP `importa_disegno` e dal comando `agentic3d importa "<lavoro>" disegno.dxf`.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import yaml

NOME_TAVOLA = "Tavola di lettura.png"


def importa_disegno(cartella_lavoro: Path, disegno: str | Path, livello_muri: str | None = None,
                    temporanei: Path | None = None) -> str:
    """Legge il DXF, scrive la `Scheda stanze.yaml` del lavoro (la precedente resta nei temporanei) e la tavola
    di lettura in Riferimenti. Restituisce il rapporto: cosa è stato letto e cosa va confermato."""
    from .lettura_dxf import leggi
    from .tavola import disegna
    sorgente = Path(disegno)
    if sorgente.suffix.lower() == ".dwg":
        raise ValueError("Agentic 3D legge i DXF, non i DWG: aprire il disegno nel programma CAD e salvarlo come DXF "
                         "(Salva con nome > DXF), poi importare il file DXF. Non convertirlo in altri modi.")
    if sorgente.suffix.lower() != ".dxf":
        raise ValueError(f"{sorgente.name}: serve un file DXF (per foto e schizzi si scrive la scheda e si conferma "
                         "con `tavola_di_lettura`)")
    if not sorgente.is_file():
        raise FileNotFoundError(f"disegno non trovato: {sorgente}")
    cartella = Path(cartella_lavoro)
    riferimenti = cartella / "Riferimenti"
    riferimenti.mkdir(parents=True, exist_ok=True)
    copia = riferimenti / sorgente.name
    if sorgente.resolve() != copia.resolve():
        shutil.copy2(sorgente, copia)                      # si copia, l'originale non si sposta
    scheda_vecchia = yaml.safe_load((cartella / "Scheda stanze.yaml").read_text(encoding="utf-8")) \
        if (cartella / "Scheda stanze.yaml").is_file() else {}
    nome = (scheda_vecchia or {}).get("progetto", cartella.name)
    lettura = leggi(copia, {"muri": [livello_muri]} if livello_muri else None, nome=nome)
    for chiave in ("comune", "destinazione", "intervento"):       # le scelte già fatte restano
        if scheda_vecchia and chiave in scheda_vecchia:
            lettura.scheda[chiave] = scheda_vecchia[chiave]
    lettura.scheda["ipotesi_lettura"] = list(lettura.dubbi)
    scheda = cartella / "Scheda stanze.yaml"
    if scheda.is_file() and temporanei is not None:
        temporanei.mkdir(parents=True, exist_ok=True)
        shutil.copy2(scheda, temporanei / f"{cartella.name} scheda {datetime.now():%Y%m%d %H%M%S}.yaml")
    intestazione = (f"# {nome}: scheda letta automaticamente da {copia.name} (Agentic 3D, lettura del DXF).\n"
                    "# Misure del CAD in metri, origine nell'angolo in basso a sinistra dei muri. Confermare la\n"
                    f"# \"{NOME_TAVOLA}\" in Riferimenti prima di costruire; i dubbi sono in `ipotesi_lettura`.\n\n")
    scheda.write_text(intestazione + yaml.safe_dump(lettura.scheda, allow_unicode=True, sort_keys=False, width=160),
                      encoding="utf-8")
    tavola = disegna(riferimenti / NOME_TAVOLA, lettura=lettura, titolo=f"Tavola di lettura: {nome}")
    return (lettura.rapporto() + f"\n\nScheda scritta: {scheda}\nTavola da mostrare all'utente: {tavola}\n"
            "Prima di costruire: l'utente confronta la tavola con il disegno e conferma o corregge.")


def tavola_di_lettura(cartella_lavoro: Path) -> Path:
    """Tavola dalla scheda attuale (per foto e schizzi: la lettura dell'agente da far confermare)."""
    from .scheda import carica_scheda
    from .tavola import disegna
    cartella = Path(cartella_lavoro)
    scheda = carica_scheda(cartella / "Scheda stanze.yaml")
    if "edificio" not in scheda:
        raise ValueError("la tavola di lettura si disegna per le schede con `edificio:` (più stanze)")
    return disegna(cartella / "Riferimenti" / NOME_TAVOLA, scheda=scheda,
                   titolo=f"Tavola di lettura: {scheda.get('progetto', cartella.name)} (lettura dell'agente)")
