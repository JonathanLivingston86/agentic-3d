"""Muri a impronta: le masse murarie come poligoni in pianta (lette da un disegno CAD), con i vani tra le masse.

È l'alternativa alle pareti per linea d'asse (`pareti.py`) quando il disegno è preciso: ogni massa chiusa del CAD
diventa un prisma esatto e ogni vuoto tra due masse con un infisso diventa un vano, con davanzale e architrave.
Niente giunti da ricostruire, quindi niente scarti tra tramezzi e tamponature.

Scheda, nel piano:

    muri:
      - {id: M1, poligono_m: [[x, y], ...], classe: tamponatura}      # classe: tamponatura (predefinita) o tramezzo
    vani:
      - {id: Finestra 1, tipo: finestra, poligono_m: [[x, y] x 4], quota_davanzale_m: 0.60, altezza_m: 1.19}
      - {id: Porta bagno, tipo: porta, poligono_m: [...], altezza_m: 2.10}    # porta, portafinestra, vano (passaggio)

Il solido si costruisce a strati di quota (pavimento, davanzali, architravi, soffitto): in ogni strato l'impronta
piena è l'unione delle masse e dei vani chiusi a quella quota; ogni strato dà le sue facce laterali e, tra uno strato
e l'altro, solo le differenze (sopra il vano l'architrave, sotto il davanzale). Il solido è chiuso senza operazioni
booleane in tre dimensioni.
"""

from __future__ import annotations

from . import geom2d as g
from .forme import Telaio, parte_obb
from .mesh import Mesh
from .scena import Oggetto

MAT = "Intonaco pareti"
TOL = 0.01          # m: una massa e un vano più vicini di così si toccano


def _poligono(spec_poligono):
    from shapely.geometry import Polygon
    from shapely.geometry.polygon import orient
    p = Polygon([tuple(map(float, q)) for q in spec_poligono])
    if not p.is_valid:
        p = p.buffer(0)
    return orient(p, 1.0)


class Vano:
    """Vano rettangolare tra due masse: larghezza lungo il muro, profondità = spessore del muro."""

    def __init__(self, spec: dict, masse=()):
        self.spec = spec
        self.id = str(spec["id"])
        self.tipo = spec.get("tipo", "porta")
        pts = [tuple(map(float, q)) for q in spec["poligono_m"]]
        if len(pts) < 3:
            raise ValueError(f"vano {self.id}: servono i vertici del vano (poligono_m)")
        self.forma = _poligono(pts)
        if "faccia_m" in spec:                       # vano di forma libera (sguinci, muri diagonali)
            a, b = (tuple(map(float, q)) for q in spec["faccia_m"])
            self._da_faccia(a, b)
            return
        if len(pts) != 4:
            raise ValueError(f"vano {self.id}: un vano non rettangolare richiede `faccia_m` (il lato verso la stanza)")
        self.pts = g.antiorario(pts)
        lati = [(self.pts[i], self.pts[(i + 1) % 4]) for i in range(4)]
        # le spallette (lati contro le masse) danno la profondità; altrimenti il lato più corto
        def tocca(lato):
            # a contatto per gran parte della lunghezza (ogni lato tocca le masse almeno in un angolo)
            from shapely.geometry import LineString
            segmento = LineString(lato)
            return any(segmento.intersection(m.buffer(TOL)).length > 0.6 * segmento.length for m in masse)
        spallette = [i for i, l in enumerate(lati) if tocca(l)]
        i_prof = spallette[0] if spallette else min(range(4), key=lambda i: g.lunghezza(g.sottrai(*lati[i][::-1])))
        a, b = lati[(i_prof + 1) % 4]                # un lato lungo: una faccia del muro
        self.larghezza = g.lunghezza(g.sottrai(b, a))
        self.profondita = g.lunghezza(g.sottrai(*lati[i_prof][::-1]))
        self.eu = g.unitario(g.sottrai(b, a))
        self.faccia_a = a                            # inizio del lato lungo (faccia A)
        self.dentro = (-self.eu[1], self.eu[0])      # poligono antiorario: dalla faccia A verso il muro
        self._quote(spec)

    def _quote(self, spec):
        alt = float(spec.get("altezza_m", 2.10))
        if self.tipo == "finestra":
            self.z0 = float(spec.get("quota_davanzale_m", 1.0))
        else:
            self.z0 = 0.0
        self.z1 = self.z0 + alt

    def _da_faccia(self, a, b):
        """Orientamento dal lato verso la stanza: larghezza = quel lato, profondità = quanto il vano si allunga
        dall'altra parte."""
        self.eu = g.unitario(g.sottrai(b, a))
        normale = (-self.eu[1], self.eu[0])
        c = self.forma.centroid
        if g.dot(g.sottrai((c.x, c.y), a), normale) < 0:          # il vano sta dall'altra parte: si gira il lato
            a, b = b, a
            self.eu = g.per(self.eu, -1.0)
            normale = (-self.eu[1], self.eu[0])
        self.faccia_a = a
        self.dentro = normale
        self.larghezza = g.lunghezza(g.sottrai(b, a))
        self.profondita = max(0.02, max(g.dot(g.sottrai(p, a), normale) for p in list(self.forma.exterior.coords)))
        r = self.forma.minimum_rotated_rectangle
        self.pts = g.antiorario([tuple(p) for p in list(r.exterior.coords)[:4]])
        self._quote(self.spec)

    def telaio(self, verso_stanza: int = 1) -> Telaio:
        """Telaio dei serramenti: origine sulla faccia del muro verso la stanza, d positivo verso la stanza.
        `verso_stanza` = 1 se la stanza sta dal lato della faccia A, -1 se dal lato opposto."""
        if verso_stanza > 0:
            return Telaio(self.faccia_a, self.eu, g.per(self.dentro, -1.0))
        b = g.somma(self.faccia_a, g.per(self.dentro, self.profondita))
        return Telaio(g.somma(b, g.per(self.eu, self.larghezza)), g.per(self.eu, -1.0), self.dentro)

    def punto_di_lato(self, lato: int, scarto: float = 0.05):
        """Punto a metà vano, appena fuori dalla faccia A (lato 1) o dalla faccia opposta (lato -1)."""
        m = g.somma(self.faccia_a, g.per(self.eu, self.larghezza / 2))
        if lato > 0:
            return g.somma(m, g.per(self.dentro, -scarto))
        return g.somma(m, g.per(self.dentro, self.profondita + scarto))


def _anelli(geom):
    from shapely.geometry.polygon import orient
    out = []
    for p in (geom.geoms if hasattr(geom, "geoms") else [geom]):
        if p.is_empty or p.geom_type != "Polygon":
            continue
        p = orient(p, 1.0)
        out.append(list(p.exterior.coords)[:-1])
        out += [list(r.coords)[:-1] for r in p.interiors]
    return out


def _orizzontali(mesh: Mesh, geom, z: float, su: bool, mat: str) -> None:
    from shapely import constrained_delaunay_triangles
    for p in (geom.geoms if hasattr(geom, "geoms") else [geom]):
        if p.is_empty or p.geom_type != "Polygon" or p.area < 1e-6:
            continue
        for t in constrained_delaunay_triangles(p).geoms:
            c = list(t.exterior.coords)[:-1]
            if len(c) == 3:
                mesh.faccia([(x, y, z) for x, y in c], mat, normale=(0, 0, 1 if su else -1))


def solido(nome: str, masse: list, vani: list[Vano], z0: float, z1: float, tipo: str = "muro") -> Oggetto:
    """Solido unico delle masse (poligoni Shapely) e dei vani tra loro, dal pavimento z0 al soffitto z1."""
    from shapely.ops import unary_union
    quote = sorted({z0, z1} | {z0 + v.z0 for v in vani if z0 < z0 + v.z0 < z1}
                   | {z0 + v.z1 for v in vani if z0 < z0 + v.z1 < z1})
    strati = []
    for za, zb in zip(quote, quote[1:]):
        chiusi = [v.forma for v in vani if not (z0 + v.z0 < zb - 1e-9 and z0 + v.z1 > za + 1e-9)]
        strati.append((za, zb, unary_union(list(masse) + chiusi).buffer(0)))
    mesh = Mesh()
    mesh.nuovo_pezzo()
    for za, zb, f in strati:
        for anello in _anelli(f):
            n = len(anello)
            for i in range(n):
                (xa, ya), (xb, yb) = anello[i], anello[(i + 1) % n]
                if abs(xa - xb) + abs(ya - yb) < 1e-9:
                    continue
                mesh.faccia([(xa, ya, za), (xb, yb, za), (xb, yb, zb), (xa, ya, zb)], MAT, normale=(yb - ya, xa - xb, 0))
    from shapely.geometry import Polygon
    vuoto = Polygon()
    for k, z in enumerate(quote):
        sotto = strati[k - 1][2] if k > 0 else vuoto
        sopra = strati[k][2] if k < len(strati) else vuoto
        _orizzontali(mesh, sotto.difference(sopra), z, True, MAT)
        _orizzontali(mesh, sopra.difference(sotto), z, False, MAT)
    parti = []
    for m in masse:
        parti += parti_massa(m, z0, z1)
    for v in vani:
        for za, zb in ((z0, z0 + v.z0), (z0 + v.z1, z1)):
            if zb - za > 1e-6:
                parti.append(parte_rettangolo(v.pts, za, zb))
    return Oggetto(nome, mesh, (0.0, 0.0, 0.0), "Architettura", "architettura", tipo, parti, True)


def parte_rettangolo(pts, za, zb):
    """Parte orientata di un rettangolo in pianta (anche ruotato) tra due quote."""
    a, b, c = pts[0], pts[1], pts[2]
    e1 = g.unitario(g.sottrai(b, a))
    e2 = g.unitario(g.sottrai(c, b))
    centro = (sum(p[0] for p in pts[:4]) / 4, sum(p[1] for p in pts[:4]) / 4, (za + zb) / 2)
    return parte_obb(centro, ((e1[0], e1[1], 0.0), (e2[0], e2[1], 0.0), (0.0, 0.0, 1.0)),
                     (g.lunghezza(g.sottrai(b, a)) / 2, g.lunghezza(g.sottrai(c, b)) / 2, (zb - za) / 2))


def parti_massa(massa, z0: float, z1: float) -> list:
    """Parti di controllo di una massa: il rettangolo orientato se la massa è un rettangolo, altrimenti una scatola
    per triangolo (una massa a L non deve coprire la stanza nell'angolo)."""
    from shapely import constrained_delaunay_triangles
    rett = massa.minimum_rotated_rectangle
    if rett.area > 0 and massa.area / rett.area > 0.98:
        return [parte_rettangolo(list(rett.exterior.coords)[:4], z0, z1)]
    parti = []
    for t in constrained_delaunay_triangles(massa).geoms:
        c = list(t.exterior.coords)[:-1]
        xs, ys = [p[0] for p in c], [p[1] for p in c]
        parti.append(((min(xs), min(ys), z0), (max(xs), max(ys), z1)))
    return parti


def masse_della_scheda(piano: dict) -> list[tuple[str, str, object]]:
    """(id, classe, poligono) delle masse del piano."""
    out = []
    for m in piano.get("muri", []) or []:
        classe = m.get("classe", "tamponatura")
        if classe not in ("tamponatura", "tramezzo"):
            raise ValueError(f"muro {m.get('id')}: classe {classe!r} sconosciuta (tamponatura o tramezzo)")
        out.append((str(m["id"]), classe, _poligono(m["poligono_m"])))
    return out


def contorno(masse: list, vani: list[Vano], stanze=()):
    """Filo esterno di muri, vani e stanze: il bordo di pavimento e soffitto. None se non è un pezzo unico che
    contiene tutte le stanze (allora pavimenti e soffitti si fanno stanza per stanza)."""
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    poligoni_stanze = [Polygon(s) for s in stanze]
    # chiusura delle fessure ad angoli vivi (quelli arrotondati spezzano ogni spigolo in archi di micro-lati, che
    # SketchUp rifiuta) e semplificazione entro 1,5 mm: nessun lato più corto di quanto SketchUp sappia disegnare
    from shapely.geometry import JOIN_STYLE
    tutto = unary_union(list(masse) + [v.forma for v in vani] + poligoni_stanze)
    tutto = tutto.buffer(0.002, join_style=JOIN_STYLE.mitre).buffer(-0.002, join_style=JOIN_STYLE.mitre)
    tutto = tutto.simplify(0.0015, preserve_topology=True)
    pezzi = list(tutto.geoms) if hasattr(tutto, "geoms") else [tutto]
    grande = max(pezzi, key=lambda p: p.area, default=None)
    if grande is None:
        return None
    pieno = Polygon(grande.exterior)
    if not all(pieno.contains(Point(p.representative_point())) for p in poligoni_stanze):
        return None
    return g.antiorario([(float(x), float(y)) for x, y in list(grande.exterior.coords)[:-1]])
