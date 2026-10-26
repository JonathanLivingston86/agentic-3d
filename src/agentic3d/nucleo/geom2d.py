"""Geometria piana di supporto per pareti e stanze: punti come tuple (x, y), nessuna dipendenza esterna."""

from __future__ import annotations

import math

Punto2 = tuple[float, float]
TOL = 1e-9


def sottrai(a, b):
    return (a[0] - b[0], a[1] - b[1])


def somma(a, b):
    return (a[0] + b[0], a[1] + b[1])


def per(a, k):
    return (a[0] * k, a[1] * k)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def croce(a, b):
    return a[0] * b[1] - a[1] * b[0]


def lunghezza(a):
    return math.hypot(a[0], a[1])


def unitario(a):
    n = lunghezza(a)
    if n < TOL:
        raise ValueError("vettore nullo")
    return (a[0] / n, a[1] / n)


def normale_sinistra(d):
    """Normale a sinistra di una direzione (rotazione di +90 gradi)."""
    return (-d[1], d[0])


def intersezione_rette(p, d1, q, d2) -> Punto2 | None:
    """Punto in cui si incontrano la retta p + t*d1 e la retta q + s*d2; None se sono parallele."""
    den = croce(d1, d2)
    if abs(den) < 1e-12:
        return None
    t = croce(sottrai(q, p), d2) / den
    return (p[0] + t * d1[0], p[1] + t * d1[1])


def area_con_segno(poligono) -> float:
    n = len(poligono)
    return sum(poligono[i][0] * poligono[(i + 1) % n][1] - poligono[(i + 1) % n][0] * poligono[i][1]
               for i in range(n)) / 2.0


def area(poligono) -> float:
    return abs(area_con_segno(poligono))


def antiorario(poligono) -> list[Punto2]:
    return list(poligono) if area_con_segno(poligono) >= 0 else list(reversed(poligono))


def punto_in_poligono(p, poligono) -> bool:
    """Test del raggio (punti sul bordo: indefinito)."""
    x, y = p
    dentro = False
    n = len(poligono)
    for i in range(n):
        x1, y1 = poligono[i]
        x2, y2 = poligono[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            dentro = not dentro
    return dentro


def baricentro(poligono) -> Punto2:
    """Baricentro dell'area (non la media dei vertici)."""
    a = area_con_segno(poligono)
    n = len(poligono)
    if abs(a) < TOL:
        return (sum(p[0] for p in poligono) / n, sum(p[1] for p in poligono) / n)
    cx = cy = 0.0
    for i in range(n):
        x1, y1 = poligono[i]
        x2, y2 = poligono[(i + 1) % n]
        c = x1 * y2 - x2 * y1
        cx += (x1 + x2) * c
        cy += (y1 + y2) * c
    return (cx / (6 * a), cy / (6 * a))


def distanza_punto_segmento(p, a, b) -> float:
    ab = sottrai(b, a)
    l2 = dot(ab, ab)
    t = 0.0 if l2 < TOL else max(0.0, min(1.0, dot(sottrai(p, a), ab) / l2))
    q = (a[0] + t * ab[0], a[1] + t * ab[1])
    return lunghezza(sottrai(p, q))


def arco_in_segmenti(centro, raggio, da_gradi, a_gradi, passo_gradi=7.5) -> list[Punto2]:
    """Punti lungo un arco di circonferenza, dall'angolo `da` all'angolo `a` (gradi, antiorario se a > da)."""
    n = max(2, int(math.ceil(abs(a_gradi - da_gradi) / passo_gradi)))
    return [(centro[0] + raggio * math.cos(math.radians(da_gradi + (a_gradi - da_gradi) * i / n)),
             centro[1] + raggio * math.sin(math.radians(da_gradi + (a_gradi - da_gradi) * i / n))) for i in range(n + 1)]


class IndiceCelle:
    """Indice spaziale a celle: trova in fretta gli oggetti (indici interi) vicini a un punto, anche in edifici con
    migliaia di pareti. Ogni oggetto entra con la sua scatola di ingombro."""

    def __init__(self, cella: float = 3.0):
        self.cella = cella
        self.celle: dict[tuple[int, int], list[int]] = {}

    def aggiungi(self, k: int, xmin: float, ymin: float, xmax: float, ymax: float, margine: float = 0.0) -> None:
        c = self.cella
        for ix in range(int((xmin - margine) // c), int((xmax + margine) // c) + 1):
            for iy in range(int((ymin - margine) // c), int((ymax + margine) // c) + 1):
                self.celle.setdefault((ix, iy), []).append(k)

    def vicini(self, p, raggio: float = 0.0) -> set[int]:
        c = self.cella
        out: set[int] = set()
        for ix in range(int((p[0] - raggio) // c), int((p[0] + raggio) // c) + 1):
            for iy in range(int((p[1] - raggio) // c), int((p[1] + raggio) // c) + 1):
                out.update(self.celle.get((ix, iy), ()))
        return out
