"""Impacchetta l'estensione di SketchUp (`agentic3d/estensione_sketchup/`) in un file .rbz da installare una volta sola.

In SketchUp: Estensioni > Gestione estensioni > Installa estensione, poi si sceglie il file .rbz. In alternativa,
senza installare nulla, nella Console Ruby (Estensioni > Console Ruby):  load '<cartella>/agentic3d_sketchup/principale.rb'
"""

from __future__ import annotations

import zipfile
from pathlib import Path

SORGENTE = Path(__file__).resolve().parent / "estensione_sketchup"


def crea_rbz(destinazione: str | Path | None = None) -> Path:
    if destinazione is None:
        from .configurazione import radice_sviluppo
        sviluppo = radice_sviluppo()
        destinazione = sviluppo / "dist" if sviluppo else Path.cwd()
    cartella = Path(destinazione)
    cartella.mkdir(parents=True, exist_ok=True)
    rbz = cartella / "Agentic 3D per SketchUp.rbz"
    with zipfile.ZipFile(rbz, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(SORGENTE.rglob("*.rb")):
            z.write(f, f.relative_to(SORGENTE).as_posix())
    return rbz
