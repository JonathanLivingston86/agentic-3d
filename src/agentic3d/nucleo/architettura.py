"""Architettura senza Blender: pareti con aperture, pavimenti e soffitti.

Una parete è un solido costruito direttamente a facce (niente operazioni booleane): le due facce principali sono
divise in celle lungo una griglia fatta dai bordi delle aperture, le celle dentro un'apertura non esistono, e
le "mazzette" (spalle, architrave, davanzale) chiudono il vano. Le celle si incontrano punto contro punto, quindi la
mesh è senza giunzioni a T. In SketchUp le facce complanari si fondono (`fondi_complanari`).

Il telaio della parete ha l'origine nell'angolo iniziale, `u` lungo la parete, `d` verso l'interno della stanza
(la parete occupa d tra -spessore e 0), `z` alto. Funziona con qualunque orientamento in pianta.
"""

from __future__ import annotations

from .forme import Costruttore, Telaio, parte_obb
from .mesh import Mesh, unitario
from .scena import Oggetto

TOL = 1e-6


def _unici(valori, tol=1e-9):
    out: list[float] = []
    for v in sorted(valori):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def muro(nome: str, m: Telaio, spessore: float, z0: float, z1: float, u_interno: tuple[float, float],
         u_esterno: tuple[float, float] | None = None, aperture: list[dict] | None = None,
         fascia_z: float | None = None, mat_interno="Intonaco pareti", mat_fascia="Fascia pareti verde salvia",
         mat_esterno="Intonaco pareti", fascia_a: bool = True, fascia_b: bool = False) -> Oggetto:
    """Parete piena con aperture rettangolari passanti.

    `u_interno` e `u_esterno` sono gli estremi della faccia verso la stanza e di quella esterna lungo u: se sono
    diversi la parete ha le teste inclinate (angoli a 45 gradi, pareti non ortogonali). Ogni apertura è un
    dizionario con u0, u1, z0, z1 (z fuori dalla parete viene tagliato: una porta parte da terra).
    La faccia a d=0 (`mat_interno`) e quella a d=-spessore (`mat_esterno`) hanno la fascia di colore sotto
    `fascia_z` se `fascia_a` / `fascia_b` sono veri (una parete tra due stanze la vuole su entrambe).
    """
    ui0, ui1 = u_interno
    uo0, uo1 = u_esterno if u_esterno is not None else u_interno
    t = float(spessore)
    ap = []
    for a in aperture or []:
        zlo, zhi = max(a["z0"], z0), min(a["z1"], z1)
        if zhi - zlo < TOL or a["u1"] - a["u0"] < TOL:
            continue
        ap.append((a["u0"], a["u1"], zlo, zhi))
    ap.sort()
    minimo, massimo = max(ui0, uo0), min(ui1, uo1)
    for k, (a, b, zlo, zhi) in enumerate(ap):
        if a < minimo + TOL or b > massimo - TOL:
            raise ValueError(f"{nome}: l'apertura da {a:.3f} a {b:.3f} m arriva al bordo della parete "
                             f"(la parete va da {minimo:.3f} a {massimo:.3f} m): lascia almeno un tratto di muro")
        if k and a < ap[k - 1][1] + TOL:
            raise ValueError(f"{nome}: due aperture si toccano o si sovrappongono")

    rotti = _unici([a for a, b, _, _ in ap] + [b for _, b, _, _ in ap])
    zlist = _unici([z0, z1] + [x for _, _, lo, hi in ap for x in (lo, hi)] + ([fascia_z] if fascia_z and z0 < fascia_z < z1 else []))
    nodi_i = _unici([ui0, ui1] + rotti)
    nodi_e = _unici([uo0, uo1] + rotti)

    def aperto(u, z):
        return any(a < u < b and lo < z < hi for a, b, lo, hi in ap)

    mesh = Mesh()
    dirn = m.direzione
    for nodi, d, normale, lato in ((nodi_i, 0.0, dirn(0, 1, 0), "a"), (nodi_e, -t, dirn(0, -1, 0), "b")):
        for ua, ub in zip(nodi, nodi[1:]):
            for za, zb in zip(zlist, zlist[1:]):
                if aperto((ua + ub) / 2, (za + zb) / 2):
                    continue
                sotto = bool(fascia_z) and zb <= fascia_z + 1e-9
                if lato == "a":
                    mat = mat_fascia if (fascia_a and sotto) else mat_interno
                else:
                    mat = mat_fascia if (fascia_b and sotto) else mat_esterno
                mesh.faccia([m(ua, d, za), m(ub, d, za), m(ub, d, zb), m(ua, d, zb)], mat, normale=normale)
    # testa e piede (cella per cella, con gli stessi nodi delle facce principali)
    ni = [ui0] + [b for b in rotti if ui0 + TOL < b < ui1 - TOL] + [ui1]
    ne = [uo0] + [b for b in rotti if uo0 + TOL < b < uo1 - TOL] + [uo1]
    for k in range(len(ni) - 1):
        mid = (ni[k] + ni[k + 1]) / 2
        quad = [m(ni[k], 0, 0), m(ni[k + 1], 0, 0), m(ne[k + 1], -t, 0), m(ne[k], -t, 0)]
        mesh.faccia([(p[0], p[1], z1) for p in quad], mat_esterno, normale=(0, 0, 1))
        if not any(a < mid < b and lo <= z0 + TOL for a, b, lo, _ in ap):
            mesh.faccia([(p[0], p[1], z0) for p in quad], mat_esterno, normale=(0, 0, -1))
    for u_i, u_e, segno in ((ui0, uo0, -1), (ui1, uo1, 1)):
        for za, zb in zip(zlist, zlist[1:]):
            mesh.faccia([m(u_i, 0, za), m(u_e, -t, za), m(u_e, -t, zb), m(u_i, 0, zb)], mat_esterno,
                        normale=dirn(segno, 0, 0))
    # mazzette delle aperture
    for a, b, lo, hi in ap:
        righe = [z for z in zlist if lo - 1e-9 <= z <= hi + 1e-9]
        for za, zb in zip(righe, righe[1:]):
            mesh.faccia([m(a, -t, za), m(a, 0, za), m(a, 0, zb), m(a, -t, zb)], mat_interno, normale=dirn(1, 0, 0))
            mesh.faccia([m(b, -t, za), m(b, 0, za), m(b, 0, zb), m(b, -t, zb)], mat_interno, normale=dirn(-1, 0, 0))
        if hi < z1 - TOL:
            mesh.faccia([m(a, -t, hi), m(b, -t, hi), m(b, 0, hi), m(a, 0, hi)], mat_interno, normale=(0, 0, -1))
        if lo > z0 + TOL:
            mesh.faccia([m(a, -t, lo), m(b, -t, lo), m(b, 0, lo), m(a, 0, lo)], mat_interno, normale=(0, 0, 1))

    u_min, u_max = min(ui0, uo0), max(ui1, uo1)
    if m.assiale:
        angoli = [m(u, d, z) for u in (u_min, u_max) for d in (0.0, -t) for z in (z0, z1)]
        parti = [((min(p[0] for p in angoli), min(p[1] for p in angoli), z0),
                  (max(p[0] for p in angoli), max(p[1] for p in angoli), z1))]
    else:                      # parete inclinata: scatola orientata lungo la parete
        parti = [parte_obb(m((u_min + u_max) / 2, -t / 2, (z0 + z1) / 2),
                           (unitario(m.direzione(1, 0, 0)), unitario(m.direzione(0, 1, 0)), (0.0, 0.0, 1.0)),
                           ((u_max - u_min) / 2, t / 2, (z1 - z0) / 2))]
    return Oggetto(nome, mesh, (0.0, 0.0, 0.0), "Architettura", "architettura", "muro", parti, True)


def lastra(nome: str, poligono_xy, z0: float, z1: float, tipo: str, mat_alto: str, mat_basso: str,
           mat_lati: str) -> Oggetto:
    """Pavimento o soffitto: poligono in pianta (anche concavo) con spessore. L'origine è al centro della base."""
    c = Costruttore(nome, "Architettura", tipo, fondi_complanari=True)
    c.estrusione(poligono_xy, z0, z1, mat_alto, mat_basso, mat_lati)
    return c.chiudi()
