"""Lettura automatica di una planimetria DXF: muri, vani, stanze, altezze, controsoffitti e balconi.

Dal disegno CAD alla scheda di Agentic 3D senza interpretazioni dell'agente: le misure sono quelle del CAD.

1. Unità: ricavate dalle dimensioni del disegno (l'intestazione `$INSUNITS` è spesso sbagliata).
2. Livelli: muri, infissi, proiezioni e testi riconosciuti dal nome e dal contenuto (o indicati).
3. Masse murarie: i contorni chiusi del livello dei muri; le spallette mancanti si chiudono (due estremi liberi a
   distanza di spessore di muro, uno di fronte all'altro); un muro disegnato con una sola faccia riceve uno spessore
   ipotizzato verso l'esterno, dichiarato.
4. Vani: due spallette una di fronte all'altra con il vuoto in mezzo. Tipo dagli infissi e dalla posizione
   (esterno: finestra; interno: porta); larghezza e altezza dalle quote scritte accanto ("112 / 187").
5. Stanze: i vuoti chiusi da muri e vani, con nome, altezza ("h 3,15 m") e superficie scritta ("19,63 mq"), che si
   confronta con quella calcolata.
6. Controsoffitti: le linee di proiezione che dividono una stanza in zone con altezze scritte diverse.
7. Balconi: i contorni del livello delle proiezioni con la scritta BALCONE, TERRAZZO o LOGGIA.

Ciò che non si riesce a leggere finisce nell'elenco dei dubbi, non nella scheda.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

SPESSORE_IPOTIZZATO = 0.30        # m: muro esterno disegnato con una sola faccia
SPESSORE_MIN, SPESSORE_MAX = 0.04, 0.80
VANO_MIN, VANO_MAX = 0.40, 3.60
VANO_MAX_INFISSO = 5.50          # chiusura disegnata con una linea d'infisso (portone del garage)
TOL = 0.005                       # m: punti più vicini di così coincidono

RX_ALTEZZA = re.compile(r"^\s*h\s*=?\s*(\d+[.,]\d+)\s*m?\s*$", re.I)
RX_AREA = re.compile(r"^\s*(\d+[.,]\d+)\s*m(q|²|2)\s*$", re.I)
RX_NUMERO = re.compile(r"^\s*(\d{2,3})(?:[.,]\d)?\s*$")
RX_BALCONE = re.compile(r"balcon|terrazz|loggia", re.I)
TIPI_STANZA = [(r"camera|letto", "camera"), (r"soggiorno|salone|living", "soggiorno"), (r"cucin|angolo cottura", "cucina"),
               (r"bagno|wc|servizi", "bagno"), (r"corridoio|disimpegno|ingresso|atrio|vestibolo", "disimpegno"),
               (r"rip|ripostiglio|lavanderia|cabina|armadi", "ripostiglio"), (r"studio|ufficio", "studio")]


@dataclass
class Lettura:
    scheda: dict
    masse: list = field(default_factory=list)          # (id, classe, poligono, ipotizzata)
    vani: list = field(default_factory=list)           # (id, tipo, poligono, larghezza, nota)
    stanze: list = field(default_factory=list)         # dict con poligono, nome, altezza, area_scritta
    balconi: list = field(default_factory=list)
    zone: list = field(default_factory=list)           # (stanza, poligono, altezza)
    letti: list[str] = field(default_factory=list)     # cosa è stato letto, per il rapporto
    dubbi: list[str] = field(default_factory=list)     # cosa non è stato letto o è ipotizzato
    livelli: dict = field(default_factory=dict)

    def rapporto(self) -> str:
        righe = ["LETTURA DEL DISEGNO"] + [f"- {r}" for r in self.letti]
        if self.dubbi:
            righe += ["DA CONFERMARE"] + [f"- {r}" for r in self.dubbi]
        return "\n".join(righe)


# ------------------------------------------------------------------ geometria del disegno
def _segmenti_e_testi(doc):
    """Segmenti (livello, a, b), archi (livello, centro, raggio) e testi (livello, x, y, testo) in unità del disegno."""
    segmenti, archi, testi = [], [], []
    msp = doc.modelspace()

    def da_entita(e, livello=None):
        livello = livello or e.dxf.layer
        t = e.dxftype()
        if t == "LINE":
            segmenti.append((livello, (e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)))
        elif t in ("LWPOLYLINE", "POLYLINE"):
            pts = [(p[0], p[1]) for p in (e.get_points("xy") if t == "LWPOLYLINE" else [v.dxf.location for v in e.vertices])]
            if e.closed and pts:
                pts.append(pts[0])
            segmenti.extend((livello, a, b) for a, b in zip(pts, pts[1:]))
        elif t == "ARC":
            archi.append((livello, (e.dxf.center.x, e.dxf.center.y), e.dxf.radius))
        elif t in ("TEXT", "MTEXT"):
            testo = e.dxf.text if t == "TEXT" else e.plain_text()
            p = e.dxf.insert
            testi.append((livello, p.x, p.y, _testo_pulito(testo)))
    for e in msp:
        if e.dxftype() == "INSERT":
            continue                                   # blocchi (arredi, simboli): elencati a parte
        da_entita(e)
    blocchi = [e.dxf.name for e in msp.query("INSERT")]
    return segmenti, archi, testi, blocchi


RX_PIEDI = re.compile(r"\d+\s*'\s*-?\s*\d*\s*\"?")          # 13'8, 7' x 5'11, 2'-8"


def _testo_pulito(testo: str) -> str:
    """Testo senza i codici di formattazione di AutoCAD (%%u sottolineato, %%d gradi...)."""
    testo = re.sub(r"%%[uUoOkK]", "", testo)
    testo = testo.replace("%%d", "°").replace("%%D", "°").replace("%%c", "Ø").replace("%%C", "Ø")
    testo = testo.replace("%%p", "±").replace("%%P", "±").replace("%%%", "%")
    return re.sub(r"\s+", " ", testo).strip()


def _sembra_nome_di_stanza(t: str) -> bool:
    """Un nome di stanza è breve: le note tecniche (lunghe, con virgolette, due punti o misure) non lo sono."""
    return len(t) <= 28 and len(t.split()) <= 4 and not re.search(r'[":;]|\d+\s*/\s*\d+|@', t)


def _spessore_tipico(segmenti) -> float | None:
    """Distanza più frequente tra due linee di muro parallele e affacciate (in unità del disegno): lo spessore dei
    muri, che dice l'unità meglio delle dimensioni d'insieme."""
    import statistics
    pezzi = [(a, b) for a, b in segmenti if math.dist(a, b) > 0]
    pezzi.sort(key=lambda s: -math.dist(*s))
    pezzi = pezzi[:400]
    distanze = []
    for i, (a, b) in enumerate(pezzi):
        L = math.dist(a, b)
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        migliore = None
        for j, (c, d) in enumerate(pezzi):
            if i == j:
                continue
            Lc = math.dist(c, d)
            if abs(((d[0] - c[0]) * u[0] + (d[1] - c[1]) * u[1]) / Lc) < 0.995:
                continue
            dist = abs((c[0] - a[0]) * -u[1] + (c[1] - a[1]) * u[0])
            if dist <= 1e-9:
                continue
            t0, t1 = sorted(((c[0] - a[0]) * u[0] + (c[1] - a[1]) * u[1], (d[0] - a[0]) * u[0] + (d[1] - a[1]) * u[1]))
            if min(L, t1) - max(0.0, t0) < 0.5 * min(L, Lc):
                continue
            if migliore is None or dist < migliore:
                migliore = dist
        if migliore is not None:
            distanze.append(migliore)
    return statistics.median(distanze) if len(distanze) >= 5 else None


def _scala(segmenti, insunits: int, testi=(), muri=None) -> tuple[float, str]:
    """Metri per unità del disegno. Un'unità vale se l'edificio risulta largo da 4 a 120 m e i muri spessi da 5 a
    80 cm. Pollici e piedi solo se il disegno scrive misure in piedi e pollici (l'intestazione spesso è sbagliata)."""
    xs = [c for _, a, b in (muri or segmenti) for c in (a[0], b[0])]
    ys = [c for _, a, b in (muri or segmenti) for c in (a[1], b[1])]
    lato = max(max(xs) - min(xs), max(ys) - min(ys)) if xs else 0
    spessore = _spessore_tipico([(a, b) for _, a, b in muri]) if muri else None
    imperiale = sum(1 for *_, tx in testi if RX_PIEDI.search(tx or "")) >= 2
    candidate = [(1.0, "metri"), (0.01, "centimetri"), (0.001, "millimetri")]
    if imperiale:
        candidate = [(0.0254, "pollici"), (0.3048, "piedi")] + candidate
    dichiarate = {1: "pollici", 2: "piedi", 4: "millimetri", 5: "centimetri", 6: "metri"}.get(insunits)
    for fattore, nome in candidate:
        if not 4 <= lato * fattore <= 120:
            continue
        if spessore is not None and not 0.05 <= spessore * fattore <= 0.80:
            continue
        motivo = " (misure scritte in piedi e pollici)" if imperiale and nome in ("pollici", "piedi") else ""
        return fattore, nome + motivo + ("" if dichiarate in (None, nome) else f" (l'intestazione dichiara {dichiarate}: ignorata)")
    raise ValueError(f"unità del disegno non riconoscibili (lato massimo {lato:.0f} unità): indica la scala")


def _ruoli_dei_livelli(segmenti, testi, scelti: dict | None) -> dict:
    """Livello dei muri, degli infissi e delle proiezioni: dai nomi, oppure il livello con più linee per i muri."""
    scelti = dict(scelti or {})
    lunghezze: dict[str, float] = {}
    for liv, a, b in segmenti:
        lunghezze[liv] = lunghezze.get(liv, 0.0) + math.dist(a, b)

    def per_nome(rx):
        return [l for l in lunghezze if re.search(rx, l, re.I)]
    if "muri" not in scelti:
        esclusi = per_nome(r"test|quot|dim|arred|infiss|serram|proiez|hatch|campit|retin"
                           r"|stem|foot|fondaz|plint|slab|solaio|beam|trave")      # fondazioni e strutture sotto il piano
        candidati = [l for l in per_nome(r"mur|wall|ricostr|parete|pareti|struttur|tramezz") if l not in esclusi]
        scelti["muri"] = candidati or [max((l for l in lunghezze if l not in esclusi), key=lunghezze.get)]
    scelti.setdefault("infissi", per_nome(r"infiss|serram|window|door|port[ae]|finestr|opening|apertur"))
    scelti.setdefault("proiezioni", per_nome(r"proiez|soffitt|controsoff|balcon|aggett"))
    for k in ("muri", "infissi", "proiezioni"):
        if isinstance(scelti[k], str):
            scelti[k] = [scelti[k]]
    return scelti


# ------------------------------------------------------------------ masse murarie
def _chiudi_spallette(linee):
    """Aggiunge i segmenti che chiudono le spallette: due estremi liberi a distanza di spessore di muro, sulle due
    facce parallele dello stesso muro, uno di fronte all'altro."""
    from shapely import STRtree
    from shapely.geometry import LineString, Point
    gradi: dict[tuple, list] = {}
    for i, l in enumerate(linee):
        c = list(l.coords)
        for e, (p, q) in enumerate(((c[0], c[1]), (c[-1], c[-2]))):
            gradi.setdefault((round(p[0] / TOL), round(p[1] / TOL)), []).append((i, p, (q[0] - p[0], q[1] - p[1])))
    albero = STRtree(linee)
    liberi = []
    for k, usi in gradi.items():
        if len(usi) != 1:
            continue
        i, p, d = usi[0]
        vicine = [j for j in albero.query(Point(p).buffer(TOL)) if j != i and linee[j].distance(Point(p)) < TOL]
        if not vicine:
            liberi.append((p, d))
    nuovi, presi = [], set()
    for a, (p, d) in enumerate(liberi):
        if a in presi:
            continue
        migliore = None
        for b, (q, e) in enumerate(liberi):
            if b == a or b in presi:
                continue
            dist = math.dist(p, q)
            if not SPESSORE_MIN <= dist <= SPESSORE_MAX:
                continue
            v = ((q[0] - p[0]) / dist, (q[1] - p[1]) / dist)
            ld, le = math.hypot(*d) or 1, math.hypot(*e) or 1
            if abs(v[0] * d[0] + v[1] * d[1]) / ld > 0.2 or abs(v[0] * e[0] + v[1] * e[1]) / le > 0.2:
                continue
            if (d[0] * e[0] + d[1] * e[1]) / (ld * le) < 0.9:
                continue
            if migliore is None or dist < migliore[0]:
                migliore = (dist, b, q)
        if migliore:
            presi |= {a, migliore[1]}
            nuovi.append(LineString([p, migliore[2]]))
    return nuovi


def _masse(linee, punti_stanza):
    """(poligoni chiusi, poligoni a spessore ipotizzato, catene a faccia singola) dalle linee dei muri (in metri)."""
    from shapely import STRtree, polygonize_full, set_precision, unary_union
    from shapely.geometry import LineString, Point
    from shapely.ops import linemerge
    linee = [set_precision(l, TOL) for l in linee if l.length > TOL]
    linee += _chiudi_spallette(linee)
    rete = unary_union(linee)
    poligoni, _, appesi, _ = polygonize_full(list(rete.geoms) if hasattr(rete, "geoms") else [rete])
    chiuse = [p for p in poligoni.geoms if p.area > 1e-4]
    # i poligoni chiusi che contengono il nome di una stanza sono stanze disegnate a filo singolo, non masse
    chiuse = [p for p in chiuse if not any(p.contains(Point(t)) for t in punti_stanza) and _larghezza(p) <= SPESSORE_MAX]
    unite = linemerge(list(appesi.geoms)) if len(appesi.geoms) else None
    catene = [] if unite is None else (list(unite.geoms) if hasattr(unite, "geoms") else [unite])
    ipotizzate = []
    base = unary_union(chiuse) if chiuse else None
    # una catena aperta mescola spesso muri a una faccia (verso un confinante) e muri veri a due facce: i tratti con
    # la faccia di fronte diventano la striscia di muro tra le due facce; solo gli altri hanno lo spessore ipotizzato
    tratti = []
    for l in linee:
        cc = list(l.coords)
        tratti += [LineString([cc[i], cc[i + 1]]) for i in range(len(cc) - 1) if math.dist(cc[i], cc[i + 1]) > TOL]
    albero = STRtree(tratti)
    strisce, sole = [], []
    for c in catene:
        cc = list(c.coords)
        corrente = []
        for i in range(len(cc) - 1):
            s = LineString([cc[i], cc[i + 1]])
            if s.length < 0.05:                      # sporgenze di pochi centimetri oltre un incrocio
                continue
            if _testata(cc, i, punti_stanza):
                # la testata di un muro (accanto a una porta) non è una faccia: due testate si guardano a distanza
                # di vano e sembrerebbero le facce di un muro
                if corrente:
                    sole.append(LineString(corrente))
                    corrente = []
                continue
            di_fronte = _facce_di_fronte(s, tratti, albero, punti_stanza)
            strisce += di_fronte
            # le parti del tratto senza faccia di fronte hanno una faccia sola: spessore ipotizzato
            a_, b_ = cc[i], cc[i + 1]
            L_ = s.length
            coperti = sorted((min(s.project(Point(v)) for v in st.exterior.coords),
                              max(s.project(Point(v)) for v in st.exterior.coords)) for st in di_fronte)
            scoperti, inizio = [], 0.0
            for c0, c1 in coperti:
                if c0 - inizio > 0.05:
                    scoperti.append((inizio, c0))
                inizio = max(inizio, c1)
            if L_ - inizio > 0.05:
                scoperti.append((inizio, L_))
            if not scoperti or scoperti[0][0] > 1e-6:
                if corrente:
                    sole.append(LineString(corrente))
                corrente = []
            for k_, (u0, u1) in enumerate(scoperti):
                P0, P1 = s.interpolate(u0).coords[0], s.interpolate(u1).coords[0]
                if u0 <= 1e-6 and corrente and corrente[-1] == a_:
                    corrente.append(P1 if u1 < L_ - 1e-6 else b_)
                else:
                    if corrente:
                        sole.append(LineString(corrente))
                    corrente = [a_ if u0 <= 1e-6 else P0, b_ if u1 >= L_ - 1e-6 else P1]
                if u1 < L_ - 1e-6:
                    sole.append(LineString(corrente))
                    corrente = []
        if corrente:
            sole.append(LineString(corrente))
    if strisce:
        muri_veri = unary_union(strisce).buffer(0)
        if base is not None:
            muri_veri = muri_veri.difference(base)
        parti = [q for q in (muri_veri.geoms if hasattr(muri_veri, "geoms") else [muri_veri])
                 if q.geom_type == "Polygon" and q.area > 1e-3]
        chiuse += parti
        # blocchi d'angolo: dove due strisce si toccano solo in un vertice resta un quadratino chiuso da linee di
        # muro, senza nome, non più grande dello spessore dei muri che lo toccano: è muro
        from shapely.ops import polygonize
        rete_angoli = unary_union(list(linee) + [q.exterior for q in parti])
        for f in polygonize(rete_angoli):
            if not 1e-4 < f.area < 0.5 or f.intersection(unary_union(chiuse)).area > 0.5 * f.area:
                continue
            if any(f.contains(Point(pt)) for pt in punti_stanza):
                continue
            vicine = [q for q in parti if f.boundary.intersection(q.boundary).length > 0.02]
            if len(vicine) < 2:
                continue
            r_ = list(f.minimum_rotated_rectangle.exterior.coords)
            lato_max = max(math.dist(r_[0], r_[1]), math.dist(r_[1], r_[2]))
            if lato_max <= max(_larghezza(q) for q in vicine) + 0.02:
                chiuse.append(f)
        base = unary_union(chiuse)
    # un tratto a una faccia che finisce nel vuoto (estremo libero di una catena) è la facciata che prosegue oltre
    # l'appartamento, non un muro: si toglie fino al primo vertice
    estremi_liberi = set()
    for c in catene:
        for e in (c.coords[0], c.coords[-1]):
            pe = Point(e)
            tocchi = sum(1 for j in albero.query(pe.buffer(0.005)) if tratti[j].distance(pe) < 0.005)
            if tocchi <= 1:                          # nessun'altra linea di muro lo tocca: estremo davvero libero
                estremi_liberi.add((round(e[0], 3), round(e[1], 3)))
    # una catena libera ai due capi e lontana da ogni muro chiuso è una linea isolata (bordo di terrazza, quota)
    isolate = [c for c in catene if all((round(e[0], 3), round(e[1], 3)) in estremi_liberi for e in (c.coords[0], c.coords[-1]))
               and (base is None or c.distance(base) > SPESSORE_MAX)]
    accorciate = []
    for c in sole:
        if any(c.within(i_.buffer(0.01)) for i_ in isolate):
            continue
        cc = list(c.coords)
        if (round(cc[0][0], 3), round(cc[0][1], 3)) in estremi_liberi:
            cc = cc[1:]
        if len(cc) >= 2 and (round(cc[-1][0], 3), round(cc[-1][1], 3)) in estremi_liberi:
            cc = cc[:-1]
        if len(cc) >= 2:
            accorciate.append(LineString(cc))
    for c in accorciate:
        if c.length < 0.20:                         # uno spigolo di pochi centimetri non è un muro a sé
            continue
        lato = _lato_dai_raggi(c, tratti, albero) or _lato_esterno(c, punti_stanza)
        p = c.buffer(SPESSORE_IPOTIZZATO * lato, single_sided=True, cap_style="flat", join_style="mitre")
        if base is not None:
            p = p.difference(base)
        for q in (p.geoms if hasattr(p, "geoms") else [p]):
            if q.area > 1e-3:
                ipotizzate.append(q)
    return chiuse, ipotizzate, catene


def _facce_di_fronte(s, tratti, albero, punti_stanza) -> list:
    """Strisce di muro tra il tratto `s` e le facce parallele di fronte più vicine (un muro disegnato a due facce):
    [] se il tratto ha una faccia sola. La faccia più vicina vince (un muro è più sottile della stanza accanto);
    una striscia che contiene il nome di una stanza è una stanza stretta, non un muro."""
    from shapely.geometry import Point, Polygon
    (ax, ay), (bx, by) = s.coords[0], s.coords[-1]
    L = s.length
    u = ((bx - ax) / L, (by - ay) / L)
    n = (-u[1], u[0])
    candidati = []
    for j in albero.query(s.buffer(SPESSORE_MAX)):
        t = tratti[j]
        (cx, cy), (dx, dy) = t.coords[0], t.coords[-1]
        Lt = t.length
        if Lt < 0.02 or abs(((dx - cx) * u[0] + (dy - cy) * u[1]) / Lt) < 0.995:
            continue
        d = (cx - ax) * n[0] + (cy - ay) * n[1]                 # con segno: da che parte sta la faccia
        if not SPESSORE_MIN <= abs(d) <= SPESSORE_MAX:
            continue
        t0, t1 = sorted(((cx - ax) * u[0] + (cy - ay) * u[1], (dx - ax) * u[0] + (dy - ay) * u[1]))
        s0, s1 = max(0.0, t0), min(L, t1)
        if s1 - s0 < 0.05 or s1 - s0 < 0.8 * abs(d):
            continue                                # due stipiti che si guardano attraverso un vano: più larghi che lunghi
        striscia = Polygon([(ax + u[0] * s0, ay + u[1] * s0), (ax + u[0] * s1, ay + u[1] * s1),
                            (ax + u[0] * s1 + n[0] * d, ay + u[1] * s1 + n[1] * d),
                            (ax + u[0] * s0 + n[0] * d, ay + u[1] * s0 + n[1] * d)])
        # il nome di una stanza nella striscia o appena oltre, lungo il muro: è una stanza stretta (un ripostiglio),
        # e le due linee sono le sue pareti, non le facce di un muro
        allungata = Polygon([(ax + u[0] * (s0 - 0.7), ay + u[1] * (s0 - 0.7)), (ax + u[0] * (s1 + 0.7), ay + u[1] * (s1 + 0.7)),
                             (ax + u[0] * (s1 + 0.7) + n[0] * d, ay + u[1] * (s1 + 0.7) + n[1] * d),
                             (ax + u[0] * (s0 - 0.7) + n[0] * d, ay + u[1] * (s0 - 0.7) + n[1] * d)])
        if any(allungata.contains(Point(pt)) for pt in punti_stanza):
            continue
        candidati.append((abs(d), striscia))
    if not candidati:
        return []
    vicina = min(c[0] for c in candidati)
    return [st for d, st in candidati if d <= vicina + 0.03]


def _testata(cc, i, punti_stanza=()) -> bool:
    """Il tratto i della catena `cc` chiude un muro: corto (spessore di muro) tra due lati che tornano indietro."""
    if not 0 < i < len(cc) - 2:
        return False
    a, b, p, q = cc[i], cc[i + 1], cc[i - 1], cc[i + 2]
    if math.dist(a, b) > SPESSORE_MAX:
        return False
    # una U: i due lati vicini corrono in versi opposti (uno smusso o un angolo non lo sono)
    va = (a[0] - p[0], a[1] - p[1])
    vq = (q[0] - b[0], q[1] - b[1])
    la, lq = math.hypot(*va), math.hypot(*vq)
    if la < 1e-9 or lq < 1e-9:
        return False
    if (va[0] * vq[0] + va[1] * vq[1]) / (la * lq) >= -0.8:
        return False
    # dentro la U di una testata c'è muro; dentro la U di una stanza stretta (un ripostiglio) c'è il suo nome
    from shapely.geometry import Point, Polygon
    k = min(lq, 2.0) / lq
    u_ = Polygon([a, b, (b[0] + vq[0] * k, b[1] + vq[1] * k), (a[0] + vq[0] * k, a[1] + vq[1] * k)])
    return not any(u_.contains(Point(pt)) for pt in punti_stanza)


def _larghezza(p) -> float:
    """Spessore di una massa: il diametro del cerchio più grande che ci sta dentro (un muro a T o a L è sottile anche
    se il rettangolo che lo contiene è grande)."""
    from shapely import maximum_inscribed_circle
    if p.is_empty or p.area <= 0:
        return 0.0
    return 2 * maximum_inscribed_circle(p, tolerance=0.002).length


def _lato_dai_raggi(catena, tratti, albero) -> int:
    """+1 se l'esterno è a sinistra della catena, -1 se a destra, 0 se non si decide: da metà di ogni tratto una
    semiretta per lato; verso l'esterno dell'edificio si incontrano meno linee di muro (di solito nessuna). Voto
    pesato sulla lunghezza dei tratti."""
    from shapely.geometry import LineString
    voto = 0.0
    cc = list(catena.coords)
    for i in range(len(cc) - 1):
        (ax, ay), (bx, by) = cc[i], cc[i + 1]
        L = math.dist(cc[i], cc[i + 1])
        if L < 0.10:
            continue
        mx, my = (ax + bx) / 2, (ay + by) / 2
        n = (-(by - ay) / L, (bx - ax) / L)                     # a sinistra del verso della catena
        conta = []
        for s in (1, -1):
            raggio = LineString([(mx + s * n[0] * 0.02, my + s * n[1] * 0.02), (mx + s * n[0] * 40, my + s * n[1] * 40)])
            conta.append(sum(1 for j in albero.query(raggio) if tratti[j].intersects(raggio)))
        if conta[0] != conta[1]:
            voto += L if conta[0] < conta[1] else -L
    return 0 if abs(voto) < 1e-9 else (1 if voto > 0 else -1)


def _lato_esterno(catena, punti_stanza) -> int:
    """+1 se l'esterno è a sinistra della catena, -1 se a destra: la stanza più vicina sta dall'altra parte."""
    from shapely.geometry import Point
    # contano i nomi che stanno di fronte alla catena (proiezione dentro, non oltre un capo): il nome più vicino
    # in assoluto può stare oltre la fine del muro, dall'altra parte
    di_fronte = [t for t in punti_stanza if 0.05 < catena.project(Point(t)) < catena.length - 0.05]
    migliore = None
    for t in (di_fronte or punti_stanza):
        pt = Point(t)
        d = catena.distance(pt)
        s = catena.project(pt)
        a = catena.interpolate(max(0.0, s - 0.01))
        b = catena.interpolate(min(catena.length, s + 0.01))
        v = (b.x - a.x, b.y - a.y)
        w = (pt.x - a.x, pt.y - a.y)
        lato = 1 if v[0] * w[1] - v[1] * w[0] > 0 else -1
        if migliore is None or d < migliore[0]:
            migliore = (d, lato)
    return -migliore[1] if migliore else 1


# ------------------------------------------------------------------ vani
def _angoli(masse):
    """Vertici delle masse con le direzioni (unitarie, uscenti dal vertice) dei due lati che vi arrivano."""
    out = []
    for k, m in enumerate(masse):
        for anello in [m.exterior] + list(m.interiors):
            c = list(anello.coords)[:-1]
            n = len(c)
            for i in range(n):
                p, prima, dopo = c[i], c[i - 1], c[(i + 1) % n]
                dirs = []
                for q in (prima, dopo):
                    L = math.dist(p, q)
                    if L > 1e-6:
                        dirs.append(((q[0] - p[0]) / L, (q[1] - p[1]) / L, L))
                out.append((k, p, dirs))
    return out


def _chiusure(masse, unione):
    """Segmenti che chiudono le stanze sui vani: uniscono due angoli di masse dove le facce dei muri sono allineate
    ai due lati del vuoto (la faccia prosegue idealmente attraverso il vano), senza attraversare i muri."""
    from shapely import STRtree
    from shapely.geometry import LineString, Point
    angoli = _angoli(masse)
    albero = STRtree([Point(p) for _, p, _ in angoli])
    trovate = []
    for i, (ka, a, da) in enumerate(angoli):
        for j in albero.query(Point(a).buffer(VANO_MAX)):
            if j <= i:
                continue
            kb, b, db = angoli[j]
            L = math.dist(a, b)
            if not VANO_MIN <= L <= VANO_MAX:
                continue
            u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            # in a una faccia che va all'indietro (lontano da b) lungo la stessa retta; in b lo stesso, verso l'altra parte
            fa = [d for d in da if d[0] * -u[0] + d[1] * -u[1] > 0.999 and d[2] > 0.04]
            fb = [d for d in db if d[0] * u[0] + d[1] * u[1] > 0.999 and d[2] > 0.04]
            if not fa or not fb:
                continue
            s = LineString([a, b])
            if s.intersection(unione).length > 0.01:
                continue
            trovate.append((L, a, b, ka, kb))
    # per ogni angolo la chiusura più corta: un vano, non un collegamento tra vani lontani
    trovate.sort(key=lambda x: x[0])
    usati, chiusure = set(), []
    for L, a, b, ka, kb in trovate:
        ca, cb = (round(a[0], 3), round(a[1], 3)), (round(b[0], 3), round(b[1], 3))
        if ca in usati or cb in usati:
            continue
        usati |= {ca, cb}
        chiusure.append(LineString([a, b]))
    return chiusure


def _chiusure_da_infissi(infissi_seg, archi_infissi, unione, gia):
    """Chiusure dove le facce non sono allineate (muri diagonali, spallette svasate): una linea di infisso che va da
    una massa all'altra, oppure l'anta di una porta (dal cardine, centro dell'arco, all'altra spalletta)."""
    from shapely.geometry import LineString, Point
    from shapely.ops import nearest_points
    bordo = unione.boundary
    nuove = []

    def gia_chiuso(s):
        return any(s.distance(c) < 0.03 and abs(s.length - c.length) < 0.15 for c in gia + nuove)
    for s in infissi_seg:
        a, b = Point(s.coords[0]), Point(s.coords[-1])
        if s.length < VANO_MIN or a.distance(bordo) > 0.10 or b.distance(bordo) > 0.10:
            continue
        if s.intersection(unione).length > 0.1 * s.length:
            continue
        pa, pb = nearest_points(bordo, a)[0], nearest_points(bordo, b)[0]
        c = LineString([pa, pb])
        if VANO_MIN <= c.length <= VANO_MAX_INFISSO and not gia_chiuso(c):   # un portone disegnato può superare 3,6 m
            nuove.append(c)
    for centro, raggio in archi_infissi:
        cp = Point(centro)
        if cp.distance(bordo) > 0.08:
            continue
        cerniera = nearest_points(bordo, cp)[0]
        anello = cerniera.buffer(raggio + 0.10).exterior.intersection(unione.buffer(0.001))
        candidati = []
        for g in (anello.geoms if hasattr(anello, "geoms") else [anello]):
            for q in ([Point(x) for x in g.coords] if hasattr(g, "coords") else []):
                d = q.distance(cerniera)
                s = LineString([cerniera, q])
                if raggio - 0.15 <= d <= raggio + 0.15 and s.intersection(unione).length < 0.05:
                    candidati.append((abs(d - raggio), s))
        if candidati:
            s = min(candidati, key=lambda c: c[0])[1]
            if not gia_chiuso(s):
                nuove.append(s)
    return nuove


def _rettangolo_di_luce(q, c, n, profondita):
    """Il vano rettangolare dentro un vuoto svasato o storto: largo quanto la luce comune a tutte le sezioni,
    profondo quanto il muro. Le parti del vuoto fuori dal rettangolo (sguinci) sono muro."""
    from shapely.geometry import LineString, Polygon
    (ax, ay), (bx, by) = c.coords[0], c.coords[-1]
    L = c.length
    u = ((bx - ax) / L, (by - ay) / L)
    migliore = None                                 # luce comune a tutte le profondità (intersezione delle sezioni)
    for k in [0.25] + list(range(1, 12)) + [11.75]:
        d = profondita * k / 12
        o = (ax + n[0] * d - u[0] * 2, ay + n[1] * d - u[1] * 2)
        linea = LineString([o, (o[0] + u[0] * (L + 4), o[1] + u[1] * (L + 4))])
        sez = linea.intersection(q)
        pezzi = [g for g in (sez.geoms if hasattr(sez, "geoms") else [sez]) if g.geom_type == "LineString" and g.length > 0]
        if not pezzi:
            continue
        g = max(pezzi, key=lambda x: x.length)
        s0 = min((x - ax) * u[0] + (y - ay) * u[1] for x, y in g.coords)
        s1 = max((x - ax) * u[0] + (y - ay) * u[1] for x, y in g.coords)
        migliore = (s0, s1) if migliore is None else (max(migliore[0], s0), min(migliore[1], s1))
    if migliore is None or migliore[1] - migliore[0] < VANO_MIN:
        return None, []
    s0, s1 = migliore

    def pt(s, d):
        return (ax + u[0] * s + n[0] * d, ay + u[1] * s + n[1] * d)
    rett = Polygon([pt(s0, 0), pt(s1, 0), pt(s1, profondita), pt(s0, profondita)])
    resto = q.difference(rett.buffer(0.001))
    sguinci = [g for g in (resto.geoms if hasattr(resto, "geoms") else [resto]) if g.geom_type == "Polygon" and g.area > 1e-3]
    return rett, sguinci


def rett_larghezza(rett, c) -> float:
    """Larghezza del vano lungo la chiusura."""
    a, b = list(rett.exterior.coords)[0], list(rett.exterior.coords)[1]
    return math.dist(a, b)


def _sulla_griglia(poligono, passo: float = 0.001) -> list:
    """Il poligono con i vertici su una griglia di `passo` metri (i lati più corti del passo spariscono)."""
    from shapely import set_precision
    q = set_precision(poligono, passo)
    return [gm for gm in (q.geoms if hasattr(q, "geoms") else [q]) if gm.geom_type == "Polygon" and gm.area > 2e-4]


def _allunga(linea, d=0.03):
    """La stessa linea allungata di `d` ai due capi: una proiezione che si ferma a pochi millimetri dal muro deve
    comunque dividere la stanza."""
    from shapely.geometry import LineString
    (ax, ay), (bx, by) = linea.coords[0], linea.coords[-1]
    L = math.dist((ax, ay), (bx, by)) or 1.0
    ux, uy = (bx - ax) / L, (by - ay) / L
    return LineString([(ax - ux * d, ay - uy * d), (bx + ux * d, by + uy * d)])


def _vani(chiusure, unione):
    """Vani: due chiusure affacciate ai due lati dello stesso muro (distanza = spessore). Il vano è il quadrilatero
    tra le due, anche svasato; una chiusura senza compagna (muro a faccia singola) dà un vano spesso quanto il muro
    accanto."""
    from shapely.geometry import Polygon
    vani, prese = [], set()
    for i, s in enumerate(chiusure):
        if i in prese:
            continue
        (a1, b1) = list(s.coords)
        migliore = None
        for j, r in enumerate(chiusure):
            if j == i or j in prese:
                continue
            (a2, b2) = list(r.coords)
            # stessa direzione (o opposta), parallele, a distanza di spessore, affacciate
            d1 = (b1[0] - a1[0], b1[1] - a1[1])
            d2 = (b2[0] - a2[0], b2[1] - a2[1])
            if abs(d1[0] * d2[1] - d1[1] * d2[0]) / (s.length * r.length) > 0.15:
                continue
            if abs(s.length - r.length) > 0.06:            # lati di lunghezza diversa: sguinci, non un vano rettangolare
                continue
            if d1[0] * d2[0] + d1[1] * d2[1] < 0:
                a2, b2 = b2, a2
            dist = s.distance(r)
            if not SPESSORE_MIN <= dist <= SPESSORE_MAX or math.dist(a1, a2) > SPESSORE_MAX + 0.4 or math.dist(b1, b2) > SPESSORE_MAX + 0.4:
                continue
            q = Polygon([a1, b1, b2, a2])
            if not q.is_valid or q.area <= 0 or q.intersection(unione).area > 0.05 * q.area:
                continue
            spalla = (a2[0] - a1[0], a2[1] - a1[1])          # il vano deve essere squadrato, non un parallelogramma
            if abs(spalla[0] * d1[0] + spalla[1] * d1[1]) / (math.hypot(*spalla) * s.length + 1e-9) > 0.08:
                continue
            if migliore is None or dist < migliore[0]:
                migliore = (dist, j, q)
        if migliore:
            prese |= {i, migliore[1]}
            vani.append((migliore[2], min(s.length, chiusure[migliore[1]].length)))
    return vani


def _vani_da_asse(assi, chiusure, vani, unione, infissi=()):
    """Vani dove una faccia del muro non prosegue allineata oltre il vano (muretti che scendono ai lati, come in un
    vestibolo): la linea d'asse dell'infisso sta a metà spessore, parallela alla chiusura dell'altra faccia; il vano
    va da quella faccia alla sua simmetrica rispetto all'asse."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union
    gia = unary_union([v[0] for v in vani]) if vani else None
    nuovi = []
    for ci in assi:
        if gia is not None and ci.distance(gia) < 0.02:
            continue
        # una finestra ha due linee di vetro affiancate; la porta una sola linea d'asse (con la crocetta)
        if sum(1 for s in infissi if 0.005 < s.distance(ci) <= 0.3 and s.length >= 0.8 * ci.length
               and abs((s.coords[-1][0] - s.coords[0][0]) * (ci.coords[-1][1] - ci.coords[0][1])
                       - (s.coords[-1][1] - s.coords[0][1]) * (ci.coords[-1][0] - ci.coords[0][0])) < 0.05 * s.length * ci.length):
            continue
        (a1, b1) = list(ci.coords)
        d1 = (b1[0] - a1[0], b1[1] - a1[1])
        for cf in chiusure:
            (a2, b2) = list(cf.coords)
            d2 = (b2[0] - a2[0], b2[1] - a2[1])
            if abs(d1[0] * d2[1] - d1[1] * d2[0]) / (ci.length * cf.length) > 0.05 or abs(ci.length - cf.length) > 0.06:
                continue
            if d1[0] * d2[0] + d1[1] * d2[1] < 0:
                a2, b2 = b2, a2
            h = ci.distance(cf)
            if not 0.02 <= h <= SPESSORE_MAX / 2 or abs(math.dist(a1, a2) - h) > 0.03 or abs(math.dist(b1, b2) - h) > 0.03:
                continue
            if gia is not None and cf.distance(gia) < 0.02 and cf.intersection(gia.buffer(0.02)).length > 0.4 * cf.length:
                continue
            a3 = (2 * a1[0] - a2[0], 2 * a1[1] - a2[1])
            b3 = (2 * b1[0] - b2[0], 2 * b1[1] - b2[1])
            q = Polygon([a2, b2, b3, a3])
            if not q.is_valid or q.area <= 0 or q.intersection(unione).area > 0.05 * q.area:
                continue
            nuovi.append((q, cf.length, ci, LineString([a3, b3])))
            break
    return nuovi


def _ante_scorrevoli(rett, larghezza, infissi_seg) -> int:
    """Ante scorrevoli disegnate aperte: linee d'infisso parallele al muro, lunghe almeno un quarto della luce,
    accostate al muro e tutte fuori dalla luce del vano. Una per lato occupato (0 = nessuna)."""
    cc = list(rett.exterior.coords)[:4]
    lati = [(cc[i], cc[(i + 1) % 4]) for i in range(4)]
    a, b = min(lati, key=lambda l: abs(math.dist(*l) - larghezza))
    Lw = math.dist(a, b) or 1.0
    w = ((b[0] - a[0]) / Lw, (b[1] - a[1]) / Lw)
    u = (-w[1], w[0])
    c = rett.centroid
    profondita = rett.area / Lw
    occupati = set()
    for s in infissi_seg:
        (sx, sy), (ex, ey) = s.coords[0], s.coords[-1]
        Ls = s.length
        if Ls < 0.25 * larghezza or abs(((ex - sx) * w[0] + (ey - sy) * w[1]) / Ls) < 0.98:
            continue
        if abs(((sx + ex) / 2 - c.x) * u[0] + ((sy + ey) / 2 - c.y) * u[1]) > profondita / 2 + 0.15:
            continue
        t0, t1 = sorted(((sx - c.x) * w[0] + (sy - c.y) * w[1], (ex - c.x) * w[0] + (ey - c.y) * w[1]))
        if t1 - t0 > 1.2 * larghezza:
            continue
        # l'anta aperta parte dallo stipite (non è la linea d'asse di un'altra porta più in là sullo stesso muro)
        if larghezza / 2 - 0.03 <= t0 <= larghezza / 2 + 0.15:
            occupati.add(1)
        elif -larghezza / 2 - 0.15 <= t1 <= -larghezza / 2 + 0.03:
            occupati.add(-1)
    return len(occupati)


def _quote_vicine(testi_m, centro, raggio=1.6):
    """Coppia di numeri scritti vicino al vano (larghezza e altezza in centimetri, es. 112 / 187)."""
    numeri = [(x, y, int(RX_NUMERO.match(t).group(1))) for _, x, y, t in testi_m if RX_NUMERO.match(t)]
    vicini = sorted((math.dist((x, y), centro), x, y, n) for x, y, n in numeri if math.dist((x, y), centro) <= raggio)
    for _, x, y, n in vicini:
        compagni = [m for _, x2, y2, m in vicini if 0 < math.dist((x, y), (x2, y2)) < 0.6 and m != n]
        if compagni:
            return n, compagni[0]
    return None


# ------------------------------------------------------------------ lettura completa
def leggi(percorso: str | Path, livelli: dict | None = None, nome: str = "Progetto") -> Lettura:
    import ezdxf
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import polygonize, unary_union
    doc = ezdxf.readfile(str(percorso))
    segmenti, archi, testi, blocchi = _segmenti_e_testi(doc)
    if not segmenti:
        raise ValueError("nel disegno non ci sono linee")
    ruoli = _ruoli_dei_livelli(segmenti, testi, livelli)
    fattore, unita = _scala(segmenti, int(doc.header.get("$INSUNITS", 0) or 0), testi,
                            [s for s in segmenti if s[0] in ruoli["muri"]])
    muri_seg = [s for s in segmenti if s[0] in ruoli["muri"]]
    x0 = min(min(a[0], b[0]) for _, a, b in muri_seg)
    y0 = min(min(a[1], b[1]) for _, a, b in muri_seg)

    def m(p):
        return (round((p[0] - x0) * fattore, 4), round((p[1] - y0) * fattore, 4))
    testi_m = [(l, *m((x, y)), t) for l, x, y, t in testi]
    nomi_stanza = [(x, y, t) for _, x, y, t in testi_m
                   if t and not RX_ALTEZZA.match(t) and not RX_AREA.match(t) and not RX_NUMERO.match(t)
                   and re.search(r"[A-Za-z]{3,}", t) and not re.search(r"piano|int\.|scala|quota|sez", t, re.I)
                   and _sembra_nome_di_stanza(t)]
    punti_stanza = [(x, y) for x, y, t in nomi_stanza if not RX_BALCONE.search(t)]
    let = Lettura(scheda={}, livelli=ruoli)
    let.letti.append(f"unità: {unita}; muri dal livello {', '.join(ruoli['muri'])}"
                     + (f", infissi da {', '.join(ruoli['infissi'])}" if ruoli["infissi"] else "")
                     + (f", proiezioni da {', '.join(ruoli['proiezioni'])}" if ruoli["proiezioni"] else ""))

    linee = [LineString([m(a), m(b)]) for _, a, b in muri_seg if math.dist(a, b) * fattore > TOL]
    chiuse, ipotizzate, catene = _masse(linee, punti_stanza)
    masse = chiuse + ipotizzate
    # fessure tra due masse più strette di un vano (pochi centimetri): sono muro, non vuoto
    from shapely.geometry import JOIN_STYLE
    base = unary_union(masse).buffer(0)
    chiuso = base.buffer(0.08, join_style=JOIN_STYLE.mitre).buffer(-0.08, join_style=JOIN_STYLE.mitre)
    fessure = [f for f in (chiuso.difference(base).geoms if hasattr(chiuso.difference(base), "geoms") else [chiuso.difference(base)])
               if f.geom_type == "Polygon" and f.area > 2e-4 and _larghezza(f) < 0.16]
    if fessure:
        ipotizzate += fessure
        masse = chiuse + ipotizzate
        let_fessure = len(fessure)
    else:
        let_fessure = 0
    if ipotizzate:
        let.dubbi.append(f"{len(ipotizzate)} tratti di muro esterno disegnati con una sola faccia: spessore ipotizzato "
                         f"{SPESSORE_IPOTIZZATO:.2f} m verso l'esterno (in arancione nella tavola)")
    if let_fessure:
        let.letti.append(f"{let_fessure} fessure di pochi centimetri tra due muri riempite come muro")
    unione = unary_union(masse).buffer(0)
    # le facce allineate si cercano sul contorno dell'unione: due masse che si toccano formano una faccia continua
    parti_unione = [q for q in (unione.geoms if hasattr(unione, "geoms") else [unione]) if q.geom_type == "Polygon"]
    chiusure = _chiusure([q.simplify(0.0005) for q in parti_unione], unione)
    vani = _vani(chiusure, unione)
    infissi_pre = [LineString([m(a), m(b)]) for l, a, b in segmenti if l in ruoli["infissi"]]
    archi_pre = [(m(c), r * fattore) for l, c, r in archi if l in ruoli["infissi"]]
    da_infissi = _chiusure_da_infissi(infissi_pre, archi_pre, unione, chiusure)
    da_asse = _vani_da_asse(da_infissi, chiusure, vani, unione, infissi_pre)
    vani += [(q, L) for q, L, _, _ in da_asse]
    # per questi vani il confine della stanza è la faccia del muro dalla parte dell'asse, non l'asse
    sostituite = {id(ci): faccia for _, _, ci, faccia in da_asse}
    chiusure += [sostituite.get(id(c), c) for c in da_infissi]
    tutto = unary_union([unione] + [v[0] for v in vani]).buffer(0)
    esterno = max((tutto.geoms if hasattr(tutto, "geoms") else [tutto]), key=lambda p: p.area)

    # stanze: i vuoti chiusi da muri e vani
    stanze, contatori = [], {}
    proiezioni = [LineString([m(a), m(b)]) for l, a, b in segmenti if l in ruoli["proiezioni"]]
    # stanze: le facce chiuse da bordi delle masse e chiusure dei vani, che non sono masse né vani
    bordi = [m_.exterior for m_ in masse] + [r for m_ in masse for r in m_.interiors] + list(chiusure)
    facce = [f for f in polygonize(unary_union(bordi)) if f.area >= 0.02]    # anche i piccoli vuoti delle svasature
    pieni = unary_union(masse + [v[0] for v in vani])
    facce = [f for f in facce if f.intersection(pieni).area <= 0.5 * f.area]
    con_nome = [f for f in facce if any(f.contains(Point(x, y)) for x, y, t in nomi_stanza if not RX_BALCONE.search(t))]
    infissi_tutti = [LineString([m(a), m(b)]) for l, a, b in segmenti if l in ruoli["infissi"]]
    unite = {id(f): f for f in con_nome}
    for f in facce:
        if f in con_nome:
            continue
        migliore = None
        for g_ in con_nome:
            comune = f.boundary.intersection(unite[id(g_)].boundary)
            # un vuoto grande separato da un infisso è un'altra stanza; uno piccolo (sguincio, mazzetta) no
            if comune.length < 0.3 or (f.area >= 0.8 and any(s.intersects(comune.buffer(0.02)) for s in infissi_tutti)):
                continue
            if migliore is None or comune.length > migliore[0]:
                migliore = (comune.length, g_)
        if migliore:
            g_ = migliore[1]
            unite[id(g_)] = unary_union([unite[id(g_)], f]).buffer(0)
            if f.area >= 0.8:
                let.letti.append(f"un vuoto di {f.area:.2f} m2 senza nome unito alla stanza accanto (nicchia o rientranza)")
        elif f.area >= 0.8:
            unite[id(f)] = f
    facce = list(unite.values())
    for pol in facce:
        if pol.geom_type != "Polygon":
            pol = max(pol.geoms, key=lambda q: q.area)
        dentro = [(x, y, t) for x, y, t in nomi_stanza if pol.contains(Point(x, y)) and not RX_BALCONE.search(t)]
        alt = [float(RX_ALTEZZA.match(t).group(1).replace(",", ".")) for _, x, y, t in testi_m
               if RX_ALTEZZA.match(t) and pol.contains(Point(x, y))]
        aree = [float(RX_AREA.match(t).group(1).replace(",", ".")) for _, x, y, t in testi_m
                if RX_AREA.match(t) and pol.contains(Point(x, y))]
        nome_st = dentro[0][2].strip().rstrip(".").title() if dentro else None
        tipo = next((tp for rx, tp in TIPI_STANZA if nome_st and re.search(rx, nome_st, re.I)), "locale")
        if tipo == "camera":
            tipo = "camera_doppia" if pol.area >= 14 else "camera_singola"
        base = nome_st or "Locale"
        if pol.area < 0.5:                          # sotto il minimo del motore: non è una stanza (cavedio, nicchia)
            let.dubbi.append(f"\"{base}\" ({pol.area:.2f} m2): troppo piccolo per una stanza, non modellato a parte")
            continue
        contatori[base] = contatori.get(base, 0) + 1
        stanze.append({"pol": pol, "base": base, "tipo": tipo, "altezze": alt, "aree": aree, "nomi": dentro})
    for st in stanze:
        st["id"] = st["base"] if contatori[st["base"]] == 1 else f"{st['base']} {sum(1 for s in stanze[:stanze.index(st) + 1] if s['base'] == st['base'])}"
    nomi_trovati = {t for st in stanze for _, _, t in st["nomi"]}
    for x, y, t in nomi_stanza:
        if t not in nomi_trovati and not RX_BALCONE.search(t):
            let.dubbi.append(f"\"{t}\" (in {x:.2f}; {y:.2f}): la stanza non risulta chiusa da muri e vani (un vano non "
                             "riconosciuto o un muro mancante): non modellata")
    schede_stanze = []
    for st in stanze:
        pol = st["pol"]
        area = pol.area
        spec = {"id": st["id"], "tipo": st["tipo"],
                "poligono_m": [[round(x, 3), round(y, 3)] for x, y in list(pol.exterior.coords)[:-1]]}
        alt_principale = None
        if st["altezze"]:
            # con più altezze scritte, la stanza prende quella vicina al nome; le altre sono zone di controsoffitto
            if st["nomi"]:
                nx, ny, _ = st["nomi"][0]
                vicine = sorted(((math.dist((nx, ny), (x, y)), float(RX_ALTEZZA.match(t).group(1).replace(",", "."))) for _, x, y, t in testi_m
                                 if RX_ALTEZZA.match(t) and pol.contains(Point(x, y))))
                alt_principale = vicine[0][1]
            else:
                alt_principale = max(st["altezze"])
            spec["altezza_m"] = alt_principale
        if len(st["altezze"]) > 1 and proiezioni:
            tagli = [_allunga(l).intersection(pol) for l in proiezioni if _allunga(l).intersects(pol)]
            pezzi = list(polygonize(unary_union([pol.exterior] + tagli)))
            zone = []
            for z in pezzi:
                hz = [float(RX_ALTEZZA.match(t).group(1).replace(",", ".")) for _, x, y, t in testi_m
                      if RX_ALTEZZA.match(t) and z.contains(Point(x, y))]
                if hz and abs(hz[0] - alt_principale) > 0.005 and z.area > 0.3:
                    zone.append({"poligono_m": [[round(x, 3), round(y, 3)] for x, y in list(z.exterior.coords)[:-1]], "altezza_m": hz[0]})
                    let.zone.append((st["id"], z, hz[0]))
            if zone:
                spec["controsoffitti"] = zone
        if st["aree"]:
            scritta = st["aree"][0]
            scarto = area - scritta
            st["area_scritta"] = scritta
            esito = "uguale" if abs(scarto) <= max(0.15, 0.02 * scritta) else f"DIVERSA di {scarto:+.2f} m2"
            let.letti.append(f"{st['id']}: {area:.2f} m2 calcolati, {scritta:.2f} scritti ({esito})"
                             + (f", h {alt_principale:.2f} m" if alt_principale else ""))
            if esito != "uguale":
                let.dubbi.append(f"{st['id']}: superficie calcolata {area:.2f} m2 contro {scritta:.2f} scritta: controllare muri e vani")
        else:
            let.letti.append(f"{st['id']}: {area:.2f} m2" + (f", h {alt_principale:.2f} m" if alt_principale else ""))
        if not st["altezze"]:
            let.dubbi.append(f"{st['id']}: altezza non scritta (vale quella del piano)")
        st["altezza"] = alt_principale
        st["spec"] = spec
        schede_stanze.append(spec)
        let.stanze.append(st)

    # balconi: i contorni delle proiezioni si chiudono contro la facciata (che sta sul livello dei muri)
    schede_balconi = []
    if proiezioni:
        facce_p = [f for f in polygonize(unary_union([_allunga(l) for l in proiezioni] + [esterno.exterior]))
                   if not tutto.buffer(-0.01).contains(f.representative_point()) and f.area > 0.05]
        for f in facce_p:
            etichette = [t_ for x, y, t_ in nomi_stanza if RX_BALCONE.search(t_) and f.contains(Point(x, y))]
            if not etichette:
                continue
            # il parapetto disegnato (due contorni annidati): l'anello sottile attorno, senza scritte
            anelli = [g_ for g_ in facce_p if g_ is not f and g_.distance(f) < 0.005 and _larghezza(g_) <= 0.45
                      and not any(g_.contains(Point(x, y)) for x, y, _ in nomi_stanza)]
            soletta = unary_union([f] + anelli).buffer(0)
            if soletta.geom_type != "Polygon":
                soletta = max(soletta.geoms, key=lambda q: q.area)
            soletta = soletta.difference(tutto.buffer(0.003))
            if soletta.geom_type != "Polygon":
                soletta = max(soletta.geoms, key=lambda q: q.area)
            if soletta.area < 0.8:
                continue
            bid = f"{etichette[0].strip().title()} {len(schede_balconi) + 1}"
            spec_b = {"id": bid, "poligono_m": [[round(x, 3), round(y, 3)] for x, y in list(soletta.exterior.coords)[:-1]]}
            if anelli:
                spec_b["parapetto"] = "muratura"
                spec_b["spessore_parapetto_m"] = round(min(0.40, max(0.06, _larghezza(anelli[0]))), 2)
            schede_balconi.append(spec_b)
            let.balconi.append((bid, soletta))
        if schede_balconi:
            let.dubbi.append(f"{len(schede_balconi)} balconi: parapetto alto 1,00 m (predefinito: il disegno non lo indica)")

    # chiusure rimaste senza compagna dall'altro lato del muro: il vano è il vuoto tra le masse oltre quel lato
    poligoni_stanze0 = unary_union([st["pol"] for st in let.stanze]) if let.stanze else None
    gia_vani = unary_union([r for r, _ in vani]) if vani else None
    involucro = unary_union(masse + [r for r, _ in vani] + [st["pol"] for st in let.stanze]).buffer(0.003).buffer(-0.003)
    involucro = Polygon(max((involucro.geoms if hasattr(involucro, "geoms") else [involucro]), key=lambda x: x.area).exterior)

    def profondita_muro(c, n):
        """Spessore del muro all'apertura: la lunghezza delle spallette, cioè dei lati delle masse che partono dai
        due capi della chiusura e vanno dentro il muro (lungo n). Vale la spalletta più corta."""
        valori = []
        for e in (c.coords[0], c.coords[-1]):
            migliore = 0.0
            for massa in masse:
                for anello in [massa.exterior] + list(massa.interiors):
                    cc = list(anello.coords)[:-1]
                    for i, v in enumerate(cc):
                        if math.dist(v, e) > 0.02:
                            continue
                        for w in (cc[i - 1], cc[(i + 1) % len(cc)]):
                            L = math.dist(v, w)
                            if L <= 1e-6:
                                continue
                            lungo_n = ((w[0] - v[0]) * n[0] + (w[1] - v[1]) * n[1])
                            if lungo_n / L >= 0.6:
                                migliore = max(migliore, min(lungo_n, SPESSORE_MAX))
            if migliore > 0:
                valori.append(migliore)
        if valori:
            return min(valori)
        # chiusura da una linea di infisso (non parte da un vertice): dal centro fino al filo esterno dell'edificio
        mx, my = (c.coords[0][0] + c.coords[-1][0]) / 2, (c.coords[0][1] + c.coords[-1][1]) / 2
        for k in range(1, 41):
            d = 0.02 * k
            if not involucro.contains(Point(mx + n[0] * d, my + n[1] * d)):
                return d if d <= SPESSORE_MAX else 0.0
        return 0.0

    def fascia_dalla_stanza(c):
        """La stanza arriva fino al filo esterno: la fascia profonda quanto il muro diventa il vano e si toglie
        dalla stanza."""
        nonlocal gia_vani
        if c.distance(involucro.exterior) < 0.01 and c.intersection(involucro.exterior.buffer(0.01)).length > 0.8 * c.length:
            (ax, ay), (bx, by) = c.coords[0], c.coords[-1]
            n = (-(by - ay) / c.length, (bx - ax) / c.length)
            if not involucro.contains(Point((ax + bx) / 2 + n[0] * 0.05, (ay + by) / 2 + n[1] * 0.05)):
                n = (-n[0], -n[1])
            prof = profondita_muro(c, n)
            if prof >= SPESSORE_MIN:
                fascia = Polygon([(ax, ay), (bx, by), (bx + n[0] * prof, by + n[1] * prof), (ax + n[0] * prof, ay + n[1] * prof)])
                for st in let.stanze:
                    parte = st["pol"].intersection(fascia)
                    if parte.area > 0.02:
                        q = parte if parte.geom_type == "Polygon" else max(parte.geoms, key=lambda x: x.area)
                        resto = st["pol"].difference(fascia.buffer(0.001)).buffer(0)
                        if resto.geom_type != "Polygon":
                            resto = max(resto.geoms, key=lambda x: x.area)
                        st["pol"] = resto
                        st["spec"]["poligono_m"] = [[round(x, 3), round(y, 3)] for x, y in list(resto.exterior.coords)[:-1]]
                        vani.append((fascia, c.length))                 # sempre un rettangolo: la fascia del muro
                        gia_vani = unary_union([gia_vani, q]) if gia_vani is not None else q
                        return

    for c in chiusure:
        if gia_vani is not None and c.distance(gia_vani) < 0.02 and c.intersection(gia_vani.buffer(0.02)).length > 0.4 * c.length:
            continue                                    # la stessa apertura vista dall'altro lato del muro
        intorno = c.buffer(0.6, cap_style="flat")
        vuoto = intorno.difference(unione.buffer(0.001))
        if poligoni_stanze0 is not None:
            vuoto = vuoto.difference(poligoni_stanze0.buffer(0.001))
        if gia_vani is not None:
            vuoto = vuoto.difference(gia_vani.buffer(0.001))
        # fuori dall'involucro va bene solo se la chiusura è il bordo di una stanza (la soglia della porta d'ingresso);
        # altrimenti è un vuoto esterno, per esempio la rientranza di una portafinestra vista dal balcone
        bordo_di_stanza = any(c.intersection(st["pol"].exterior.buffer(0.01)).length > 0.8 * c.length for st in let.stanze)
        pezzi = [q for q in (vuoto.geoms if hasattr(vuoto, "geoms") else [vuoto])
                 if q.geom_type == "Polygon" and q.distance(c) < 0.01 and q.area > 0.02
                 and (bordo_di_stanza or involucro.buffer(-0.01).contains(q.representative_point()))]
        if not pezzi:
            fascia_dalla_stanza(c)
            continue
        q = max(pezzi, key=lambda x: x.area)
        # profondità: la lunghezza delle spallette ai due capi dell'apertura
        (ax, ay), (bx, by) = c.coords[0], c.coords[-1]
        L = c.length
        u = ((bx - ax) / L, (by - ay) / L)
        n = (-u[1], u[0])
        cq = q.centroid
        if (cq.x - ax) * n[0] + (cq.y - ay) * n[1] < 0:
            n = (-n[0], -n[1])
        profondita = profondita_muro(c, n)
        if profondita < SPESSORE_MIN:
            fascia_dalla_stanza(c)              # oltre la chiusura c'è il fuori, non un muro: il vano sta dietro
            continue
        fascia = Polygon([(ax, ay), (bx, by), (bx + n[0] * profondita, by + n[1] * profondita),
                          (ax + n[0] * profondita, ay + n[1] * profondita)])
        q = q.intersection(fascia).buffer(0)
        if q.geom_type != "Polygon":
            q = max((g_ for g_ in getattr(q, "geoms", []) if g_.geom_type == "Polygon"), key=lambda x: x.area, default=None)
        if q is None or q.area < 0.02:
            continue
        rett, sguinci = _rettangolo_di_luce(q, c, n, profondita)
        if rett is None:
            continue
        masse.extend(sguinci)
        vani.append((rett, rett_larghezza(rett, c)))
        gia_vani = unary_union([gia_vani, q]) if gia_vani is not None else q

    # garanzia: ogni vano è un rettangolo (porte e finestre si costruiscono squadrate); il resto del vuoto è muro
    squadrati = []
    bordo_masse = unary_union([m.boundary for m in masse]) if masse else None
    for vano in vani:
        poli = vano[0]
        r = poli.minimum_rotated_rectangle
        if r.area > 0 and poli.area / r.area >= 0.9999:
            squadrati.append((r, vano[1]))
            continue
        # il rettangolo si appoggia al lato libero del vuoto (la chiusura verso una stanza o l'esterno), non ai lati
        # che toccano il muro: un vuoto con una spalletta storta non deve ruotare il vano
        cc = list(poli.exterior.coords)[:-1]
        lati = []
        for i in range(len(cc)):
            seg = LineString([cc[i], cc[(i + 1) % len(cc)]])
            contatto = seg.intersection(bordo_masse.buffer(0.005)).length if bordo_masse is not None else 0.0
            lati.append((seg.length - contatto, seg.length, seg))
        _, L_, c_ = max(lati, key=lambda x: (x[0], x[1]))
        a_, b_ = c_.coords[0], c_.coords[-1]
        n_ = (-(b_[1] - a_[1]) / L_, (b_[0] - a_[0]) / L_)
        cen = poli.centroid
        if (cen.x - a_[0]) * n_[0] + (cen.y - a_[1]) * n_[1] < 0:
            n_ = (-n_[0], -n_[1])
        alto = max((x - a_[0]) * n_[0] + (y - a_[1]) * n_[1] for x, y in cc)
        dentro = poli.buffer(0.003)

        def prova(prof_):
            rett_ = _rettangolo_di_luce(poli, c_, n_, prof_)[0]
            return rett_ if rett_ is not None and rett_.within(dentro) else None
        rett = prova(alto)
        if rett is None:                            # la profondità più grande che resta dentro il vuoto
            basso = 0.0
            for _ in range(14):
                medio = (basso + alto) / 2
                r_ = prova(medio)
                if r_ is not None:
                    rett, basso = r_, medio
                else:
                    alto = medio
        if rett is None:
            continue
        resto = poli.difference(rett.buffer(0.001))
        masse.extend(gm for gm in (resto.geoms if hasattr(resto, "geoms") else [resto])
                     if gm.geom_type == "Polygon" and gm.area > 1e-4)
        squadrati.append((rett, rett_larghezza(rett, c_)))
    vani = squadrati

    # vani: il tipo si decide dalle stanze ai due lati (dopo averle riconosciute)
    infissi_seg = [LineString([m(a), m(b)]) for l, a, b in segmenti if l in ruoli["infissi"]]
    archi_m = [Point(m(c)).buffer(r * fattore) for l, c, r in archi if l in ruoli["infissi"]]
    poligoni_stanze = [st["pol"] for st in let.stanze]
    elenco_vani, conta = [], {}
    for vano in vani:
        rett, dist = vano[0], vano[1]
        faccia = vano[2] if len(vano) > 2 else None
        sulla_griglia = _sulla_griglia(rett)
        if not faccia and sulla_griglia and len(sulla_griglia[0].exterior.coords) == 5:
            rett = sulla_griglia[0]                     # stessa griglia delle masse
        c = rett.centroid
        q = list(rett.minimum_rotated_rectangle.exterior.coords)[:4] if faccia else list(rett.exterior.coords)[:4]
        if math.dist(q[0], q[1]) < math.dist(q[1], q[2]):
            q = q[1:] + q[:1]                       # q0-q1 è un lato lungo (la larghezza): u attraversa il muro
        m1 = ((q[0][0] + q[1][0]) / 2, (q[0][1] + q[1][1]) / 2)
        m2 = ((q[2][0] + q[3][0]) / 2, (q[2][1] + q[3][1]) / 2)
        L12 = math.dist(m1, m2) or 1.0
        u = ((m2[0] - m1[0]) / L12, (m2[1] - m1[1]) / L12)
        def stanza_dal_lato(origine, verso):
            # si avanza dal vano finché si trova una stanza o un muro (gli sguinci profondi non contano)
            for passo in (0.06, 0.12, 0.20, 0.30, 0.40, 0.55, 0.70):
                pt = Point(origine[0] + verso[0] * passo, origine[1] + verso[1] * passo)
                if any(sp.contains(pt) for sp in poligoni_stanze):
                    return True
                if unione.contains(pt):
                    return False
            return False
        in_stanza = [stanza_dal_lato(m1, (-u[0], -u[1])), stanza_dal_lato(m2, u)]
        lati = [Point(m1[0] - u[0] * 0.10, m1[1] - u[1] * 0.10), Point(m2[0] + u[0] * 0.10, m2[1] + u[1] * 0.10)]
        vetri = [s for s in infissi_seg if s.intersects(rett.buffer(0.02)) and s.length > 0.25 * dist]
        arco = any(a.intersects(rett.buffer(0.05)) for a in archi_m)
        interno = all(in_stanza)
        ante_scorrevoli = _ante_scorrevoli(rett, dist, infissi_seg) if interno else 0
        quote = _quote_vicine(testi_m, (c.x, c.y))
        nota, larghezza, altezza = "", dist, None
        if quote:
            l_cm, h_cm = quote
            if abs(l_cm / 100 - dist) <= 0.08:
                larghezza, altezza = l_cm / 100, h_cm / 100
                nota = f"quote scritte {l_cm}/{h_cm}"
        # un vuoto senza alcun segno (infisso, soglia, arco, quota) accanto a un muro a spessore ipotizzato nasce
        # dall'ipotesi, non dal disegno: è muro
        segni = vetri or arco or nota or any(pr.intersects(rett.buffer(0.02)) for pr in proiezioni)
        if not segni and any(rett.distance(ip) < 0.01 for ip in ipotizzate):
            masse.append(rett)
            continue
        if interno:
            tipo = "vano" if (dist > 1.30 and not vetri and not arco and not ante_scorrevoli) else "porta"
        elif not any(in_stanza) and not arco:
            masse.append(rett)                                # vuoto tra due muri senza stanza da nessuna parte: muro
            continue
        elif arco:
            tipo = "porta"                                    # porta d'ingresso (arco dell'anta)
        else:
            # sul balcone si esce: portafinestra anche senza quota scritta (una quota larghezza/altezza: finestra)
            fuori = lati[1] if in_stanza[0] else lati[0]
            sul_balcone = any(bp.buffer(0.35).contains(fuori) for _, bp in let.balconi)
            tipo = "portafinestra" if ((altezza and altezza >= 2.20) or (altezza is None and sul_balcone)) else "finestra"
        conta[tipo] = conta.get(tipo, 0) + 1
        vid = {"finestra": "Finestra", "portafinestra": "Porta finestra", "porta": "Porta", "vano": "Passaggio"}[tipo] + f" {conta[tipo]}"
        spec = {"id": vid, "tipo": tipo, "poligono_m": [[round(x, 4), round(y, 4)] for x, y in
                                                        (list(rett.exterior.coords)[:-1] if faccia else q)]}
        if faccia:
            spec["faccia_m"] = [[round(x, 4), round(y, 4)] for x, y in faccia]   # stessa precisione delle masse
        if tipo == "finestra":
            spec["altezza_m"] = altezza or 1.40
            spec["quota_davanzale_m"] = round(max(0.0, 2.75 - spec["altezza_m"]), 2) if altezza else 1.00
            let.dubbi.append(f"{vid}: davanzale non scritto, {spec['quota_davanzale_m']:.2f} m"
                             + (f" (architrave a 2,75 m con l'altezza scritta {altezza:.2f})" if altezza else " (predefinito)"))
            if not vetri:
                let.dubbi.append(f"{vid}: nessun infisso disegnato nel vano, letto come finestra perché dà sull'esterno")
        elif tipo == "portafinestra":
            spec["altezza_m"] = altezza if (altezza and altezza >= 2.0) else 2.40
            if not (altezza and altezza >= 2.0):
                let.dubbi.append(f"{vid}: altezza non scritta, 2,40 m (predefinito per una porta finestra)")
        else:
            spec["altezza_m"] = 2.10
            if tipo == "porta" and not interno:
                spec["ingresso"] = True
            if ante_scorrevoli:
                spec["apertura"] = "scorrevole"
                spec["ante"] = ante_scorrevoli
                let.letti.append(f"{vid}: {ante_scorrevoli} {'ante scorrevoli' if ante_scorrevoli > 1 else 'anta scorrevole'} "
                                 "(disegnate accanto al vano, lungo il muro)")
        elenco_vani.append(spec)
        let.vani.append((vid, tipo, rett, larghezza, nota))

    if blocchi:
        let.dubbi.append(f"{len(blocchi)} blocchi nel disegno ({', '.join(sorted(set(blocchi)))}): arredi non importati")
    altezze = [st["altezza"] for st in let.stanze if st.get("altezza")]
    H = max(altezze) if altezze else 2.70
    schede_masse = []
    from shapely.geometry import JOIN_STYLE as _JS
    bordo_esterno = Polygon(involucro.exterior).exterior
    k = 0
    for i_m, poly in enumerate(masse, 1):
        ipot = i_m > len(chiuse)
        # nel CAD un muro esterno e un tramezzo che vi arriva sono spesso un solo contorno: si separano per spessore
        spesse = poly.buffer(-0.09, join_style=_JS.mitre).buffer(0.09, join_style=_JS.mitre).intersection(poly)
        sottili = poly.difference(spesse.buffer(0.0005))
        pezzi = []
        for geom in (spesse, sottili):
            pezzi += [g for g in (geom.geoms if hasattr(geom, "geoms") else [geom]) if g.geom_type == "Polygon" and g.area > 2e-4]
        if not pezzi:
            pezzi = [poly]
        # griglia comune di 1 mm per masse e vani: i vertici condivisi restano identici, i lati più corti spariscono
        pezzi = [q for pz in pezzi for q in _sulla_griglia(pz)]
        for pezzo in pezzi:
            k += 1
            classe = "tamponatura" if pezzo.distance(bordo_esterno) < 0.02 else "tramezzo"
            coords = [[round(x, 4), round(y, 4)] for x, y in list(pezzo.exterior.coords)[:-1]]
            schede_masse.append({"id": f"M{k}", "poligono_m": coords, "classe": classe})
            let.masse.append((f"M{k}", classe, pezzo, ipot))
    let.letti.append(f"{len(masse)} masse murarie ({len(ipotizzate)} con spessore ipotizzato), {len(elenco_vani)} vani, "
                     f"{len(schede_stanze)} stanze, {len(schede_balconi)} balconi; altezza del piano {H:.2f} m")
    piano = {"id": "Piano", "altezza_m": H, "muri": schede_masse, "vani": elenco_vani, "stanze": schede_stanze}
    if schede_balconi:
        piano["balconi"] = schede_balconi
    let.scheda = {"progetto": nome, "comune": "Roma", "destinazione": "abitazione", "intervento": "esistente",
                  "edificio": {"soffitto": True, "piani": [piano]}}
    return let
