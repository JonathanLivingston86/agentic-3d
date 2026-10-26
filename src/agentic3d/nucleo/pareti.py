"""Rete di pareti: dalle linee d'asse con spessore ai solidi con giunti puliti.

Ogni parete è un segmento (asse da p0 a p1) con uno spessore. Il risolutore:
  1. espande le pareti curve (`tipo: arco`) in catene di segmenti;
  2. spezza le pareti dove un'altra parete ci si appoggia (nodi a T);
  3. in ogni nodo ordina le pareti per angolo e taglia le teste con i giunti: angoli (anche non retti), prolungamenti,
     T e incroci a più pareti, senza sovrapposizioni;
  4. restituisce per ogni pezzo le estensioni delle sue due facce (sinistra e destra rispetto al verso p0 -> p1).

Telaio di una parete: origine sulla faccia sinistra all'inizio dell'asse, u lungo l'asse, d verso sinistra: la
parete occupa d tra -spessore e 0. Una stanza a sinistra ha d positivo (come nelle stanze rettangolari).

La linea `da` -> `a` è di solito l'asse del muro (`linea: asse`). Con `linea: filo_sinistro` è la faccia sinistra
(il muro sta tutto a destra della linea), con `linea: filo_destro` la faccia destra. Serve ai muri di facciata: si
disegna la faccia esterna, dritta, e lo spessore cresce verso l'interno; pezzi con spessori diversi sulla stessa
linea danno risalti solo dentro. I nodi si trovano sempre sulla linea disegnata.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import geom2d as g
from .forme import Telaio

MM = 1e-3
LIMITE_SPIGOLO = 4.0       # un giunto che si allontana dal nodo di più di 4 spessori viene smussato


@dataclass
class Pezzo:
    id: str                       # nome del pezzo (uguale all'id della parete se non è spezzata)
    origine_id: str               # id della parete indicata nella scheda
    u_inizio: float               # distanza dell'inizio del pezzo dall'inizio della parete originale
    p0: tuple[float, float]
    p1: tuple[float, float]
    spessore: float
    curva: bool = False
    ui: tuple[float, float] = (0.0, 0.0)      # estremi della faccia sinistra (d = 0)
    uo: tuple[float, float] = (0.0, 0.0)      # estremi della faccia destra (d = -spessore)
    extra: dict = field(default_factory=dict)
    hs: float | None = None                   # distanza della faccia sinistra dalla linea (predefinito: metà spessore)
    hd: float | None = None                   # distanza della faccia destra dalla linea

    def __post_init__(self):
        if self.hs is None and self.hd is None:
            self.hs = self.hd = self.spessore / 2.0
        elif self.hs is None:
            self.hs = self.spessore - self.hd
        elif self.hd is None:
            self.hd = self.spessore - self.hs

    def mezzo(self, lato: str) -> float:
        """Distanza della faccia (sinistra o destra) dalla linea del muro."""
        return self.hs if lato == "sinistra" else self.hd

    @property
    def lunghezza(self) -> float:
        return g.lunghezza(g.sottrai(self.p1, self.p0))

    @property
    def eu(self):
        return g.unitario(g.sottrai(self.p1, self.p0))

    @property
    def en(self):
        return g.normale_sinistra(self.eu)

    def telaio(self, lato: str = "sinistra") -> Telaio:
        """Telaio della faccia da cui guarda la stanza: d = 0 sulla faccia, d positivo verso la stanza."""
        eu, en = self.eu, self.en
        if lato == "sinistra":
            return Telaio(g.somma(self.p0, g.per(en, self.hs)), eu, en)
        if lato == "destra":
            return Telaio(g.sottrai(self.p0, g.per(en, self.hd)), eu, g.per(en, -1.0))
        raise ValueError(f"lato sconosciuto: {lato!r} (sinistra o destra)")

    def telaio_solido(self) -> Telaio:
        return self.telaio("sinistra")

    def punto_faccia(self, u: float, lato: str):
        """Punto della faccia (sinistra o destra) alla posizione u lungo l'asse."""
        h = self.hs if lato == "sinistra" else -self.hd
        return g.somma(g.somma(self.p0, g.per(self.eu, u)), g.per(self.en, h))


def _chiave(p):
    return (round(p[0] / MM), round(p[1] / MM))


class Rete(list):
    """Elenco di pezzi con un indice spaziale per cercare le pareti vicine a un punto."""

    def __init__(self, pezzi):
        super().__init__(pezzi)
        self._indice = g.IndiceCelle(3.0)
        for k, w in enumerate(self):
            xs, ys = (w.p0[0], w.p1[0]), (w.p0[1], w.p1[1])
            self._indice.aggiungi(k, min(xs), min(ys), max(xs), max(ys), w.spessore + 0.05)

    def vicine(self, p, raggio: float = 0.0):
        return [self[k] for k in sorted(self._indice.vicini(p, raggio))]


def espandi(specifiche: list[dict]) -> list[Pezzo]:
    """Da specifiche della scheda a pezzi rettilinei (archi in catene di segmenti)."""
    out: list[Pezzo] = []
    visti = set()
    for s in specifiche:
        pid = str(s["id"])
        if pid in visti:
            raise ValueError(f"id di parete duplicato: {pid!r}")
        visti.add(pid)
        t = float(s["spessore_m"])
        if t <= 0:
            raise ValueError(f"parete {pid}: spessore non valido")
        linea = s.get("linea", "asse")
        if linea not in ("asse", "filo_sinistro", "filo_destro"):
            raise ValueError(f"parete {pid}: linea sconosciuta {linea!r} (asse, filo_sinistro, filo_destro)")
        hs = {"asse": t / 2.0, "filo_sinistro": 0.0, "filo_destro": t}[linea]
        if s.get("tipo") == "arco":
            punti = g.arco_in_segmenti(s["centro"], float(s["raggio_m"]), float(s["da_gradi"]), float(s["a_gradi"]),
                                       float(s.get("passo_gradi", 7.5)))
            u = 0.0
            for k in range(len(punti) - 1):
                a, b = punti[k], punti[k + 1]
                out.append(Pezzo(f"{pid}.{k + 1}", pid, u, a, b, t, curva=True, hs=hs, hd=t - hs))
                u += g.lunghezza(g.sottrai(b, a))
        else:
            a, b = tuple(map(float, s["da"])), tuple(map(float, s["a"]))
            if g.lunghezza(g.sottrai(b, a)) < 0.05:
                raise ValueError(f"parete {pid}: lunga meno di 5 cm")
            out.append(Pezzo(pid, pid, 0.0, a, b, t, hs=hs, hd=t - hs))
    return out


def spezza_ai_nodi(pezzi: list[Pezzo]) -> list[Pezzo]:
    """Dove l'estremo di una parete cade dentro un'altra, quest'ultima si divide in due pezzi (nodo a T)."""
    rete = Rete(pezzi)
    tagli: dict[int, list[float]] = {}
    for altro in pezzi:
        for p in (altro.p0, altro.p1):
            for w in rete.vicine(p, 0.01):
                if w is altro:
                    continue
                if g.distanza_punto_segmento(p, w.p0, w.p1) < 2 * MM:
                    u = g.dot(g.sottrai(p, w.p0), w.eu)
                    if 1e-2 < u < w.lunghezza - 1e-2:
                        tagli.setdefault(id(w), []).append(u)
    risultato: list[Pezzo] = []
    for w in pezzi:
        ts = sorted(set(round(u, 4) for u in tagli.get(id(w), [])))
        if not ts:
            risultato.append(w)
            continue
        estremi = [0.0] + ts + [w.lunghezza]
        for k in range(len(estremi) - 1):
            a = g.somma(w.p0, g.per(w.eu, estremi[k]))
            b = g.somma(w.p0, g.per(w.eu, estremi[k + 1]))
            nome = w.id if k == 0 else f"{w.id}.{k + 1}"
            risultato.append(Pezzo(nome, w.origine_id, w.u_inizio + estremi[k], a, b, w.spessore, w.curva, hs=w.hs, hd=w.hd))
    nomi = [p.id for p in risultato]
    if len(set(nomi)) != len(nomi):
        raise ValueError("nomi di pezzi di parete duplicati dopo la divisione (cambia gli id delle pareti)")
    return risultato


def _sposta_il_cambio_di_spessore(nodo, va, vb, appoggiate, angoli) -> None:
    """Parete continua che cambia spessore proprio dove arriva un tramezzo: il cambio cade sulla faccia del tramezzo
    dal lato del pezzo più sottile, non sul suo asse. Altrimenti tra la testa del tramezzo (che arriva alla faccia
    più profonda) e il pezzo sottile resta un vuoto largo metà tramezzo (errore visto in prova
    in un appartamento reale: rientranza quadrata nell'angolo)."""
    scelte = []
    for lato in (1.0, -1.0):
        sul_lato = [v for v in appoggiate if g.dot(v["d"], va["n"]) * lato > 0]
        h_a = va["hl"] if lato > 0 else va["hr"]
        h_b = vb["hr"] if lato > 0 else vb["hl"]
        if not sul_lato or abs(h_a - h_b) < 1e-6:
            continue
        sottile = va if h_a < h_b else vb
        # faccia di ogni tramezzo rivolta verso il pezzo sottile
        e = max(v["hl"] if g.dot(sottile["d"], v["n"]) > 0 else v["hr"] for v in sul_lato)
        scelte.append((sottile, e))
    if not scelte or any(s[0] is not scelte[0][0] for s in scelte):
        return                                   # nessun cambio, o cambi opposti sui due lati: si lascia sull'asse
    sottile, e = scelte[0][0], max(s[1] for s in scelte)
    c = g.somma(nodo, g.per(sottile["d"], e))
    for v in (va, vb):
        angoli[id(v)] = [g.somma(c, g.per(v["n"], v["hl"])), g.sottrai(c, g.per(v["n"], v["hr"]))]


RAPPORTO_TESTA = 1.3        # oltre questo rapporto tra gli spessori, nell'angolo il muro sottile si appoggia


def _testa_contro_faccia(nodo, va, vb, angoli) -> bool:
    """Angolo tra due muri di spessore molto diverso (facciata e tramezzo): il muro spesso prosegue intero fino a
    coprire il sottile e il sottile si ferma contro la sua faccia, come si costruisce. Il taglio a 45 gradi lasciava
    in vista una giunzione obliqua tra i due solidi (errore visto in prova nell'angolo tra la
    facciata della cucina e il tramezzo di una camera in un appartamento reale)."""
    ta, tb = va["hl"] + va["hr"], vb["hl"] + vb["hr"]
    if max(ta, tb) < RAPPORTO_TESTA * min(ta, tb) or abs(g.croce(va["d"], vb["d"])) < 0.1:
        return False
    spesso, sottile = (va, vb) if ta > tb else (vb, va)
    lato = 1.0 if g.dot(sottile["d"], spesso["n"]) > 0 else -1.0
    h = spesso["hl"] if lato > 0 else spesso["hr"]
    faccia_p = g.somma(nodo, g.per(spesso["n"], lato * h))
    for idx, segno in ((0, 1.0), (1, -1.0)):
        base = g.somma(nodo, g.per(sottile["n"], segno * (sottile["hl"] if segno > 0 else sottile["hr"])))
        pt = g.intersezione_rette(base, sottile["d"], faccia_p, spesso["d"])
        if pt is None:
            return False
        angoli[id(sottile)][idx] = pt
    # il muro spesso arriva fino alla faccia esterna del sottile (la più lontana nel verso opposto al suo)
    indietro = g.per(spesso["d"], -1.0)
    e = max(0.0, g.dot(g.per(sottile["n"], sottile["hl"]), indietro), g.dot(g.per(sottile["n"], -sottile["hr"]), indietro))
    c = g.somma(nodo, g.per(indietro, e))
    angoli[id(spesso)] = [g.somma(c, g.per(spesso["n"], spesso["hl"])), g.sottrai(c, g.per(spesso["n"], spesso["hr"]))]
    return True


def calcola_giunti(pezzi: list[Pezzo]) -> None:
    """Imposta `ui` e `uo` di ogni pezzo con i giunti dei nodi."""
    nodi: dict[tuple, list[tuple[int, int]]] = {}
    for i, w in enumerate(pezzi):
        nodi.setdefault(_chiave(w.p0), []).append((i, 0))
        nodi.setdefault(_chiave(w.p1), []).append((i, 1))
    ui = [[0.0, 0.0] for _ in pezzi]
    uo = [[0.0, 0.0] for _ in pezzi]
    for chiave, estremi in nodi.items():
        # direzione che esce dal nodo per ogni estremo
        voci = []
        for i, e in estremi:
            w = pezzi[i]
            nodo = w.p0 if e == 0 else w.p1
            d = w.eu if e == 0 else g.per(w.eu, -1.0)
            # hl, hr: distanze delle facce a sinistra e a destra della direzione uscente dal nodo
            hl, hr = (w.hs, w.hd) if e == 0 else (w.hd, w.hs)
            voci.append({"i": i, "e": e, "nodo": nodo, "d": d, "n": g.normale_sinistra(d), "hl": hl, "hr": hr,
                         "ang": math.atan2(d[1], d[0])})
        voci.sort(key=lambda v: v["ang"])
        nodo = voci[0]["nodo"]
        k = len(voci)
        angoli = {}                       # voce -> [punto sinistro, punto destro] rispetto alla direzione uscente
        for v in voci:
            angoli[id(v)] = [g.somma(nodo, g.per(v["n"], v["hl"])), g.sottrai(nodo, g.per(v["n"], v["hr"]))]
        # due pareti in prosecuzione (direzioni opposte sulla stessa retta) formano una parete continua: teste
        # squadrate; le altre pareti del nodo vi si appoggiano e arrivano fino alla loro faccia
        passante = None
        for a in range(k):
            for b in range(a + 1, k):
                va, vb = voci[a], voci[b]
                if abs(g.croce(va["d"], vb["d"])) < 2e-3 and g.dot(va["d"], vb["d"]) < 0:
                    if passante is None or va["hl"] + va["hr"] + vb["hl"] + vb["hr"] > \
                            passante[0]["hl"] + passante[0]["hr"] + passante[1]["hl"] + passante[1]["hr"]:
                        passante = (va, vb)
        if passante is not None:
            va, vb = passante
            for v in voci:
                if v is va or v is vb:
                    continue
                lato = 1.0 if g.dot(v["d"], va["n"]) > 0 else -1.0            # da che parte della parete continua sta
                # la faccia della parete continua da quel lato (vb ha verso opposto: la sua destra è la sinistra di va)
                h_t = max(va["hl"], vb["hr"]) if lato > 0 else max(va["hr"], vb["hl"])
                faccia_p = g.somma(nodo, g.per(va["n"], lato * h_t))
                for idx, segno in ((0, 1.0), (1, -1.0)):
                    base = g.somma(nodo, g.per(v["n"], segno * (v["hl"] if segno > 0 else v["hr"])))
                    pt = g.intersezione_rette(base, v["d"], faccia_p, va["d"])
                    if pt is not None:
                        angoli[id(v)][idx] = pt
            _sposta_il_cambio_di_spessore(nodo, va, vb, [v for v in voci if v is not va and v is not vb], angoli)
        elif k == 2 and _testa_contro_faccia(nodo, voci[0], voci[1], angoli):
            pass
        elif k >= 2:
            for a in range(k):
                v, succ = voci[a], voci[(a + 1) % k]
                p = g.intersezione_rette(g.somma(nodo, g.per(v["n"], v["hl"])), v["d"],
                                         g.sottrai(nodo, g.per(succ["n"], succ["hr"])), succ["d"])
                limite = LIMITE_SPIGOLO * max(v["hl"] + v["hr"], succ["hl"] + succ["hr"])
                if p is not None and g.lunghezza(g.sottrai(p, nodo)) <= limite:
                    angoli[id(v)][0] = p
                    angoli[id(succ)][1] = p
        for v in voci:
            w = pezzi[v["i"]]
            sin, des = angoli[id(v)]
            u_sin = g.dot(g.sottrai(sin, w.p0), w.eu)
            u_des = g.dot(g.sottrai(des, w.p0), w.eu)
            if v["e"] == 0:                # direzione uscente = verso della parete: sinistra = faccia sinistra
                ui[v["i"]][0], uo[v["i"]][0] = u_sin, u_des
            else:                          # all'estremo finale la sinistra uscente è la faccia destra della parete
                uo[v["i"]][1], ui[v["i"]][1] = u_sin, u_des
    for i, w in enumerate(pezzi):
        w.ui, w.uo = (ui[i][0], ui[i][1]), (uo[i][0], uo[i][1])


def risolvi(specifiche: list[dict]) -> Rete:
    pezzi = spezza_ai_nodi(espandi(specifiche))
    calcola_giunti(pezzi)
    return Rete(pezzi)


def impronta(w: Pezzo) -> list[tuple[float, float]]:
    """Il pezzo in pianta, dopo i giunti: quadrilatero tra le facce sinistra e destra, in senso antiorario."""
    return g.antiorario([w.punto_faccia(w.ui[0], "sinistra"), w.punto_faccia(w.ui[1], "sinistra"),
                         w.punto_faccia(w.uo[1], "destra"), w.punto_faccia(w.uo[0], "destra")])


def _ritaglia(soggetto, finestra):
    """Parte del poligono `soggetto` dentro il poligono convesso antiorario `finestra` (Sutherland-Hodgman)."""
    out = list(soggetto)
    for i in range(len(finestra)):
        a, b = finestra[i], finestra[(i + 1) % len(finestra)]
        dentro = lambda p: g.croce(g.sottrai(b, a), g.sottrai(p, a)) >= -1e-12
        entrata, out = out, []
        for j in range(len(entrata)):
            p, q = entrata[j], entrata[(j + 1) % len(entrata)]
            if dentro(q):
                if not dentro(p):
                    out.append(g.intersezione_rette(p, g.sottrai(q, p), a, g.sottrai(b, a)) or q)
                out.append(q)
            elif dentro(p):
                out.append(g.intersezione_rette(p, g.sottrai(q, p), a, g.sottrai(b, a)) or p)
        if not out:
            return []
    return out


def _linee_si_incontrano(w: Pezzo, v: Pezzo, tol: float = 1e-4) -> bool:
    """Le linee dei due pezzi hanno un punto in comune (estremo su estremo, estremo sull'altra linea, incrocio)."""
    d1, d2 = g.sottrai(w.p1, w.p0), g.sottrai(v.p1, v.p0)
    for p, a, b in ((w.p0, v.p0, v.p1), (w.p1, v.p0, v.p1), (v.p0, w.p0, w.p1), (v.p1, w.p0, w.p1)):
        if g.distanza_punto_segmento(p, a, b) < tol:
            return True
    den = g.croce(d1, d2)
    if abs(den) < 1e-12:
        return False
    r = g.sottrai(v.p0, w.p0)
    s, u = g.croce(r, d2) / den, g.croce(r, d1) / den
    return -1e-9 <= s <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9


def sovrapposizioni(pezzi: list[Pezzo], soglia_m2: float = 0.0025) -> list[tuple[str, str, float]]:
    """Coppie di pareti che si sovrappongono in pianta (oltre `soglia_m2`, 5 x 5 cm) senza che le loro linee si
    incontrino. Dove le linee si incontrano (angoli, T, incroci a croce) i pezzi si toccano o si incrociano per
    costruzione; un risalto che parte dal mezzo dello spessore di un muro, invece, finisce dentro il muro senza
    toccarne la linea: solidi uno dentro l'altro, facce doppie in SketchUp."""
    rete = pezzi if isinstance(pezzi, Rete) else Rete(pezzi)
    impronte = {id(w): impronta(w) for w in rete if not w.curva}
    out = []
    for k, w in enumerate(rete):
        if w.curva:
            continue
        for v in rete.vicine(g.per(g.somma(w.p0, w.p1), 0.5), w.lunghezza / 2 + w.spessore):
            if v is w or v.curva or v.origine_id == w.origine_id or rete.index(v) <= k:
                continue
            if _linee_si_incontrano(w, v):
                continue                 # giunto o incrocio previsto dalla rete
            area = g.area(_ritaglia(impronte[id(w)], impronte[id(v)]) or [(0, 0)] * 3)
            if area > soglia_m2:
                out.append((w.origine_id, v.origine_id, area))
    return out


def pezzo_che_contiene(pezzi: list[Pezzo], origine_id: str, u0: float, u1: float) -> tuple[Pezzo, float]:
    """Pezzo (e distanza u0 dall'inizio del pezzo) che contiene l'apertura [u0, u1] misurata lungo la parete
    originale `origine_id`."""
    candidati = [p for p in pezzi if p.origine_id == origine_id]
    if not candidati:
        raise ValueError(f"parete {origine_id!r} non trovata")
    for p in candidati:
        a = u0 - p.u_inizio
        if a >= -1e-6 and u1 - p.u_inizio <= p.lunghezza + 1e-6:
            return p, a
    if any(p.curva for p in candidati):
        raise ValueError(f"l'apertura tra {u0:.2f} e {u1:.2f} m cade su una parete curva o su un giunto: "
                         "le aperture su pareti curve devono stare dentro un solo segmento (aumenta passo_gradi)")
    raise ValueError(f"l'apertura tra {u0:.2f} e {u1:.2f} m attraversa un nodo della parete {origine_id!r}: "
                     "spostala o dividila")


def faccia_che_copre(pezzi: list[Pezzo], p_a, p_b, tol: float = 0.02):
    """(pezzo, lato, u_a) della faccia di parete che contiene i due punti, oppure None."""
    candidati = pezzi.vicine(p_a, 0.05) if isinstance(pezzi, Rete) else pezzi
    for w in candidati:
        for lato in ("sinistra", "destra"):
            h = w.hs if lato == "sinistra" else -w.hd
            ok = True
            us = []
            for p in (p_a, p_b):
                d_perp = g.dot(g.sottrai(p, w.p0), w.en) - h
                u = g.dot(g.sottrai(p, w.p0), w.eu)
                if abs(d_perp) > tol:
                    ok = False
                    break
                us.append(u)
            if not ok:
                continue
            lo, hi = (w.ui if lato == "sinistra" else w.uo)
            if min(us) >= min(lo, hi) - tol and max(us) <= max(lo, hi) + tol:
                return w, lato, us[0]
    return None
