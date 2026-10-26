"""Controlli di uso degli arredi rispetto all'architettura: un arredo non deve stare dove si apre una porta né davanti
a una finestra. Sono AVVISI (la geometria non è sbagliata, è l'uso a esserlo) e compaiono nel rapporto GEOMETRIA.

Le porte si registrano con `registra_porta` (cerniera, direzione dell'anta chiusa, verso di apertura, larghezza): l'anta
spazza un quarto di cerchio dal vano chiuso fino a 90 gradi. Le finestre con `registra_finestra`: davanti al vano, per
`PROFONDITA_FINESTRA`, non deve esserci un mobile che arriva sopra il davanzale. Le tende (livello Tessili) sono
escluse: stanno davanti alle finestre per natura.
"""

from __future__ import annotations

import math

PROFONDITA_FINESTRA = 0.25     # m: zona davanti alla finestra che non va coperta
PENETRAZIONE_MIN = 0.01        # m: sotto questa sovrapposizione un arredo "sfiora" l'area e non è un problema
PASSO_ARCO = 10                # tratti dell'arco di apertura di una porta


def registra_porta(scena, id_: str, cerniera, dir_chiusa, normale, larghezza: float, z0: float, z1: float) -> None:
    """`cerniera` = punto (x, y) della cerniera; `dir_chiusa` = direzione (unitaria) dell'anta chiusa; `normale` = verso
    in cui si apre l'anta; `larghezza` = lunghezza dell'anta; `z0`, `z1` = quota del pavimento e della sommità."""
    scena.meta.setdefault("porte", []).append({"id": id_, "cerniera": tuple(cerniera), "chiusa": tuple(dir_chiusa),
                                               "normale": tuple(normale), "larghezza": larghezza, "z0": z0, "z1": z1})


def registra_finestra(scena, id_: str, punto_a, punto_b, normale, z0: float, z1: float) -> None:
    """`punto_a`, `punto_b` = estremi (x, y) del vano sulla faccia verso la stanza; `normale` = verso la stanza."""
    scena.meta.setdefault("vani_finestra", []).append({"id": id_, "a": tuple(punto_a), "b": tuple(punto_b),
                                                       "normale": tuple(normale), "z0": z0, "z1": z1})


# ------------------------------------------------------------------ geometria piana
def _inviluppo(punti):
    """Inviluppo convesso (catena monotona) di punti (x, y), in senso antiorario."""
    p = sorted(set((round(x, 9), round(y, 9)) for x, y in punti))
    if len(p) <= 2:
        return p

    def croce(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    basso: list = []
    for q in p:
        while len(basso) >= 2 and croce(basso[-2], basso[-1], q) <= 0:
            basso.pop()
        basso.append(q)
    alto: list = []
    for q in reversed(p):
        while len(alto) >= 2 and croce(alto[-2], alto[-1], q) <= 0:
            alto.pop()
        alto.append(q)
    return basso[:-1] + alto[:-1]


def _sovrapposizione(a, b) -> float:
    """Profondità di sovrapposizione di due poligoni convessi (asse separatore); 0 se non si toccano."""
    minima = math.inf
    for poli in (a, b):
        for i in range(len(poli)):
            p, q = poli[i], poli[(i + 1) % len(poli)]
            ex, ey = q[0] - p[0], q[1] - p[1]
            n = math.hypot(ex, ey)
            if n < 1e-12:
                continue
            ax, ay = -ey / n, ex / n
            pa = [x * ax + y * ay for x, y in a]
            pb = [x * ax + y * ay for x, y in b]
            sov = min(max(pa), max(pb)) - max(min(pa), min(pb))
            if sov <= 0:
                return 0.0
            minima = min(minima, sov)
    return 0.0 if minima is math.inf else minima


def _settore(c, chiusa, normale, raggio: float):
    pts = [c]
    for k in range(PASSO_ARCO + 1):
        f = (math.pi / 2) * k / PASSO_ARCO
        pts.append((c[0] + raggio * (math.cos(f) * chiusa[0] + math.sin(f) * normale[0]),
                    c[1] + raggio * (math.cos(f) * chiusa[1] + math.sin(f) * normale[1])))
    return pts


def _impronta(parte):
    """(poligono in pianta, z minima, z massima) di una parte (scatola sugli assi o orientata)."""
    if len(parte) > 2:
        c, assi, mezzi = parte[2]
        angoli = [(c[0] + sx * assi[0][0] * mezzi[0] + sy * assi[1][0] * mezzi[1] + sz * assi[2][0] * mezzi[2],
                   c[1] + sx * assi[0][1] * mezzi[0] + sy * assi[1][1] * mezzi[1] + sz * assi[2][1] * mezzi[2],
                   c[2] + sx * assi[0][2] * mezzi[0] + sy * assi[1][2] * mezzi[1] + sz * assi[2][2] * mezzi[2])
                  for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    else:
        a, b = parte[0], parte[1]
        angoli = [(x, y, z) for x in (a[0], b[0]) for y in (a[1], b[1]) for z in (a[2], b[2])]
    return _inviluppo([(p[0], p[1]) for p in angoli]), min(p[2] for p in angoli), max(p[2] for p in angoli)


# ------------------------------------------------------------------ controllo
def controlla(scena) -> list[dict]:
    """AVVISI sull'uso degli arredi: arco di apertura delle porte libero, finestre non coperte."""
    porte, vani = scena.meta.get("porte", []), scena.meta.get("vani_finestra", [])
    if not porte and not vani:
        return []
    arredi = []
    for o in scena.oggetti:
        if o.categoria != "arredo" or o.collezione == "Tessili":
            continue
        for q in o.parti:
            poli, z0, z1 = _impronta(q)
            if len(poli) >= 3:
                arredi.append((o.nome, poli, z0, z1))
    problemi: dict[tuple, dict] = {}
    for p in porte:
        zona = _settore(p["cerniera"], p["chiusa"], p["normale"], p["larghezza"])
        for nome, poli, z0, z1 in arredi:
            if z1 <= p["z0"] + 0.02 or z0 >= p["z1"]:
                continue
            prof = _sovrapposizione(zona, poli)
            if prof > PENETRAZIONE_MIN and (p["id"], nome) not in problemi:
                problemi[(p["id"], nome)] = {
                    "gravita": "AVVISO", "tipo": "porta ostruita", "oggetti": (p["id"], nome), "mm": prof * 1000,
                    "dettaglio": f"{nome} entra nell'arco di apertura della porta {p['id']} "
                                 f"(raggio {p['larghezza']:.2f} m, di {prof * 1000:.0f} mm)"}
    for v in vani:
        a, b, n = v["a"], v["b"], v["normale"]
        d = PROFONDITA_FINESTRA
        zona = _inviluppo([a, b, (b[0] + n[0] * d, b[1] + n[1] * d), (a[0] + n[0] * d, a[1] + n[1] * d)])
        for nome, poli, z0, z1 in arredi:
            if z1 <= v["z0"] or z0 >= v["z1"]:
                continue
            prof = _sovrapposizione(zona, poli)
            if prof > PENETRAZIONE_MIN and (v["id"], nome) not in problemi:
                problemi[(v["id"], nome)] = {
                    "gravita": "AVVISO", "tipo": "finestra coperta", "oggetti": (v["id"], nome), "mm": prof * 1000,
                    "dettaglio": f"{nome} copre la finestra {v['id']} (arriva a {z1:.2f} m davanti al vano)"}
    return sorted(problemi.values(), key=lambda p: (p["tipo"], p["oggetti"]))
