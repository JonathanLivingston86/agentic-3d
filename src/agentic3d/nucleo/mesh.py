"""Mesh pura: vertici, facce poligonali, materiali per faccia. Nessuna dipendenza da Blender né da altre librerie.

Un punto è una tupla (x, y, z) in metri; sistema di riferimento: X est, Y nord, Z alto. Le facce guardano
verso l'esterno del solido con i vertici in senso antiorario (regola della mano destra).
"""

from __future__ import annotations

import math

Punto = tuple[float, float, float]
EPS = 1e-12


# ------------------------------------------------------------------ vettori su tuple
def somma(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def diff(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def per(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def lunghezza(a):
    return math.sqrt(dot(a, a))


def unitario(a):
    n = lunghezza(a)
    return (0.0, 0.0, 0.0) if n < EPS else (a[0] / n, a[1] / n, a[2] / n)


def normale_poligono(punti) -> Punto:
    """Normale non normalizzata di un poligono (metodo di Newell); la sua lunghezza è il doppio dell'area."""
    nx = ny = nz = 0.0
    n = len(punti)
    for i in range(n):
        x1, y1, z1 = punti[i]
        x2, y2, z2 = punti[(i + 1) % n]
        nx += (y1 - y2) * (z1 + z2)
        ny += (z1 - z2) * (x1 + x2)
        nz += (x1 - x2) * (y1 + y2)
    return (nx, ny, nz)


# ------------------------------------------------------------------ triangolazione
def triangola_poligono(punti) -> list[tuple[int, int, int]]:
    """Triangola un poligono semplice (anche concavo) con il metodo delle orecchie. Restituisce terne di indici
    che mantengono il verso del poligono. Per poligoni degeneri ricade su un ventaglio."""
    n = len(punti)
    if n < 3:
        return []
    if n == 3:
        return [(0, 1, 2)]
    nv = normale_poligono(punti)
    asse = max(range(3), key=lambda i: abs(nv[i]))
    a, b = (asse + 1) % 3, (asse + 2) % 3        # ordine ciclico: antiorario 2D = normale positiva
    flip = nv[asse] < 0
    p2 = [(p[a], p[b]) for p in punti]
    if flip:
        p2 = [(x, -y) for x, y in p2]

    def area2(i, j, k):
        return (p2[j][0] - p2[i][0]) * (p2[k][1] - p2[i][1]) - (p2[j][1] - p2[i][1]) * (p2[k][0] - p2[i][0])

    def dentro(p, i, j, k):
        d1 = area2(i, j, p)
        d2 = area2(j, k, p)
        d3 = area2(k, i, p)
        return d1 >= -1e-14 and d2 >= -1e-14 and d3 >= -1e-14

    resto = list(range(n))
    out = []
    guardia = 0
    while len(resto) > 3 and guardia < 10 * n * n:
        guardia += 1
        trovato = False
        m = len(resto)
        for pos in range(m):
            i, j, k = resto[pos - 1], resto[pos], resto[(pos + 1) % m]
            if area2(i, j, k) <= 1e-14:        # angolo piatto o concavo
                continue
            if any(dentro(q, i, j, k) for q in resto if q not in (i, j, k)
                   and p2[q] not in (p2[i], p2[j], p2[k])):
                continue
            out.append((i, j, k))
            resto.pop(pos)
            trovato = True
            break
        if not trovato:
            break
    if len(resto) == 3:
        out.append((resto[0], resto[1], resto[2]))
    elif len(resto) > 3:                         # degenere: ventaglio
        out += [(resto[0], resto[t], resto[t + 1]) for t in range(1, len(resto) - 1)]
    return out


# ------------------------------------------------------------------ mesh
class Mesh:
    """Vertici + facce poligonali (indici), con materiale e flag di ombreggiatura liscia per faccia."""

    def __init__(self):
        self.v: list[Punto] = []
        self.f: list[tuple[int, ...]] = []
        self.mat: list[int] = []
        self.liscia: list[bool] = []
        self.materiali: list[str] = []
        self.pezzo: list[int] = []         # solido di appartenenza di ogni faccia (scatola, cilindro, cuscino...)
        self._pezzo = 0
        self._chiavi: dict[tuple, int] = {}
        # solidi di rivoluzione (cilindri, aste, torniti): pezzo -> angolo tra due facce vicine attorno all'asse
        # (360 / segmenti), per ammorbidire le linee laterali qualunque sia il numero di segmenti
        self.rivoluzione: dict[int, float] = {}

    def segna_rivoluzione(self, segmenti: int) -> None:
        """Il pezzo corrente è un solido di rivoluzione con `segmenti` facce attorno all'asse."""
        self.rivoluzione[self._pezzo] = 360.0 / segmenti

    def nuovo_pezzo(self) -> int:
        """Le facce aggiunte da qui in poi formano un solido a sé: in SketchUp va in un gruppo diverso da quelli che
        tocca, altrimenti le facce a contatto si fondono (geometria "appiccicosa")."""
        if self.pezzo and self.pezzo[-1] == self._pezzo:
            self._pezzo += 1
        return self._pezzo

    # -- costruzione
    def idx_mat(self, nome: str) -> int:
        if nome not in self.materiali:
            self.materiali.append(nome)
        return self.materiali.index(nome)

    def vertice(self, p, condiviso: bool = False) -> int:
        p = (float(p[0]), float(p[1]), float(p[2]))
        if condiviso:
            k = (round(p[0], 9), round(p[1], 9), round(p[2], 9))
            if k in self._chiavi:
                return self._chiavi[k]
            self._chiavi[k] = len(self.v)
        self.v.append(p)
        return len(self.v) - 1

    def faccia_idx(self, indici, mat: str, liscia: bool = False) -> int:
        self.f.append(tuple(indici))
        self.mat.append(self.idx_mat(mat))
        self.liscia.append(liscia)
        self.pezzo.append(self._pezzo)
        return len(self.f) - 1

    def faccia(self, punti, mat: str, liscia: bool = False, normale=None) -> int:
        """Aggiunge una faccia con vertici propri. Se `normale` è data e la faccia guarda dall'altra parte,
        inverte il verso: così chi costruisce non deve contare i vertici in senso antiorario."""
        punti = [(float(p[0]), float(p[1]), float(p[2])) for p in punti]
        if normale is not None and dot(normale_poligono(punti), normale) < 0:
            punti.reverse()
        return self.faccia_idx([self.vertice(p) for p in punti], mat, liscia)

    def faccia_condivisa(self, punti, mat: str, liscia: bool = False, normale=None) -> int:
        punti = [(float(p[0]), float(p[1]), float(p[2])) for p in punti]
        if normale is not None and dot(normale_poligono(punti), normale) < 0:
            punti.reverse()
        return self.faccia_idx([self.vertice(p, True) for p in punti], mat, liscia)

    def aggiungi(self, altra: "Mesh", tutta_liscia: bool | None = None):
        """Accoda un'altra mesh (con i suoi materiali)."""
        base = len(self.v)
        base_pezzo = (max(self.pezzo) + 1) if self.pezzo else 0
        self.v += altra.v
        for fi, mi, li, pz in zip(altra.f, altra.mat, altra.liscia, altra.pezzo):
            self.f.append(tuple(i + base for i in fi))
            self.mat.append(self.idx_mat(altra.materiali[mi]))
            self.liscia.append(li if tutta_liscia is None else tutta_liscia)
            self.pezzo.append(base_pezzo + pz)
        for pz, angolo in altra.rivoluzione.items():
            self.rivoluzione[base_pezzo + pz] = angolo
        self._pezzo = (max(self.pezzo) + 1) if self.pezzo else 0

    # -- trasformazioni
    def trasforma(self, fn):
        self.v = [fn(p) for p in self.v]
        self._chiavi = {}

    def salda(self, tol: float = 1e-6):
        """Unisce i vertici più vicini di `tol` e toglie le facce degeneri (come `remove_doubles`)."""
        celle: dict[tuple, int] = {}
        nuovi: list[Punto] = []
        mappa: list[int] = []
        for p in self.v:
            k = (round(p[0] / tol), round(p[1] / tol), round(p[2] / tol))
            if k not in celle:
                celle[k] = len(nuovi)
                nuovi.append(p)
            mappa.append(celle[k])
        self.v = nuovi
        f2, m2, l2, p2 = [], [], [], []
        for fi, mi, li, pz in zip(self.f, self.mat, self.liscia, self.pezzo):
            ids = []
            for i in fi:
                j = mappa[i]
                if not ids or ids[-1] != j:
                    ids.append(j)
            if len(ids) > 1 and ids[0] == ids[-1]:
                ids.pop()
            if len(set(ids)) >= 3:
                f2.append(tuple(ids))
                m2.append(mi)
                l2.append(li)
                p2.append(pz)
        self.f, self.mat, self.liscia, self.pezzo = f2, m2, l2, p2
        self._chiavi = {}

    def ricalcola_normali(self):
        """Rende coerente il verso delle facce e le fa guardare all'esterno (superfici chiuse e continue)."""
        n = len(self.f)
        spigoli: dict[tuple[int, int], list[int]] = {}
        for k, fi in enumerate(self.f):
            for a in range(len(fi)):
                i, j = fi[a], fi[(a + 1) % len(fi)]
                spigoli.setdefault((min(i, j), max(i, j)), []).append(k)
        visto = [False] * n
        for inizio in range(n):
            if visto[inizio]:
                continue
            comp = [inizio]
            visto[inizio] = True
            pila = [inizio]
            orient = {inizio: False}      # True = da invertire
            while pila:
                k = pila.pop()
                fi = self.f[k]
                for a in range(len(fi)):
                    i, j = fi[a], fi[(a + 1) % len(fi)]
                    vicini = [q for q in spigoli[(min(i, j), max(i, j))] if q != k]
                    if len(vicini) != 1:      # spigolo libero o non-manifold: non propaga
                        continue
                    q = vicini[0]
                    if visto[q]:
                        continue
                    fq = self.f[q]
                    stesso_verso = any(fq[b] == i and fq[(b + 1) % len(fq)] == j for b in range(len(fq)))
                    # nell'orientamento coerente le facce adiacenti percorrono lo spigolo in versi opposti
                    effettivo_k = orient[k]
                    percorre_k = (i, j) if not effettivo_k else (j, i)
                    percorre_q = (i, j) if stesso_verso else (j, i)
                    orient[q] = (percorre_q == percorre_k)
                    visto[q] = True
                    comp.append(q)
                    pila.append(q)
            for k in comp:
                if orient[k]:
                    self.f[k] = tuple(reversed(self.f[k]))
            if self._volume_componente(comp) < 0:
                for k in comp:
                    self.f[k] = tuple(reversed(self.f[k]))

    def _volume_componente(self, facce) -> float:
        vol = 0.0
        for k in facce:
            fi = self.f[k]
            p0 = self.v[fi[0]]
            for t in range(1, len(fi) - 1):
                vol += dot(p0, cross(self.v[fi[t]], self.v[fi[t + 1]])) / 6.0
        return vol

    # -- misure
    def limiti(self):
        xs = [p[0] for p in self.v]
        ys = [p[1] for p in self.v]
        zs = [p[2] for p in self.v]
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

    def area_per_materiale(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for fi, mi in zip(self.f, self.mat):
            a = lunghezza(normale_poligono([self.v[i] for i in fi])) / 2.0
            nome = self.materiali[mi]
            out[nome] = out.get(nome, 0.0) + a
        return out

    def area(self) -> float:
        return sum(self.area_per_materiale().values())

    def volume(self) -> float:
        """Volume con segno (formula della divergenza): per una mesh chiusa e orientata bene è il volume vero."""
        return self._volume_componente(range(len(self.f)))

    def triangoli(self):
        """Per ogni faccia: (indice faccia, terne di indici di vertice)."""
        for k, fi in enumerate(self.f):
            if len(fi) == 3:
                yield k, [tuple(fi)]
            elif len(fi) == 4:
                yield k, [(fi[0], fi[1], fi[2]), (fi[0], fi[2], fi[3])]
            else:
                tri = triangola_poligono([self.v[i] for i in fi])
                yield k, [(fi[a], fi[b], fi[c]) for a, b, c in tri]

    def normali_facce(self):
        return [unitario(normale_poligono([self.v[i] for i in fi])) for fi in self.f]

    def normali_angolo(self):
        """Normali per vertice delle facce lisce (media pesata sull'angolo, come fa Blender), per faccia e vertice."""
        nf = self.normali_facce()
        acc: dict[int, list[float]] = {}
        for k, fi in enumerate(self.f):
            if not self.liscia[k]:
                continue
            m = len(fi)
            for a in range(m):
                p = self.v[fi[a]]
                e1 = unitario(diff(self.v[fi[(a + 1) % m]], p))
                e2 = unitario(diff(self.v[fi[a - 1]], p))
                ang = math.acos(max(-1.0, min(1.0, dot(e1, e2))))
                s = acc.setdefault(fi[a], [0.0, 0.0, 0.0])
                s[0] += nf[k][0] * ang
                s[1] += nf[k][1] * ang
                s[2] += nf[k][2] * ang
        return nf, {i: unitario(tuple(s)) for i, s in acc.items()}

    def bordi_complanari(self, tol: float = 1e-9):
        """Coppie di vertici (spigoli) tra due facce complanari dello stesso materiale: in SketchUp si possono
        cancellare per ottenere una faccia sola. Usa la saldatura per posizione, senza cambiare la mesh."""
        chiave = {}
        ids = []
        for p in self.v:
            k = (round(p[0], 7), round(p[1], 7), round(p[2], 7))
            ids.append(chiave.setdefault(k, len(chiave)))
        nf = self.normali_facce()
        spigoli: dict[tuple[int, int], list[int]] = {}
        for k, fi in enumerate(self.f):
            for a in range(len(fi)):
                i, j = ids[fi[a]], ids[fi[(a + 1) % len(fi)]]
                if i != j:
                    spigoli.setdefault((min(i, j), max(i, j)), []).append(k)
        out = []
        for (i, j), facce in spigoli.items():
            if len(facce) == 2:
                a, b = facce
                if self.mat[a] == self.mat[b] and not (self.liscia[a] or self.liscia[b]) \
                        and lunghezza(diff(nf[a], nf[b])) < 1e-7:
                    out.append((i, j))
        return out, ids
