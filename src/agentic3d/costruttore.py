"""Costruttore: dalla scheda stanze al modello, con render ed esportazione.

Prende la scheda (anche minima), la completa con i valori predefiniti conformi alle norme e costruisce la scena.
Due motori:

- `nucleo` (predefinito): la geometria nasce in Python puro (`nucleo/`), senza Blender. Il GLB per SketchUp e i
  controlli geometrici escono in pochi millisecondi. Blender serve solo per i render: riceve il GLB, rimette i
  materiali e aggiunge luci e camere. Gira senza finestra (`blender/sottofondo.py`), con avanzamento e galleria.
- `classico`: la geometria nasce dentro Blender (`blender/costruttore_classico.py`). Conservato come riferimento e per
  confronto con il nucleo.

Uso:  python -m agentic3d costruisci "lavori/<Nome>/Scheda stanze.yaml" [--render] [--esporta] [--solo-script]
                                      [--motore nucleo|classico]
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

from .blender import sottofondo
from .blender.ponte import avvia_blender, chiudi_blender
from .nucleo.materiali import preambolo_blender
from .scheda import completa

SORGENTE_CLASSICO = Path(__file__).parent / "blender" / "costruttore_classico.py"
SORGENTE_REGIA = Path(__file__).parent / "blender" / "regia.py"
SORGENTE_IMPORTA = Path(__file__).parent / "blender" / "importa.py"
SORGENTE_VERIFICA = Path(__file__).with_name("verifica_geometria.py")


def _sulla_parete(parete: str, u: float, d: float, L: float, W: float) -> tuple[float, float]:
    """Punto (x, y) a distanza `d` dalla parete, alla posizione `u` lungo di essa (come `mappa` nel costruttore)."""
    return {"sud": (u, d), "nord": (u, W - d), "ovest": (d, u), "est": (L - d, u)}[parete]


def _larghezza_pianta(L: float, W: float) -> float:
    """Larghezza inquadrata dalla vista in pianta (16:9). La formula storica va bene per stanze lunghe e strette;
    per quelle più profonde (aule) l'altezza dell'immagine deve comunque contenere la stanza con i muri."""
    storica = max(L, W * 1.7) + 0.6
    return storica if storica * 9 / 16 >= W + 0.2 else (W + 0.6) * 16 / 9


def viste_predefinite(L: float, W: float, H: float, porta_u: float | None = None,
                      oggetti_sud: tuple[str, ...] = (), porta_parete: str = "sud",
                      finestra_parete: str = "ovest", finestra_u: float | None = None,
                      soffitto_nelle_viste_interne: bool = True) -> list[dict]:
    """Quattro inquadrature adatte a una stanza rettangolare: dalla porta, verso la finestra, dall'alto, pianta.

    Le viste da dentro tengono il soffitto (senza, il sole entrerebbe da sopra con luci impossibili) e usano il
    profilo di luce "interno"; l'alto e la pianta lo nascondono e usano "aperto". Con `soffitto_nelle_viste_interne`
    falso (specifica diversa, o stanza senza soffitto) anche le viste interne nascondono il soffitto.

    `porta_u` e `finestra_u` sono le posizioni (centro) lungo la rispettiva parete; le distanze delle viste
    dall'alto e in pianta crescono con la stanza, così un'aula da 8 x 6 m entra in quadro come una cameretta.
    """
    lungo = L if porta_parete in ("sud", "nord") else W
    u = porta_u if porta_u is not None else lungo * 0.8
    px, py = _sulla_parete(porta_parete, u, 0.30, L, W)
    if porta_parete in ("sud", "nord"):
        tx = L * 0.25 if u > L / 2 else L * 0.75
        ty = W * 0.75 if porta_parete == "sud" else W * 0.25
    else:
        ty = W * 0.75 if u < W / 2 else W * 0.25
        tx = L * 0.75 if porta_parete == "ovest" else L * 0.25
    fu = finestra_u if finestra_u is not None else (W if finestra_parete in ("ovest", "est") else L) * 0.55
    cx, cy = _sulla_parete(finestra_parete, fu, 0.0, L, W)             # centro della finestra sul muro
    ox, oy = _sulla_parete(finestra_parete, fu, (L if finestra_parete in ("ovest", "est") else W) * 0.80, L, W)
    s = max(1.0, W / 4.0)
    dentro = ([], "interno") if soffitto_nelle_viste_interne else (["Soffitto"], "aperto")
    return [
        {"nome": "Vista dall'ingresso", "pos": (px, py, 1.55), "tgt": (tx, ty, 1.0), "lente": 17, "nascondi": dentro[0], "luci": dentro[1]},
        {"nome": "Vista verso la finestra", "pos": (ox, oy, 1.50), "tgt": (cx, cy, 1.15), "lente": 17, "nascondi": dentro[0], "luci": dentro[1]},
        {"nome": "Vista dall'alto", "pos": (L / 2, -4.2 * s, 6.0 * s), "tgt": (L / 2, W * 0.85, 0.3), "lente": round(22 * s ** 0.7),
         "nascondi": ["Soffitto", "Muro Sud", *oggetti_sud], "luci": "aperto"},
        {"nome": "Pianta", "pos": (L / 2, W / 2, 9.0), "tgt": (L / 2, W / 2, 0.0), "lente": 50,
         "ortografica": _larghezza_pianta(L, W), "nascondi": ["Soffitto"], "luci": "aperto"},
    ]


def cartella_temporanea() -> Path:
    """Cartella dei temporanei (si svuota a fine lavoro): vedi `configurazione.py`."""
    from .configurazione import cartella_temporanea as dalla_configurazione
    return dalla_configurazione()


def _distanza_dai_lati(p, poligono) -> float:
    from .nucleo import geom2d as g
    n = len(poligono)
    return min(g.distanza_punto_segmento(p, poligono[i], poligono[(i + 1) % n]) for i in range(n))


def punti_interni(poligono, passo: float = 0.15, margine: float = 0.0) -> list[tuple[float, float, float]]:
    """Punti di una griglia dentro il poligono con la loro distanza dal lato più vicino: (x, y, distanza)."""
    from .nucleo import geom2d as g
    xs, ys = [q[0] for q in poligono], [q[1] for q in poligono]
    out = []
    nx = max(1, int((max(xs) - min(xs)) / passo))
    ny = max(1, int((max(ys) - min(ys)) / passo))
    for i in range(nx + 1):
        for j in range(ny + 1):
            p = (min(xs) + (max(xs) - min(xs)) * (i + 0.5) / (nx + 1), min(ys) + (max(ys) - min(ys)) * (j + 0.5) / (ny + 1))
            if g.punto_in_poligono(p, poligono):
                d = _distanza_dai_lati(p, poligono)
                if d >= margine:
                    out.append((p[0], p[1], d))
    return out


def cuore_della_stanza(poligono) -> tuple[float, float, float]:
    """Il punto della stanza più lontano dalle pareti e la sua distanza: lì va la luce e lì guarda la camera.
    Nelle stanze a L il baricentro può cadere fuori dalla stanza o contro un muro; questo punto no."""
    punti = punti_interni(poligono)
    if not punti:
        xs, ys = [q[0] for q in poligono], [q[1] for q in poligono]
        return (sum(xs) / len(xs), sum(ys) / len(ys), 0.3)
    xs, ys = [q[0] for q in punti], [q[1] for q in punti]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    # a parità di distanza dalle pareti (stanze rettangolari) vince il punto più centrale
    return max(punti, key=lambda q: (round(q[2], 2), -((q[0] - cx) ** 2 + (q[1] - cy) ** 2)))


def luce_della_stanza(poligono, area_m2: float) -> tuple[float, float, float, float]:
    """(x, y, lato, energia) della luce di riempimento: un quadrato tutto dentro la stanza, lontano dalle pareti almeno
    un quarto della distanza libera, con energia proporzionata alla superficie (taratura: 14,9 m2 -> 40 W)."""
    x, y, d = cuore_della_stanza(poligono)
    grandezza = max(0.35, area_m2 / 14.9)
    lato = min(2.2 * grandezza ** 0.5, 1.06 * d)          # mezza diagonale = 0,75 d: resta dentro la stanza
    return x, y, max(0.2, lato), 40.0 * grandezza


def _area_poligono(p) -> float:
    return sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p))) / 2.0


def _viste_della_scheda(st: dict, viste: list[dict] | None) -> list[dict]:
    L, W, H = float(st["lunghezza_m"]), float(st["larghezza_m"]), float(st["altezza_m"])
    porta = next((a for a in st.get("aperture", []) if a.get("tipo") == "porta"), None)
    finestra = next((a for a in st.get("aperture", []) if a.get("tipo") in ("finestra", "portafinestra")), None)
    sud = tuple(a["id"] for a in st.get("aperture", []) if a.get("parete") == "sud" and a.get("id"))
    return viste or viste_predefinite(
        L, W, H,
        porta_u=(porta["da_m"] + porta["larghezza_m"] / 2) if porta else None, oggetti_sud=sud,
        porta_parete=porta["parete"] if porta else "sud",
        finestra_parete=finestra["parete"] if finestra else "ovest",
        finestra_u=(finestra["da_m"] + finestra["larghezza_m"] / 2) if finestra else None,
        soffitto_nelle_viste_interne=bool(st.get("soffitto", True)) and bool(st.get("viste_interne_con_soffitto", True)))


def _in(base: str, *parti: str) -> str:
    """Percorso assoluto dentro il lavoro, con il separatore del sistema (su macOS la barra rovesciata non vale)."""
    return str(Path(base).joinpath(*parti))


def _codice_render(viste: list[dict], base: str, risoluzione, campioni) -> list[str]:
    """Camere e render. Le righe `AGENTIC3D_VISTA` danno l'avanzamento a chi esegue Blender senza finestra."""
    n = len(viste)
    parti = [f"imposta_render({risoluzione[0]}, {risoluzione[1]}, {campioni})\n"]
    for v in viste:
        parti.append(f"camera({v['nome']!r}, {tuple(v['pos'])!r}, {tuple(v['tgt'])!r}, {v['lente']!r}, {v.get('ortografica')!r})\n")
    parti.append(f"print({f'{sottofondo.SEGNALE} 0 {n} -'!r}, flush=True)\n")
    for k, v in enumerate(viste, 1):
        parti.append(f"render({_in(base, 'Render', v['nome'] + '.png')!r}, {v['nome']!r}, "
                     f"{tuple(v.get('nascondi', ()))!r}, {v.get('luci', 'aperto')!r})\n")
        parti.append(f"print({f'{sottofondo.SEGNALE} {k} {n} ' + v['nome']!r}, flush=True)\n")
    return parti


def inquadratura_interna(poligono, ostacoli=()) -> tuple[float, float, float, float]:
    """(camera x, y, bersaglio x, y) per guardare una stanza da dentro: il bersaglio è il cuore della stanza, la
    camera il punto più lontano da cui lo si vede senza attraversare pareti, ad almeno 30 cm dai muri e fuori dagli
    `ostacoli` (rettangoli x0, y0, x1, y1 degli arredi all'altezza della camera: un pensile la oscurava del tutto)."""
    from .nucleo import geom2d as g
    tx, ty, _ = cuore_della_stanza(poligono)
    candidati = punti_interni(poligono, passo=0.12, margine=0.30) or [(tx, ty, 0.0)]
    liberi = [p for p in candidati if not any(r[0] - 0.15 <= p[0] <= r[2] + 0.15 and r[1] - 0.15 <= p[1] <= r[3] + 0.15
                                              for r in ostacoli)]
    candidati = liberi or candidati

    def libero(p):
        for k in range(1, 20):
            q = (p[0] + (tx - p[0]) * k / 20, p[1] + (ty - p[1]) * k / 20)
            if not g.punto_in_poligono(q, poligono) or _distanza_dai_lati(q, poligono) < 0.12:
                return False
        return True

    for p in sorted(candidati, key=lambda q: -((q[0] - tx) ** 2 + (q[1] - ty) ** 2)):
        if libero(p):
            return p[0], p[1], tx, ty
    return candidati[0][0], candidati[0][1], tx, ty


def viste_edificio(scena) -> list[dict]:
    """Viste di un edificio: pianta, vista dall'alto e una vista da dentro per ogni stanza (fino a 8).
    Soffitti nascosti solo nelle viste dall'alto e in pianta."""
    x0, y0, x1, y1 = scena.meta["bbox"]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = x1 - x0, y1 - y0
    alto = scena.meta.get("altezza_totale", 3.0)
    soffitti = [o.nome for o in scena.oggetti if o.tipo == "soffitto"]
    d = 1.15 * max(dx, dy * 1.6)
    # dal sud si toglie la fascia di pareti e serramenti che coprirebbe l'interno (come "Muro Sud" nella stanza singola)
    davanti = []
    for o in scena.oggetti:
        if o.tipo in ("muro", "finestra", "portafinestra", "porta") and o.mesh.v:
            ymax = max(p[1] for p in o.mesh.v) + o.origine[1]
            if ymax <= y0 + 0.45:
                davanti.append(o.nome)
    viste = [
        {"nome": "Pianta", "pos": (cx, cy, alto + 8.0), "tgt": (cx, cy, 0.0), "lente": 50,
         "ortografica": max(dx + 1.2, (dy + 1.2) * 16 / 9), "nascondi": soffitti, "luci": "aperto"},
        {"nome": "Vista dall'alto", "pos": (cx, y0 - d * 0.62, alto + d * 0.78), "tgt": (cx, cy - dy * 0.05, 0.3), "lente": 28,
         "nascondi": soffitti + davanti, "luci": "aperto"},
    ]
    for st in scena.meta["stanze"][:8]:
        quota = st["quota"] + 1.5
        ostacoli = [(q[0][0], q[0][1], q[1][0], q[1][1]) for o in scena.oggetti if o.categoria == "arredo"
                    for q in o.parti if q[0][2] - 0.1 <= quota <= q[1][2] + 0.1]
        px, py, tx, ty = inquadratura_interna(st["poligono"], ostacoli)
        viste.append({"nome": f"Vista {st['id']}", "pos": (px, py, st["quota"] + 1.5), "tgt": (tx, ty, st["quota"] + 1.0),
                      "lente": 17, "nascondi": [], "luci": "interno"})
    return viste


def genera_script(scheda: dict, cartella_lavoro: str | Path, render: bool = False, esporta: bool = False,
                  viste: list[dict] | None = None, risoluzione=(1280, 720), campioni: int = 96) -> str:
    """Script Python per Blender del motore CLASSICO (la geometria nasce in Blender). `scheda` già completata."""
    st = scheda["stanza"]
    viste = _viste_della_scheda(st, viste)
    base = str(Path(cartella_lavoro).resolve()).rstrip("\\/")
    nome = scheda.get("progetto", "Progetto")
    parti = [preambolo_blender(), "\n", SORGENTE_REGIA.read_text(encoding="utf-8"), "\n\n",
             SORGENTE_CLASSICO.read_text(encoding="utf-8"),
             "\n\n# ---- controlli geometrici (funzioni pure)\n",
             SORGENTE_VERIFICA.read_text(encoding="utf-8"),
             "\n\n# ---- dati e regia generati da agentic3d.costruttore\n",
             f"DATI = {{'stanza': {st!r}}}\n",
             "NOMI = costruisci(DATI)\n",
             "print(rapporto_geometria())\n"]
    if render:
        parti += _codice_render(viste, base, risoluzione, campioni)
    if esporta:
        parti.append(f"salva_blend({_in(base, 'Modello', nome + '.blend')!r})\n")
        parti.append(f"esporta_glb({_in(base, 'Esportazioni', nome + '.glb')!r})\n")
    parti.append("print('FATTO', len(NOMI), 'oggetti')\n")
    return "".join(parti)


# soglie di peso (decise il 22 ottobre 2026): oltre, il rapporto lo dice; vedi la Skill interni-italia-progettazione
TRIANGOLI_ARREDO = 20000
TRIANGOLI_SCENA = 300000


def peso_della_scena(scena, file: list) -> str:
    """Riga di rapporto: triangoli totali, arredo più pesante, peso dei file; segnala chi supera le soglie."""
    per = sorted(((sum(len(f) - 2 for f in o.mesh.f), o.nome) for o in scena.oggetti), reverse=True)
    totale = sum(t for t, _ in per)
    righe = [f"PESO: {totale} triangoli (il più pesante: {per[0][1]}, {per[0][0]}); "
             + ", ".join(f"{Path(f).name} {Path(f).stat().st_size / 1e6:.1f} MB" for f in file if Path(f).exists())]
    righe += [f"PESO: {n} ha {t} triangoli, oltre i {TRIANGOLI_ARREDO} di un arredo: va semplificato"
              for t, n in per if t > TRIANGOLI_ARREDO and not n.startswith(("Tamponature", "Tramezzi"))]
    if totale > TRIANGOLI_SCENA:
        righe.append(f"PESO: la scena supera i {TRIANGOLI_SCENA} triangoli: SketchUp rallenta")
    return "\n".join(righe)


def genera_script_nucleo(scheda: dict, scena, cartella_lavoro: str | Path, percorso_glb: str | Path,
                         viste: list[dict] | None = None, risoluzione=(1280, 720), campioni: int = 96,
                         blend: str | Path | None = None) -> str:
    """Script per Blender del motore NUCLEO: importa il GLB, aggiunge luci e camere, fa i render e salva il .blend
    (in `blend`, se indicato: vedi `sottofondo.destinazione_blend`)."""
    base = str(Path(cartella_lavoro).resolve()).rstrip("\\/")
    nome = scheda.get("progetto", "Progetto")
    raccolte = {o.nome: o.collezione for o in scena.oggetti}
    if "edificio" in scheda:
        if not viste:
            # viste della scheda: si aggiungono a quelle automatiche, o sostituiscono quella con lo stesso nome
            extra = [{"nome": f"Vista {v['nome']}", "pos": tuple(v["da_m"]), "tgt": tuple(v["verso_m"]),
                      "lente": v.get("lente_mm", 24), "nascondi": [], "luci": "interno"}
                     for v in scheda["edificio"].get("viste", [])]
            nomi_extra = {v["nome"] for v in extra}
            viste = [v for v in viste_edificio(scena) if v["nome"] not in nomi_extra] + extra
        fin = scena.meta.get("finestre") or []
        direzione = tuple(fin[0]["direzione"]) if fin else (1.0, 0.0)
        stanze = [luce_della_stanza(s["poligono"], abs(_area_poligono(s["poligono"]))) + (s["quota"] + 0.65 * s["altezza"],)
                  for s in scena.meta["stanze"]]
        luci = f"luci_edificio({stanze!r}, {direzione!r})\n"
    else:
        st = scheda["stanza"]
        L, W, H = float(st["lunghezza_m"]), float(st["larghezza_m"]), float(st["altezza_m"])
        finestra = next((a for a in st.get("aperture", []) if a.get("tipo") in ("finestra", "portafinestra")), None)
        viste = _viste_della_scheda(st, viste)
        luci = f"luci_e_cielo({L!r}, {W!r}, {H!r}, {(finestra['parete'] if finestra else 'ovest')!r})\n"
    parti = [preambolo_blender(), "\n", SORGENTE_REGIA.read_text(encoding="utf-8"), "\n\n",
             SORGENTE_IMPORTA.read_text(encoding="utf-8"),
             "\n\n# ---- regia generata da agentic3d.costruttore\n",
             "pulisci_scena()\n",
             f"NOMI = importa_glb({str(Path(percorso_glb).resolve())!r}, {raccolte!r})\n",
             luci]
    parti += _codice_render(viste, base, risoluzione, campioni)
    parti.append(f"salva_blend({str(blend) if blend else _in(base, 'Modello', nome + '.blend')!r})\n")
    parti.append("print('FATTO', len(NOMI), 'oggetti')\n")
    return "".join(parti)


def nomi_delle_viste(codice: str) -> list[str]:
    """Le viste nell'ordine in cui lo script le renderizza (dalle righe di avanzamento, con qualunque virgolette)."""
    import ast
    nomi = []
    for r in codice.splitlines():
        if r.startswith("print(") and sottofondo.SEGNALE in r and r.endswith(", flush=True)"):
            segnale = sottofondo.leggi_segnale(ast.literal_eval(r[len("print("):-len(", flush=True)")]))
            if segnale and segnale[0] > 0:
                nomi.append(segnale[2])
    return nomi


def invia_a_blender(codice: str, porta: int = 9876, timeout: float = 900.0) -> dict:
    """Esegue il codice in Blender tramite il ponte MCP (Blender deve essere aperto con il server acceso)."""
    s = socket.socket()
    s.settimeout(timeout)
    s.connect(("localhost", porta))
    s.sendall(json.dumps({"type": "execute_code", "params": {"code": codice}}).encode())
    buf = b""
    while True:
        pezzo = s.recv(65536)
        if not pezzo:
            break
        buf += pezzo
        try:
            return json.loads(buf.decode())
        except ValueError:
            continue
    return json.loads(buf.decode())


def separa_cime_dei_muri(scena) -> None:
    """Solo per i render, dove i muri restano a pezzi: negli incroci a croce due pezzi si sovrappongono e le loro cime
    stanno alla stessa quota; Cycles fa ombra da una faccia all'altra e il quadrato dell'incrocio esce nero. Ogni pezzo
    alza la sua cima di qualche decimo di millimetro (invisibile), così le facce non coincidono più."""
    muri = [o for o in scena.oggetti if o.tipo == "muro" and o.mesh.v]
    for k, o in enumerate(muri):
        cima = max(p[2] for p in o.mesh.v)
        alza = 0.0002 * (k % 5 + 1)
        o.mesh.v = [(p[0], p[1], p[2] + alza) if abs(p[2] - cima) < 1e-6 else p for p in o.mesh.v]


def costruisci(scheda_grezza: dict, cartella_lavoro: str | Path, render: bool = False, esporta: bool = False,
               solo_script: bool = False, motore: str = "nucleo", tieni_blender: bool = False,
               al_progresso=None, apri_galleria: bool = True) -> tuple[dict, dict]:
    """Costruisce il modello. Restituisce (scheda completata, risultato) con `geometria` (rapporto), `file` scritti
    e, se è stato usato Blender, il suo esito in `blender` (o lo `script` con `solo_script`).

    Con `render` (motore nucleo) Blender lavora senza finestra e si chiude da solo; `al_progresso(fatte, totale,
    messaggio)` riceve l'avanzamento e la galleria nel browser mostra le immagini appena pronte. Poi il .blend si apre
    in un Blender normale secondo l'impostazione `dopo_render` (o sempre, con `tieni_blender`)."""
    scheda = completa(scheda_grezza)
    if motore == "classico":
        codice = genera_script(scheda, cartella_lavoro, render=render, esporta=esporta)
        if solo_script:
            return scheda, {"script": codice}
        aperto_da_noi = avvia_blender()
        try:
            return scheda, {"blender": invia_a_blender(codice), "file": []}
        finally:
            if aperto_da_noi and not tieni_blender:
                chiudi_blender()
    if motore != "nucleo":
        raise ValueError(f"motore sconosciuto: {motore!r} (nucleo o classico)")

    from .nucleo.costruzione import scena_da_scheda
    from .nucleo.glb import glb_bytes, scrivi_glb
    from .nucleo.sketchup import scrivi_sketchup

    base = Path(cartella_lavoro).resolve()
    nome = scheda.get("progetto", "Progetto")
    scena = scena_da_scheda(scheda)
    risultato: dict = {"geometria": scena.rapporto_geometria(), "oggetti": len(scena.oggetti), "file": [],
                       "avvisi": list(scena.note)}
    if esporta:
        risultato["file"].append(str(scrivi_glb(scena, base / "Esportazioni" / f"{nome}.glb")))
        risultato["file"].append(str(scrivi_sketchup(scena, base / "Esportazioni" / f"{nome} per SketchUp.json")))
        risultato["peso"] = peso_della_scena(scena, [Path(f) for f in risultato["file"]])
    if render:
        # per i render i muri restano a pezzi: la vista dall'alto nasconde quelli tra la camera e le stanze
        scena_render = scena_da_scheda(scheda, muri_uniti=False)
        separa_cime_dei_muri(scena_render)
        glb = cartella_temporanea() / f"{nome} per Blender.glb"
        glb.write_bytes(glb_bytes(scena_render))          # con il soffitto: le viste interne lo mostrano
        blend = sottofondo.destinazione_blend(base / "Modello" / f"{nome}.blend")
        try:
            codice = genera_script_nucleo(scheda, scena_render, base, glb, blend=blend)
            if solo_script:
                risultato["script"] = codice
            else:
                (base / "Render").mkdir(parents=True, exist_ok=True)
                (base / "Modello").mkdir(parents=True, exist_ok=True)
                esito = sottofondo.esegui(codice, nomi_delle_viste(codice), base / "Render", nome,
                                          al_progresso=al_progresso, apri_galleria=apri_galleria)
                risultato["blender"] = esito
                if esito["esito"] == "ok":
                    sottofondo.annota_blend(blend)
                    risultato["file"] += [str(base / "Render" / f"{v}.png") for v in esito["viste"]]
                    risultato["file"] += [str(blend), esito["galleria"]]
                    if blend.name != f"{nome}.blend":
                        risultato["avvisi"].append(f"{nome}.blend è stato modificato a mano: il nuovo modello è "
                                                   f"in {blend.name}, l'originale non è stato toccato")
                    _apri_dopo_render(blend, risultato, sempre=tieni_blender)
        finally:
            glb.unlink(missing_ok=True)
    return scheda, risultato


def _apri_dopo_render(blend: Path, risultato: dict, sempre: bool = False) -> None:
    """Regola dell'impostazione `dopo_render`: senza SketchUp sul computer (scelta `automatico`), o con `apri`,
    il .blend si apre in un Blender normale perché l'utente possa continuare a lavorarci."""
    from .installazione import sketchup_installati
    scelta = "apri" if sempre else sottofondo.dopo_render()
    if not sottofondo.da_aprire(scelta, bool(sketchup_installati())):
        return
    try:
        sottofondo.apri_in_blender(blend)
        motivo = "SketchUp non è installato" if scelta == "automatico" else "impostazione dopo_render = apri"
        risultato["blender"]["aperto"] = f"{blend.name} aperto in Blender ({motivo})"
    except OSError as e:
        risultato["avvisi"].append(f"non è stato possibile aprire {blend.name} in Blender: {e}")
