"""Tavola di lettura: la pianta 2D di ciò che Agentic 3D ha capito, da confrontare con il disegno prima di costruire.

Funziona per qualunque scheda di edificio (pareti per linea d'asse o muri a impronta) e, dopo la lettura di un DXF,
mostra anche ciò che è ipotizzato (arancione) o non letto (rosso). Si salva come PNG nella cartella Riferimenti del
lavoro: l'utente la guarda accanto al disegno e conferma o corregge.
"""

from __future__ import annotations

from pathlib import Path

COLORI_STANZE = [(0.86, 0.93, 0.98), (0.93, 0.97, 0.88), (0.99, 0.95, 0.86), (0.95, 0.90, 0.98), (0.88, 0.97, 0.95),
                 (0.99, 0.90, 0.90), (0.92, 0.92, 0.86)]


def _poligoni_della_scheda(scheda: dict):
    """Masse, vani, stanze, zone e balconi del primo piano della scheda, come poligoni Shapely."""
    from shapely.geometry import Polygon
    from .nucleo import muri_impronta as mi
    from .nucleo.pareti import impronta, risolvi
    piano = scheda["edificio"]["piani"][0]
    masse = [(m["id"], m.get("classe", "tamponatura"), Polygon(m["poligono_m"]), False) for m in piano.get("muri", []) or []]
    if piano.get("pareti"):
        masse += [(w.id, "tamponatura", Polygon(impronta(w)), False) for w in risolvi(piano["pareti"]) if not w.curva]
    forme = [m[2] for m in masse]
    vani = []
    for v in piano.get("vani", []) or []:
        vv = mi.Vano(v, forme)
        vani.append((vv.id, vv.tipo, vv.forma, vv.larghezza, ""))
    stanze = [{"id": s["id"], "pol": Polygon(s["poligono_m"]), "altezza": s.get("altezza_m", piano.get("altezza_m"))}
              for s in piano.get("stanze", [])]
    zone = [(s["id"], Polygon(z["poligono_m"]), z["altezza_m"]) for s in piano.get("stanze", [])
            for z in s.get("controsoffitti", []) or []]
    balconi = [(b["id"], Polygon(b["poligono_m"])) for b in piano.get("balconi", []) or []]
    return masse, vani, stanze, zone, balconi


def disegna(destinazione: str | Path, scheda: dict | None = None, lettura=None, titolo: str = "") -> Path:
    """Disegna la tavola (PNG). Da una `lettura` del DXF (con ipotesi e dubbi) o da una `scheda`."""
    import fitz
    if lettura is not None:
        masse, vani, stanze, zone, balconi = lettura.masse, lettura.vani, lettura.stanze, lettura.zone, lettura.balconi
        stanze = [{"id": s["id"], "pol": s["pol"], "altezza": s.get("altezza"), "area_scritta": s.get("area_scritta")} for s in stanze]
        dubbi = lettura.dubbi
    else:
        masse, vani, stanze, zone, balconi = _poligoni_della_scheda(scheda)
        dubbi = []
    tutte = [m[2] for m in masse] + [s["pol"] for s in stanze] + [b[1] for b in balconi] + [v[2] for v in vani]
    if not tutte:
        raise ValueError("niente da disegnare")
    x0 = min(p.bounds[0] for p in tutte) - 0.6
    y0 = min(p.bounds[1] for p in tutte) - 0.6
    x1 = max(p.bounds[2] for p in tutte) + 0.6
    y1 = max(p.bounds[3] for p in tutte) + 0.6
    S = 80.0                                                       # punti per metro
    legenda_h = 70 + 13 * min(len(dubbi), 30)
    W, H = (x1 - x0) * S, (y1 - y0) * S + legenda_h
    doc = fitz.open()
    pg = doc.new_page(width=W, height=H)

    def p(x, y):
        return fitz.Point((x - x0) * S, (y1 - y) * S)

    def poligono(pol, riempi, bordo=(0.25, 0.25, 0.25), spessore=0.6, tratteggio=None):
        if pol.is_empty:
            return
        for parte in (pol.geoms if hasattr(pol, "geoms") else [pol]):
            if parte.geom_type != "Polygon":
                continue
            pts = [p(*c) for c in parte.exterior.coords]
            pg.draw_polyline(pts, color=bordo, fill=riempi, width=spessore, closePath=True, dashes=tratteggio)

    for k, st in enumerate(stanze):
        poligono(st["pol"], COLORI_STANZE[k % len(COLORI_STANZE)], (0.5, 0.5, 0.5), 0.4)
    for _, pol in balconi:
        poligono(pol, (0.93, 0.93, 0.93), (0.45, 0.45, 0.45), 0.8)
    for _, pol, _ in zone:
        poligono(pol, None, (0.55, 0.35, 0.75), 1.0, "[4 3] 0")
    for _, classe, pol, ipot in masse:
        poligono(pol, (0.98, 0.62, 0.25) if ipot else ((0.35, 0.35, 0.35) if classe == "tamponatura" else (0.55, 0.55, 0.55)),
                 (0.15, 0.15, 0.15), 0.4)
    for vid, tipo, pol, larghezza, _ in vani:
        colore = (0.25, 0.55, 0.95) if tipo in ("finestra", "portafinestra") else (0.2, 0.7, 0.35)
        poligono(pol, colore, colore, 0.4)
        c = pol.centroid
        pg.insert_text(p(c.x, c.y) + (4, -4), f"{larghezza * 100:.0f}", fontsize=7, color=colore)
    for st in stanze:
        c = st["pol"].representative_point()
        righe = [st["id"], f"{st['pol'].area:.2f} m2" + (f" (scritti {st['area_scritta']:.2f})" if st.get("area_scritta") else "")]
        if st.get("altezza"):
            righe.append(f"h {st['altezza']:.2f} m")
        for i, r in enumerate(righe):
            pg.insert_text(p(c.x, c.y) + (-30, -8 + 11 * i), r, fontsize=8 if i else 9, color=(0.1, 0.1, 0.1))
    for _, pol, h in zone:
        c = pol.representative_point()
        pg.insert_text(p(c.x, c.y) + (-20, 14), f"controsoffitto h {h:.2f}", fontsize=7, color=(0.45, 0.25, 0.65))
    for bid, pol in balconi:
        c = pol.representative_point()
        pg.insert_text(p(c.x, c.y), bid, fontsize=8, color=(0.3, 0.3, 0.3))
    # scala grafica: 1 m
    base = fitz.Point(20, (y1 - y0) * S - 14)
    pg.draw_line(base, base + (S, 0), color=(0, 0, 0), width=1.5)
    pg.insert_text(base + (S + 6, 4), "1 m", fontsize=8)
    y = (y1 - y0) * S + 18
    pg.insert_text((20, y), titolo or "Tavola di lettura: confrontare con il disegno prima di costruire", fontsize=11)
    pg.insert_text((20, y + 16), "grigio: muri   arancione: spessore ipotizzato   azzurro: finestre   verde: porte "
                   "(larghezza in cm)   viola tratteggiato: controsoffitti", fontsize=8, color=(0.3, 0.3, 0.3))
    for i, d in enumerate(dubbi[:30]):
        pg.insert_text((20, y + 34 + 13 * i), f"- {d}"[:170], fontsize=8, color=(0.75, 0.15, 0.1))
    destinazione = Path(destinazione)
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    pg.get_pixmap(dpi=110).save(str(destinazione))
    return destinazione
