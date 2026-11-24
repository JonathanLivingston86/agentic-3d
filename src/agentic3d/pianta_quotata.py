"""Pianta quotata e confronto con il disegno di partenza: due documenti A3 distinti (il confronto anche in PNG).

Regole delle quote, dalla prassi del disegno architettonico:
- non si quotano spessori e lunghezze dei muri: i muri esterni confinano spesso con altre unità e il loro spessore
  non è noto; si quotano le misure nette dei vani (le due dimensioni principali di ogni stanza), la posizione di
  porte e finestre dall'angolo più vicino della stanza e la loro larghezza per altezza;
- risalti, nicchie e pilastri (lati corti del poligono della stanza) si quotano come quote normali accanto
  all'oggetto, larghezza e profondità, con le linee di richiamo dagli spigoli; le mazzette dei vani no;
- le quote stanno in pianta: prima del richiamo si provano numero sopra e sotto la linea, al centro o spostato,
  centrato anche se sporge dai trattini, più piccolo (1,8 mm invece di 2,5) e più staccato, in linea oltre un
  trattino, e la linea di quota spostata di qualche centimetro. Il richiamo (pallino, linea di riferimento, testo
  fuori pianta) resta solo quando non c'è posto, come per i nomi delle stanze più piccole; un risalto senza posto
  non va in un richiamo: si omette e il rapporto lo elenca;
- i numeri non si sovrappongono e non toccano linee: dopo il disegno un controllo legge il PDF e segnala i testi
  che si intersecano oltre il 15% del più piccolo e quelli toccati da linee di quota, trattini, linee di richiamo o
  facce dei muri;
- se la scheda riporta le misure scritte sul disegno di partenza (`quote_scritte_cm`, `superficie_scritta_m2`),
  in pianta si scrivono quelle e le differenze con il modello si elencano.

Confronto: con il blocco `sorgente` della scheda (file del disegno e almeno due punti corrispondenti tra modello e
disegno) i muri del modello (rosso) e le stanze (blu tratteggiato) si sovrappongono al disegno di partenza, con la
percentuale di contorno dei muri che cade sulle linee del disegno e i tratti che non coincidono.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

MM = 72 / 25.4                       # punti tipografici per millimetro
A3 = (297 * MM, 420 * MM)
SCALE = (50, 100, 200, 500)
MARGINE = 14 * MM
COLONNA_RICHIAMI = 30 * MM           # spazio ai lati della pianta per i richiami
CARTIGLIO = 46 * MM
SOVRAPPOSIZIONE_MAX = 0.15           # oltre questa frazione del testo più piccolo due testi si sovrappongono
CORPO = 7.0                          # corpo dei numeri (2,5 mm)
CORPO_PICCOLO = 5.1                  # quote corte, quando il numero normale non sta (1,8 mm)
LATO_CORTO = 1.0                     # m: lati della stanza più corti di così sono risalti, nicchie, pilastri
NOMI_TIPI = {"porta": "porta", "finestra": "finestra", "portafinestra": "porta finestra", "vano": "passaggio"}


@dataclass
class Apertura:
    id: str
    tipo: str
    forma: object                    # poligono Shapely del vano nel muro
    larghezza: float
    altezza: float | None
    altezza_ipotizzata: bool = False
    scritte: list | None = None      # [larghezza, altezza] in cm scritte sul disegno di partenza


@dataclass
class Esito:
    pdf: Path | None = None
    confronto_pdf: Path | None = None
    confronto_png: Path | None = None
    sovrapposizioni: list[str] = field(default_factory=list)
    differenze: list[str] = field(default_factory=list)
    coincidenza: float | None = None
    richiami: int = 0
    omesse: list[str] = field(default_factory=list)

    def testo(self) -> str:
        righe = []
        if self.pdf:
            righe.append(f"Pianta quotata: {self.pdf}")
        if self.confronto_pdf:
            righe.append(f"Confronto con il disegno di partenza (uso interno): {self.confronto_pdf} e {self.confronto_png}"
                         + (f" (contorno dei muri sulle linee del disegno: {self.coincidenza:.0%})"
                            if self.coincidenza is not None else ""))
        else:
            righe.append("Confronto con il disegno di partenza: manca il blocco `sorgente` nella scheda (file del "
                         "disegno e almeno due punti corrispondenti): va aggiunto, il confronto si consegna sempre")
        if self.omesse:
            righe.append("Quote omesse per mancanza di spazio (da aggiungere a mano se servono): " + "; ".join(self.omesse))
        if self.sovrapposizioni:
            righe.append("ERRORE: numeri illeggibili nella pianta: " + "; ".join(self.sovrapposizioni))
        if self.differenze:
            righe += ["DIFFERENZE CON IL DISEGNO DI PARTENZA"] + [f"- {d}" for d in self.differenze]
        return "\n".join(righe)


# ------------------------------------------------------------------ dati dalla scheda
def raccogli(scheda: dict):
    """(muri, aperture, stanze, differenze) del primo piano: muri come poligoni Shapely, aperture con le misure,
    stanze con poligono, altezza e misure scritte; differenze tra misure scritte e modello."""
    from shapely.geometry import Polygon
    from .nucleo import muri_impronta as mi
    from .nucleo.edificio import _risolvi_apertura, _Stanza
    from .nucleo.pareti import impronta, risolvi
    from .scheda import completa
    if "edificio" not in scheda:
        raise ValueError("la pianta quotata si disegna per le schede con `edificio:`")
    originale = scheda["edificio"]["piani"][0]
    piano = completa(scheda)["edificio"]["piani"][0]
    masse = [Polygon(m["poligono_m"]) for m in piano.get("muri", []) or []]
    pezzi = risolvi(piano["pareti"]) if piano.get("pareti") else []
    muri = masse + [Polygon(impronta(w)) for w in pezzi]

    def ipotizzata(i, chiave):
        elenco = originale.get(chiave, []) or []
        return i < len(elenco) and "altezza_m" not in elenco[i]

    aperture = []
    for i, v in enumerate(piano.get("vani", []) or []):
        vv = mi.Vano(v, masse)
        aperture.append(Apertura(vv.id, vv.tipo, vv.forma, vv.larghezza, vv.z1 - vv.z0, ipotizzata(i, "vani"),
                                 v.get("quote_scritte_cm")))
    if piano.get("aperture") and pezzi:
        stanze_ed = {}
        for s in piano.get("stanze", []):
            st = _Stanza(s)
            stanze_ed[st.id] = st
        for i, ap in enumerate(piano["aperture"]):
            w, _, u0, u1 = _risolvi_apertura(ap, pezzi, stanze_ed)
            forma = Polygon([w.punto_faccia(u0, "sinistra"), w.punto_faccia(u1, "sinistra"),
                             w.punto_faccia(u1, "destra"), w.punto_faccia(u0, "destra")])
            aperture.append(Apertura(str(ap["id"]), ap["tipo"], forma, u1 - u0, ap.get("altezza_m"),
                                     ipotizzata(i, "aperture"), ap.get("quote_scritte_cm")))
    stanze = [{"id": str(s["id"]), "pol": Polygon(s["poligono_m"]), "altezza": s.get("altezza_m", piano.get("altezza_m")),
               "scritte": s.get("quote_scritte_cm"), "superficie_scritta": s.get("superficie_scritta_m2")}
              for s in piano.get("stanze", [])]
    differenze = []
    for st in stanze:
        sup = st["superficie_scritta"]
        if sup is not None and abs(st["pol"].area - float(sup)) > max(0.15, 0.02 * float(sup)):
            differenze.append(f"{st['id']}: superficie del modello {st['pol'].area:.2f} m2, scritta {float(sup):.2f} m2")
        if st["scritte"]:
            for (a, b, misura), scritta, nome in zip(misure_nette(st["pol"]), st["scritte"], ("larghezza", "profondità")):
                if abs(misura * 100 - float(scritta)) > 2:
                    differenze.append(f"{st['id']}: {nome} del modello {misura * 100:.0f} cm, scritta {float(scritta):.0f} cm")
    for ap in aperture:
        if ap.scritte and abs(ap.larghezza * 100 - float(ap.scritte[0])) > 2:
            differenze.append(f"{ap.id}: larghezza del modello {ap.larghezza * 100:.0f} cm, scritta {float(ap.scritte[0]):.0f} cm")
    return muri, aperture, stanze, differenze


def direzione_prevalente(pol) -> float:
    """Angolo (gradi, tra 0 e 90) dei lati della stanza, pesato sulle lunghezze: in un trapezio con un lato obliquo
    vince la direzione dei lati ortogonali."""
    coords = list(pol.exterior.coords)[:-1]
    pesi: dict[int, float] = {}
    for i in range(len(coords)):
        a, b = coords[i], coords[(i + 1) % len(coords)]
        ang = round(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 90.0) % 90
        pesi[ang] = pesi.get(ang, 0.0) + math.dist(a, b)
    return float(max(pesi, key=pesi.get))


def misure_nette(pol, candidati: bool = False):
    """Le due misure nette principali della stanza: [(a, b, lunghezza)] lungo la direzione prevalente dei lati e di
    traverso. Ogni misura è la corda più lunga del pavimento in quella direzione, presa vicino al centro della stanza.
    Con `candidati` restituisce per ogni direzione tutte le corde lunghe quanto la massima (entro 5 mm), dalla più
    centrale: chi disegna sceglie quella che non passa sopra i testi."""
    from shapely import affinity
    from shapely.geometry import LineString
    ang = direzione_prevalente(pol)
    out = []
    for giro in (0.0, 90.0):
        c = pol.centroid
        ruotato = affinity.rotate(pol, -(ang + giro), origin=c)
        x0, y0, x1, y1 = ruotato.bounds
        migliori = []
        n = 120
        for k in range(n + 1):
            y = y0 + 0.003 + (y1 - y0 - 0.006) * k / n
            pezzo = ruotato.intersection(LineString([(x0 - 1, y), (x1 + 1, y)]))
            parti = getattr(pezzo, "geoms", [pezzo])
            lunghe = [p for p in parti if p.geom_type == "LineString" and not p.is_empty]
            if lunghe:
                lunga = max(lunghe, key=lambda p: p.length)
                migliori.append((lunga.length, -abs(y - (y0 + y1) / 2), lunga))
        lmax = max(m[0] for m in migliori)
        scelte = []
        for m in sorted((m for m in migliori if m[0] >= lmax - 0.005), key=lambda m: -m[1]):
            p, q = (affinity.rotate(m[2], ang + giro, origin=c).coords)
            if (q[0] - p[0]) < -1e-9 or (abs(q[0] - p[0]) < 1e-9 and q[1] < p[1]):
                p, q = q, p
            scelte.append((tuple(p), tuple(q), m[2].length))
        out.append(scelte if candidati else scelte[0])
    return out


def lati_corti(pol, vani=()) -> list[tuple]:
    """Lati della stanza da quotare come risalti, nicchie e pilastri: [(p0, p1, normale verso la stanza)].
    Sono i lati più corti di `LATO_CORTO`, paralleli o perpendicolari ai lati principali, tra due lati che lo sono
    anch'essi (il lato corto accanto a un muro obliquo è già detto dalle misure nette). In un gruppo di lati corti
    consecutivi, di due lati paralleli e uguali (i fianchi di un risalto) se ne quota uno. Un gruppo che combacia
    con un vano (`vani`: poligoni) per un tratto è la mazzetta di una porta o di una finestra, non un risalto: non si
    quota. Un pilastro che tocca un vano solo in uno spigolo si quota."""
    from shapely.geometry import LineString
    from shapely.geometry import Point
    from shapely.geometry.polygon import orient
    pol = orient(pol, 1.0)                                    # antiorario: la stanza sta a sinistra di ogni lato
    coords = list(pol.exterior.coords)[:-1]
    n = len(coords)
    ang0 = direzione_prevalente(pol)

    def allineato(a, b):
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        r = (ang - ang0) % 90.0
        return min(r, 90.0 - r) < 0.5

    lati = [(coords[i], coords[(i + 1) % n]) for i in range(n)]
    corti = [0.05 <= math.dist(a, b) < LATO_CORTO and allineato(a, b) and allineato(*lati[i - 1])
             and allineato(*lati[(i + 1) % n]) for i, (a, b) in enumerate(lati)]
    if all(corti) or not any(corti):
        return []
    inizio = next(i for i in range(n) if not corti[i])
    gruppi, gruppo = [], []
    for k in range(1, n + 1):
        i = (inizio + k) % n
        if corti[i]:
            gruppo.append(i)
        elif gruppo:
            gruppi.append(gruppo)
            gruppo = []
    out = []
    for gruppo in gruppi:
        # mazzetta: un lato del gruppo combacia con il vano per un tratto (non solo in uno spigolo)
        if any(LineString(lati[i]).intersection(v.buffer(0.005)).length > 0.02 for i in gruppo for v in vani):
            continue
        scelti = []
        for i in gruppo:
            a, b = lati[i]
            dx, dy = b[0] - a[0], b[1] - a[1]
            if any(abs(abs(dx * (q[1][1] - q[0][1]) - dy * (q[1][0] - q[0][0]))) < 1e-9 * max(1.0, math.dist(a, b))
                   and abs(math.dist(a, b) - math.dist(*q)) < 0.005 for q in scelti):
                continue                                     # fianco uguale a uno già quotato
            scelti.append((a, b))
            lung = math.dist(a, b)
            normale = (-dy / lung, dx / lung)
            out.append((a, b, normale))
    return out


def _cm(v: float) -> str:
    """Centimetri arrotondati per eccesso dal mezzo (80,5 -> 81), come si legge in pianta."""
    return f"{math.floor(v * 100 + 0.5 + 1e-9):d}"


def _numero(v) -> str:
    v = float(v)
    return f"{v:.0f}" if abs(v - round(v)) < 1e-6 else f"{v:.1f}".replace(".", ",")


# ------------------------------------------------------------------ impaginazione
class _Foglio:
    """Pagina con la trasformazione dal modello (metri, y verso l'alto) ai punti della pagina (y verso il basso)."""

    def __init__(self, doc, larghezza_m, altezza_m, x_min, y_max, scala=None):
        import fitz
        self.fitz = fitz
        opzioni = []
        for verso, formato in enumerate((A3, (A3[1], A3[0]))):
            area_w = formato[0] - 2 * MARGINE - 2 * COLONNA_RICHIAMI
            area_h = formato[1] - 2 * MARGINE - CARTIGLIO - 10 * MM
            for s in ([scala] if scala else SCALE):
                k = 1000 / s * MM
                if larghezza_m * k <= area_w and altezza_m * k <= area_h:
                    opzioni.append((s, -(area_w - larghezza_m * k), k, formato, area_h))
                    break
        if not opzioni:                                  # più grande del foglio anche a 1:500: si riduce
            formato = A3
            area_w = formato[0] - 2 * MARGINE - 2 * COLONNA_RICHIAMI
            area_h = formato[1] - 2 * MARGINE - CARTIGLIO - 10 * MM
            k = min(area_w / larghezza_m, area_h / altezza_m)
            opzioni.append((round(1000 * MM / k), 0, k, formato, area_h))
        s, _, k, formato, area_h = min(opzioni, key=lambda o: (o[0], o[1]))
        self.scala, self.k, self.formato = s, k, formato
        self.pagina = doc.new_page(width=formato[0], height=formato[1])
        self.ox = (formato[0] - larghezza_m * k) / 2 - x_min * k
        self.oy = MARGINE + 6 * MM + (area_h - altezza_m * k) / 2 + y_max * k
        self.occupati: list = []                     # rettangoli dei testi già scritti
        self.linee: list = []                        # linee di quota e di richiamo (punti della pagina)
        self.richiami = {"sinistra": [], "destra": []}
        self.omesse: list[str] = []                  # quote di risalti senza posto in pianta
        self.bordo_pianta = (self.p(x_min, y_max).x, self.p(x_min + larghezza_m, y_max).x)

    def p(self, x, y):
        return self.fitz.Point(self.ox + x * self.k, self.oy - y * self.k)

    def poligono(self, pol, riempi=None, bordo=(0, 0, 0), spessore=0.5, tratteggio=None):
        for parte in getattr(pol, "geoms", [pol]):
            if parte.geom_type != "Polygon" or parte.is_empty:
                continue
            self.pagina.draw_polyline([self.p(*c) for c in parte.exterior.coords], color=bordo, fill=riempi,
                                      width=spessore, closePath=True, dashes=tratteggio)
            for buco in parte.interiors:
                self.pagina.draw_polyline([self.p(*c) for c in buco.coords], color=bordo, fill=(1, 1, 1),
                                          width=spessore, closePath=True)

    # testi con controllo degli ingombri
    def rettangolo_testo(self, centro, testo, corpo, ruota=0):
        w = self.fitz.get_text_length(testo, fontname="helv", fontsize=corpo)
        h = corpo * 1.15
        if ruota in (90, 270):
            w, h = h, w
        return self.fitz.Rect(centro.x - w / 2, centro.y - h / 2, centro.x + w / 2, centro.y + h / 2)

    def libero(self, r, dentro=None, ostacoli=()) -> bool:
        """Il testo nel rettangolo `r` non tocca altri testi, linee di quota, trattini, richiami, facce dei muri, né
        le linee `ostacoli` (quelle della sua stessa quota); con `dentro` sta tutto nel poligono."""
        r = self.fitz.Rect(r.x0 - 1, r.y0 - 1, r.x1 + 1, r.y1 + 1)
        if any(r.intersects(o) and (r & o).get_area() > 0.02 * min(r.get_area(), o.get_area()) for o in self.occupati):
            return False
        from shapely.geometry import LineString, box
        x0, y0, x1, y1 = r.x0 - 0.5, r.y0 - 0.5, r.x1 + 0.5, r.y1 + 0.5
        b = box(x0, y0, x1, y1)
        for l in list(self.linee) + list(ostacoli):
            (ax, ay), (bx, by) = l[0], l[-1]
            if max(ax, bx) < x0 or min(ax, bx) > x1 or max(ay, by) < y0 or min(ay, by) > y1:
                continue
            if b.intersects(LineString(l)):
                return False
        if dentro is not None:
            from shapely.geometry import box
            angoli = box(r.x0, r.y0, r.x1, r.y1)
            if not dentro.contains(angoli):
                return False
        return True

    def testi_attraversati(self, a, b) -> int:
        """Quanti testi già scritti attraversa la linea tra i punti della pagina `a` e `b`."""
        from shapely.geometry import LineString, box
        l = LineString([(a.x, a.y), (b.x, b.y)])
        return sum(l.intersects(box(o.x0 - 1, o.y0 - 1, o.x1 + 1, o.y1 + 1)) for o in self.occupati)

    def linea_libera(self, a, b) -> bool:
        """La linea tra i punti della pagina `a` e `b` non passa sopra i testi già scritti."""
        return self.testi_attraversati(a, b) == 0

    def fuori_dai_testi(self, punto) -> bool:
        return not any(self.fitz.Rect(o.x0 - 1, o.y0 - 1, o.x1 + 1, o.y1 + 1).contains(punto) for o in self.occupati)

    def scrivi(self, centro, testo, corpo=CORPO, ruota=0, colore=(0, 0, 0)):
        r = self.rettangolo_testo(centro, testo, corpo, ruota)
        w = self.fitz.get_text_length(testo, fontname="helv", fontsize=corpo)
        if ruota == 90:        # dal basso verso l'alto
            punto = self.fitz.Point(centro.x + corpo * 0.35, centro.y + w / 2)
        else:
            punto = self.fitz.Point(centro.x - w / 2, centro.y + corpo * 0.35)
        self.pagina.insert_text(punto, testo, fontsize=corpo, fontname="helv", color=colore, rotate=ruota)
        self.occupati.append(r)
        return r

    def richiamo(self, ancora, testo, corpo=CORPO, alternative=()):
        """Pallino sull'oggetto, linea di riferimento e testo fuori pianta (lato più vicino). `alternative`: altri
        punti dell'oggetto da cui può partire la linea, se da `ancora` attraversa dei testi."""
        vicino = "sinistra" if ancora.x < (self.bordo_pianta[0] + self.bordo_pianta[1]) / 2 else "destra"
        lontano = "destra" if vicino == "sinistra" else "sinistra"

        def attraversati(lato):
            x = self.bordo_pianta[1 if lato == "destra" else 0]
            return sum(not self.linea_libera(ancora, self.fitz.Point(x, ancora.y)) for _ in (0,))
        lato = vicino if attraversati(vicino) <= attraversati(lontano) else lontano
        self.richiami[lato].append((ancora, testo, corpo, tuple(alternative)))

    def disegna_richiami(self):
        n = 0
        for lato, elenco in self.richiami.items():
            elenco.sort(key=lambda r: r[0].y)
            ultimo = -1e9
            for ancora, testo, corpo, alternative in elenco:
                w = self.fitz.get_text_length(testo, fontname="helv", fontsize=corpo)
                x_testo = self.bordo_pianta[1] + 8 * MM if lato == "destra" else self.bordo_pianta[0] - 8 * MM
                x_gomito = x_testo - 2 if lato == "destra" else x_testo + 2
                minimo = ultimo + corpo * 1.6
                # la linea di riferimento non attraversa i testi: si cerca il punto di partenza e l'altezza liberi
                scelta = None
                for punto in (ancora,) + alternative:
                    prove = [punto.y + d * corpo for d in (0, -1.5, 1.5, -3, 3, -4.5, 4.5, -6, 6, -8, 8, -10, 10)]
                    y = next((max(y, minimo) for y in prove
                              if self.linea_libera(punto, self.fitz.Point(x_gomito, max(y, minimo)))), None)
                    if y is not None:
                        scelta = (punto, y)
                        break
                ancora, y = scelta or (ancora, max(ancora.y, minimo))
                ultimo = y
                gomito = self.fitz.Point(x_gomito, y)
                centro = self.fitz.Point(x_testo + w / 2 if lato == "destra" else x_testo - w / 2, y)
                self.pagina.draw_circle(ancora, 1.2, color=(0, 0, 0), fill=(0, 0, 0))
                self.pagina.draw_polyline([ancora, gomito], color=(0, 0, 0), width=0.35)
                self.linee.append(((ancora.x, ancora.y), (gomito.x, gomito.y)))
                self.scrivi(centro, testo, corpo)
                n += 1
        return n

    def segmento(self, a, b, spessore=0.35):
        """Linea (punti della pagina) disegnata e registrata tra gli ostacoli dei testi."""
        self.pagina.draw_line(a, b, color=(0, 0, 0), width=spessore)
        self.linee.append(((a.x, a.y), (b.x, b.y)))

    def quota(self, a, b, valore: str, dentro=None, lato_preferito=1.0, ultima=True, richiami_da=()):
        """Linea di quota tra i punti del modello `a` e `b` con trattini obliqui agli estremi e il numero in pianta.
        Prima del richiamo si provano tutte le posizioni: numero sopra o sotto la linea, al centro o spostato, che
        sporge dai trattini se la quota è corta, poi più piccolo e più staccato. Se non c'è posto: con `ultima` la
        quota si disegna con il richiamo fuori pianta, altrimenti non si disegna nulla e si restituisce False (chi
        chiama prova la linea in un'altra posizione). `richiami_da`: coppie di punti del modello da cui partono le
        linee di richiamo verso la linea di quota (risalti e pilastri)."""
        pa, pb = self.p(*a), self.p(*b)
        d = (pb - pa)
        lung = math.hypot(d.x, d.y)
        if lung < 1e-6:
            return False
        u = self.fitz.Point(d.x / lung, d.y / lung)
        obl = self.fitz.Point((u.x - u.y) * 2.2, (u.y + u.x) * 2.2)
        trattini = [(p - obl, p + obl) for p in (pa, pb)]
        estensioni = [(self.p(*q0), self.p(*q1)) for q0, q1 in richiami_da]
        propri = [((pa.x, pa.y), (pb.x, pb.y))] + [((s.x, s.y), (e.x, e.y)) for s, e in trattini + estensioni]
        if not ultima and any(self.testi_attraversati(self.fitz.Point(*a_), self.fitz.Point(*b_)) for a_, b_ in propri):
            return False
        verticale = abs(u.x) < abs(u.y)
        ruota = 90 if verticale else 0
        n = self.fitz.Point(-u.y, u.x) if not verticale else self.fitz.Point(u.y, -u.x)
        if n.y > 0 or (abs(n.y) < 1e-9 and n.x > 0):
            n = self.fitz.Point(-n.x, -n.y)                   # sopra la linea, o a sinistra se verticale
        def prove():
            # numero normale sopra (o sotto) la linea, al centro o spostato; poi centrato anche se sporge dai
            # trattini; poi più piccolo e più staccato; infine in linea, appena oltre un trattino
            for corpo, stacchi, sporge in ((CORPO, (0.95,), False), (CORPO, (0.95,), True),
                                           (CORPO_PICCOLO, (1.05, 1.4), True)):
                larghezza_testo = self.fitz.get_text_length(valore, fontname="helv", fontsize=corpo)
                if not sporge and larghezza_testo + 6 > lung:
                    continue
                posizioni = (0.5,) if sporge and larghezza_testo + 6 > lung else (0.5, 0.3, 0.7)
                for verso in (lato_preferito, -lato_preferito):
                    for stacco in stacchi:
                        for t in posizioni:
                            yield pa + (pb - pa) * t + n * (verso * (corpo * stacco)), corpo
            for corpo in (CORPO, CORPO_PICCOLO):
                larghezza_testo = self.fitz.get_text_length(valore, fontname="helv", fontsize=corpo)
                fuori = (larghezza_testo if not verticale else corpo * 1.15) / 2 + 5
                for estremo, verso in ((pb, 1.0), (pa, -1.0)):
                    yield estremo + u * (verso * fuori), corpo

        scelta = None
        for c, corpo in prove():
            if self.libero(self.rettangolo_testo(c, valore, corpo, ruota), dentro, ostacoli=propri):
                scelta = (c, corpo)
                break
        if scelta is None and not ultima:
            return False
        for s, e in estensioni:
            self.segmento(s, e, 0.25)
        self.segmento(pa, pb)
        for s, e in trattini:
            self.segmento(s, e, 0.6)
        if scelta:
            self.scrivi(scelta[0], valore, scelta[1], ruota)
            return True
        # il richiamo parte da un punto della linea che non sta sotto un testo
        ancora = next((pa + (pb - pa) * t for t in (0.5, 0.35, 0.65, 0.2, 0.8, 0.1, 0.9)
                       if self.fuori_dai_testi(pa + (pb - pa) * t)), (pa + pb) / 2)
        self.richiamo(ancora, valore)
        return True


def _apertura_e_stanze(ap: Apertura, stanze):
    """Stanze che toccano il vano, dalla più grande."""
    tocca = [st for st in stanze if st["pol"].distance(ap.forma) < 0.005]
    return sorted(tocca, key=lambda st: -st["pol"].area)


def _posizione(ap: Apertura, stanza):
    """(angolo della stanza, punto d'inizio del vano, distanza) dall'angolo più vicino lungo il lato della stanza
    che contiene il vano; None se non si trova."""
    contatto = stanza["pol"].exterior.intersection(ap.forma.buffer(0.003))
    if contatto.is_empty:
        return None
    pts = [c for g_ in getattr(contatto, "geoms", [contatto]) for c in getattr(g_, "coords", [])]
    if len(pts) < 2:
        return None
    coords = list(stanza["pol"].exterior.coords)[:-1]
    for i in range(len(coords)):
        e0, e1 = coords[i], coords[(i + 1) % len(coords)]
        lung = math.dist(e0, e1)
        if lung < 1e-6:
            continue
        eu = ((e1[0] - e0[0]) / lung, (e1[1] - e0[1]) / lung)
        ts = []
        ok = True
        for q in pts:
            t = (q[0] - e0[0]) * eu[0] + (q[1] - e0[1]) * eu[1]
            d = abs((q[0] - e0[0]) * eu[1] - (q[1] - e0[1]) * eu[0])
            if d > 0.004 or t < -0.004 or t > lung + 0.004:
                ok = False
                break
            ts.append(t)
        if not ok:
            continue
        t0, t1 = min(ts), max(ts)
        if lung - (t1 - t0) < 0.10:
            return None                     # il vano occupa tutto il lato (in una mazzetta): la posizione è già detta
        if (t0 <= lung - t1 and t0 > 0.05) or lung - t1 <= 0.05:
            return e0, (e0[0] + eu[0] * t0, e0[1] + eu[1] * t0), t0, eu
        return e1, (e0[0] + eu[0] * t1, e0[1] + eu[1] * t1), lung - t1, eu
    return None


def _assi_vano(ap: Apertura, stanza):
    """(direzione lungo il muro, normale verso la stanza, profondità) del vano, dalla sua forma."""
    from shapely.geometry import Point
    coords = list(ap.forma.exterior.coords)[:-1]
    lati = [(coords[i], coords[(i + 1) % len(coords)]) for i in range(len(coords))]
    a, b = max(lati, key=lambda l: math.dist(*l))
    lung = math.dist(a, b) or 1.0
    eu = ((b[0] - a[0]) / lung, (b[1] - a[1]) / lung)
    normale = (-eu[1], eu[0])
    prof = min(math.dist(*l) for l in lati if math.dist(*l) > 1e-6)
    c = ap.forma.centroid
    prova = Point(c.x + normale[0] * (prof / 2 + 0.05), c.y + normale[1] * (prof / 2 + 0.05))
    if stanza["pol"].distance(prova) > stanza["pol"].distance(
            Point(c.x - normale[0] * (prof / 2 + 0.05), c.y - normale[1] * (prof / 2 + 0.05))):
        normale = (-normale[0], -normale[1])
    return eu, normale, prof


def disegna_pianta(doc, scheda: dict, titolo: str = "", scala: int | None = None):
    """Prima pagina: la pianta quotata. Restituisce (foglio, differenze)."""
    from shapely.geometry import LineString, Point
    from shapely.ops import polylabel, unary_union
    muri, aperture, stanze, differenze = raccogli(scheda)
    tutto = unary_union(muri + [st["pol"] for st in stanze] + [a.forma for a in aperture])
    x0, y0, x1, y1 = tutto.bounds
    f = _Foglio(doc, x1 - x0, y1 - y0, x0, y1, scala)
    pareti = unary_union([m.buffer(1e-5, join_style=2) for m in muri]).buffer(-1e-5, join_style=2).difference(unary_union([a.forma for a in aperture]) if aperture else Point(0, 0).buffer(0))
    f.poligono(pareti, (0.62, 0.62, 0.62), (0, 0, 0), 0.6)
    for ap in aperture:                                     # vano: spallette e, per le finestre, il vetro
        f.poligono(ap.forma, (1, 1, 1), (0.25, 0.25, 0.25), 0.3)
    for forma in [pareti] + [ap.forma for ap in aperture]:  # i numeri non toccano le facce dei muri né i vani
        for parte in getattr(forma, "geoms", [forma]):
            if parte.geom_type != "Polygon":
                continue
            for anello in [parte.exterior] + list(parte.interiors):
                cs = [f.p(*c) for c in anello.coords]
                f.linee += [((cs[i].x, cs[i].y), (cs[i + 1].x, cs[i + 1].y)) for i in range(len(cs) - 1)]
        if ap.tipo in ("finestra", "portafinestra"):
            coords = list(ap.forma.exterior.coords)[:-1]
            lati = sorted(((coords[i], coords[(i + 1) % len(coords)]) for i in range(len(coords))),
                          key=lambda l: -math.dist(*l))[:2]
            (a, b), (c, d) = lati
            if math.dist(a, d) > math.dist(a, c):
                c, d = d, c
            f.segmento(f.p((a[0] + c[0]) / 2, (a[1] + c[1]) / 2), f.p((b[0] + d[0]) / 2, (b[1] + d[1]) / 2), 0.5)
    # nomi delle stanze: nome, superficie (scritta, se c'è) e altezza
    corde_di = {id(st): misure_nette(st["pol"], candidati=True) for st in stanze}

    def lascia_le_misure(st, rett):
        """Il nome nei rettangoli `rett` lascia libera almeno una corda per ciascuna misura netta."""
        from shapely.geometry import box
        scatole = [box(r.x0 - 2, r.y0 - 2, r.x1 + 2, r.y1 + 2) for r in rett]
        for corde in corde_di[id(st)]:
            if not any(not any(LineString([(f.p(*a).x, f.p(*a).y), (f.p(*b).x, f.p(*b).y)]).intersects(sc)
                               for sc in scatole) for a, b, _ in corde):
                return False
        return True

    for st in stanze:
        sup = st["superficie_scritta"] if st["superficie_scritta"] is not None else st["pol"].area
        righe = [st["id"].upper(), f"S = {float(sup):.2f} m²".replace(".", ",")]
        if st["altezza"]:
            righe.append(f"h = {float(st['altezza']):.2f} m".replace(".", ","))
        centro_m = polylabel(st["pol"], 0.01)
        dentro = _pol_pagina(f, st["pol"].buffer(-0.03))
        # posto libero più vicino al centro della stanza, lontano dalle linee di quota
        passi = [(dx * 0.2, dy * 0.2) for dx in range(-8, 9) for dy in range(-8, 9)]
        passi.sort(key=lambda d: math.hypot(*d))
        scritto = False
        for dx, dy in passi:
            c = f.p(centro_m.x + dx, centro_m.y + dy)
            rett = [f.rettangolo_testo(c + (0, (i - (len(righe) - 1) / 2) * 10), r, 8 if i == 0 else CORPO)
                    for i, r in enumerate(righe)]
            if all(f.libero(r, dentro) for r in rett) and lascia_le_misure(st, rett):
                for i, r in enumerate(righe):
                    f.scrivi(c + (0, (i - (len(righe) - 1) / 2) * 10), r, 8 if i == 0 else CORPO)
                scritto = True
                break
        if not scritto:
            c = f.p(centro_m.x, centro_m.y)
            interni = [f.p(centro_m.x + dx, centro_m.y + dy) for dx, dy in passi[1:60]
                       if st["pol"].buffer(-0.05).contains(Point(centro_m.x + dx, centro_m.y + dy))]
            f.richiamo(c, "  ".join(righe[:2]).replace(st["id"].upper(), st["id"].upper() + ","), alternative=interni)
    # misure nette delle stanze (quelle scritte sul disegno vincono)
    for st in stanze:
        dentro = _pol_pagina(f, st["pol"])
        for k, corde in enumerate(corde_di[id(st)]):
            scritta = st["scritte"][k] if st["scritte"] and k < len(st["scritte"]) else None
            libere = [c for c in corde if f.testi_attraversati(f.p(*c[0]), f.p(*c[1])) == 0]
            passo = max(1, len(libere) // 12)
            prove = libere[::passo] or sorted(corde, key=lambda c: f.testi_attraversati(f.p(*c[0]), f.p(*c[1])))[:1]
            for j, (a, b, misura) in enumerate(prove):
                if f.quota(a, b, _numero(scritta) if scritta is not None else _cm(misura), dentro,
                           ultima=j == len(prove) - 1):
                    break
    # vani: posizione dall'angolo della stanza e larghezza x altezza
    for ap in aperture:
        vicine = _apertura_e_stanze(ap, stanze)
        lx = _numero(ap.scritte[0]) if ap.scritte else _cm(ap.larghezza)
        hx = _numero(ap.scritte[1]) if ap.scritte and len(ap.scritte) > 1 else (_cm(ap.altezza) if ap.altezza else "")
        misure = (f"{lx} x {hx}" + ("*" if ap.altezza_ipotizzata and not ap.scritte else "")) if hx else lx
        etichetta = misure if ap.tipo == "porta" else f"{NOMI_TIPI.get(ap.tipo, ap.tipo)} {misure}"
        posto = False
        for k_st, st in enumerate(vicine):
            eu, normale, prof = _assi_vano(ap, st)
            pos = _posizione(ap, st) if k_st == 0 else None
            if pos is not None:
                angolo, inizio, dist, _ = pos
                scosta = min(0.25, 0.35 * min(st["pol"].bounds[2] - st["pol"].bounds[0],
                                               st["pol"].bounds[3] - st["pol"].bounds[1]))
                if dist > 0.05:
                    prove = [scosta] + [x for x in (0.15, 0.35, 0.45, 0.10) if abs(x - scosta) > 0.02]
                    for k, sc in enumerate(prove):
                        a = (angolo[0] + normale[0] * sc, angolo[1] + normale[1] * sc)
                        b = (inizio[0] + normale[0] * sc, inizio[1] + normale[1] * sc)
                        if f.quota(a, b, _cm(dist), ultima=k == len(prove) - 1):
                            break
            # etichetta del vano dentro la stanza, davanti al vano (nella stanza più grande, poi nell'altra)
            c_m = ap.forma.centroid
            dentro = _pol_pagina(f, st["pol"])
            for distanza in (0.12, 0.25, 0.40, 0.60):
                for lungo in (0.0, -0.3, 0.3, -0.6, 0.6):
                    x = c_m.x + normale[0] * (prof / 2 + distanza) + eu[0] * lungo
                    y = c_m.y + normale[1] * (prof / 2 + distanza) + eu[1] * lungo
                    c = f.p(x, y)
                    if f.libero(f.rettangolo_testo(c, etichetta, CORPO), dentro):
                        f.scrivi(c, etichetta, CORPO)
                        posto = True
                        break
                if posto:
                    break
            if posto:
                break
        if not posto:
            c_m = ap.forma.centroid
            f.richiamo(f.p(c_m.x, c_m.y), f"{ap.id}: {misure}")
    # risalti, nicchie e pilastri: quote normali accanto all'oggetto, con le linee di richiamo dagli spigoli
    for st in stanze:
        dentro = _pol_pagina(f, st["pol"])
        for a, b, normale in lati_corti(st["pol"], [ap.forma for ap in aperture]):
            posta = False
            for d in (0.10, 0.16, 0.22, 0.30, 0.06):
                qa = (a[0] + normale[0] * d, a[1] + normale[1] * d)
                qb = (b[0] + normale[0] * d, b[1] + normale[1] * d)
                if not st["pol"].buffer(1e-6).contains(LineString([qa, qb])):
                    continue
                stacco = 0.015                                  # le linee di richiamo partono poco dopo lo spigolo
                da = [((a[0] + normale[0] * stacco, a[1] + normale[1] * stacco),
                       (a[0] + normale[0] * (d + 0.03), a[1] + normale[1] * (d + 0.03))),
                      ((b[0] + normale[0] * stacco, b[1] + normale[1] * stacco),
                       (b[0] + normale[0] * (d + 0.03), b[1] + normale[1] * (d + 0.03)))]
                # un risalto senza posto in pianta non va in un richiamo: si omette e il rapporto lo dice
                if f.quota(qa, qb, _cm(math.dist(a, b)), dentro, ultima=False, richiami_da=da):
                    posta = True
                    break
            if not posta:
                f.omesse.append(f"{st['id']}: risalto di {_cm(math.dist(a, b))} cm")
    n_richiami = f.disegna_richiami()
    _cartiglio(f, titolo or "Pianta quotata", [
        f"Scala 1:{f.scala} su foglio A3. Quote in cm, misure nette dei vani; superfici nette in m².",
        "Muri non quotati: i muri esterni confinano con altre unità e i loro spessori non sono noti.",
        "Vani: posizione dall'angolo della stanza, larghezza x altezza (* altezza ipotizzata).",
        "Dove il disegno di partenza riporta una misura scritta, in pianta si scrive quella."])
    _barra_scala(f)
    return f, differenze, n_richiami


def _pol_pagina(f: _Foglio, pol):
    from shapely.geometry import Polygon
    if pol.is_empty:
        return Polygon()
    parti = getattr(pol, "geoms", [pol])
    from shapely.ops import unary_union
    return unary_union([Polygon([(f.p(*c).x, f.p(*c).y) for c in p.exterior.coords]) for p in parti
                        if p.geom_type == "Polygon"])


def _cartiglio(f: _Foglio, titolo: str, righe: list[str]):
    W, H = f.formato
    y = H - MARGINE - CARTIGLIO
    f.pagina.draw_rect(f.fitz.Rect(MARGINE, MARGINE, W - MARGINE, H - MARGINE), color=(0, 0, 0), width=0.8)
    f.pagina.draw_line(f.fitz.Point(MARGINE, y), f.fitz.Point(W - MARGINE, y), color=(0, 0, 0), width=0.8)
    f.pagina.insert_text((MARGINE + 6 * MM, y + 9 * MM), titolo, fontsize=13, fontname="hebo")
    for i, r in enumerate(righe):
        f.pagina.insert_text((MARGINE + 6 * MM, y + 16 * MM + i * 11), r[:150], fontsize=7.5, fontname="helv")


def _barra_scala(f: _Foglio):
    W, H = f.formato
    y = H - MARGINE - CARTIGLIO - 5 * MM
    x = W - MARGINE - 6 * MM - 3 * f.k
    for i in range(3):
        f.pagina.draw_rect(f.fitz.Rect(x + i * f.k, y - 2, x + (i + 1) * f.k, y + 2), color=(0, 0, 0),
                           fill=(0, 0, 0) if i % 2 == 0 else (1, 1, 1), width=0.5)
        f.pagina.insert_text((x + i * f.k - 2, y + 11), str(i), fontsize=7)
    f.pagina.insert_text((x + 3 * f.k - 2, y + 11), "3 m", fontsize=7)


# ------------------------------------------------------------------ controllo dei testi
def numeri_sovrapposti(pagina, soglia: float = SOVRAPPOSIZIONE_MAX) -> list[str]:
    """Problemi di leggibilità dei testi della pagina: coppie di testi i cui rettangoli si intersecano oltre `soglia`
    dell'area del più piccolo, e testi toccati da una linea disegnata (linee e trattini di quota, linee di richiamo,
    facce dei muri). Per le linee conta la sagoma delle cifre (dalla linea di base all'altezza delle maiuscole), non
    il rettangolo del carattere, che comprende lo spazio per accenti e discendenti."""
    import fitz
    testi = []
    for blocco in pagina.get_text("dict")["blocks"]:
        for riga in blocco.get("lines", []):
            for span in riga.get("spans", []):
                if not span["text"].strip():
                    continue
                r = fitz.Rect(span["bbox"])
                ox, oy = span["origin"]
                alto = 0.72 * span["size"]
                dx, dy = riga.get("dir", (1, 0))
                if abs(dx) >= abs(dy):                         # orizzontale
                    sagoma = fitz.Rect(r.x0 + 0.2, oy - alto, r.x1 - 0.2, oy)
                else:                                          # verticale, dal basso verso l'alto
                    sagoma = fitz.Rect(ox - alto, r.y0 + 0.2, ox, r.y1 - 0.2)
                testi.append((span["text"].strip(), r, sagoma))
    out = []
    for i in range(len(testi)):
        for j in range(i + 1, len(testi)):
            (ta, ra, _), (tb, rb, _) = testi[i], testi[j]
            inter = ra & rb
            if inter.is_empty:
                continue
            piccolo = min(ra.get_area(), rb.get_area())
            if piccolo > 0 and inter.get_area() > soglia * piccolo:
                out.append(f"\"{ta}\" e \"{tb}\" si sovrappongono")
    from shapely.geometry import LineString, box
    segmenti = []
    for disegno in pagina.get_drawings():
        for voce in disegno["items"]:
            if voce[0] == "l":
                segmenti.append((voce[1], voce[2]))
            elif voce[0] == "re":
                q = voce[1]
                segmenti += [(q.tl, q.tr), (q.tr, q.br), (q.br, q.bl), (q.bl, q.tl)]
            elif voce[0] == "qu":
                q = voce[1]
                segmenti += [(q.ul, q.ur), (q.ur, q.lr), (q.lr, q.ll), (q.ll, q.ul)]
    for testo, _, sagoma in testi:
        b = box(sagoma.x0, sagoma.y0, sagoma.x1, sagoma.y1)
        for a, c in segmenti:
            if max(a.x, c.x) < sagoma.x0 or min(a.x, c.x) > sagoma.x1 or max(a.y, c.y) < sagoma.y0 \
                    or min(a.y, c.y) > sagoma.y1:
                continue
            if b.intersects(LineString([(a.x, a.y), (c.x, c.y)])):
                out.append(f"\"{testo}\" tocca una linea")
                break
    return out


# ------------------------------------------------------------------ confronto con il disegno di partenza
def trasformazione(punti: list[dict], specchio: bool):
    """Similitudine dal modello al disegno, ai minimi quadrati, da almeno due punti {modello: [x, y], disegno: [u, v]}.
    `specchio`: il disegno ha l'asse y verso il basso (immagini). Restituisce (funzione, scarto massimo in m)."""
    if len(punti) < 2:
        raise ValueError("`sorgente.punti`: servono almeno due punti corrispondenti tra modello e disegno")
    zs = [complex(*map(float, p["modello"])) for p in punti]
    ws = [complex(*map(float, p["disegno"])) for p in punti]
    zs2 = [z.conjugate() for z in zs] if specchio else zs
    zm, wm = sum(zs2) / len(zs2), sum(ws) / len(ws)
    den = sum(abs(z - zm) ** 2 for z in zs2)
    if den < 1e-12:
        raise ValueError("`sorgente.punti`: i punti del modello coincidono")
    a = sum((z - zm).conjugate() * (w - wm) for z, w in zip(zs2, ws)) / den
    b = wm - a * zm

    def f(x, y):
        z = complex(x, -y) if specchio else complex(x, y)
        w = a * z + b
        return (w.real, w.imag)
    scarto = max(abs(a * z + b - w) for z, w in zip(zs2, ws)) / abs(a)
    return f, scarto, abs(a)


def _file_sorgente(spec: dict, cartella: Path | None) -> Path:
    nome = Path(spec["file"])
    for base in ([cartella / "Riferimenti", cartella] if cartella else []) + [Path.cwd()]:
        if (base / nome).is_file():
            return base / nome
    if nome.is_file():
        return nome
    raise FileNotFoundError(f"disegno di partenza non trovato: {spec['file']} (si cerca in Riferimenti)")


def _carica_sorgente(spec: dict, cartella: Path | None):
    """("raster", pixmap in grigio) oppure ("vettori", [polilinee nelle unità del DXF])."""
    import fitz
    percorso = _file_sorgente(spec, cartella)
    est = percorso.suffix.lower()
    if est == ".dxf":
        import ezdxf
        from ezdxf import disassemble
        doc = ezdxf.readfile(str(percorso))
        linee = []
        for prim in disassemble.to_primitives(disassemble.recursive_decompose(doc.modelspace())):
            if prim.entity is not None and prim.entity.dxftype() in ("TEXT", "MTEXT", "ATTRIB", "INSERT"):
                continue
            v = [(p.x, p.y) for p in prim.vertices()]
            if len(v) >= 2:
                linee.append(v)
        return "vettori", linee, percorso
    if est == ".pdf":
        doc = fitz.open(str(percorso))
        pagina = doc[int(spec.get("pagina", 1)) - 1]
        return "raster", pagina.get_pixmap(dpi=int(spec.get("dpi", 200)), colorspace=fitz.csGRAY), percorso
    pix = fitz.Pixmap(str(percorso))
    if pix.n - pix.alpha != 1:
        pix = fitz.Pixmap(fitz.csGRAY, pix)
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)
    return "raster", pix, percorso


def _contorni_dei_muri(muri, aperture):
    from shapely.ops import unary_union
    pieno = unary_union(muri)
    if aperture:
        pieno = pieno.difference(unary_union([a.forma for a in aperture]))
    return pieno


def disegna_confronto(doc, scheda: dict, cartella: Path | None, titolo: str = ""):
    """Pagina del confronto: il disegno di partenza con sopra i muri del modello (rosso) e le stanze (blu
    tratteggiato). Restituisce (pagina, differenze, coincidenza) oppure None se la scheda non ha `sorgente`."""
    import fitz
    from shapely.geometry import LineString, MultiLineString, Point
    from shapely.ops import unary_union
    spec = scheda.get("sorgente")
    if not spec:
        return None
    muri, aperture, stanze, _ = raccogli(scheda)
    tipo, dati, percorso = _carica_sorgente(spec, cartella)
    specchio = tipo == "raster"
    T, scarto, unita_per_m = trasformazione(spec.get("punti", []), specchio)
    differenze = []
    if scarto > 0.05:
        differenze.append(f"i punti di riferimento non concordano: scarto fino a {scarto * 100:.0f} cm "
                          "(controllare `sorgente.punti`)")
    pieno = _contorni_dei_muri(muri, aperture)
    x0, y0, x1, y1 = unary_union([pieno] + [st["pol"] for st in stanze]).bounds
    margine = 0.8
    angoli = [T(x, y) for x in (x0 - margine, x1 + margine) for y in (y0 - margine, y1 + margine)]
    u0, u1 = min(a[0] for a in angoli), max(a[0] for a in angoli)
    v0, v1 = min(a[1] for a in angoli), max(a[1] for a in angoli)
    W, H = A3
    area = fitz.Rect(MARGINE + 6 * MM, MARGINE + 6 * MM, W - MARGINE - 6 * MM, H - MARGINE - CARTIGLIO - 6 * MM)
    if (u1 - u0) > (v1 - v0) * 1.25:
        W, H = H, W
        area = fitz.Rect(MARGINE + 6 * MM, MARGINE + 6 * MM, W - MARGINE - 6 * MM, H - MARGINE - CARTIGLIO - 6 * MM)
    pagina = doc.new_page(width=W, height=H)
    s = min(area.width / (u1 - u0), area.height / (v1 - v0))
    ox = area.x0 + (area.width - (u1 - u0) * s) / 2
    oy = area.y0 + (area.height - (v1 - v0) * s) / 2

    if specchio:
        def pg(u, v):
            return fitz.Point(ox + (u - u0) * s, oy + (v - v0) * s)
        pix = dati
        ritaglio = fitz.IRect(max(0, int(u0)), max(0, int(v0)), min(pix.width, int(math.ceil(u1))),
                              min(pix.height, int(math.ceil(v1))))
        if not ritaglio.is_empty:
            pezzo = fitz.Pixmap(pix.colorspace, ritaglio, False)
            pezzo.copy(pix, ritaglio)
            pagina.insert_image(fitz.Rect(pg(ritaglio.x0, ritaglio.y0), pg(ritaglio.x1, ritaglio.y1)), pixmap=pezzo)
    else:
        def pg(u, v):
            return fitz.Point(ox + (u - u0) * s, oy + (v1 - v) * s)
        for linea in dati:
            if all(not (u0 <= p[0] <= u1 and v0 <= p[1] <= v1) for p in linea):
                continue
            pagina.draw_polyline([pg(*p) for p in linea], color=(0.15, 0.15, 0.15), width=0.4)

    def pm(x, y):
        return pg(*T(x, y))

    for st in stanze:
        pagina.draw_polyline([pm(*c) for c in st["pol"].exterior.coords], color=(0.1, 0.3, 0.9), width=0.7,
                             dashes="[3 2] 0", closePath=True)
    bordi = []
    for parte in getattr(pieno, "geoms", [pieno]):
        if parte.geom_type != "Polygon":
            continue
        for anello in [parte.exterior] + list(parte.interiors):
            pagina.draw_polyline([pm(*c) for c in anello.coords], color=(0.9, 0.1, 0.1), width=0.6, closePath=True)
            cs = list(anello.coords)
            bordi += [(cs[i], cs[i + 1]) for i in range(len(cs) - 1)]

    # quanto del contorno dei muri cade sulle linee del disegno
    toll = 0.05                                           # m: tolleranza di una lettura in scala
    if specchio:
        pix = dati
        raggio = max(2, int(round(toll * unita_per_m)))
        campioni = pix.samples
        larghezza = pix.width

        def sulla_linea(x, y):
            u, v = T(x, y)
            u, v = int(round(u)), int(round(v))
            for dv in range(-raggio, raggio + 1):
                for du in range(-raggio, raggio + 1):
                    uu, vv = u + du, v + dv
                    if 0 <= uu < pix.width and 0 <= vv < pix.height and campioni[vv * larghezza + uu] < 140:
                        return True
            return False
    else:
        linee = unary_union([LineString(l) for l in dati if len(l) >= 2])

        def sulla_linea(x, y):
            return linee.distance(Point(T(x, y))) <= toll * unita_per_m

    totale = dentro = 0
    lontani = []
    for a, b in bordi:
        lung = math.dist(a, b)
        n = max(2, int(lung / 0.02))
        ok = sum(sulla_linea(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1))
        totale += n + 1
        dentro += ok
        if lung >= 0.30 and ok < 0.5 * (n + 1):
            lontani.append((lung, a, b))
    coincidenza = dentro / totale if totale else None
    for lung, a, b in sorted(lontani, reverse=True)[:12]:
        differenze.append(f"muro del modello da ({a[0]:.2f}; {a[1]:.2f}) a ({b[0]:.2f}; {b[1]:.2f}), "
                          f"{lung:.2f} m: non coincide con le linee del disegno")
    differenze += [str(d) for d in spec.get("differenze", []) or []]
    y = H - MARGINE - CARTIGLIO
    pagina.draw_rect(fitz.Rect(MARGINE, MARGINE, W - MARGINE, H - MARGINE), color=(0, 0, 0), width=0.8)
    pagina.draw_line(fitz.Point(MARGINE, y), fitz.Point(W - MARGINE, y), color=(0, 0, 0), width=0.8)
    pagina.insert_text((MARGINE + 6 * MM, y + 9 * MM), titolo or "CONFRONTO CON IL DISEGNO DI PARTENZA",
                       fontsize=13, fontname="hebo")
    righe = [f"Rosso: muri del modello.  Blu tratteggiato: stanze del modello.  Sotto: {percorso.name}.",
             f"Contorno dei muri sulle linee del disegno (entro 5 cm): {coincidenza:.0%}." if coincidenza is not None else ""]
    spazio = int((CARTIGLIO - 18 * MM) / 10) - len([r for r in righe if r])
    mostrate = differenze if len(differenze) <= spazio else differenze[:spazio - 1]
    righe += [("Differenze: " if i == 0 else "") + d for i, d in enumerate(mostrate)]
    if len(mostrate) < len(differenze):
        righe.append(f"... e altre {len(differenze) - len(mostrate)} differenze (elenco completo nel rapporto).")
    if not differenze:
        righe.append("Differenze: nessuna.")
    for i, r in enumerate(r for r in righe if r):
        pagina.insert_text((MARGINE + 6 * MM, y + 16 * MM + i * 10), r[:170], fontsize=7.5, fontname="helv")
    return pagina, differenze, coincidenza


# ------------------------------------------------------------------ consegna
def crea(scheda: dict, destinazione_pdf: Path, cartella: Path | None = None, confronto_pdf: Path | None = None,
         titolo: str = "") -> Esito:
    """Pianta quotata e confronto con il disegno di partenza in due documenti distinti: la pianta si inoltra così
    com'è, il confronto (PDF e PNG accanto, stesso nome) resta di uso interno. Senza `confronto_pdf` il confronto si
    calcola per il rapporto ma non si salva."""
    import fitz
    doc = fitz.open()
    nome = titolo or f"PIANTA - {scheda.get('progetto', 'Progetto')}"
    foglio, differenze, richiami = disegna_pianta(doc, scheda, nome)
    esito = Esito(richiami=richiami, differenze=list(differenze), omesse=list(foglio.omesse))
    esito.sovrapposizioni = numeri_sovrapposti(foglio.pagina)
    destinazione_pdf.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(destinazione_pdf))
    esito.pdf = destinazione_pdf
    doc_confronto = fitz.open()
    confronto = disegna_confronto(doc_confronto, scheda, cartella)
    if confronto is not None:
        pagina, diff, esito.coincidenza = confronto
        esito.differenze += diff
        if confronto_pdf is not None:
            confronto_pdf.parent.mkdir(parents=True, exist_ok=True)
            esito.confronto_png = confronto_pdf.with_suffix(".png")
            pagina.get_pixmap(dpi=110).save(str(esito.confronto_png))
            doc_confronto.save(str(confronto_pdf))
            esito.confronto_pdf = confronto_pdf
    return esito
