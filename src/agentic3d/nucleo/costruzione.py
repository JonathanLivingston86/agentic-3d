"""Dalla scheda alla scena, senza Blender.

`scena_da_scheda(scheda)` prende la scheda già completata (`scheda.completa`) e costruisce tutti gli oggetti:
pavimento, soffitto, pareti con le loro aperture, serramenti, arredi. Per le stanze rettangolari ripete le
convenzioni del costruttore per Blender: origine nell'angolo interno sud-ovest, pareti nord e sud che coprono gli
angoli, ovest ed est tra le due.
"""

from __future__ import annotations

from .aperture import cerniera_a_u1, serramento
from .ergonomia import registra_finestra, registra_porta
from .architettura import lastra, muro
from .arredi import Contesto, arredo
from .forme import telaio_parete
from .scena import Scena

PARETI = ("sud", "nord", "ovest", "est")
NOMI_MURI = {"sud": "Muro Sud", "nord": "Muro Nord", "ovest": "Muro Ovest", "est": "Muro Est"}


def _pezzo_della_parete(parete: str, m, spessore: float, estremi) -> tuple:
    """La parete di una stanza come pezzo della rete (asse a metà spessore, stesso u del telaio) e il lato della
    faccia rivolta alla stanza."""
    from . import geom2d as g
    from .pareti import Pezzo
    p0, p1 = m(0.0, -spessore / 2, 0.0)[:2], m(1.0, -spessore / 2, 0.0)[:2]
    w = Pezzo(NOMI_MURI[parete][5:], NOMI_MURI[parete][5:], 0.0, p0, p1, spessore)
    w.ui = w.uo = tuple(estremi)
    verso_stanza = m.direzione(0, 1, 0)[:2]
    return w, ("sinistra" if g.dot(verso_stanza, w.en) > 0 else "destra")


def scena_da_stanza(st: dict, nome: str = "Progetto", muri_uniti: bool = True) -> Scena:
    """Con `muri_uniti` le quattro pareti sono un solo solido ("Tamponature"); senza, quattro oggetti "Muro ..."
    (usati dai render e dal confronto con il costruttore classico)."""
    from .muri_uniti import muri_uniti as unisci_muri
    scena = Scena(nome)
    L, W, H = float(st["lunghezza_m"]), float(st["larghezza_m"]), float(st["altezza_m"])
    t = {p: float(st["pareti"][p]["spessore_m"]) for p in PARETI}
    fascia = st.get("fascia_altezza_m")
    x0, x1 = -t["ovest"], L + t["est"]
    y0, y1 = -t["sud"], W + t["nord"]
    contorno = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

    scena.aggiungi(lastra("Pavimento", contorno, -0.10, 0.0, "pavimento", "Pavimento rovere", "Intonaco pareti",
                          "Intonaco pareti")).gruppo = "Solai/Pavimenti"
    if st.get("soffitto", True):      # senza soffitto (esterni, oggetti): `soffitto: false` nella stanza
        scena.aggiungi(lastra("Soffitto", contorno, H, H + 0.10, "soffitto", "Soffitto bianco", "Soffitto bianco",
                              "Soffitto bianco")).gruppo = "Solai/Soffitto"

    estremi = {"sud": (x0, x1), "nord": (x0, x1), "ovest": (0.0, W), "est": (0.0, W)}
    pezzi: list[dict] = []
    for parete in PARETI:
        m = telaio_parete(parete, L, W)
        aperture = []
        for ap in st.get("aperture", []):
            if ap["parete"] != parete:
                continue
            fin = ap["tipo"] in ("finestra", "portafinestra")
            q = ap.get("quota_davanzale_m", 0.0) if fin else -0.05
            aperture.append({"u0": ap["da_m"], "u1": ap["da_m"] + ap["larghezza_m"], "z0": q,
                             "z1": q + ap["altezza_m"] if fin else ap["altezza_m"]})
        if muri_uniti:
            w, lato_stanza = _pezzo_della_parete(parete, m, t[parete], estremi[parete])
            pezzi.append({"w": w, "tagli": aperture, "fascia_a": bool(fascia) and lato_stanza == "sinistra",
                          "fascia_b": bool(fascia) and lato_stanza == "destra"})
        else:
            scena.aggiungi(muro(NOMI_MURI[parete], m, t[parete], 0.0, H, estremi[parete], None, aperture, fascia))
    if muri_uniti:
        scena.aggiungi(unisci_muri("Tamponature", pezzi, 0.0, H, float(fascia) if fascia else None)).gruppo = "Muri"

    for ap in st.get("aperture", []):
        m = telaio_parete(ap["parete"], L, W)
        scena.aggiungi(serramento(ap, m, t[ap["parete"]]))
        u0, u1 = ap["da_m"], ap["da_m"] + ap["larghezza_m"]
        verso_stanza = m.direzione(0, 1, 0)[:2]
        if ap["tipo"] == "porta":
            a_u1 = cerniera_a_u1(ap)
            registra_porta(scena, ap["id"], m(u1 if a_u1 else u0, 0.0, 0.0)[:2], m.direzione(-1 if a_u1 else 1, 0, 0)[:2],
                           verso_stanza, (u1 - u0) - 0.008, 0.0, float(ap["altezza_m"]))
        else:
            q = ap.get("quota_davanzale_m", 0.0)
            registra_finestra(scena, ap["id"], m(u0, 0.0, 0.0)[:2], m(u1, 0.0, 0.0)[:2], verso_stanza, q, q + ap["altezza_m"])

    ctx = Contesto.rettangolare(L, W, H, st.get("arredi", []))
    for sp in st.get("arredi", []):
        ob = scena.aggiungi(arredo(sp, ctx))
        if sp.get("componente"):                 # oggetti ripetuti: componenti in SketchUp, come negli edifici
            from .edificio import componi
            componi(ob, sp, arredo(dict(sp, posizione_m=[0.0, 0.0], rotazione_gradi=0.0), ctx), 0.0)
    return scena


def scena_da_scheda(scheda: dict, muri_uniti: bool = True) -> Scena:
    """Costruisce la scena dalla scheda (con `stanza` oppure `edificio`, già completata). `muri_uniti`: vedi
    `scena_da_edificio` (i render usano i muri separati)."""
    if "edificio" in scheda:
        from .edificio import scena_da_edificio
        return scena_da_edificio(scheda, muri_uniti)
    if "stanza" in scheda:
        return scena_da_stanza(scheda["stanza"], scheda.get("progetto", "Progetto"), muri_uniti)
    raise ValueError("scheda senza `stanza` né `edificio`")
