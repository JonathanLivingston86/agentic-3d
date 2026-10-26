"""Serramenti senza Blender: finestra (telaio, ante, vetro, davanzale) e porta (mostre, anta chiusa, maniglie).

Stesse misure e stessi materiali del costruttore per Blender; funzionano con il telaio di qualunque parete.
"""

from __future__ import annotations

import math

from .forme import Costruttore, Telaio
from .scena import Oggetto


def finestra(ap: dict, m: Telaio, spess: float) -> Oggetto:
    u0, u1 = ap["da_m"], ap["da_m"] + ap["larghezza_m"]
    q, h = ap["quota_davanzale_m"], ap["altezza_m"]
    z0, z1 = q, q + h
    porta_finestra = ap.get("tipo") == "portafinestra"
    p = Costruttore(ap.get("id", "Finestra"), "Architettura", "portafinestra" if porta_finestra else "finestra")
    prof, prof_d = 0.06, 0.08
    d_stanza = -(spess * 0.5 - prof_d / 2)      # faccia del telaio verso la stanza
    d_fondo = d_stanza - prof_d
    # telaio fisso, dentro lo spessore del muro
    for a, b in (((u0, z0), (u1, z0 + prof)), ((u0, z1 - prof), (u1, z1)),
                 ((u0, z0 + prof), (u0 + prof, z1 - prof)), ((u1 - prof, z0 + prof), (u1, z1 - prof))):
        p.box_p(m, a[0], d_fondo, a[1], b[0], d_stanza, b[1], "Telaio bianco")
    n = max(ap.get("ante", 2), 1)
    anta = (u1 - u0 - 2 * prof) / n
    for i in range(n):
        a0 = u0 + prof + i * anta
        a1 = a0 + anta
        pr = 0.045
        dd0, dd1 = d_stanza + 0.002, d_stanza + 0.04
        zz0, zz1 = z0 + prof, z1 - prof
        g = 0.0005   # piccolo distacco tra ante vicine
        for a, b in (((a0 + g, zz0 + 0.001), (a1 - g, zz0 + pr)), ((a0 + g, zz1 - pr), (a1 - g, zz1 - 0.001)),
                     ((a0 + g, zz0 + pr), (a0 + pr, zz1 - pr)), ((a1 - pr, zz0 + pr), (a1 - g, zz1 - pr))):
            p.box_p(m, a[0], dd0, a[1], b[0], dd1, b[1], "Telaio bianco")
        p.box_p(m, a0 + pr, d_stanza + 0.015, zz0 + pr, a1 - pr, d_stanza + 0.023, zz1 - pr, "Vetro")
    if porta_finestra:                      # a pavimento: nessun davanzale interno, il traverso basso fa da soglia
        return p.chiudi()
    # davanzale interno: sporge di 3 cm dal filo del muro
    p.box_p(m, u0 - 0.04, -spess * 0.5, z0 - 0.03, u1 + 0.04, 0.03, z0 + 0.001, "Laccato bianco")   # 1 mm sopra il vano: niente facce complanari
    return p.chiudi()


def cerniera_a_u1(ap: dict) -> bool:
    """Vero se la cerniera sta dal lato di u crescente (est, nord, fine)."""
    return ap.get("cerniera", "est") in ("est", "nord", "fine")


def porta(ap: dict, m: Telaio, spess: float) -> Oggetto:
    """Porta: mostre (architravi) su tutte e due le facce del muro, anta chiusa a metà spessore, maniglia con rosetta
    su tutte e due le facce, dalla parte opposta alla cerniera, con la leva rivolta verso la cerniera."""
    u0, u1 = ap["da_m"], ap["da_m"] + ap["larghezza_m"]
    h = ap["altezza_m"]
    p = Costruttore(ap.get("id", "Porta"), "Architettura", "porta")
    arch, arch_d = 0.09, 0.014
    for (da, db) in ((0.0, arch_d), (-spess - arch_d, -spess)):        # faccia verso la stanza e faccia opposta
        for a, b in (((u0 - arch, 0.0), (u0, h + arch)), ((u1, 0.0), (u1 + arch, h + arch)), ((u0, h), (u1, h + arch))):
            p.box_p(m, a[0], da, a[1], b[0], db, b[1], "Porta laccata")
    # anta chiusa dentro il vano, a metà dello spessore del muro
    f0, f1 = -(spess * 0.5 + 0.02), -(spess * 0.5 - 0.02)
    p.box_p(m, u0 + 0.004, f0, 0.0, u1 - 0.004, f1, h - 0.004, "Porta laccata")
    # maniglia sul lato opposto alla cerniera, a sinistra o a destra dell'anta; la leva punta verso la cerniera
    quota_m = ap.get("altezza_maniglia_m", 0.90)
    a_u1 = cerniera_a_u1(ap)
    um = u0 + 0.07 if a_u1 else u1 - 0.07
    verso = 1.0 if a_u1 else -1.0
    cerchio = [(um + 0.027 * math.cos(2 * math.pi * i / 12), quota_m + 0.027 * math.sin(2 * math.pi * i / 12))
               for i in range(12)]
    for faccia, s in ((f1, 1.0), (f0, -1.0)):
        p.prisma(m, cerchio, min(faccia, faccia + s * 0.012), max(faccia, faccia + s * 0.012), "Maniglia")                       # rosetta
        p.box_p(m, um - 0.011, faccia + s * 0.012, quota_m - 0.011, um + 0.011, faccia + s * 0.040, quota_m + 0.011,
                "Maniglia")                                                                # collo
        a, b = (um - 0.011, um + 0.115) if verso > 0 else (um - 0.115, um + 0.011)
        p.box_p(m, a, faccia + s * 0.028, quota_m - 0.010, b, faccia + s * 0.048, quota_m + 0.010, "Maniglia")   # leva
    return p.chiudi()


def porta_scorrevole(ap: dict, m: Telaio, spess: float) -> Oggetto:
    """Ante scorrevoli nel vano (armadi a muro, `apertura: scorrevole`): due binari a metà del muro, ante che si
    sovrappongono di 3 cm, maniglia a incasso verticale sul bordo esterno di ogni anta, dal lato della stanza. Niente
    mostre: l'anta è a filo del vano e non c'è arco di apertura."""
    u0, u1 = ap["da_m"], ap["da_m"] + ap["larghezza_m"]
    h = ap["altezza_m"]
    p = Costruttore(ap.get("id", "Porta"), "Architettura", "porta")
    n = max(int(ap.get("ante", 2)), 1)
    sov, sp = 0.03, 0.02
    luce = (u1 - u0) - 0.008
    larg = (luce + sov * (n - 1)) / n
    meta = -spess * 0.5
    for i in range(n):
        a0 = u0 + 0.004 + i * (larg - sov)
        a1 = a0 + larg
        verso_stanza = i % 2 == 0                         # binari alternati: le ante vicine non si toccano
        d0 = meta + 0.005 if verso_stanza else meta - 0.005 - sp
        p.box_p(m, a0, d0, 0.0, a1, d0 + sp, h - 0.004, "Porta laccata")
        um = a0 + 0.04 if i == 0 else a1 - 0.04 if i == n - 1 else (a0 + a1) / 2
        p.box_p(m, um - 0.006, d0 + sp, 0.85, um + 0.006, d0 + sp + 0.008, 1.15, "Maniglia")
    return p.chiudi()


def serramento(ap: dict, m: Telaio, spess: float) -> Oggetto:
    if ap["tipo"] in ("finestra", "portafinestra"):
        return finestra(ap, m, spess)
    if ap["tipo"] == "porta" and ap.get("apertura") == "scorrevole":
        return porta_scorrevole(ap, m, spess)
    if ap["tipo"] == "porta":
        return porta(ap, m, spess)
    raise ValueError(f"tipo di apertura sconosciuto: {ap['tipo']}")
