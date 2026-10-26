"""Importatori di planimetrie: DXF (ezdxf) e PDF vettoriale (PyMuPDF).

Restituiscono la geometria in metri, con l'asse Y verso l'alto, pronta per essere letta dall'agente
(rettangoli di arredi e vani, segmenti dei muri, testi delle quote).

- DXF: l'unità si legge da `$INSUNITS`; se il file non la dichiara va passata (`unita="cm"`).
  Gli errori di unità (cm scambiati per m) sono la causa più comune di modelli sbagliati: controlla sempre
  `Geometria.estensione()` contro una misura nota.
- PDF: un PDF stampato da AutoCAD conserva i vettori. La scala si calibra con una quota nota
  (`calibrazione=((x1, y1), (x2, y2), metri)` in punti PDF) oppure con `punti_per_metro`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Fattori di conversione da unità di disegno DXF a metri ($INSUNITS)
_INSUNITS_A_METRI = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0, 7: 1000.0}
_NOMI_UNITA = {"mm": 0.001, "cm": 0.01, "m": 1.0, "in": 0.0254, "ft": 0.3048}


@dataclass
class Segmento:
    x1: float
    y1: float
    x2: float
    y2: float
    spessore: float = 0.0
    layer: str = ""

    @property
    def lunghezza(self) -> float:
        return ((self.x2 - self.x1) ** 2 + (self.y2 - self.y1) ** 2) ** 0.5


@dataclass
class Rettangolo:
    x0: float
    y0: float
    x1: float
    y1: float
    layer: str = ""

    @property
    def larghezza(self) -> float:
        return abs(self.x1 - self.x0)

    @property
    def altezza(self) -> float:
        return abs(self.y1 - self.y0)

    def __str__(self) -> str:
        return (f"x {min(self.x0, self.x1):.3f}..{max(self.x0, self.x1):.3f}  "
                f"y {min(self.y0, self.y1):.3f}..{max(self.y0, self.y1):.3f}  "
                f"({self.larghezza:.3f} x {self.altezza:.3f} m)")


@dataclass
class Testo:
    testo: str
    x: float
    y: float
    altezza: float = 0.0


@dataclass
class Geometria:
    segmenti: list[Segmento] = field(default_factory=list)
    rettangoli: list[Rettangolo] = field(default_factory=list)
    testi: list[Testo] = field(default_factory=list)
    avvisi: list[str] = field(default_factory=list)

    def estensione(self) -> tuple[float, float, float, float]:
        """(xmin, ymin, xmax, ymax) in metri di tutta la geometria."""
        xs, ys = [], []
        for s in self.segmenti:
            xs += [s.x1, s.x2]
            ys += [s.y1, s.y2]
        for r in self.rettangoli:
            xs += [r.x0, r.x1]
            ys += [r.y0, r.y1]
        if not xs:
            raise ValueError("geometria vuota")
        return min(xs), min(ys), max(xs), max(ys)

    def in_regione(self, x0: float, y0: float, x1: float, y1: float) -> "Geometria":
        def dentro(x, y):
            return x0 <= x <= x1 and y0 <= y <= y1

        return Geometria(
            segmenti=[s for s in self.segmenti if dentro(s.x1, s.y1) and dentro(s.x2, s.y2)],
            rettangoli=[r for r in self.rettangoli if dentro(r.x0, r.y0) and dentro(r.x1, r.y1)],
            testi=[t for t in self.testi if dentro(t.x, t.y)],
            avvisi=list(self.avvisi),
        )

    def traslata(self, dx: float, dy: float) -> "Geometria":
        """Sposta l'origine: utile per portare l'angolo interno sud-ovest di una stanza in (0, 0)."""
        return Geometria(
            segmenti=[Segmento(s.x1 + dx, s.y1 + dy, s.x2 + dx, s.y2 + dy, s.spessore, s.layer) for s in self.segmenti],
            rettangoli=[Rettangolo(r.x0 + dx, r.y0 + dy, r.x1 + dx, r.y1 + dy, r.layer) for r in self.rettangoli],
            testi=[Testo(t.testo, t.x + dx, t.y + dy, t.altezza) for t in self.testi],
            avvisi=list(self.avvisi),
        )

    def rettangoli_per_dimensione(self, larghezza: float, altezza: float, tolleranza: float = 0.03) -> list[Rettangolo]:
        """Rettangoli di una data misura (in un verso o nell'altro): per trovare letti, armadi, finestre."""
        trovati = []
        for r in self.rettangoli:
            a, b = sorted((r.larghezza, r.altezza))
            c, d = sorted((larghezza, altezza))
            if abs(a - c) <= tolleranza and abs(b - d) <= tolleranza:
                trovati.append(r)
        return trovati

    def rapporto(self) -> str:
        righe = [f"{len(self.rettangoli)} rettangoli, {len(self.segmenti)} segmenti, {len(self.testi)} testi"]
        righe += [f"- {r}" for r in sorted(self.rettangoli, key=lambda r: (-r.larghezza * r.altezza))[:40]]
        righe += [f"AVVISO: {a}" for a in self.avvisi]
        return "\n".join(righe)


# ------------------------------------------------------------------------------ DXF

def _unita_dxf(doc, unita: str | None) -> tuple[float, str | None]:
    if unita:
        return _NOMI_UNITA[unita], None
    codice = doc.header.get("$INSUNITS", 0)
    if codice in _INSUNITS_A_METRI:
        return _INSUNITS_A_METRI[codice], None
    return 1.0, ("il file DXF non dichiara l'unità ($INSUNITS = 0): ho assunto i metri. "
                 "Se il disegno è in centimetri o millimetri passa unita='cm' o 'mm' e verifica una misura nota.")


def da_dxf(percorso: str | Path, unita: str | None = None, layer: list[str] | None = None) -> Geometria:
    """Legge un DXF. `layer`: elenco di layer da considerare (tutti se omesso)."""
    import ezdxf

    doc = ezdxf.readfile(str(percorso))
    k, avviso = _unita_dxf(doc, unita)
    g = Geometria()
    if avviso:
        g.avvisi.append(avviso)

    def accetta(e) -> bool:
        return layer is None or e.dxf.layer in layer

    def aggiungi(e):
        tipo = e.dxftype()
        if tipo == "LINE":
            s, f = e.dxf.start, e.dxf.end
            g.segmenti.append(Segmento(s.x * k, s.y * k, f.x * k, f.y * k, layer=e.dxf.layer))
        elif tipo in ("LWPOLYLINE", "POLYLINE"):
            punti = [(p[0] * k, p[1] * k) for p in (e.get_points("xy") if tipo == "LWPOLYLINE" else
                                                    [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices])]
            chiusa = e.closed
            xs, ys = {round(p[0], 6) for p in punti}, {round(p[1], 6) for p in punti}
            if chiusa and len(punti) == 4 and len(xs) == 2 and len(ys) == 2:
                g.rettangoli.append(Rettangolo(min(xs), min(ys), max(xs), max(ys), e.dxf.layer))
            else:
                coppie = list(zip(punti, punti[1:] + (punti[:1] if chiusa else [])))
                for (a, b) in coppie:
                    if a != b:
                        g.segmenti.append(Segmento(a[0], a[1], b[0], b[1], layer=e.dxf.layer))
        elif tipo in ("TEXT", "MTEXT"):
            testo = e.dxf.text if tipo == "TEXT" else e.plain_text()
            p = e.dxf.insert
            g.testi.append(Testo(testo, p.x * k, p.y * k, getattr(e.dxf, "height", 0.0) * k))

    for e in doc.modelspace():
        if e.dxftype() == "INSERT":
            for v in e.virtual_entities():
                if accetta(v):
                    aggiungi(v)
        elif accetta(e):
            aggiungi(e)
    return g


# ------------------------------------------------------------------------------ PDF

def da_pdf(percorso: str | Path, pagina: int = 0, punti_per_metro: float | None = None,
           calibrazione: tuple[tuple[float, float], tuple[float, float], float] | None = None) -> Geometria:
    """Legge i vettori di una pagina PDF. Serve la scala: `punti_per_metro` oppure una `calibrazione`."""
    import pymupdf

    if punti_per_metro is None and calibrazione is None:
        raise ValueError("serve la scala: punti_per_metro oppure calibrazione=((x1, y1), (x2, y2), metri)")
    if calibrazione is not None:
        (ax, ay), (bx, by), metri = calibrazione
        punti_per_metro = (((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5) / metri
    s = 1.0 / punti_per_metro

    pag = pymupdf.open(str(percorso))[pagina]
    alt = pag.rect.height
    g = Geometria()

    def X(x):
        return x * s

    def Y(y):  # il PDF ha l'asse Y verso il basso
        return (alt - y) * s

    for d in pag.get_drawings():
        spessore = float(d.get("width") or 0.0) * s
        for it in d["items"]:
            if it[0] == "l":
                a, b = it[1], it[2]
                g.segmenti.append(Segmento(X(a.x), Y(a.y), X(b.x), Y(b.y), spessore))
            elif it[0] in ("re", "qu"):
                r = it[1] if it[0] == "re" else it[1].rect
                g.rettangoli.append(Rettangolo(X(r.x0), Y(r.y1), X(r.x1), Y(r.y0)))
            elif it[0] == "c":  # curva: ne tengo gli estremi come segmento
                a, b = it[1], it[4]
                g.segmenti.append(Segmento(X(a.x), Y(a.y), X(b.x), Y(b.y), spessore, layer="curva"))
    for w in pag.get_text("words"):
        g.testi.append(Testo(w[4], X(w[0]), Y(w[3])))
    return g
