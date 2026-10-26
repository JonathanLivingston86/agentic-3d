"""Costruttore di forme: scatole, prismi, cilindri, scatole arrotondate, superfici, estrusioni, solidi di rotazione.

È la versione senza Blender della classe `Pezzo` di `blender/costruttore_classico.py`: stessa interfaccia, stesse forme,
ma il risultato è una `Mesh` pura. Un oggetto si costruisce aggiungendo forme e si chiude con `chiudi()`.

Le coordinate di parete (u, d, z) passano da un `Telaio`: u lungo la parete, d verso l'interno della stanza, z alto.
Con un telaio qualunque (anche inclinato) le forme restano corrette; i controlli geometrici a scatole sugli assi
si fanno solo se il telaio è allineato agli assi.
"""

from __future__ import annotations

import math

from .mesh import Mesh, cross, diff, dot, lunghezza, normale_poligono, per, somma, unitario
from .scena import Oggetto


class Telaio:
    """Sistema di coordinate di parete: punto del mondo = origine + u * eu + d * ed + z * Z."""

    def __init__(self, origine=(0.0, 0.0), eu=(1.0, 0.0), ed=(0.0, 1.0)):
        self.o = (float(origine[0]), float(origine[1]))
        self.eu = (float(eu[0]), float(eu[1]))
        self.ed = (float(ed[0]), float(ed[1]))

    def __call__(self, u, d, z):
        return (self.o[0] + u * self.eu[0] + d * self.ed[0], self.o[1] + u * self.eu[1] + d * self.ed[1], float(z))

    def direzione(self, nu, nd, nz):
        return (nu * self.eu[0] + nd * self.ed[0], nu * self.eu[1] + nd * self.ed[1], float(nz))

    @property
    def assiale(self) -> bool:
        return abs(self.eu[0] * self.eu[1]) < 1e-9 and abs(self.ed[0] * self.ed[1]) < 1e-9


def telaio_parete(parete: str, L: float, W: float) -> Telaio:
    """Telaio delle quattro pareti di una stanza rettangolare (stesse convenzioni di `mappa` in Blender)."""
    if parete == "sud":
        return Telaio((0, 0), (1, 0), (0, 1))
    if parete == "nord":
        return Telaio((0, W), (1, 0), (0, -1))
    if parete == "ovest":
        return Telaio((0, 0), (0, 1), (1, 0))
    if parete == "est":
        return Telaio((L, 0), (0, 1), (-1, 0))
    raise ValueError(f"parete sconosciuta: {parete}")


def telaio_cardinale(parete: str, x0: float, y0: float, x1: float, y1: float) -> Telaio:
    """Telaio della parete `sud`, `nord`, `ovest` o `est` di una stanza rettangolare con angoli (x0, y0) e (x1, y1):
    u parte dall'angolo sud-ovest, d verso l'interno. Con x0 = y0 = 0 coincide con `telaio_parete`."""
    if parete == "sud":
        return Telaio((x0, y0), (1, 0), (0, 1))
    if parete == "nord":
        return Telaio((x0, y1), (1, 0), (0, -1))
    if parete == "ovest":
        return Telaio((x0, y0), (0, 1), (1, 0))
    if parete == "est":
        return Telaio((x1, y0), (0, 1), (-1, 0))
    raise ValueError(f"parete sconosciuta: {parete!r}")


def _aabb(punti):
    return ((min(p[0] for p in punti), min(p[1] for p in punti), min(p[2] for p in punti)),
            (max(p[0] for p in punti), max(p[1] for p in punti), max(p[2] for p in punti)))


def _assi_telaio(m: Telaio):
    """Assi unitari del mondo corrispondenti a u, d, z di un telaio."""
    return (unitario(m.direzione(1, 0, 0)), unitario(m.direzione(0, 1, 0)), (0.0, 0.0, 1.0))


def parte_obb(centro, assi, mezzi):
    """Parte `(min, max, obb)`: la scatola orientata e la scatola sugli assi che la contiene."""
    cs = [somma(centro, somma(somma(per(assi[0], sx * mezzi[0]), per(assi[1], sy * mezzi[1])), per(assi[2], sz * mezzi[2])))
          for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    a, b = _aabb(cs)
    return (a, b, (tuple(centro), tuple(tuple(x) for x in assi), tuple(mezzi)))


def _ruota_parte(parte, c, s, tx, ty, multiplo):
    """Applica rotazione attorno a Z (coseno c, seno s) e traslazione (tx, ty) a una parte."""
    def pt(p):
        return (tx + p[0] * c - p[1] * s, ty + p[0] * s + p[1] * c, p[2])

    def vt(v):
        return (v[0] * c - v[1] * s, v[0] * s + v[1] * c, v[2])

    a, b = parte[0], parte[1]
    if len(parte) > 2:                                           # già inclinata: ruota centro e assi
        centro, assi, mezzi = parte[2]
        return parte_obb(pt(centro), tuple(vt(x) for x in assi), mezzi)
    if multiplo:                                                 # multipli di 90 gradi: resta sugli assi
        return _aabb([pt((x, y, z)) for x in (a[0], b[0]) for y in (a[1], b[1]) for z in (a[2], b[2])])
    centro = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)
    return parte_obb(pt(centro), (vt((1.0, 0.0, 0.0)), vt((0.0, 1.0, 0.0)), (0.0, 0.0, 1.0)),
                     ((b[0] - a[0]) / 2, (b[1] - a[1]) / 2, (b[2] - a[2]) / 2))


class Costruttore:
    """Un oggetto fatto di forme, con materiali per faccia. Si chiude in una sola mesh."""

    def __init__(self, nome, collezione="Arredi", tipo="arredo", fondi_complanari=False):
        self.nome = nome
        self.collezione = collezione
        self.categoria = "architettura" if collezione == "Architettura" else "arredo"
        self.tipo = tipo
        self.fondi_complanari = fondi_complanari
        self.mesh = Mesh()
        self.parti: list = []           # (min, max) per le scatole sugli assi; (min, max, obb) per quelle inclinate

    # ------------------------------------------------------------ forme di base
    def _parte(self, punti):
        self.parti.append(_aabb(punti))

    def _parte_obb(self, centro, assi, mezzi):
        """Parte inclinata: scatola orientata con centro, tre assi unitari e le mezze misure lungo gli assi."""
        self.parti.append(parte_obb(centro, assi, mezzi))

    def box(self, p0, p1, mat):
        """Scatola con spigoli sugli assi: p0 e p1 sono due angoli opposti."""
        x0, y0, z0 = (min(p0[i], p1[i]) for i in range(3))
        x1, y1, z1 = (max(p0[i], p1[i]) for i in range(3))
        if x1 - x0 < 1e-6 or y1 - y0 < 1e-6 or z1 - z0 < 1e-6:
            return
        self._parte([(x0, y0, z0), (x1, y1, z1)])
        self._scatola(lambda u, d, z: (u, d, z), (x0, y0, z0), (x1, y1, z1), mat,
                      lambda nu, nd, nz: (nu, nd, nz))

    def box_p(self, m: Telaio, u0, d0, z0, u1, d1, z1, mat):
        """Scatola in coordinate di parete (con qualunque telaio)."""
        a, b = (min(u0, u1), min(d0, d1), min(z0, z1)), (max(u0, u1), max(d0, d1), max(z0, z1))
        if b[0] - a[0] < 1e-6 or b[1] - a[1] < 1e-6 or b[2] - a[2] < 1e-6:
            return
        if m.assiale:
            self._parte([m(*a), m(*b)])
        else:
            self._parte_obb(m((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2), _assi_telaio(m),
                            ((b[0] - a[0]) / 2, (b[1] - a[1]) / 2, (b[2] - a[2]) / 2))
        self._scatola(m, a, b, mat, m.direzione)

    def _scatola(self, m, a, b, mat, dirn):
        self.mesh.nuovo_pezzo()
        (u0, d0, z0), (u1, d1, z1) = a, b
        facce = (
            ([(u0, d0, z0), (u1, d0, z0), (u1, d1, z0), (u0, d1, z0)], (0, 0, -1)),
            ([(u0, d0, z1), (u1, d0, z1), (u1, d1, z1), (u0, d1, z1)], (0, 0, 1)),
            ([(u0, d0, z0), (u1, d0, z0), (u1, d0, z1), (u0, d0, z1)], (0, -1, 0)),
            ([(u0, d1, z0), (u1, d1, z0), (u1, d1, z1), (u0, d1, z1)], (0, 1, 0)),
            ([(u0, d0, z0), (u0, d1, z0), (u0, d1, z1), (u0, d0, z1)], (-1, 0, 0)),
            ([(u1, d0, z0), (u1, d1, z0), (u1, d1, z1), (u1, d0, z1)], (1, 0, 0)),
        )
        for punti, (nu, nd, nz) in facce:
            self.mesh.faccia([m(*p) for p in punti], mat, normale=dirn(nu, nd, nz))

    def prisma(self, m: Telaio, punti_uz, d0, d1, mat):
        """Poligono nel piano (u, z) estruso tra d0 e d1."""
        self.mesh.nuovo_pezzo()
        n = len(punti_uz)
        fronte = [m(u, d0, z) for u, z in punti_uz]
        retro = [m(u, d1, z) for u, z in punti_uz]
        if m.assiale:
            self._parte(fronte + retro)
        else:
            us, zs = [q[0] for q in punti_uz], [q[1] for q in punti_uz]
            u0, u1, z0, z1 = min(us), max(us), min(zs), max(zs)
            self._parte_obb(m((u0 + u1) / 2, (d0 + d1) / 2, (z0 + z1) / 2), _assi_telaio(m),
                            ((u1 - u0) / 2, abs(d1 - d0) / 2, (z1 - z0) / 2))
        area2 = sum(punti_uz[i][0] * punti_uz[(i + 1) % n][1] - punti_uz[(i + 1) % n][0] * punti_uz[i][1] for i in range(n))
        ccw = area2 > 0
        self.mesh.faccia(fronte, mat, normale=m.direzione(0, -1, 0))
        self.mesh.faccia(retro, mat, normale=m.direzione(0, 1, 0))
        for i in range(n):
            j = (i + 1) % n
            du, dz = punti_uz[j][0] - punti_uz[i][0], punti_uz[j][1] - punti_uz[i][1]
            nu, nz = (dz, -du) if ccw else (-dz, du)
            self.mesh.faccia([fronte[i], fronte[j], retro[j], retro[i]], mat, normale=m.direzione(nu, 0, nz))

    def cilindro(self, cx, cy, z0, z1, r, mat, seg=20):
        self.mesh.nuovo_pezzo()
        self.mesh.segna_rivoluzione(seg)
        basso = [(cx + r * math.cos(2 * math.pi * i / seg), cy + r * math.sin(2 * math.pi * i / seg), z0) for i in range(seg)]
        alto = [(p[0], p[1], z1) for p in basso]
        self._parte(basso + alto)
        self.mesh.faccia(list(reversed(basso)), mat, normale=(0, 0, -1))
        self.mesh.faccia(alto, mat, normale=(0, 0, 1))
        for i in range(seg):
            j = (i + 1) % seg
            q = [basso[i], basso[j], alto[j], alto[i]]
            mx, my = (q[0][0] + q[1][0]) / 2 - cx, (q[0][1] + q[1][1]) / 2 - cy
            self.mesh.faccia(q, mat, normale=(mx, my, 0))

    def cilindro_asse(self, a, b, r, mat, seg=14):
        """Cilindro tra due punti qualsiasi (bastone, gambe)."""
        self.mesh.nuovo_pezzo()
        self.mesh.segna_rivoluzione(seg)
        a, b = tuple(map(float, a)), tuple(map(float, b))
        asse = unitario(diff(b, a))
        rif = (0, 0, 1) if abs(asse[2]) < 0.9 else (1, 0, 0)
        e1 = unitario(cross(asse, rif))
        e2 = unitario(cross(asse, e1))
        c0 = [somma(a, per(somma(per(e1, math.cos(2 * math.pi * i / seg)), per(e2, math.sin(2 * math.pi * i / seg))), r))
              for i in range(seg)]
        v = diff(b, a)
        c1 = [somma(p, v) for p in c0]
        if max(abs(asse[0]), abs(asse[1]), abs(asse[2])) > 0.9999:
            self._parte(c0 + c1)
        else:       # cilindro inclinato: scatola orientata lungo l'asse
            self._parte_obb(per(somma(a, b), 0.5), (asse, e1, e2), (lunghezza(v) / 2, r, r))
        self.mesh.faccia(list(reversed(c0)), mat, normale=per(asse, -1))
        self.mesh.faccia(c1, mat, normale=asse)
        for i in range(seg):
            j = (i + 1) % seg
            q = [c0[i], c0[j], c1[j], c1[i]]
            centro = per(somma(somma(q[0], q[1]), somma(q[2], q[3])), 0.25)
            radiale = diff(centro, somma(a, per(asse, dot(diff(centro, a), asse))))
            self.mesh.faccia(q, mat, normale=radiale)

    def smussato(self, p0, p1, mat, raggio=0.02, segmenti=2):
        """Scatola con spigoli arrotondati (materassi, cuscini): scatola smussata con ombreggiatura liscia.
        Ogni spigolo ha `segmenti` tratti di arco; ogni angolo è un ottavo di sfera suddiviso in modo uguale."""
        self.mesh.nuovo_pezzo()
        x0, y0, z0 = (min(p0[i], p1[i]) for i in range(3))
        x1, y1, z1 = (max(p0[i], p1[i]) for i in range(3))
        self._parte([p0, p1])
        r = min(raggio, (x1 - x0) / 2 - 1e-9, (y1 - y0) / 2 - 1e-9, (z1 - z0) / 2 - 1e-9)
        n = max(1, int(segmenti))
        m = self.mesh
        lisce = True
        # angoli interni del nucleo piatto
        ci = {s: (x0 + r if s[0] < 0 else x1 - r, y0 + r if s[1] < 0 else y1 - r, z0 + r if s[2] < 0 else z1 - r)
              for s in ((a, b, c) for a in (-1, 1) for b in (-1, 1) for c in (-1, 1))}

        def vert(s, nrm):
            c = ci[s]
            return m.vertice((c[0] + r * nrm[0], c[1] + r * nrm[1], c[2] + r * nrm[2]), condiviso=True)

        def arco(ax_a, ax_b, t):
            """Normale a metà tra due assi (versori) all'angolo t in [0, pi/2]."""
            return tuple(ax_a[k] * math.cos(t) + ax_b[k] * math.sin(t) for k in range(3))

        assi = {0: (1, 0, 0), 1: (0, 1, 0), 2: (0, 0, 1)}
        # facce piatte
        for k in range(3):
            for sgn in (-1, 1):
                n_f = tuple(sgn if i == k else 0 for i in range(3))
                altri = [i for i in range(3) if i != k]
                ang = []
                for sa in (-1, 1):
                    for sb in (-1, 1):
                        s = [0, 0, 0]
                        s[k], s[altri[0]], s[altri[1]] = sgn, sa, sb
                        ang.append((sa, sb, vert(tuple(s), n_f)))
                (_, _, v00), (_, _, v01), (_, _, v10), (_, _, v11) = ang
                self._faccia_orientata([v00, v10, v11, v01], mat, n_f, lisce)
        # strisce degli spigoli: 12 spigoli, ciascuno con n quadrilateri
        for k in range(3):                                   # asse lungo lo spigolo
            altri = [i for i in range(3) if i != k]
            for sa in (-1, 1):
                for sb in (-1, 1):
                    na = tuple(sa if i == altri[0] else 0 for i in range(3))
                    nb = tuple(sb if i == altri[1] else 0 for i in range(3))
                    for t in range(n):
                        n1 = arco(na, nb, math.pi / 2 * t / n)
                        n2 = arco(na, nb, math.pi / 2 * (t + 1) / n)
                        quad = []
                        for sk in (-1, 1):
                            s = [0, 0, 0]
                            s[k], s[altri[0]], s[altri[1]] = sk, sa, sb
                            quad.append((tuple(s), n1, n2))
                        (s0, a1, a2), (s1, _, _) = quad
                        idx = [vert(s0, a1), vert(s1, a1), vert(s1, a2), vert(s0, a2)]
                        esterno = tuple((a1[i] + a2[i]) / 2 for i in range(3))
                        self._faccia_orientata(idx, mat, esterno, lisce)
        # angoli: ottavo di sfera suddiviso in n*n triangoli
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    s = (sx, sy, sz)
                    ex, ey, ez = (sx, 0, 0), (0, sy, 0), (0, 0, sz)

                    def p(i, j):             # i + j <= n; barycentric su (ex, ey, ez)
                        kk = n - i - j
                        nrm = unitario(tuple((ex[a] * i + ey[a] * j + ez[a] * kk) / n for a in range(3)))
                        return vert(s, nrm)

                    def triangolo(a, b, c):
                        pts = [m.v[a], m.v[b], m.v[c]]
                        centro = per(somma(somma(pts[0], pts[1]), pts[2]), 1 / 3)
                        self._faccia_orientata([a, b, c], mat, diff(centro, ci[s]), lisce)

                    for i in range(n):
                        for j in range(n - i):
                            triangolo(p(i, j), p(i + 1, j), p(i, j + 1))
                            if i + j + 2 <= n:
                                triangolo(p(i + 1, j), p(i + 1, j + 1), p(i, j + 1))

    def _faccia_orientata(self, indici, mat, normale_attesa, liscia):
        pts = [self.mesh.v[i] for i in indici]
        if dot(normale_poligono(pts), normale_attesa) < 0:
            indici = list(reversed(indici))
        self.mesh.faccia_idx(indici, mat, liscia)

    def griglia(self, quadri, mat):
        """Superficie libera da una lista di quadrilateri (4 punti ciascuno)."""
        self.mesh.nuovo_pezzo()
        self._parte([v for q in quadri for v in q])
        for q in quadri:
            self.mesh.faccia(q, mat)

    # ------------------------------------------------------------ forme nuove (edifici, arredi non scatolari)
    def estrusione(self, poligono_xy, z0, z1, mat_alto, mat_basso=None, mat_lati=None):
        """Poligono in pianta (anche concavo) esteso in altezza tra z0 e z1."""
        self.mesh.nuovo_pezzo()
        pts = [(float(x), float(y)) for x, y in poligono_xy]
        area2 = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
        if area2 < 0:
            pts.reverse()
        n = len(pts)
        mat_basso = mat_basso or mat_alto
        mat_lati = mat_lati or mat_alto
        self._parte([(x, y, z0) for x, y in pts] + [(x, y, z1) for x, y in pts])
        self.mesh.faccia([(x, y, z1) for x, y in pts], mat_alto, normale=(0, 0, 1))
        self.mesh.faccia([(x, y, z0) for x, y in pts], mat_basso, normale=(0, 0, -1))
        for i in range(n):
            j = (i + 1) % n
            (xa, ya), (xb, yb) = pts[i], pts[j]
            self.mesh.faccia([(xa, ya, z0), (xb, yb, z0), (xb, yb, z1), (xa, ya, z1)], mat_lati,
                             normale=(yb - ya, xa - xb, 0))

    def torno(self, profilo_rz, cx, cy, z0, mat, seg=24, chiuso=True):
        """Solido di rotazione attorno a un asse verticale in (cx, cy): `profilo_rz` = [(raggio, altezza)] dal basso."""
        self.mesh.nuovo_pezzo()
        self.mesh.segna_rivoluzione(seg)
        anelli = [[(cx + r * math.cos(2 * math.pi * i / seg), cy + r * math.sin(2 * math.pi * i / seg), z0 + z)
                   for i in range(seg)] for r, z in profilo_rz]
        self._parte([p for a in anelli for p in a])
        for k in range(len(anelli) - 1):
            r0, r1 = profilo_rz[k][0], profilo_rz[k + 1][0]
            for i in range(seg):
                j = (i + 1) % seg
                # ordine che dà la normale verso l'esterno quando il profilo sale dal basso
                a, b, c, d = anelli[k][i], anelli[k][j], anelli[k + 1][j], anelli[k + 1][i]
                q = [a, c, d] if r0 < 1e-12 else [a, b, d] if r1 < 1e-12 else [a, b, c, d]
                if lunghezza(normale_poligono(q)) > 1e-12:
                    self.mesh.faccia(q, mat)
        if chiuso:
            for anello, giu in ((anelli[0], True), (anelli[-1], False)):
                r = profilo_rz[0][0] if giu else profilo_rz[-1][0]
                if r > 1e-9:
                    self.mesh.faccia(anello, mat, normale=(0, 0, -1 if giu else 1))

    # ------------------------------------------------------------ piani forati e vasche
    def _anello_orizzontale(self, est, foro, z, mat, su):
        """Faccia orizzontale tra un rettangolo esterno e un foro rettangolare, in quattro pezzi che condividono gli
        spigoli (nessuna giunzione a T): in SketchUp si fondono in una faccia sola con il foro."""
        x0, y0, x1, y1 = est
        a0, b0, a1, b1 = foro
        n = (0, 0, 1 if su else -1)
        for q in ([(x0, y0), (x1, y0), (x1, b0), (a1, b0), (a0, b0), (x0, b0)],
                  [(x0, b1), (a0, b1), (a1, b1), (x1, b1), (x1, y1), (x0, y1)],
                  [(x0, b0), (a0, b0), (a0, b1), (x0, b1)],
                  [(a1, b0), (x1, b0), (x1, b1), (a1, b1)]):
            self.mesh.faccia([(x, y, z) for x, y in q], mat, normale=n)

    def _fianchi(self, rett, z0, z1, mat, verso_fuori, tagli_x=(), tagli_y=()):
        """Quattro fianchi verticali di un rettangolo, divisi dove arrivano altri spigoli (tagli)."""
        x0, y0, x1, y1 = rett
        xs = sorted({x0, x1, *[t for t in tagli_x if x0 < t < x1]})
        ys = sorted({y0, y1, *[t for t in tagli_y if y0 < t < y1]})
        s = 1.0 if verso_fuori else -1.0
        for i in range(len(xs) - 1):
            self.mesh.faccia([(xs[i], y0, z0), (xs[i + 1], y0, z0), (xs[i + 1], y0, z1), (xs[i], y0, z1)], mat, normale=(0, -s, 0))
            self.mesh.faccia([(xs[i], y1, z0), (xs[i + 1], y1, z0), (xs[i + 1], y1, z1), (xs[i], y1, z1)], mat, normale=(0, s, 0))
        for i in range(len(ys) - 1):
            self.mesh.faccia([(x0, ys[i], z0), (x0, ys[i + 1], z0), (x0, ys[i + 1], z1), (x0, ys[i], z1)], mat, normale=(-s, 0, 0))
            self.mesh.faccia([(x1, ys[i], z0), (x1, ys[i + 1], z0), (x1, ys[i + 1], z1), (x1, ys[i], z1)], mat, normale=(s, 0, 0))

    def piano_forato(self, p0, p1, foro, mat):
        """Lastra orizzontale (top di cucina, mensola) con un foro rettangolare passante (lavello, piano cottura a
        incasso): un solo solido chiuso. `foro` = (x0, y0, x1, y1) dentro il piano."""
        self.mesh.nuovo_pezzo()
        x0, y0, z0 = (min(p0[i], p1[i]) for i in range(3))
        x1, y1, z1 = (max(p0[i], p1[i]) for i in range(3))
        a0, b0, a1, b1 = foro
        if not (x0 < a0 < a1 < x1 and y0 < b0 < b1 < y1):
            raise ValueError("il foro deve stare dentro il piano")
        est = (x0, y0, x1, y1)
        for q in ((x0, y0, a0, y1), (a1, y0, x1, y1), (a0, y0, a1, b0), (a0, b1, a1, y1)):   # il piano attorno al foro
            self._parte([(q[0], q[1], z0), (q[2], q[3], z1)])
        self._anello_orizzontale(est, foro, z1, mat, True)
        self._anello_orizzontale(est, foro, z0, mat, False)
        self._fianchi(est, z0, z1, mat, True, tagli_y=(b0, b1))
        self._fianchi(foro, z0, z1, mat, False)

    def vasca(self, p0, p1, spessore, mat):
        """Vasca aperta in alto (lavello): pareti e fondo di spessore costante, un solo solido chiuso."""
        self.mesh.nuovo_pezzo()
        x0, y0, z0 = (min(p0[i], p1[i]) for i in range(3))
        x1, y1, z1 = (max(p0[i], p1[i]) for i in range(3))
        t = spessore
        est, dentro = (x0, y0, x1, y1), (x0 + t, y0 + t, x1 - t, y1 - t)
        self._parte([(x0, y0, z0), (x1, y1, z0 + t)])                              # fondo e quattro pareti:
        for q in ((x0, y0, x0 + t, y1), (x1 - t, y0, x1, y1), (x0 + t, y0, x1 - t, y0 + t), (x0 + t, y1 - t, x1 - t, y1)):
            self._parte([(q[0], q[1], z0 + t), (q[2], q[3], z1)])                  # il vuoto non sostiene nulla
        self._anello_orizzontale(est, dentro, z1, mat, True)                     # bordo
        self._fianchi(est, z0, z1, mat, True, tagli_y=(dentro[1], dentro[3]))
        self._fianchi(dentro, z0 + t, z1, mat, False)                            # pareti interne
        self.mesh.faccia([(dentro[0], dentro[1], z0 + t), (dentro[2], dentro[1], z0 + t), (dentro[2], dentro[3], z0 + t),
                          (dentro[0], dentro[3], z0 + t)], mat, normale=(0, 0, 1))  # fondo interno
        b0, b1 = dentro[1], dentro[3]               # i fianchi sono divisi qui: anche il fondo esterno
        self.mesh.faccia([(x0, y0, z0), (x1, y0, z0), (x1, b0, z0), (x1, b1, z0), (x1, y1, z0), (x0, y1, z0),
                          (x0, b1, z0), (x0, b0, z0)], mat, normale=(0, 0, -1))

    # ------------------------------------------------------------ imbottiti
    def cuscino(self, centro, semiassi, mat, tondo=(0.5, 0.35), piega=0.0, inclina_gradi=0.0, ruota_gradi=0.0,
                bottoni=(), profondita_bottoni=0.012, seg=(28, 14), mat_bottoni=None):
        """Imbottito: superellissoide liscio (scatola dagli spigoli arrotondati quando `tondo` è piccolo, ellissoide
        con 1). `semiassi` = (larghezza, profondità, altezza) a metà; il davanti guarda verso +y.
        `piega` = raggio (m) con cui il cuscino si curva attorno a un asse verticale davanti a sé (schienali che
        avvolgono); `inclina_gradi` lo inclina all'indietro (la cima va verso -y); `ruota_gradi` lo gira attorno
        alla verticale. `bottoni` = punti (x, z) sul davanti, relativi al centro: trapuntatura capitonné, con la
        stoffa infossata attorno a ogni bottone. Restituisce i centri dei bottoni nel mondo."""
        self.mesh.nuovo_pezzo()
        a, b, c = semiassi
        e1, e2 = tondo
        nu = seg[0]                                  # suddivisioni attorno: ogni faccia del cubo ne ha nu / 3
        cx, cy, cz = centro
        sigma = 0.35 * min(a, c)

        def superficie(d):
            """Punto della superficie nella direzione d (proiezione radiale), con le fossette dei bottoni."""
            x, y, z = d
            fx = (abs(x / a) ** (2 / e2) + abs(y / b) ** (2 / e2)) ** (e2 / e1) + abs(z / c) ** (2 / e1)
            r = fx ** (-e1 / 2)
            x, y, z = x * r, y * r, z * r
            if y > 0:                                  # davanti: la stoffa tira verso i bottoni
                for bx, bz in bottoni:
                    y -= profondita_bottoni * math.exp(-((x - bx) ** 2 + (z - bz) ** 2) / (2 * sigma ** 2)) * (y / b)
            return (x, y, z)

        ci, si = math.cos(math.radians(inclina_gradi)), math.sin(math.radians(inclina_gradi))
        cr, sr = math.cos(math.radians(ruota_gradi)), math.sin(math.radians(ruota_gradi))

        def mondo(p):
            x, y, z = p
            if piega:
                t = x / piega
                x, y = (piega - y) * math.sin(t), piega - (piega - y) * math.cos(t)
            y, z = y * ci - z * si, y * si + z * ci
            x, y = x * cr - y * sr, x * sr + y * cr
            return (cx + x, cy + y, cz + z)

        # cubo suddiviso in modo uniforme e gonfiato fino alla superficie: nessun polo, quindi niente triangoli lunghi
        # e sottili al centro delle facce piatte (la piega a V sulla seduta della prima prova)
        n = max(3, nu // 3)
        locali: list[tuple] = []
        tutti = []
        for asse in range(3):
            for segno in (-1.0, 1.0):
                u_ax, v_ax = (asse + 1) % 3, (asse + 2) % 3

                def cubo(i, j, asse=asse, segno=segno, u_ax=u_ax, v_ax=v_ax):
                    q = [0.0, 0.0, 0.0]
                    q[asse] = segno
                    q[u_ax] = -1.0 + 2.0 * i / n
                    q[v_ax] = -1.0 + 2.0 * j / n
                    return (q[0] * a, q[1] * b, q[2] * c)

                for i in range(n):
                    for j in range(n):
                        q = [superficie(cubo(i, j)), superficie(cubo(i + 1, j)), superficie(cubo(i + 1, j + 1)),
                             superficie(cubo(i, j + 1))]
                        nrm = normale_poligono(q)
                        m = tuple(sum(pp[t] for pp in q) / 4 for t in range(3))
                        if dot(nrm, (m[0] / a ** 2, m[1] / b ** 2, m[2] / c ** 2)) < 0:   # verso l'esterno
                            q.reverse()
                        locali += q
                        pts = [mondo(pp) for pp in q]
                        tutti += pts
                        self.mesh.faccia_idx([self.mesh.vertice(pp, True) for pp in pts], mat, True)
        self._parte(tutti)
        centri = []
        for bx, bz in bottoni:
            vicino = min((pp for pp in locali if pp[1] > 0), key=lambda pp: (pp[0] - bx) ** 2 + (pp[2] - bz) ** 2)
            centri.append(mondo((bx, vicino[1] - 0.004, bz)))
        for p in centri:
            self.sfera_liscia(p, 0.011, mat_bottoni or mat)
        return centri

    def sfera_liscia(self, centro, r, mat, seg=(12, 6)):
        """Sferetta liscia (bottoni, pomoli)."""
        self.cuscino(centro, (r, r, r), mat, tondo=(1.0, 1.0), seg=seg)

    # ------------------------------------------------------------ chiusura
    def chiudi(self, trasf=None, origine_base=True, liscio=False, nome=None, ricalcola_normali=False) -> Oggetto:
        """Trasforma la costruzione in un `Oggetto`. `trasf` = (angolo_rad, cx, cy): rotazione attorno a Z poi
        traslazione. Con `origine_base` l'origine dell'oggetto è il centro della base."""
        mesh = self.mesh
        if ricalcola_normali:       # solo per superfici chiuse e continue (tende): saldatura e normali coerenti
            mesh.salda(1e-6)
            mesh.ricalcola_normali()
        parti = list(self.parti)
        if trasf is not None:
            ang, tx, ty = trasf
            c, s = math.cos(ang), math.sin(ang)

            def f(p):
                return (tx + p[0] * c - p[1] * s, ty + p[0] * s + p[1] * c, p[2])

            mesh.trasforma(f)
            multiplo = abs(ang / (math.pi / 2) - round(ang / (math.pi / 2))) < 1e-9
            parti = [_ruota_parte(q, c, s, tx, ty, multiplo) for q in parti]
        if liscio:
            mesh.liscia = [True] * len(mesh.f)
        (x0, y0, z0), (x1, y1, z1) = mesh.limiti() if mesh.v else ((0, 0, 0), (0, 0, 0))
        centro = ((x0 + x1) / 2, (y0 + y1) / 2, z0) if origine_base else (0.0, 0.0, 0.0)
        if origine_base:
            mesh.trasforma(lambda p: (p[0] - centro[0], p[1] - centro[1], p[2] - centro[2]))
        return Oggetto(nome or self.nome, mesh, centro, self.collezione, self.categoria, self.tipo,
                       parti, self.fondi_complanari)
