"""Arredi senza Blender: stessi pezzi, stesse misure e stessi materiali del costruttore per Blender.

Ogni funzione prende la scheda dell'arredo `sp` e il contesto `ctx` (telai delle pareti, altezza, elenco arredi)
e restituisce un `Oggetto` con nome leggibile e origine alla base: in SketchUp diventa un solo gruppo.
Le relazioni (piano su colonne) si leggono dalla scheda e non si digitano due volte.
"""

from __future__ import annotations

import math

from .forme import Costruttore, Telaio, telaio_parete
from .materiali import CESTONI, LIBRI, TELE, TESSUTI
from .scena import Oggetto
from ..verifica_geometria import estremi_piano


class Contesto:
    """Ciò che un arredo deve sapere della stanza: i telai delle pareti, le lunghezze, l'altezza, gli altri arredi."""

    def __init__(self, telai: dict[str, Telaio], lunghezze: dict[str, float], altezza: float, arredi: list[dict]):
        self._telai = telai
        self._lunghezze = lunghezze
        self.H = altezza
        self.arredi = arredi

    def telaio(self, parete: str) -> Telaio:
        try:
            return self._telai[parete]
        except KeyError:
            raise ValueError(f"parete sconosciuta: {parete!r} (pareti note: {', '.join(sorted(self._telai))})") from None

    def lunghezza(self, parete: str) -> float:
        return self._lunghezze[parete]

    @classmethod
    def rettangolare(cls, L: float, W: float, H: float, arredi: list[dict]) -> "Contesto":
        pareti = ("sud", "nord", "ovest", "est")
        return cls({p: telaio_parete(p, L, W) for p in pareti},
                   {"sud": L, "nord": L, "ovest": W, "est": W}, H, arredi)


def _libri(p, m, u0, u1, d0, d1, zb, hmax, indice0=0):
    """Fila di libri in piedi tra u0 e u1."""
    u = u0 + 0.01
    i = indice0
    while u < u1 - 0.03:
        sp = 0.018 + 0.006 * ((i * 7) % 4)
        h = hmax * (0.72 + 0.07 * ((i * 5) % 5))
        p.box_p(m, u, d0, zb, min(u + sp, u1 - 0.005), d1, zb + h, LIBRI[i % 5])
        u += sp + 0.002
        i += 1


def letto(sp, ctx):
    testa = sp["testa"]
    dx, dy = sp["dx_m"], sp["dy_m"]
    lunghezza, larghezza = (dy, dx) if testa in ("nord", "sud") else (dx, dy)
    w, l = larghezza, lunghezza
    p = Costruttore(sp["id"])
    tess = TESSUTI.get(sp.get("colore_tessuto", "azzurro"), "Tessuto azzurro")
    p.box((-w / 2, -l / 2, 0.0), (w / 2, l / 2, 0.20), "Legno chiaro")
    p.box((-w / 2 + 0.006, -l / 2 + 0.006, 0.20), (w / 2 - 0.006, l / 2 - 0.006, 0.40), "Legno chiaro")
    p.smussato((-w / 2 + 0.03, -l / 2 + 0.03, 0.40), (w / 2 - 0.03, l / 2 - 0.03, 0.62), "Cuscino bianco", 0.025)
    testa_y = l / 2 - 0.04
    cusc = 0.441
    p.smussato((-0.343, testa_y - cusc, 0.62), (0.343, testa_y, 0.74), "Cuscino bianco", 0.04)
    p.smussato((-w / 2 + 0.02, -l / 2 + 0.02, 0.60), (w / 2 - 0.02, testa_y - cusc - 0.03, 0.665), tess, 0.025)
    cx = sp["x0_m"] + sp["dx_m"] / 2
    cy = sp["y0_m"] + sp["dy_m"] / 2
    ang = {"nord": 0.0, "sud": math.pi, "ovest": math.pi / 2, "est": -math.pi / 2}[testa]
    return p.chiudi((ang, cx, cy))


def cassettiera(sp, ctx):
    m = ctx.telaio(sp["parete"])
    p = Costruttore(sp["id"])
    prof = sp["profondita_m"]
    u = sp["da_m"]
    k = 0
    for c in sp["colonne"]:
        w, h = c["larghezza_m"], c["altezza_m"]
        p.box_p(m, u, 0.0, 0.0, u + w, prof, h, "Laccato bianco")
        n = c.get("cestoni", 1)
        # tipi di cestone: (quota da terra, altezza): dal basso verso l'alto
        schema = {1: [(0.087, 0.231)], 2: [(0.087, 0.231), (0.337, 0.231)],
                  4: [(0.087, 0.231), (0.337, 0.231), (0.587, 0.093), (0.701, 0.093)]}[n]
        for (zb, hb) in schema:
            larg_alto, larg_basso = w * 0.83, w * 0.60
            uc = u + w / 2
            poly = [(uc - larg_basso / 2, zb), (uc + larg_basso / 2, zb),
                    (uc + larg_alto / 2, zb + hb), (uc - larg_alto / 2, zb + hb)]
            p.prisma(m, poly, prof - 0.05, prof + 0.012, CESTONI[k % 3])
            k += 1
        u += w
    return p.chiudi()


def piano_scrivania(sp, ctx):
    """Piano su colonne di cassettiere: se c'è `su`, estremi e quota derivano dalle colonne (mai a mano)."""
    m = ctx.telaio(sp["parete"])
    p = Costruttore(sp["id"])
    if "su" in sp:
        u0, u1, z0 = estremi_piano(sp, ctx.arredi)
    else:
        u0, u1, z0 = sp["da_m"], sp["a_m"], sp["z0_m"]
    p.box_p(m, u0, 0.0, z0, u1, sp["profondita_m"], z0 + sp["spessore_m"], "Legno chiaro")
    return p.chiudi()


def sgabello(sp, ctx):
    p = Costruttore(sp["id"])
    r, h = sp["diametro_m"] / 2, sp["altezza_m"]
    cx, cy = sp["x_m"], sp["y_m"]
    p.cilindro(cx, cy, h - 0.04, h, r, "Sgabello senape", 28)
    for i in range(4):
        a = math.pi / 4 + i * math.pi / 2
        gx, gy = cx + 0.62 * r * math.cos(a), cy + 0.62 * r * math.sin(a)
        p.cilindro_asse((gx, gy, 0.0), (gx, gy, h - 0.04), 0.014, "Legno chiaro", 10)
    return p.chiudi()


def pensile_libri(sp, ctx):
    """Pensile a scomparti. Uno scomparto "libri" con `elementi: [[u0, larghezza, altezza], ...]` usa i dorsi
    del disegno; senza `elementi` i libri sono generici (pseudo-casuali) e `completa()` lo dichiara come ipotesi."""
    m = ctx.telaio(sp["parete"])
    p = Costruttore(sp["id"])
    u0, w, pr = sp["da_m"], sp["larghezza_m"], sp["profondita_m"]
    z0, h = sp["z0_m"], sp["altezza_m"]
    s = sp.get("spessore_m", 0.02)
    scomparti = sp["scomparti"]
    n = len(scomparti)
    p.box_p(m, u0, 0, z0, u0 + w, pr, z0 + s, "Laccato bianco")
    p.box_p(m, u0, 0, z0 + h - s, u0 + w, pr, z0 + h, "Laccato bianco")
    p.box_p(m, u0, 0, z0 + s, u0 + w, 0.012, z0 + h - s, "Laccato bianco")
    for i in range(n + 1):      # fianchi e divisori, centrati sugli scomparti uguali
        centro = u0 + i * w / n
        a_ = min(max(centro - s / 2, u0), u0 + w - s)
        p.box_p(m, a_, 0.012, z0 + s, a_ + s, pr, z0 + h - s, "Laccato bianco")
    for i, sc in enumerate(scomparti):
        tipo = sc["tipo"] if isinstance(sc, dict) else sc
        ua, ub = u0 + i * w / n + s, u0 + (i + 1) * w / n - s
        if tipo == "libri":
            if isinstance(sc, dict) and sc.get("elementi"):
                for k, (u, lw, lh) in enumerate(sc["elementi"]):
                    p.box_p(m, u, 0.02, z0 + s, u + lw, pr - 0.03, z0 + s + lh, LIBRI[(k + 5 * i) % 5])
            else:
                _libri(p, m, ua, ub, 0.02, pr - 0.03, z0 + s, h - 2 * s - 0.02, indice0=i * 4)
        else:
            for j in range(2):
                zb = z0 + s + j * 0.095            # impilati: il secondo appoggia sul primo
                uc = (ua + ub) / 2
                poly = [(uc - 0.07, zb), (uc + 0.07, zb), (uc + 0.115, zb + 0.095), (uc - 0.115, zb + 0.095)]
                p.prisma(m, poly, 0.03, pr - 0.02, CESTONI[(i + j) % 3])
    return p.chiudi()


def mensola_vassoio(sp, ctx):
    """Vassoio a muro (fondo, due bordi, schienale e frontale) con blocchi [u0, larghezza, altezza] appoggiati
    sul fondo: libri o scatole come nel disegno."""
    m = ctx.telaio(sp["parete"])
    p = Costruttore(sp["id"])
    u0, w, pr = sp["da_m"], sp["larghezza_m"], sp["profondita_m"]
    z0, h = sp["z0_m"], sp["altezza_m"]
    f, b = sp.get("spessore_fondo_m", 0.015), sp.get("spessore_bordo_m", 0.013)
    p.box_p(m, u0, 0, z0, u0 + w, pr, z0 + f, "Legno chiaro")                    # fondo
    p.box_p(m, u0, 0, z0 + f, u0 + b, pr, z0 + h, "Legno chiaro")                # bordo
    p.box_p(m, u0 + w - b, 0, z0 + f, u0 + w, pr, z0 + h, "Legno chiaro")        # bordo
    p.box_p(m, u0 + b, 0, z0 + f, u0 + w - b, b, z0 + h, "Legno chiaro")         # schienale
    p.box_p(m, u0 + b, pr - b, z0 + f, u0 + w - b, pr, z0 + h, "Legno chiaro")   # frontale
    for k, (u, lw, lh) in enumerate(sp["blocchi"]):
        p.box_p(m, u, b + 0.003, z0 + f, u + lw, pr - b - 0.003, z0 + f + lh, LIBRI[k % 5])
    return p.chiudi()


def mensola_portalibri(sp, ctx):
    m = ctx.telaio(sp["parete"])
    p = Costruttore(sp["id"])
    u0, w, pr = sp["da_m"], sp["larghezza_m"], sp["profondita_m"]
    z0, h = sp["z0_m"], sp["altezza_m"]
    p.box_p(m, u0, 0, z0, u0 + w, pr, z0 + h, "Legno chiaro")
    _libri(p, m, u0 + 0.02, u0 + w - 0.02, 0.02, pr - 0.015, z0 + h, 0.145, indice0=int(u0 * 10))
    return p.chiudi()


def quadro(sp, ctx):
    m = ctx.telaio(sp["parete"])
    p = Costruttore(sp["id"])
    c, w, h, z0 = sp["centro_m"], sp["larghezza_m"], sp["altezza_m"], sp["z0_m"]
    p.box_p(m, c - w / 2, 0, z0, c + w / 2, 0.025, z0 + h, "Cornice nera")
    idx = int("".join(ch for ch in sp["id"] if ch.isdigit()) or 1) - 1
    p.box_p(m, c - w / 2 + 0.01, 0.025, z0 + 0.01, c + w / 2 - 0.01, 0.027, z0 + h - 0.01, TELE[idx % 4])
    return p.chiudi()


def arco(sp, ctx):
    m = ctx.telaio(sp["parete"])
    p = Costruttore(sp["id"])
    u0, w, h = sp["da_m"], sp["larghezza_m"], sp["altezza_m"]
    r = w / 2
    pts = [(u0, 0.0), (u0 + w, 0.0)]
    seg = 20
    for i in range(seg + 1):
        a = math.pi * i / seg
        pts.append((u0 + r + r * math.cos(a), h - r + r * math.sin(a)))
    p.prisma(m, pts, 0.0, 0.012, "Arco terracotta")
    return p.chiudi()


def tv(sp, ctx):
    m = ctx.telaio(sp["parete"])
    p = Costruttore(sp["id"])
    u0, w, h, z0 = sp["da_m"], sp["larghezza_m"], sp["altezza_m"], sp["z0_m"]
    p.box_p(m, u0, 0, z0, u0 + w, 0.04, z0 + h, "Televisore nero")
    p.box_p(m, u0 + 0.015, 0.04, z0 + 0.015, u0 + w - 0.015, 0.042, z0 + h - 0.015, "Schermo spento")
    return p.chiudi()


def termosifone(sp, ctx):
    m = ctx.telaio(sp["parete"])
    p = Costruttore(sp["id"])
    u0, w, h, z0, pr = sp["da_m"], sp["larghezza_m"], sp["altezza_m"], sp["z0_m"], sp["profondita_m"]
    n = 10
    el = w / n
    for i in range(n):
        p.box_p(m, u0 + i * el + 0.004, 0.03, z0, u0 + (i + 1) * el - 0.004, pr, z0 + h - 0.04, "Termosifone bianco")
    p.box_p(m, u0, 0.02, z0 + h - 0.04, u0 + w, pr - 0.01, z0 + h, "Termosifone bianco")
    for uu in (u0 + 0.05, u0 + w - 0.07):   # staffe a muro
        p.box_p(m, uu, 0.0, z0 + 0.10, uu + 0.02, 0.03, z0 + 0.14, "Metallo bastone")
        p.box_p(m, uu, 0.0, z0 + h - 0.16, uu + 0.02, 0.03, z0 + h - 0.12, "Metallo bastone")
    return p.chiudi()


def bastone_tende(sp, ctx):
    m = ctx.telaio(sp["parete"])
    p = Costruttore(sp["id"])
    a = m(sp["da_m"], 0.10, sp["z_m"])
    b = m(sp["a_m"], 0.10, sp["z_m"])
    p.cilindro_asse(a, b, 0.012, "Metallo bastone", 16)
    for u in (sp["da_m"] + 0.03, sp["a_m"] - 0.03):
        p.cilindro_asse(m(u, 0.0, sp["z_m"]), m(u, 0.10, sp["z_m"]), 0.008, "Metallo bastone", 8)
    return p.chiudi()


def tenda(sp, ctx, z_bastone=2.977):
    """Tenda a pieghe: superficie ondulata con spessore, appesa al bastone e lunga fino a 2 cm da terra."""
    m = ctx.telaio(sp["parete"])
    p = Costruttore(sp["id"], "Tessili")
    u0, w = sp["da_m"], sp["larghezza_m"]
    z_alto, z_basso = z_bastone - 0.012, 0.02   # la sommità tocca il bastone (raggio 12 mm)
    n_u, n_z = 56, 6
    fold = w / 0.10          # una piega ogni 10 cm
    amp, d_c, spess = 0.035, 0.10, 0.006

    def d_f(t, z):
        return d_c + amp * math.sin(2 * math.pi * fold * t + 0.5 * math.sin(z * 1.9))

    griglia = []
    for j in range(n_z + 1):
        z = z_alto - (z_alto - z_basso) * j / n_z
        griglia.append([(u0 + w * i / n_u, d_f(i / n_u, z), z) for i in range(n_u + 1)])

    def pt(i, j, off=0.0):
        u, d, z = griglia[j][i]
        return m(u, d + off, z)

    quadri = []
    for j in range(n_z):
        for i in range(n_u):
            quadri.append([pt(i, j), pt(i + 1, j), pt(i + 1, j + 1), pt(i, j + 1)])
            quadri.append([pt(i, j, spess), pt(i, j + 1, spess), pt(i + 1, j + 1, spess), pt(i + 1, j, spess)])
    for i in range(n_u):
        quadri.append([pt(i, 0), pt(i, 0, spess), pt(i + 1, 0, spess), pt(i + 1, 0)])
        quadri.append([pt(i, n_z), pt(i + 1, n_z), pt(i + 1, n_z, spess), pt(i, n_z, spess)])
    for j in range(n_z):
        quadri.append([pt(0, j), pt(0, j + 1), pt(0, j + 1, spess), pt(0, j, spess)])
        quadri.append([pt(n_u, j), pt(n_u, j, spess), pt(n_u, j + 1, spess), pt(n_u, j + 1)])
    p.griglia(quadri, "Tenda crema")
    return p.chiudi(liscio=True, ricalcola_normali=True)


def armadio_a_muro(sp, ctx):
    m = ctx.telaio(sp["parete"])
    p = Costruttore(sp["id"])
    pr = sp["profondita_m"]
    lung = ctx.lunghezza(sp["parete"])
    p.box_p(m, 0.0, 0.0, 0.0, lung, pr, ctx.H, "Laccato bianco")
    aw, ah = sp["anta_larghezza_m"], sp["anta_altezza_m"]
    ua = lung - aw if sp.get("anta_lato", "nord") == "nord" else 0.0
    p.box_p(m, ua, pr, 0.0, ua + aw, pr + 0.02, ah, "Anta armadio")
    um = ua + 0.05 if sp.get("anta_lato", "nord") == "nord" else ua + aw - 0.05
    p.box_p(m, um - 0.008, pr + 0.02, 1.0, um + 0.008, pr + 0.05, 1.12, "Maniglia")
    return p.chiudi()


def oggetto_libero(sp, ctx):
    """Oggetto fatto di forme libere, per arredi e strutture non scatolari. Le coordinate sono quelle della stanza
    (o dell'edificio) e, se c'è `parete`, anche di parete (`u0_m, d0_m, ...`). Con `posizione_m: [x, y]` e
    `rotazione_gradi` le parti si scrivono attorno all'origine e l'oggetto viene ruotato e spostato.

    Forme (`forma`): scatola (p0_m, p1_m), scatola_parete (u0_m, d0_m, z0_m, u1_m, d1_m, z1_m), cilindro (x_m, y_m,
    z0_m, z1_m, raggio_m), asse (da_m, a_m, raggio_m), estrusione (poligono_m, z0_m, z1_m), torno (profilo_m con
    coppie [raggio, quota], x_m, y_m, z0_m), sfera (x_m, y_m, z_m, raggio_m), prisma (piano xz o yz, punti_m, a0_m,
    a1_m), smussato (p0_m, p1_m, raggio_m), piano_forato (p0_m, p1_m, foro_m), vasca (p0_m, p1_m, spessore_m), cuscino (centro_m, semiassi_m, tondo, piega_m, inclina_gradi,
    ruota_gradi, bottoni_m: imbottiti lisci). `materiale` (nome della tavolozza) per ogni parte."""
    p = Costruttore(sp["id"], sp.get("collezione", "Arredi"))
    for k, parte in enumerate(sp["parti"]):
        mat = parte.get("materiale", "Legno chiaro")
        f = parte["forma"]
        try:
            if f == "scatola":
                p.box(parte["p0_m"], parte["p1_m"], mat)
            elif f == "scatola_parete":
                m = ctx.telaio(sp["parete"])
                p.box_p(m, parte["u0_m"], parte["d0_m"], parte["z0_m"], parte["u1_m"], parte["d1_m"], parte["z1_m"], mat)
            elif f == "cilindro":
                p.cilindro(parte["x_m"], parte["y_m"], parte["z0_m"], parte["z1_m"], parte["raggio_m"], mat,
                           parte.get("segmenti", 24))
            elif f == "asse":
                p.cilindro_asse(parte["da_m"], parte["a_m"], parte["raggio_m"], mat, parte.get("segmenti", 14))
            elif f == "estrusione":
                p.estrusione(parte["poligono_m"], parte["z0_m"], parte["z1_m"], mat, parte.get("materiale_basso"),
                             parte.get("materiale_lati"))
            elif f == "torno":
                p.torno([tuple(c) for c in parte["profilo_m"]], parte["x_m"], parte["y_m"], parte.get("z0_m", 0.0), mat,
                        parte.get("segmenti", 24))
            elif f == "sfera":
                # sfera liscia (globi, pomoli): un cubo suddiviso e gonfiato, senza poli e senza sfaccettature
                r, n = parte["raggio_m"], parte.get("segmenti", 24)
                p.cuscino((parte["x_m"], parte["y_m"], parte["z_m"]), (r, r, r), mat, tondo=(1.0, 1.0), seg=(n, 0))
            elif f == "prisma":
                piano = parte["piano"]
                m = Telaio((0, 0), (1, 0), (0, 1)) if piano == "xz" else Telaio((0, 0), (0, 1), (1, 0))
                p.prisma(m, [tuple(c) for c in parte["punti_m"]], parte["a0_m"], parte["a1_m"], mat)
            elif f == "smussato":
                p.smussato(parte["p0_m"], parte["p1_m"], mat, parte.get("raggio_m", 0.02))
            elif f == "piano_forato":
                p.piano_forato(parte["p0_m"], parte["p1_m"], tuple(parte["foro_m"]), mat)
            elif f == "vasca":
                p.vasca(parte["p0_m"], parte["p1_m"], parte.get("spessore_m", 0.008), mat)
            elif f == "cuscino":
                p.cuscino(parte["centro_m"], parte["semiassi_m"], mat, tuple(parte.get("tondo", (0.5, 0.35))),
                          parte.get("piega_m", 0.0), parte.get("inclina_gradi", 0.0), parte.get("ruota_gradi", 0.0),
                          [tuple(b) for b in parte.get("bottoni_m", [])], seg=tuple(parte.get("segmenti", (28, 14))))
            else:
                raise ValueError(f"forma sconosciuta: {f!r}")
        except KeyError as e:
            raise ValueError(f"{sp['id']}, parte {k + 1} ({f}): manca il campo {e.args[0]!r}") from None
    pos = sp.get("posizione_m")
    trasf = None
    if pos is not None or sp.get("rotazione_gradi"):
        x, y = (pos or (0.0, 0.0))[:2]
        trasf = (math.radians(sp.get("rotazione_gradi", 0.0)), x, y)
    return p.chiudi(trasf, liscio=bool(sp.get("liscio", False)))


def _trasf(sp):
    x, y = sp["posizione_m"][:2]
    return (math.radians(sp.get("rotazione_gradi", 0.0)), x, y)


def poltrona_guscio(sp, ctx):
    """Poltrona girevole a guscio imbottito (riferimento: Beliani NOLVIK, 82 x 85 x 82 cm, seduta a 40 cm): base a
    disco in metallo, stelo, guscio basso sotto la seduta, schienale a guscio che avvolge, cuscino dello schienale
    capitonné con quattro bottoni, braccioli a rullo, seduta. Il davanti guarda verso +y prima della rotazione;
    `posizione_m` è il centro della base. Le misure si scalano da `larghezza_m`, `profondita_m`, `altezza_m`."""
    # i divisori sono le misure della forma di base: la poltrona esce con le misure indicate (verificato)
    sx = sp.get("larghezza_m", 0.82) / 0.786
    sy = sp.get("profondita_m", 0.85) / 0.864
    sz = sp.get("altezza_m", 0.82) / 0.841
    v = sp.get("materiale", "Velluto senape")
    met = sp.get("materiale_base", "Metallo nero")
    p = Costruttore(sp["id"], sp.get("collezione", "Arredi"))
    # base: disco sottile e largo che sale appena verso il centro; stelo in vista (come nelle foto del prodotto)
    p.torno([(0.0, 0.0), (0.30 * sx, 0.0), (0.30 * sx, 0.006), (0.24 * sx, 0.014), (0.06, 0.035 * sz),
             (0.035, 0.045 * sz), (0.0, 0.045 * sz)], 0.0, -0.02 * sy, 0.0, met, 48)
    p.cilindro(0.0, -0.02 * sy, 0.04 * sz, 0.215 * sz, 0.03, met, 20)
    # guscio basso: una ciotola tonda sotto la seduta
    p.cuscino((0.0, 0.02 * sy, 0.30 * sz), (0.36 * sx, 0.385 * sy, 0.095 * sz), v, tondo=(0.75, 0.6), seg=(30, 0))
    # seduta: cuscino spesso e gonfio, sporge sul davanti
    p.cuscino((0.0, 0.10 * sy, 0.345 * sz), (0.28 * sx, 0.31 * sy, 0.068 * sz), v, tondo=(0.55, 0.45), seg=(30, 0))
    # guscio dello schienale: alto e avvolgente
    p.cuscino((0.0, -0.31 * sy, 0.55 * sz), (0.43 * sx, 0.11 * sy, 0.285 * sz), v, tondo=(0.6, 0.45),
              piega=0.33 * sx, inclina_gradi=14, seg=(36, 0))
    # cuscino dello schienale, gonfio e capitonné: quattro bottoni con la stoffa infossata attorno
    p.cuscino((0.0, -0.19 * sy, 0.585 * sz), (0.30 * sx, 0.10 * sy, 0.215 * sz), v, tondo=(0.6, 0.5),
              piega=0.45 * sx, inclina_gradi=14, seg=(33, 0), profondita_bottoni=0.03,
              bottoni=[(-0.12 * sx, 0.06 * sz), (0.04 * sx, 0.10 * sz), (0.13 * sx, 0.0), (0.0, -0.08 * sz)])
    # braccioli: rulli gonfi appoggiati ai lati della seduta, un po' più avanti del guscio
    for s_ in (-1, 1):
        p.cuscino((s_ * 0.30 * sx, 0.08 * sy, 0.47 * sz), (0.085 * sx, 0.31 * sy, 0.085 * sz), v, tondo=(0.85, 0.7),
                  inclina_gradi=-4, ruota_gradi=-s_ * 5, seg=(30, 0))
    return p.chiudi(_trasf(sp))


def divano_imbottito(sp, ctx):
    """Divano imbottito dalle linee morbide: basamento, cuscini di seduta, schienale, braccioli a rullo, piedini e
    due cuscini decorativi. Davanti verso +y prima della rotazione; `posizione_m` è il centro dell'ingombro."""
    L = sp.get("lunghezza_m", 2.10)
    P = sp.get("profondita_m", 0.92)
    hs = sp.get("altezza_seduta_m", 0.43)
    v = sp.get("materiale", "Velluto ruggine")
    piedi = sp.get("materiale_piedi", "Legno noce")
    n = int(sp.get("sedute", 3))
    p = Costruttore(sp["id"], sp.get("collezione", "Arredi"))
    for x in (-L / 2 + 0.14, L / 2 - 0.14):
        for y in (-P / 2 + 0.12, P / 2 - 0.12):
            p.torno([(0.0, 0.0), (0.018, 0.0), (0.024, 0.11), (0.0, 0.11)], x, y, 0.0, piedi, 16)
    p.cuscino((0.0, 0.0, 0.20), (L / 2 - 0.01, P / 2 - 0.01, 0.10), v, tondo=(0.35, 0.22), seg=(24, 0))       # basamento
    braccio = 0.13
    interno = L - 2 * braccio
    w = interno / n
    for k in range(n):
        x = -interno / 2 + w * (k + 0.5)
        p.cuscino((x, 0.07, hs - 0.065), (w / 2 - 0.006, P / 2 - 0.17, 0.07), v, tondo=(0.4, 0.28), seg=(18, 0))
    p.cuscino((0.0, -P / 2 + 0.12, hs + 0.17), (interno / 2 + 0.02, 0.11, 0.21), v, tondo=(0.45, 0.3),
              inclina_gradi=10, seg=(24, 0))                                                                     # schienale
    for s in (-1, 1):
        p.cuscino((s * (L / 2 - braccio / 2 - 0.005), 0.0, hs + 0.02), (braccio / 2, P / 2 - 0.02, 0.15), v,
                  tondo=(0.6, 0.4), seg=(18, 0))
        p.cuscino((s * (interno / 2 - 0.22), -P / 2 + 0.30, hs + 0.20), (0.21, 0.07, 0.19),
                  sp.get("materiale_cuscini", "Velluto senape"), tondo=(0.6, 0.45), inclina_gradi=18,
                  ruota_gradi=s * 8, seg=(15, 0))
    return p.chiudi(_trasf(sp))


def lavabo(sp, ctx):
    """Lavabo con vasca incassata nel piano, rubinetto e (salvo `mobile: false`) mobile sotto. Davanti verso +y
    prima della rotazione; `posizione_m` è il centro dell'ingombro a terra, contro il muro dal lato -y. Misure:
    `larghezza_m` (0,60), `profondita_m` (0,48), `altezza_m` del piano (0,85), `sospeso` (mobile staccato da terra,
    vero), `vasca_m` [larghezza, profondità] (lasciando 8 cm di piano ai lati)."""
    L = float(sp.get("larghezza_m", 0.60))
    P = float(sp.get("profondita_m", 0.48))
    zt = float(sp.get("altezza_m", 0.85))
    bw, bd = sp.get("vasca_m", [min(L - 0.16, 0.50), min(P - 0.16, 0.36)])
    bw, bd = min(float(bw), L - 0.06), min(float(bd), P - 0.10)
    zb = zt - 0.15                                   # spessore del piano con la vasca incassata
    yc = 0.02                                        # vasca un poco verso il davanti: dietro c'è il rubinetto
    ceramica = sp.get("materiale", "Ceramica bianca")
    p = Costruttore(sp["id"], sp.get("collezione", "Arredi"))
    p.piano_forato((-L / 2, -P / 2, zb), (L / 2, P / 2, zt), (-bw / 2, yc - bd / 2, bw / 2, yc + bd / 2), ceramica)
    p.vasca((-bw / 2, yc - bd / 2, zb), (bw / 2, yc + bd / 2, zt), 0.012, ceramica)
    if sp.get("mobile", True):
        z0 = 0.30 if sp.get("sospeso", True) else 0.0
        p.box((-L / 2 + 0.005, -P / 2, z0), (L / 2 - 0.005, P / 2 - 0.01, zb), sp.get("materiale_mobile", "Laccato bianco"))
    yr = (-P / 2 + (yc - bd / 2)) / 2                # rubinetto tra il muro e la vasca
    cromo = sp.get("materiale_rubinetto", "Cromo")
    p.cilindro(0.0, yr, zt, zt + 0.16, 0.018, cromo, 20)
    p.cilindro_asse((0.0, yr, zt + 0.14), (0.0, yr + 0.11, zt + 0.14), 0.011, cromo)
    return p.chiudi(_trasf(sp) if sp.get("posizione_m") is not None else None)


COSTRUTTORI = {
    "letto": letto, "cassettiera_cestoni": cassettiera, "piano": piano_scrivania, "sgabello": sgabello,
    "pensile_libri": pensile_libri, "mensola_portalibri": mensola_portalibri, "mensola_vassoio": mensola_vassoio,
    "quadro": quadro, "arco_decorativo": arco, "tv": tv, "termosifone": termosifone, "bastone_tende": bastone_tende,
    "tenda": tenda, "armadio_a_muro": armadio_a_muro, "oggetto": oggetto_libero,
    "poltrona_guscio": poltrona_guscio, "divano_imbottito": divano_imbottito, "lavabo": lavabo,
}


def arredo(sp: dict, ctx: Contesto) -> Oggetto:
    try:
        fn = COSTRUTTORI[sp["tipo"]]
    except KeyError:
        raise ValueError(f"tipo di arredo sconosciuto: {sp['tipo']}") from None
    return fn(sp, ctx)
