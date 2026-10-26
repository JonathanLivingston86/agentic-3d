"""Edifici e appartamenti: più stanze, pareti a rete con giunti, aperture, arredi, più piani.

Scheda (vedi `skills/da-disegno-a-modello`):

    edificio:
      soffitto: true                 # soffitti sull'ultimo piano (false = aperto sopra)
      fascia_altezza_m: 1.20         # solo se il disegno o l'utente la chiedono: fascia di colore sulle pareti
      piani:
        - id: Piano terra
          altezza_m: 2.70
          spessore_solaio_m: 0.10    # solaio sotto il pavimento di questo piano (0,30 sopra il piano terra)
          pareti: [{id: A, da: [0, 0], a: [8, 0], spessore_m: 0.30}, ...]   # asse della parete
          stanze: [{id: Soggiorno, tipo: soggiorno, poligono_m: [[0.15, 0.15], ...]}, ...]  # filo interno
          aperture: [...]            # su una parete (`parete`, `lato`, `da_m`) o su una stanza (`stanza`, `parete: nord`)
          arredi: [...]              # gli stessi tipi delle stanze singole, più `oggetto` (forme libere)

Coordinate globali in metri: X est, Y nord, Z alto. I pezzi si chiamano `Muro <id>`, `Pavimento <stanza>`,
`Soffitto <stanza>`; con più piani il nome del piano precede.
"""

from __future__ import annotations

from . import geom2d as g
from .aperture import serramento
from .ergonomia import registra_finestra, registra_porta
from .architettura import lastra, muro
from .arredi import Contesto, arredo
from .forme import telaio_cardinale
from . import muri_impronta as mi
from .pareti import Pezzo, faccia_che_copre, pezzo_che_contiene, risolvi, sovrapposizioni
from .scena import Oggetto, Scena

CARDINALI = {"est": (1.0, 0.0), "nord": (0.0, 1.0), "ovest": (-1.0, 0.0), "sud": (0.0, -1.0)}


def alza(ob: Oggetto, dz: float) -> Oggetto:
    """Sposta in alto un oggetto (piani sopra il terra)."""
    if dz:
        ob.origine = (ob.origine[0], ob.origine[1], ob.origine[2] + dz)
        nuove = []
        for q in ob.parti:
            a, b = (q[0][0], q[0][1], q[0][2] + dz), (q[1][0], q[1][1], q[1][2] + dz)
            if len(q) > 2:
                c, assi, mezzi = q[2]
                nuove.append((a, b, ((c[0], c[1], c[2] + dz), assi, mezzi)))
            else:
                nuove.append((a, b))
        ob.parti = nuove
    return ob


def _gruppo(categoria: str, piano: dict, k: int, multi: bool) -> str:
    """Contenitore in SketchUp: la categoria, preceduta dal piano se l'edificio ne ha più di uno."""
    return f"{categoria} {piano.get('id', f'Piano {k + 1}')}" if multi else categoria


def _rettangolo(poligono):
    """(x0, y0, x1, y1) se il poligono è un rettangolo con i lati sugli assi, altrimenti None."""
    if len(poligono) != 4:
        return None
    xs, ys = [p[0] for p in poligono], [p[1] for p in poligono]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if abs(g.area(poligono) - (x1 - x0) * (y1 - y0)) < 1e-6:
        return (x0, y0, x1, y1)
    return None


class _Stanza:
    def __init__(self, spec: dict):
        self.id = str(spec["id"])
        self.spec = spec
        self.poligono = g.antiorario([tuple(map(float, p)) for p in spec["poligono_m"]])
        if len(self.poligono) < 3:
            raise ValueError(f"stanza {self.id}: servono almeno 3 vertici in poligono_m")
        if g.area(self.poligono) < 0.5:
            raise ValueError(f"stanza {self.id}: {g.area(self.poligono):.2f} m2, sotto il minimo di 0,5 m2 per una stanza: "
                             "unirla alla stanza accanto o toglierla dalla scheda (il pavimento resta)")
        self.rett = _rettangolo(self.poligono)

    def centro(self):
        return g.baricentro(self.poligono)


def _direzione_cerniera(valore, eu) -> str:
    """Converte la cerniera della scheda ('est', 'nord'... oppure 'inizio'/'fine') nel lato di u."""
    if valore in ("inizio", "fine"):
        return valore
    if valore in CARDINALI:
        return "fine" if g.dot(CARDINALI[valore], eu) > 0 else "inizio"
    return "fine"


def _risolvi_apertura(ap: dict, pezzi: list[Pezzo], stanze: dict[str, _Stanza]):
    """(pezzo, lato, u0, u1) dell'apertura sulla rete di pareti."""
    larg = float(ap["larghezza_m"])
    if "stanza" in ap:
        st = stanze.get(ap["stanza"])
        if st is None:
            raise ValueError(f"{ap['id']}: stanza {ap['stanza']!r} sconosciuta")
        if st.rett is None:
            raise ValueError(f"{ap['id']}: la stanza {st.id} non è un rettangolo con i lati sugli assi: "
                             "indica la parete con `parete: <id>` e `lato`")
        f = telaio_cardinale(ap["parete"], *st.rett)
        pa = f(ap["da_m"], 0.0, 0.0)[:2]
        pb = f(ap["da_m"] + larg, 0.0, 0.0)[:2]
        trovata = faccia_che_copre(pezzi, pa, pb)
        if trovata is None:
            raise ValueError(f"{ap['id']}: lungo il lato {ap['parete']} della stanza {st.id} non c'è una parete "
                             "(il filo interno della stanza deve coincidere con la faccia della parete)")
        w, lato, _ = trovata
        ua, ub = g.dot(g.sottrai(pa, w.p0), w.eu), g.dot(g.sottrai(pb, w.p0), w.eu)
        return w, lato, min(ua, ub), max(ua, ub)
    w, u0 = pezzo_che_contiene(pezzi, str(ap["parete"]), float(ap["da_m"]), float(ap["da_m"]) + larg)
    return w, ap.get("lato", "sinistra"), u0, u0 + larg


def _contesto_arredo(sp: dict, stanze: dict[str, _Stanza], pezzi: list[Pezzo], altezza: float, arredi: list[dict]) -> Contesto:
    if "stanza" in sp:
        st = stanze.get(sp["stanza"])
        if st is None:
            raise ValueError(f"{sp.get('id')}: stanza {sp['stanza']!r} sconosciuta")
        if st.rett is None:
            raise ValueError(f"{sp.get('id')}: la stanza {st.id} non è un rettangolo con i lati sugli assi: "
                             "indica la parete con `parete: <id>` e `lato`")
        x0, y0, x1, y1 = st.rett
        return Contesto({p: telaio_cardinale(p, x0, y0, x1, y1) for p in CARDINALI},
                        {"sud": x1 - x0, "nord": x1 - x0, "ovest": y1 - y0, "est": y1 - y0}, altezza, arredi)
    pid = sp.get("parete")
    if pid is not None:
        propri = [p for p in pezzi if p.origine_id == str(pid)]
        if not propri:
            raise ValueError(f"{sp.get('id')}: parete {pid!r} sconosciuta")
        if propri[0].curva:
            raise ValueError(f"{sp.get('id')}: gli arredi su pareti curve non sono supportati")
        lato = sp.get("lato", "sinistra")
        return Contesto({str(pid): propri[0].telaio(lato)}, {str(pid): sum(p.lunghezza for p in propri)}, altezza, arredi)
    return Contesto({}, {}, altezza, arredi)


def _copertura_dal_piano_sopra(st: "_Stanza", piano_sopra: dict) -> float:
    """Frazione (0-1) della stanza che ha sopra una stanza del piano superiore, per campionamento."""
    sopra = [g.antiorario([tuple(map(float, p)) for p in s["poligono_m"]]) for s in piano_sopra.get("stanze", [])]
    xs, ys = [p[0] for p in st.poligono], [p[1] for p in st.poligono]
    dentro = coperti = 0
    n = 14
    for i in range(n):
        for j in range(n):
            p = (min(xs) + (max(xs) - min(xs)) * (i + 0.5) / n, min(ys) + (max(ys) - min(ys)) * (j + 0.5) / n)
            if g.punto_in_poligono(p, st.poligono):
                dentro += 1
                coperti += any(g.punto_in_poligono(p, s) for s in sopra)
    return coperti / dentro if dentro else 1.0


def _quote(piani: list[dict]) -> list[tuple[float, float, float]]:
    """(quota del pavimento finito, altezza netta, spessore del solaio sotto) per ogni piano."""
    out = []
    for k, p in enumerate(piani):
        h = float(p["altezza_m"])
        s = float(p.get("spessore_solaio_m", 0.10 if k == 0 else 0.30))
        if "quota_m" in p:
            q = float(p["quota_m"])
        elif k == 0:
            q = 0.0
        else:
            q = out[-1][0] + out[-1][1] + s
        out.append((q, h, s))
    return out


def _controlla_stanze_su_pareti(scena: Scena, pid: str, stanze, pezzi, bordo_masse=None):
    """Avvisi se il filo interno di una stanza non coincide con le facce delle pareti o con il bordo delle masse
    murarie (tolleranza 2 cm)."""
    for st in stanze.values():
        n = len(st.poligono)
        for i in range(n):
            a, b = st.poligono[i], st.poligono[(i + 1) % n]
            lung = g.lunghezza(g.sottrai(b, a))
            scoperti = 0
            for k in range(1, 10):
                p = g.somma(a, g.per(g.sottrai(b, a), k / 10.0))
                vicino = False
                if bordo_masse is not None:
                    from shapely.geometry import Point
                    vicino = bordo_masse.distance(Point(p)) <= 0.02
                    # lato in comune con un'altra stanza: un passaggio aperto, non un muro mancante
                    vicino = vicino or any(altra is not st and min(
                        g.distanza_punto_segmento(p, altra.poligono[j], altra.poligono[(j + 1) % len(altra.poligono)])
                        for j in range(len(altra.poligono))) <= 0.02 for altra in stanze.values())
                for w in pezzi.vicine(p, 0.05):
                    for lato in ("sinistra", "destra"):
                        h = w.hs if lato == "sinistra" else -w.hd
                        d_perp = g.dot(g.sottrai(p, w.p0), w.en) - h
                        u = g.dot(g.sottrai(p, w.p0), w.eu)
                        if abs(d_perp) <= 0.02 and -0.02 <= u <= w.lunghezza + 0.02:
                            vicino = True
                    # testa del muro (estremo libero, pilastro): il segmento tra le due facce all'estremo
                    for e in (0, 1):
                        a_t, b_t = w.punto_faccia(w.ui[e], "sinistra"), w.punto_faccia(w.uo[e], "destra")
                        if g.distanza_punto_segmento(p, a_t, b_t) <= 0.02:
                            vicino = True
                if not vicino:
                    scoperti += 1
            if scoperti > 1 and lung > 0.05:
                scena.note.append(f"{pid}, stanza {st.id}: il lato {i + 1} ({a[0]:.2f}; {a[1]:.2f}) -> ({b[0]:.2f}; {b[1]:.2f}) "
                                  "non coincide con la faccia di una parete (tolleranza 2 cm)")


def unisci_oggetti(nome: str, oggetti: list[Oggetto], tipo: str, gruppo: str = "") -> Oggetto:
    """Un solo oggetto con le mesh (in coordinate del mondo) e le parti di controllo di più oggetti."""
    from .mesh import Mesh
    mesh = Mesh()
    for o in oggetti:
        ox, oy, oz = o.origine
        copia = Mesh()
        copia.aggiungi(o.mesh)
        copia.trasforma(lambda v, ox=ox, oy=oy, oz=oz: (v[0] + ox, v[1] + oy, v[2] + oz))
        mesh.aggiungi(copia)
    primo = oggetti[0]
    return Oggetto(nome, mesh, (0.0, 0.0, 0.0), primo.collezione, primo.categoria, tipo,
                   [q for o in oggetti for q in o.parti], True, gruppo or nome)


def componi(ob: Oggetto, sp: dict, riferimento: Oggetto, quota: float) -> None:
    """Oggetto ripetuto (`componente: <nome>` nella scheda): la definizione è la stessa forma costruita senza
    posizione e senza rotazione; la copia è la definizione ruotata attorno alla verticale e spostata. In SketchUp le
    copie sono un componente: una sola geometria, e cambiandola cambiano tutte."""
    import math
    if "posizione_m" not in sp:
        raise ValueError(f"{sp.get('id')}: un componente si posiziona con `posizione_m` (e `rotazione_gradi`)")
    riferimento.nome = str(sp["componente"])
    ang = math.radians(float(sp.get("rotazione_gradi", 0.0)))
    c, s = math.cos(ang), math.sin(ang)
    x, y = (float(v) for v in sp["posizione_m"][:2])
    o = riferimento.origine
    tx, ty, tz = c * o[0] - s * o[1] + x, s * o[0] + c * o[1] + y, o[2] + quota
    ob.componente = str(sp["componente"])
    ob.definizione = riferimento
    ob.matrice = (c, s, 0.0, 0.0, -s, c, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, tx, ty, tz, 1.0)


def _contorno_dei_muri(pezzi: list, z0: float, z1: float, stanze) -> list | None:
    """Contorno esterno dell'impronta di tutti i muri di un piano (il filo esterno delle tamponature): è il bordo del
    pavimento e del soffitto, come nelle stanze singole (convenzione del modello). None se i muri non
    chiudono un anello attorno a tutte le stanze."""
    from .muri_uniti import muri_uniti as unisci_muri
    from .mesh import triangola_poligono
    from .sketchup import anelli_di_bordo
    try:
        ob = unisci_muri("contorno", [{"w": w, "tagli": [], "fascia_a": False, "fascia_b": False} for w in pezzi], z0, z1)
    except ValueError:
        return None
    m = ob.mesh
    sopra = [f for f in m.f if all(abs(m.v[i][2] - z1) < 1e-9 for i in f)]
    chiave = {}
    ids = {}
    for f in sopra:
        for i in f:
            k = (round(m.v[i][0], 7), round(m.v[i][1], 7))
            ids[i] = chiave.setdefault(k, len(chiave))
    conta: dict[tuple[int, int], int] = {}
    for f in sopra:
        for a in range(len(f)):
            e = (ids[f[a]], ids[f[(a + 1) % len(f)]])
            if e[0] != e[1]:
                conta[e] = conta.get(e, 0) + 1
    bordo = [(i, j) for (i, j), n in conta.items() if n > conta.get((j, i), 0)]
    punti = {v: k for k, v in chiave.items()}
    anelli = anelli_di_bordo(bordo, punti)
    if not anelli:
        return None
    esterno = max(anelli, key=lambda a: g.area([punti[i] for i in a]))
    poli = [punti[i] for i in esterno]
    if g.area(poli) <= 0:
        return None
    for st in stanze:
        a, b, c = triangola_poligono([(x, y, 0.0) for x, y in st.poligono])[0]
        prova = tuple(sum(st.poligono[i][k] for i in (a, b, c)) / 3 for k in range(2))
        if not g.punto_in_poligono(prova, poli):
            return None
    return poli


# ------------------------------------------------------------------ controsoffitti e balconi
# Il controsoffitto è pieno dalla sua quota fino all'intradosso del solaio: una lastra sottile lascerebbe una tasca
# vuota sopra, visibile nei render, e senza le facce verticali del cartongesso dove cambia quota.


def poligoni_semplici(geom, area_min: float = 0.005) -> list[list[tuple[float, float]]]:
    """Poligoni senza fori (in senso antiorario) da una geometria Shapely: un poligono con un foro si divide con
    una linea verticale che passa per il foro, così ogni pezzo si estrude come lastra semplice."""
    from shapely.geometry import LineString, MultiPolygon, Polygon
    from shapely.ops import split
    if geom.is_empty:
        return []
    pezzi = list(geom.geoms) if isinstance(geom, MultiPolygon) or hasattr(geom, "geoms") else [geom]
    out = []
    for p in pezzi:
        if not isinstance(p, Polygon) or p.area < area_min:
            continue
        if p.interiors:
            x = p.interiors[0].centroid.x
            y0, y1 = p.bounds[1] - 1, p.bounds[3] + 1
            out += poligoni_semplici(split(p, LineString([(x, y0), (x, y1)])), area_min)
            continue
        out.append(g.antiorario([(float(a), float(b)) for a, b in list(p.exterior.coords)[:-1]]))
    return out


def parti_di_poligono(poligono, z0: float, z1: float) -> list:
    """Parti di controllo di una lastra concava: una scatola per triangolo (non la scatola di tutto il poligono, che
    in una stanza a L coprirebbe anche la stanza accanto)."""
    from .mesh import triangola_poligono
    parti = []
    for a, b, c in triangola_poligono([(x, y, 0.0) for x, y in poligono]):
        xs = [poligono[i][0] for i in (a, b, c)]
        ys = [poligono[i][1] for i in (a, b, c)]
        parti.append(((min(xs), min(ys), z0), (max(xs), max(ys), z1)))
    return parti


def soffitti_della_stanza(st: "_Stanza", H: float) -> list[tuple[list, float]]:
    """(poligono, altezza) dei controsoffitti di una stanza: la stanza alla sua `altezza_m` e le zone
    `controsoffitti` alla loro; solo ciò che sta sotto l'altezza del piano H (sopra c'è già il solaio)."""
    from shapely.geometry import Polygon
    h_stanza = float(st.spec.get("altezza_m", H))
    resto = Polygon(st.poligono)
    out = []
    for k, z in enumerate(st.spec.get("controsoffitti", []) or []):
        hz = float(z["altezza_m"])
        if hz > H + 1e-6:
            raise ValueError(f"stanza {st.id}: il controsoffitto {k + 1} ({hz} m) supera l'altezza del piano ({H} m)")
        zona = Polygon([tuple(map(float, p)) for p in z["poligono_m"]])
        out += [(p, hz) for p in poligoni_semplici(zona.intersection(Polygon(st.poligono)))]
        resto = resto.difference(zona)
    out += [(p, h_stanza) for p in poligoni_semplici(resto)]
    return [(p, h) for p, h in out if h < H - 0.005]


def balcone(spec: dict, q: float, pref: str, sul_muro) -> Oggetto:
    """Balcone o terrazzo: soletta (2 cm sotto il pavimento di casa) e parapetto sui lati che non stanno contro
    l'edificio. `sul_muro(a, b)` dice se il lato a-b sta contro un muro."""
    from .forme import Costruttore
    pol = g.antiorario([tuple(map(float, p)) for p in spec["poligono_m"]])
    spessore = float(spec.get("spessore_m", 0.15))
    z_top = q - float(spec.get("gradino_m", 0.02))
    h_par = float(spec.get("parapetto_m", 1.00))
    tipo_par = spec.get("parapetto", "vetro")
    nome_b = str(spec['id']) if str(spec['id']).lower().startswith(("balcone", "terrazz", "loggia")) else f"Balcone {spec['id']}"
    # soletta e parapetto sono solidi distinti (in SketchUp un gruppo ciascuno): nello stesso gruppo la base del
    # parapetto, complanare al calpestio, verrebbe fusa e persa
    c = Costruttore(f"{pref}{nome_b}", "Architettura", "balcone")
    c.estrusione(pol, z_top - spessore, z_top, spec.get("materiale", "Pietra grigia"), "Intonaco pareti", "Intonaco pareti")
    c.parti = parti_di_poligono(pol, z_top - spessore, z_top)
    lati = spec.get("lati_parapetto")
    n = len(pol)
    t = float(spec.get("spessore_parapetto_m", 0.12)) if tipo_par == "muratura" else 0.02

    def impronta(larghezza):
        """Il parapetto in pianta come una sola forma (unione delle fasce dei lati liberi): agli angoli i lati non
        si compenetrano, così in SketchUp ogni parte è un solido pulito."""
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        fasce = []
        for i in range(n):
            a, b = pol[i], pol[(i + 1) % n]
            if (lati is not None and i not in lati) or (lati is None and sul_muro(a, b)):
                continue
            d = g.unitario(g.sottrai(b, a))
            dentro = (-d[1], d[0])                   # poligono antiorario: l'interno è a sinistra
            fasce.append(Polygon([a, b, g.somma(b, g.per(dentro, larghezza)), g.somma(a, g.per(dentro, larghezza))]))
        if not fasce:
            return []
        forma = unary_union(fasce).intersection(Polygon(pol)).simplify(1e-6)
        return poligoni_semplici(forma, 1e-5)

    if h_par > 0:
        if tipo_par == "muratura":
            for pz in impronta(t):
                c.estrusione(pz, z_top, z_top + h_par, "Intonaco pareti")
        else:
            for pz in impronta(t):
                c.estrusione(pz, z_top, z_top + h_par - 0.04, "Vetro")
            for pz in impronta(0.04):
                c.estrusione(pz, z_top + h_par - 0.04, z_top + h_par, "Metallo nero")
    return c.chiudi()


def scena_da_edificio(scheda: dict, muri_uniti: bool = True) -> Scena:
    """Con `muri_uniti` (predefinito, convenzione del modello) tamponature e tramezzi di ogni piano sono
    due solidi e i soffitti di un piano uno solo; senza, un oggetto per pezzo di muro e per soffitto di stanza (usato
    per i render, dove si nasconde il muro tra la camera e la stanza)."""
    from .muri_uniti import muri_uniti as unisci_muri
    ed = scheda["edificio"]
    scena = Scena(scheda.get("progetto", "Progetto"))
    piani = ed["piani"]
    quote = _quote(piani)
    multi = len(piani) > 1
    scena.meta.update({"stanze": [], "finestre": [], "bbox": None})
    punti_ingombro: list[tuple[float, float]] = []
    soffitto_attivo = bool(ed.get("soffitto", True))

    for k, piano in enumerate(piani):
        q, H, s_pav = quote[k]
        ultimo = k == len(piani) - 1
        extra_alto = (0.10 if soffitto_attivo else 0.0) if ultimo else quote[k + 1][2]
        pref = f"{piano.get('id', f'Piano {k + 1}')} " if multi else ""
        fascia = piano.get("fascia_altezza_m", ed.get("fascia_altezza_m"))
        fascia_z = q + float(fascia) if fascia else None

        pezzi = risolvi(piano.get("pareti", []))
        for a_id, b_id, area in sovrapposizioni(pezzi):
            scena.note.append(f"{piano.get('id', f'Piano {k + 1}')}: le pareti {a_id} e {b_id} si sovrappongono "
                              f"({area:.2f} m2 in pianta): un pilastro o un risalto si disegna dal filo del muro "
                              "verso la stanza (uno per lato, se sporge da entrambi), non dentro o attraverso il muro")
        stanze = {}
        for s in piano.get("stanze", []):
            st = _Stanza(s)
            if st.id in stanze:
                raise ValueError(f"stanza duplicata: {st.id!r}")
            stanze[st.id] = st
        # muri a impronta (masse dal disegno CAD) e vani tra le masse
        masse = mi.masse_della_scheda(piano)
        forme_masse = [m for _, _, m in masse]
        vani = [mi.Vano(v, forme_masse) for v in piano.get("vani", []) or []]
        bordo_masse = None
        if masse:
            from shapely.ops import unary_union
            bordo_masse = unary_union(forme_masse + [v.forma for v in vani]).boundary
        _controlla_stanze_su_pareti(scena, piano.get("id", f"Piano {k + 1}"), stanze, pezzi, bordo_masse)

        # pavimento e soffitto fino al filo esterno dei muri, con spessore; i muri stanno tra i due
        if masse and not pezzi:
            contorno = mi.contorno(forme_masse, vani, [s.poligono for s in stanze.values()]) if stanze else None
        else:
            contorno = _contorno_dei_muri(list(pezzi), q, q + H, stanze.values()) if stanze else None
        if contorno is not None:
            z0w, z1w = q, q + H
        else:
            z0w, z1w = q - s_pav, q + H + extra_alto
            if stanze:
                scena.note.append(f"{piano.get('id', f'Piano {k + 1}')}: i muri non chiudono un anello attorno alle "
                                  "stanze: pavimenti e soffitti stanza per stanza, muri dal solaio al soffitto")

        # aperture risolte sulla rete
        tagli: dict[str, list[dict]] = {w.id: [] for w in pezzi}
        serramenti = []
        for ap in piano.get("aperture", []):
            w, lato, u0, u1 = _risolvi_apertura(ap, pezzi, stanze)
            fin = ap["tipo"] in ("finestra", "portafinestra")
            z_lo = q + (float(ap["quota_davanzale_m"]) if fin else 0.0)
            z_hi = z_lo + float(ap["altezza_m"])
            tagli[w.id].append({"u0": u0, "u1": u1, "z0": z_lo, "z1": z_hi})
            ap2 = dict(ap, da_m=u0, larghezza_m=u1 - u0)
            n_stanza = w.en if lato == "sinistra" else g.per(w.en, -1.0)
            if ap["tipo"] == "porta" and ap.get("apertura") == "scorrevole":
                pass                                  # ante scorrevoli: nessun arco di apertura da tenere libero
            elif ap["tipo"] == "porta":
                ap2["cerniera"] = _direzione_cerniera(ap.get("cerniera", "fine"), w.eu)
                # l'anta si apre verso la stanza del lato indicato (`apre_verso: opposto` per l'altra)
                opposta = ap.get("apre_verso") == "opposto"
                lato_apre = ("destra" if lato == "sinistra" else "sinistra") if opposta else lato
                n_apre = g.per(n_stanza, -1.0) if opposta else n_stanza
                in_fondo = ap2["cerniera"] == "fine"
                registra_porta(scena, ap["id"], w.punto_faccia(u1 if in_fondo else u0, lato_apre),
                               g.per(w.eu, -1.0 if in_fondo else 1.0), n_apre, (u1 - u0) - 0.008, q, q + float(ap["altezza_m"]))
            else:
                registra_finestra(scena, ap["id"], w.punto_faccia(u0, lato), w.punto_faccia(u1, lato), n_stanza, z_lo, z_hi)
            serramenti.append((ap2, w, lato))
            if fin:
                n = w.en if lato == "sinistra" else g.per(w.en, -1.0)
                scena.meta["finestre"].append({"id": ap["id"], "parete": w.origine_id, "direzione": n,
                                               "centro": w.punto_faccia((u0 + u1) / 2, lato), "quota": q})

        # pareti
        elenco = list(stanze.values())
        indice_stanze = g.IndiceCelle(3.0)
        for k2, st in enumerate(elenco):
            xs, ys = [q[0] for q in st.poligono], [q[1] for q in st.poligono]
            indice_stanze.aggiungi(k2, min(xs), min(ys), max(xs), max(ys), 0.1)

        def rivolta_a_stanza(w, lato):
            u = w.lunghezza / 2
            n = w.en if lato == "sinistra" else g.per(w.en, -1.0)
            p = g.somma(w.punto_faccia(u, lato), g.per(n, 0.05))
            return any(g.punto_in_poligono(p, elenco[k2].poligono) for k2 in indice_stanze.vicini(p))

        classi = {str(s["id"]): s.get("classe") for s in piano.get("pareti", [])}
        per_categoria: dict[str, list[dict]] = {"Tamponature": [], "Tramezzi": []}
        for w in pezzi:
            verso_a, verso_b = rivolta_a_stanza(w, "sinistra"), rivolta_a_stanza(w, "destra")
            fa = bool(fascia_z) and verso_a
            fb = bool(fascia_z) and verso_b
            # tamponatura = con una faccia verso l'esterno (nessuna stanza); tramezzo = stanza su entrambi i lati
            classe = classi.get(w.origine_id) or ("tramezzo" if verso_a and verso_b else "tamponatura")
            categoria = "Tramezzi" if classe == "tramezzo" else "Tamponature"
            if muri_uniti:
                per_categoria[categoria].append({"w": w, "tagli": tagli[w.id], "fascia_a": fa, "fascia_b": fb})
            else:
                ob = scena.aggiungi(muro(f"{pref}Muro {w.id}", w.telaio_solido(), w.spessore, z0w, z1w, w.ui, w.uo,
                                         tagli[w.id], fascia_z, fascia_a=fa, fascia_b=fb))
                ob.gruppo = _gruppo(categoria, piano, k, multi)
            punti_ingombro += [w.punto_faccia(u, "sinistra") for u in w.ui] + [w.punto_faccia(u, "destra") for u in w.uo]
        for categoria, elenco_pezzi in per_categoria.items():
            if elenco_pezzi:
                nome_cat = _gruppo(categoria, piano, k, multi)
                scena.aggiungi(unisci_muri(nome_cat, elenco_pezzi, z0w, z1w, fascia_z)).gruppo = _gruppo("Muri", piano, k, multi)

        # muri a impronta: un solido per classe (convenzione del modello), un oggetto per massa nei render
        if masse:
            def classe_del_vano(v):
                for _, classe, m in masse:
                    if v.forma.distance(m) < mi.TOL:
                        return classe
                return "tamponatura"
            for classe, categoria in (("tamponatura", "Tamponature"), ("tramezzo", "Tramezzi")):
                propri = [(mid, m) for mid, c, m in masse if c == classe]
                vani_propri = [v for v in vani if classe_del_vano(v) == classe]
                if not propri:
                    continue
                if muri_uniti:
                    ob = mi.solido(_gruppo(categoria, piano, k, multi), [m for _, m in propri], vani_propri, z0w, z1w)
                    scena.aggiungi(ob).gruppo = _gruppo("Muri", piano, k, multi)
                else:
                    for mid, m in propri:
                        scena.aggiungi(mi.solido(f"{pref}Muro {mid}", [m], [], z0w, z1w)).gruppo = _gruppo(categoria, piano, k, multi)
                    for v in vani_propri:
                        scena.aggiungi(mi.solido(f"{pref}Muro {v.id}", [], [v], z0w, z1w)).gruppo = _gruppo(categoria, piano, k, multi)
            elenco_st = list(stanze.values())
            for v in vani:
                lato_stanza = 1 if any(g.punto_in_poligono(v.punto_di_lato(1), s.poligono) for s in elenco_st) else -1
                m = v.telaio(lato_stanza)
                ed = m.ed
                if v.tipo == "porta" and v.spec.get("apertura") != "scorrevole":   # le scorrevoli non hanno arco
                    in_fondo = v.spec.get("cerniera", "fine") == "fine"
                    opposta = v.spec.get("apre_verso") == "opposto"
                    n_apre = g.per(ed, -1.0) if opposta else ed
                    base = m(v.larghezza if in_fondo else 0.0, 0.0 if not opposta else -v.profondita, 0.0)[:2]
                    registra_porta(scena, v.id, base, g.per(m.eu, -1.0 if in_fondo else 1.0), n_apre,
                                   v.larghezza - 0.008, q, q + v.z1)
                elif v.tipo in ("finestra", "portafinestra"):
                    registra_finestra(scena, v.id, m(0.0, 0.0, 0.0)[:2], m(v.larghezza, 0.0, 0.0)[:2], ed, q + v.z0, q + v.z1)
                    scena.meta["finestre"].append({"id": v.id, "parete": v.id, "direzione": ed,
                                                   "centro": m(v.larghezza / 2, 0.0, 0.0)[:2], "quota": q})
                if v.tipo != "vano":
                    ap = {"id": v.id, "tipo": v.tipo, "da_m": 0.0, "larghezza_m": v.larghezza, "altezza_m": v.z1 - v.z0,
                          "quota_davanzale_m": v.z0, "ante": v.spec.get("ante", 2 if v.larghezza > 0.9 else 1),
                          "cerniera": v.spec.get("cerniera", "fine"), "altezza_maniglia_m": v.spec.get("altezza_maniglia_m", 0.90)}
                    for chiave in ("apertura",):
                        if chiave in v.spec:
                            ap[chiave] = v.spec[chiave]
                    scena.aggiungi(alza(serramento(ap, m, v.profondita), q)).gruppo = _gruppo("Serramenti", piano, k, multi)
            punti_ingombro += [p for m in forme_masse for p in m.exterior.coords]

        # pavimenti e soffitti
        soffitti_piano: list[Oggetto] = []
        solai = _gruppo("Solai", piano, k, multi)
        # sottogruppi dei solai: ognuno si accende e si spegne con un clic in SketchUp
        s_pavimenti, s_soffitto, s_contro, s_balconi = (f"{solai}/{x}" for x in ("Pavimenti", "Soffitto", "Controsoffitti", "Balconi"))
        if contorno is not None:
            scena.aggiungi(lastra(f"{pref}Pavimento", contorno, q - s_pav, q, "pavimento",
                                  "Pavimento rovere", "Intonaco pareti", "Intonaco pareti")).gruppo = s_pavimenti
            if soffitto_attivo and ultimo:
                scena.aggiungi(lastra(f"{pref}Soffitto", contorno, q + H, q + H + extra_alto, "soffitto",
                                      "Soffitto bianco", "Soffitto bianco", "Soffitto bianco")).gruppo = s_soffitto
        for st in stanze.values():
            if contorno is None:
                scena.aggiungi(lastra(f"{pref}Pavimento {st.id}", st.poligono, z0w, q, "pavimento",
                                      "Pavimento rovere", "Intonaco pareti", "Intonaco pareti")).gruppo = s_pavimenti
            coperta = 1.0 if ultimo else _copertura_dal_piano_sopra(st, piani[k + 1])
            if not ultimo and 0.1 < coperta < 0.9:
                scena.note.append(f"{piano.get('id', f'Piano {k + 1}')}, stanza {st.id}: coperta solo in parte dal piano sopra "
                                  f"({coperta:.0%}): il soffitto della parte scoperta non è modellato; descrivi la terrazza o "
                                  "il tetto come stanza a parte")
            if soffitto_attivo and (ultimo or coperta <= 0.1) and not (ultimo and contorno is not None):
                # soffitto: sull'ultimo piano e dove sopra non c'è nulla (terrazza, tetto); altrove è il solaio di sopra
                sof = lastra(f"{pref}Soffitto {st.id}", st.poligono, q + H, q + H + extra_alto, "soffitto",
                             "Soffitto bianco", "Soffitto bianco", "Soffitto bianco")
                if muri_uniti:
                    soffitti_piano.append(sof)
                else:
                    scena.aggiungi(sof).gruppo = s_soffitto
            # controsoffitti: stanza più bassa del piano, o zone più basse dentro la stanza (sempre tra i solai)
            if soffitto_attivo:
                for n_cs, (pol_cs, h_cs) in enumerate(soffitti_della_stanza(st, H), 1):
                    nome_cs = f"{pref}Controsoffitto {st.id}" + (f" {n_cs}" if n_cs > 1 else "")
                    z_cs = q + h_cs
                    cs = lastra(nome_cs, pol_cs, z_cs, q + H, "soffitto",
                                "Soffitto bianco", "Soffitto bianco", "Soffitto bianco")
                    cs.parti = parti_di_poligono(pol_cs, z_cs, q + H)
                    scena.aggiungi(cs).gruppo = s_contro
            cx, cy = st.centro()
            scena.meta["stanze"].append({"id": st.id, "tipo": st.spec.get("tipo"), "poligono": st.poligono,
                                         "quota": q, "altezza": float(st.spec.get("altezza_m", H)), "centro": (cx, cy)})

        # balconi e terrazzi: soletta e parapetto, nel gruppo dei solai
        def sul_muro(a, b, pezzi=pezzi, contorno=contorno):
            if contorno is not None:
                m = g.somma(a, g.per(g.sottrai(b, a), 0.5))
                n_c = len(contorno)
                if min(g.distanza_punto_segmento(m, contorno[i], contorno[(i + 1) % n_c]) for i in range(n_c)) < 0.05:
                    return True
            return faccia_che_copre(pezzi, a, b, tol=0.05) is not None
        for spec_b in piano.get("balconi", []) or []:
            scena.aggiungi(balcone(spec_b, q, pref, sul_muro)).gruppo = s_balconi

        if soffitti_piano:
            nome_sof = f"{pref}Soffitto".strip() if multi else "Soffitto"
            scena.aggiungi(unisci_oggetti(nome_sof, soffitti_piano, "soffitto")).gruppo = s_soffitto

        # serramenti
        for ap2, w, lato in serramenti:
            scena.aggiungi(alza(serramento(ap2, w.telaio(lato), w.spessore), q)).gruppo = _gruppo("Serramenti", piano, k, multi)

        # arredi
        arredi = piano.get("arredi", [])
        for sp in arredi:
            ctx = _contesto_arredo(sp, stanze, pezzi, H, arredi)
            ob = scena.aggiungi(alza(arredo(sp, ctx), q))
            ob.gruppo = _gruppo("Arredi", piano, k, multi)
            if sp.get("componente"):
                componi(ob, sp, arredo(dict(sp, posizione_m=[0.0, 0.0], rotazione_gradi=0.0), ctx), q)

    # ingombro per le viste: tutti gli oggetti (balconi, terrazzi, arredi esterni compresi), non solo i muri
    for o in scena.oggetti:
        ox, oy, _ = o.origine
        punti_ingombro += [(v[0] + ox, v[1] + oy) for v in o.mesh.v]
    if punti_ingombro:
        xs, ys = [p[0] for p in punti_ingombro], [p[1] for p in punti_ingombro]
        scena.meta["bbox"] = (min(xs), min(ys), max(xs), max(ys))
    scena.meta["altezza_totale"] = quote[-1][0] + quote[-1][1] + 0.10
    return scena


def locali_da_edificio(scheda: dict) -> list[dict]:
    """Locali per il controllo delle norme: ogni stanza con superficie, altezza, finestre e porte che la toccano
    (si decide con la geometria: l'apertura appartiene alle stanze che stanno ai suoi due lati)."""
    ed = scheda["edificio"]
    quote = _quote(ed["piani"])
    out = []
    for k, piano in enumerate(ed["piani"]):
        q, H, _ = quote[k]
        pezzi = risolvi(piano.get("pareti", []))
        stanze = {}
        for s in piano.get("stanze", []):
            st = _Stanza(s)
            stanze[st.id] = st
        locali = {st.id: {"id": st.id, "tipo": st.spec.get("tipo", "locale"), "superficie_m2": round(g.area(st.poligono), 4),
                          "poligono_m": [list(p) for p in st.poligono], "altezza_m": float(st.spec.get("altezza_m", H)),
                          "piano": piano.get("id", f"Piano {k + 1}"), "finestre": [], "porte": []} for st in stanze.values()}
        elenco = list(stanze.values())
        indice_stanze = g.IndiceCelle(3.0)
        for k2, st in enumerate(elenco):
            xs, ys = [q[0] for q in st.poligono], [q[1] for q in st.poligono]
            indice_stanze.aggiungi(k2, min(xs), min(ys), max(xs), max(ys), 0.1)
        forme_masse = [m for _, _, m in mi.masse_della_scheda(piano)]
        for spec_v in piano.get("vani", []) or []:
            v = mi.Vano(spec_v, forme_masse)
            toccate = [st.id for st in elenco for lato in (1, -1) if g.punto_in_poligono(v.punto_di_lato(lato), st.poligono)]
            for sid in dict.fromkeys(toccate):
                if v.tipo in ("finestra", "portafinestra"):
                    locali[sid]["finestre"].append({"id": v.id, "larghezza_m": spec_v.get("larghezza_apribile_m", round(v.larghezza, 3)),
                                                    "altezza_m": round(v.z1 - v.z0, 3), "apribile": spec_v.get("apribile", True),
                                                    "quota_davanzale_m": None if v.tipo == "portafinestra" else v.z0})
                elif v.tipo == "porta":
                    locali[sid]["porte"].append({"id": v.id, "luce_netta_m": round(v.larghezza, 3),
                                                 "altezza_maniglia_m": spec_v.get("altezza_maniglia_m", 0.90),
                                                 "ingresso": bool(spec_v.get("ingresso", False))})
        for ap in piano.get("aperture", []):
            w, lato, u0, u1 = _risolvi_apertura(ap, pezzi, stanze)
            um = (u0 + u1) / 2
            toccate = []
            for l2, segno in (("sinistra", 1.0), ("destra", -1.0)):
                p = g.somma(w.punto_faccia(um, l2), g.per(w.en, 0.05 * segno))
                toccate += [elenco[k2].id for k2 in sorted(indice_stanze.vicini(p))
                            if g.punto_in_poligono(p, elenco[k2].poligono)]
            for sid in dict.fromkeys(toccate):
                if ap["tipo"] in ("finestra", "portafinestra"):
                    f = {"id": ap["id"], "larghezza_m": ap.get("larghezza_apribile_m", ap["larghezza_m"]),
                         "altezza_m": ap.get("altezza_apribile_m", ap["altezza_m"]), "apribile": ap.get("apribile", True),
                         "quota_davanzale_m": None if ap["tipo"] == "portafinestra" else ap.get("quota_davanzale_m")}
                    locali[sid]["finestre"].append(f)
                else:
                    locali[sid]["porte"].append({"id": ap["id"], "luce_netta_m": ap["larghezza_m"],
                                                 "ingresso": bool(ap.get("ingresso", False)),
                                                 "altezza_maniglia_m": ap.get("altezza_maniglia_m")})
        out += list(locali.values())
    return out
