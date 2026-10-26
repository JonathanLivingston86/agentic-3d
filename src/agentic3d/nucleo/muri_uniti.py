"""Muri uniti: tutti i pezzi di una categoria (tamponature o tramezzi) di un piano in un solo solido.

I pezzi della rete di pareti si toccano senza sovrapporsi (giunti a 45 gradi, nodi a T, prosecuzioni). Il solido unito
si costruisce così, senza operazioni booleane:

1. ogni pezzo è un quadrilatero in pianta (facce sinistra e destra tra i loro estremi), diviso in fasce ai bordi delle
   aperture;
2. i lati di tutti i quadrilateri vengono spezzati nei vertici degli altri che ci cadono sopra; i lati percorsi due
   volte in versi opposti sono contatti tra pezzi e si tolgono: quelli che restano sono il contorno del solido;
3. sul contorno nascono le facce verticali (a celle, con i vani delle aperture), sulle fasce le facce orizzontali
   (sopra, sotto tranne che nelle porte, architravi e davanzali dei vani), ai bordi dei vani le mazzette.

Ogni faccia orizzontale riceve i vertici del contorno che cadono sui suoi lati e si triangola a ventaglio dal suo
centro: il solido è chiuso, senza giunzioni a T, e il suo volume è la somma dei volumi dei pezzi.
"""

from __future__ import annotations

from . import geom2d as g
from .forme import parte_obb
from .mesh import Mesh, unitario
from .scena import Oggetto

TOL = 1e-6          # m: due vertici più vicini di così sono lo stesso
TOL_LATO = 1e-5     # m: un vertice più vicino di così a un lato ci cade sopra
MAT_INTONACO = "Intonaco pareti"
MAT_FASCIA = "Fascia pareti verde salvia"


class _Vertici:
    """Vertici in pianta resi unici (entro TOL) con una griglia."""

    LARGA = 0.5     # m: celle per cercare i vertici lungo un segmento

    def __init__(self):
        self.punti: list[tuple[float, float]] = []
        self._griglia: dict[tuple[int, int], list[int]] = {}
        self._larga: dict[tuple[int, int], list[int]] = {}

    def _cella(self, p):
        return (int(p[0] // 0.01), int(p[1] // 0.01))

    def id(self, p) -> int:
        cx, cy = self._cella(p)
        for a in (-1, 0, 1):
            for b in (-1, 0, 1):
                for i in self._griglia.get((cx + a, cy + b), ()):
                    q = self.punti[i]
                    if abs(q[0] - p[0]) <= TOL and abs(q[1] - p[1]) <= TOL:
                        return i
        self.punti.append((float(p[0]), float(p[1])))
        i = len(self.punti) - 1
        self._griglia.setdefault((cx, cy), []).append(i)
        self._larga.setdefault((int(p[0] // self.LARGA), int(p[1] // self.LARGA)), []).append(i)
        return i

    def sul_segmento(self, a: int, b: int) -> list[int]:
        """Vertici che cadono dentro il segmento a-b, ordinati da a verso b."""
        pa, pb = self.punti[a], self.punti[b]
        x0, x1 = sorted((pa[0], pb[0]))
        y0, y1 = sorted((pa[1], pb[1]))
        dx, dy = pb[0] - pa[0], pb[1] - pa[1]
        l2 = dx * dx + dy * dy
        out = []
        s = self.LARGA
        for cx in range(int((x0 - TOL_LATO) // s), int((x1 + TOL_LATO) // s) + 1):
            for cy in range(int((y0 - TOL_LATO) // s), int((y1 + TOL_LATO) // s) + 1):
                for i in self._larga.get((cx, cy), ()):
                    if i in (a, b):
                        continue
                    q = self.punti[i]
                    t = ((q[0] - pa[0]) * dx + (q[1] - pa[1]) * dy) / l2
                    if TOL / 10 < t < 1 - TOL / 10 and g.distanza_punto_segmento(q, pa, pb) <= TOL_LATO:
                        out.append((t, i))
        return [i for _, i in sorted(out)]


def _valida_aperture(w, tagli):
    minimo, massimo = max(w.ui[0], w.uo[0]), min(w.ui[1], w.uo[1])
    ap = sorted((a["u0"], a["u1"], a["z0"], a["z1"]) for a in tagli)
    for k, (a, b, _, _) in enumerate(ap):
        if a < minimo + TOL or b > massimo - TOL:
            raise ValueError(f"muro {w.id}: l'apertura da {a:.3f} a {b:.3f} m arriva al bordo della parete "
                             f"(la parete va da {minimo:.3f} a {massimo:.3f} m): lascia almeno un tratto di muro")
        if k and a < ap[k - 1][1] + TOL:
            raise ValueError(f"muro {w.id}: due aperture si toccano o si sovrappongono")
    return ap


def _parti_del_pezzo(w, z0, z1):
    """Scatola (sugli assi o orientata) del pezzo, per i controlli di compenetrazione."""
    u_min, u_max = min(w.ui[0], w.uo[0]), max(w.ui[1], w.uo[1])
    eu, en = w.eu, w.en
    assiale = abs(eu[0]) < 1e-9 or abs(eu[1]) < 1e-9
    if assiale:
        angoli = [w.punto_faccia(u, lato) for u in (u_min, u_max) for lato in ("sinistra", "destra")]
        xs, ys = [p[0] for p in angoli], [p[1] for p in angoli]
        return ((min(xs), min(ys), z0), (max(xs), max(ys), z1))
    um = (u_min + u_max) / 2
    a, b = w.punto_faccia(um, "sinistra"), w.punto_faccia(um, "destra")
    c = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (z0 + z1) / 2)
    return parte_obb(c, (unitario((eu[0], eu[1], 0.0)), unitario((en[0], en[1], 0.0)), (0.0, 0.0, 1.0)),
                     ((u_max - u_min) / 2, w.spessore / 2, (z1 - z0) / 2))


def muri_uniti(nome: str, pezzi: list[dict], z0: float, z1: float, fascia_z: float | None = None,
               tipo: str = "muro") -> Oggetto:
    """`pezzi` = [{"w": Pezzo, "tagli": [{"u0","u1","z0","z1"}], "fascia_a": bool, "fascia_b": bool}].
    Restituisce un solo Oggetto (solido chiuso) con le parti di controllo di ogni pezzo."""
    V = _Vertici()
    fasce = []        # (w, info, u_sin0, u_sin1, u_des0, u_des1, apertura_che_la_contiene o None)
    lati = []         # (a, b, etichetta): etichetta = (indice pezzo, "sinistra" | "destra" | "testa")
    aperture_di: list[list[tuple]] = []
    zs = {z0, z1}
    if fascia_z and z0 < fascia_z < z1:
        zs.add(fascia_z)

    for k, info in enumerate(pezzi):
        w = info["w"]
        ap = _valida_aperture(w, info.get("tagli", []))
        ap = [(a, b, max(lo, z0), min(hi, z1)) for a, b, lo, hi in ap if min(hi, z1) - max(lo, z0) > TOL]
        aperture_di.append(ap)
        for _, _, lo, hi in ap:
            zs.update((lo, hi))
        tagli_u = sorted({u for a, b, _, _ in ap for u in (a, b)})
        ns = [w.ui[0]] + tagli_u + [w.ui[1]]
        nd = [w.uo[0]] + tagli_u + [w.uo[1]]
        for j in range(len(ns) - 1):
            us0, us1, ud0, ud1 = ns[j], ns[j + 1], nd[j], nd[j + 1]
            dentro = next((x for x in ap if x[0] - TOL <= (us0 + us1) / 2 <= x[1] + TOL and 0 < j < len(ns) - 2), None)
            r0 = V.id(w.punto_faccia(ud0, "destra"))
            r1 = V.id(w.punto_faccia(ud1, "destra"))
            l1 = V.id(w.punto_faccia(us1, "sinistra"))
            l0 = V.id(w.punto_faccia(us0, "sinistra"))
            fasce.append((k, (r0, r1, l1, l0), dentro))
            lati.append((r0, r1, (k, "destra")))
            lati.append((r1, l1, (k, "taglio" if j < len(ns) - 2 else "testa")))
            lati.append((l1, l0, (k, "sinistra")))
            lati.append((l0, r0, (k, "taglio" if j > 0 else "testa")))
    zlist = sorted(zs)

    # contorno: lati spezzati nei vertici altrui, contatti (lati percorsi nei due versi) tolti
    diretti: dict[tuple[int, int], list] = {}
    for a, b, et in lati:
        if a == b:
            continue
        catena = [a] + V.sul_segmento(a, b) + [b]
        for p, q in zip(catena, catena[1:]):
            diretti.setdefault((p, q), []).append(et)
    contorno = []
    for (p, q), ets in diretti.items():
        inversi = len(diretti.get((q, p), ()))
        if len(ets) > 1:
            nomi = sorted({pezzi[e[0]]["w"].id for e in ets})
            raise ValueError(f"pezzi di muro sovrapposti ({', '.join(nomi)}): controlla le linee delle pareti")
        if inversi == 0:
            contorno.append((p, q, ets[0]))

    mesh = Mesh()
    P = V.punti

    def ap_contiene(k, u, z):
        return any(a < u < b and lo < z < hi for a, b, lo, hi in aperture_di[k])

    # facce verticali del contorno
    for p, q, (k, lato) in contorno:
        w = pezzi[k]["w"]
        a, b = P[p], P[q]
        dx, dy = b[0] - a[0], b[1] - a[1]
        normale = (dy, -dx, 0.0)                      # interno a sinistra del contorno: fuori a destra
        um = g.dot(g.sottrai(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), w.p0), w.eu)
        con_fascia = (lato == "sinistra" and pezzi[k].get("fascia_a")) or (lato == "destra" and pezzi[k].get("fascia_b"))
        for za, zb in zip(zlist, zlist[1:]):
            if lato in ("sinistra", "destra", "taglio") and ap_contiene(k, um, (za + zb) / 2):
                continue
            mat = MAT_FASCIA if con_fascia and fascia_z and zb <= fascia_z + 1e-9 else MAT_INTONACO
            mesh.faccia([(a[0], a[1], za), (b[0], b[1], za), (b[0], b[1], zb), (a[0], a[1], zb)], mat, normale=normale)

    # facce orizzontali: ogni fascia di ogni pezzo, con i vertici del contorno che cadono sui suoi lati
    def poligono(quad):
        out = []
        for s in range(4):
            a, b = quad[s], quad[(s + 1) % 4]
            out.append(a)
            out += V.sul_segmento(a, b)
        return out

    def ventaglio(ids, z, su):
        pts = [P[i] for i in ids]
        c = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        for s in range(len(pts)):
            a, b = pts[s], pts[(s + 1) % len(pts)]
            if abs((a[0] - c[0]) * (b[1] - c[1]) - (a[1] - c[1]) * (b[0] - c[0])) < 1e-12:
                continue
            mesh.faccia_condivisa([(c[0], c[1], z), (a[0], a[1], z), (b[0], b[1], z)], MAT_INTONACO,
                                  normale=(0.0, 0.0, 1.0 if su else -1.0))

    for k, quad, dentro in fasce:
        ids = poligono(quad)
        if dentro is None:
            ventaglio(ids, z1, True)
            ventaglio(ids, z0, False)
            continue
        a, b, lo, hi = dentro
        if hi < z1 - TOL:
            ventaglio(ids, z1, True)              # sopra il vano
            ventaglio(ids, hi, False)             # architrave
        if lo > z0 + TOL:
            ventaglio(ids, z0, False)             # sotto il davanzale
            ventaglio(ids, lo, True)              # davanzale

    # mazzette: ai due bordi di ogni vano, tra la faccia destra e la sinistra
    for k, info in enumerate(pezzi):
        w = info["w"]
        for a, b, lo, hi in aperture_di[k]:
            righe = [z for z in zlist if lo - 1e-9 <= z <= hi + 1e-9]
            for u, verso in ((a, 1.0), (b, -1.0)):
                ps, pd = w.punto_faccia(u, "sinistra"), w.punto_faccia(u, "destra")
                catena = [V.id(pd)] + V.sul_segmento(V.id(pd), V.id(ps)) + [V.id(ps)]
                for za, zb in zip(righe, righe[1:]):
                    for s, t in zip(catena, catena[1:]):
                        pa, pb = P[s], P[t]
                        mesh.faccia([(pa[0], pa[1], za), (pb[0], pb[1], za), (pb[0], pb[1], zb), (pa[0], pa[1], zb)],
                                    MAT_INTONACO, normale=(w.eu[0] * verso, w.eu[1] * verso, 0.0))

    mesh.salda()
    parti = [_parti_del_pezzo(info["w"], z0, z1) for info in pezzi]
    ob = Oggetto(nome, mesh, (0.0, 0.0, 0.0), "Architettura", "architettura", tipo, parti, True)
    ob.etichette = [f"{nome} (muro {info['w'].origine_id})" for info in pezzi]
    return ob
