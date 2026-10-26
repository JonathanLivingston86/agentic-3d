"""Nome, versione, autore e licenza di Agentic 3D (comando `agentic3d informazioni`)."""

from __future__ import annotations

from importlib import metadata

NOME = "Agentic 3D"
AUTORE = "Andrea Lucarelli"


def versione() -> str:
    try:
        return metadata.version("agentic3d")
    except metadata.PackageNotFoundError:
        return "sviluppo"


def testo() -> str:
    return (f"{NOME} {versione()}\n"
            "Modellazione 3D di interni guidata da un agente, con norme italiane ed europee e SketchUp dal vivo.\n"
            f"Ideato e sviluppato da {AUTORE}.\n"
            "Licenza d'uso: consentito l'uso anche professionale; vietate redistribuzione e rivendita (LICENZA.md).")
