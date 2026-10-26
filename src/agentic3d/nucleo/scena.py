"""Scena: l'insieme degli oggetti di un progetto, indipendente da Blender, da SketchUp e da qualunque formato.

Ogni `Oggetto` ha un nome leggibile (quello che l'utente vede in SketchUp), un tipo con significato (muro, porta,
finestra, pavimento, soffitto, arredo), una mesh, l'origine e le "parti": scatole sugli assi usate per i controlli
geometrici (vedi `verifica_geometria.py`). Il tipo serve anche a un futuro IFC: un muro resta un muro.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .mesh import Mesh, Punto
from .. import verifica_geometria as vg


@dataclass
class Oggetto:
    nome: str
    mesh: Mesh
    origine: Punto = (0.0, 0.0, 0.0)
    collezione: str = "Arredi"          # Architettura, Arredi, Tessili
    categoria: str = "arredo"           # architettura | arredo (per il controllo geometrico)
    tipo: str = "arredo"                # muro, pavimento, soffitto, porta, finestra, arredo...
    parti: list = field(default_factory=list)      # [(min, max)] sugli assi o [(min, max, obb)] inclinate, in coordinate del mondo
    fondi_complanari: bool = False      # in SketchUp unisce le facce complanari (muri, pavimenti)
    gruppo: str = ""                    # contenitore in SketchUp (Tamponature, Tramezzi, Arredi...); vuoto = secondo il tipo
    etichette: list = field(default_factory=list)  # nome di ogni parte nei rapporti (muri uniti: "Tamponature (muro D)")
    componente: str = ""                # oggetti ripetuti: nome della definizione condivisa (componente di SketchUp)
    definizione: "Oggetto | None" = None   # la stessa forma costruita una volta, nella sua posizione di riferimento
    matrice: tuple = ()                 # 4x4 per colonne (traslazione in metri): dalla definizione alla copia


class Scena:
    def __init__(self, nome: str = "Progetto"):
        self.nome = nome
        self.oggetti: list[Oggetto] = []
        self._nomi: set[str] = set()
        self.note: list[str] = []
        self.meta: dict = {}               # informazioni per le viste: stanze, ingombro, finestre

    def aggiungi(self, ob: Oggetto) -> Oggetto:
        if ob.nome in self._nomi:
            raise ValueError(f"nome di oggetto duplicato: {ob.nome!r} (ogni oggetto deve avere un nome unico)")
        self._nomi.add(ob.nome)
        self.oggetti.append(ob)
        return ob

    def per_nome(self, nome: str) -> Oggetto:
        return next(o for o in self.oggetti if o.nome == nome)

    def parti_per_verifica(self) -> list[tuple]:
        return [((o.etichette[k] if k < len(o.etichette) else o.nome), o.categoria, tuple(q[0]), tuple(q[1]))
                + ((q[2],) if len(q) > 2 else ())
                for o in self.oggetti for k, q in enumerate(o.parti)]

    def verifica(self) -> list[dict]:
        from . import ergonomia
        return vg.verifica(self.parti_per_verifica()) + ergonomia.controlla(self)

    def rapporto_geometria(self) -> str:
        return vg.rapporto_in_testo(self.verifica())

    def materiali_usati(self) -> list[str]:
        visti: list[str] = []
        for o in self.oggetti:
            for m in o.mesh.materiali:
                if m not in visti:
                    visti.append(m)
        return visti
