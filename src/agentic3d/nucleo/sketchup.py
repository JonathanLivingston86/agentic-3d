"""Dati per l'estensione Agentic 3D di SketchUp: il modello come file JSON, un oggetto alla volta.

Il file è letto da `estensione_sketchup/agentic3d_sketchup/principale.rb`, che crea un gruppo per oggetto dentro un contenitore
per categoria (Muri, Solai, Serramenti, Arredi) e, a ogni modifica del file, aggiorna soltanto gli oggetti cambiati
(l'impronta di ogni oggetto dice se è cambiato).

Le facce arrivano come le disegnerebbe una persona: le facce complanari dello stesso materiale sono già fuse in un
solo POLIGONO, con i suoi fori (porte e finestre nei muri), e SketchUp lo crea con `add_face`. Non ci sono spigoli da
cancellare dopo: cancellarli uno per uno in SketchUp lasciava linee sulle facce e a volte toglieva facce (errore visto
in prova). Per ogni poligono c'è anche una riserva a triangoli, usata solo se SketchUp rifiuta il
poligono; i suoi spigoli interni vengono ammorbiditi, non cancellati.

Per ogni oggetto:
  poligoni   [materiale, anello esterno, foro, foro...]: anelli di indici di vertici; l'esterno gira in senso
             antiorario visto da fuori (dà il verso della faccia);
  triangoli  [poligono, i, j, k]: la riserva, e la misura dell'area (omessa per i poligoni che sono già un
             triangolo, come quelli delle superfici curve: il file pesa quasi la metà);
  lisci      [i, j]: spigoli di superfici curve (tende, cuscini) da ammorbidire;
  area       m2, somma dei triangoli; chiuso: ogni spigolo ha due facce (solido).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

from .materiali import MATERIALI
from .mesh import dot, lunghezza, normale_poligono, triangola_poligono, unitario
from .scena import Oggetto, Scena

FORMATO = "agentic3d"
VERSIONE = 6            # 4: parti interne, triangoli omessi per i poligoni triangolari; 5: componenti; 6: sottocontenitori "Solai/Pavimenti"
ARROTONDA = 7           # decimali (0,1 micrometri) per riconoscere i vertici coincidenti

COS_SPIGOLO_MORBIDO = math.cos(math.radians(35))   # sotto i 35 gradi di piega: superficie curva

CONTENITORI = {"muro": "Muri", "pavimento": "Solai/Pavimenti", "soffitto": "Solai/Soffitto", "balcone": "Solai/Balconi", "porta": "Serramenti",
               "finestra": "Serramenti", "portafinestra": "Serramenti"}
TAG = {"muro": "Muri", "pavimento": "Solai", "balcone": "Solai", "soffitto": "Soffitto", "porta": "Serramenti", "finestra": "Serramenti",
       "portafinestra": "Serramenti"}


def contenitore_di(o: Oggetto) -> str:
    """Contenitore in SketchUp (categoria, con il piano se l'edificio ne ha più di uno); vuoto = primo livello."""
    c = o.gruppo or CONTENITORI.get(o.tipo, "Arredi")
    return "" if c == o.nome else c


def tag_di(o: Oggetto) -> str:
    """Tag di SketchUp per accendere e spegnere una categoria; il soffitto ha il suo, per guardare dentro."""
    return TAG.get(o.tipo, "Arredi")


def _chiave(p):
    return (round(p[0], ARROTONDA), round(p[1], ARROTONDA), round(p[2], ARROTONDA))


def _piana(punti, tol=1e-5) -> bool:
    n = unitario(normale_poligono(punti))
    c = tuple(sum(p[k] for p in punti) / len(punti) for k in range(3))
    return all(abs(dot((p[0] - c[0], p[1] - c[1], p[2] - c[2]), n)) <= tol for p in punti)


def _area_triangolo(a, b, c) -> float:
    u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    w = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    cr = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
    return 0.5 * lunghezza(cr)


def _chiuso(mesh) -> bool:
    """Vero se ogni spigolo è condiviso da esattamente due facce (solido chiuso)."""
    conta: dict[tuple, int] = {}
    for fi in mesh.f:
        ks = [_chiave(mesh.v[i]) for i in fi]
        for a in range(len(ks)):
            e = (min(ks[a], ks[(a + 1) % len(ks)]), max(ks[a], ks[(a + 1) % len(ks)]))
            conta[e] = conta.get(e, 0) + 1
    return bool(conta) and all(n == 2 for n in conta.values())


def _parti(mesh) -> tuple[list[str], dict[int, int]]:
    """Gruppi interni di un oggetto fatto di più solidi (scatole, cilindri, cuscini). In SketchUp due solidi che si
    toccano nello stesso gruppo fondono le facce a contatto (le ante dell'armadio diventavano "non solide"): ogni
    gruppo riunisce solidi dello stesso materiale che non si toccano, e prende il nome dal materiale."""
    scatole: dict[int, list[float]] = {}
    materiale: dict[int, str] = {}
    for fi, mi, pz in zip(mesh.f, mesh.mat, mesh.pezzo):
        b = scatole.setdefault(pz, [math.inf] * 3 + [-math.inf] * 3)
        for i in fi:
            for k in range(3):
                b[k] = min(b[k], mesh.v[i][k])
                b[3 + k] = max(b[3 + k], mesh.v[i][k])
        materiale.setdefault(pz, mesh.materiali[mi])

    def toccano(a, b, tol=1e-6):
        return all(a[k] <= b[3 + k] + tol and b[k] <= a[3 + k] + tol for k in range(3))

    gruppi: list[tuple[str, list[int]]] = []
    di_pezzo: dict[int, int] = {}
    for pz in sorted(scatole):
        for g, (mat, membri) in enumerate(gruppi):
            if mat == materiale[pz] and not any(toccano(scatole[pz], scatole[m]) for m in membri):
                membri.append(pz)
                di_pezzo[pz] = g
                break
        else:
            di_pezzo[pz] = len(gruppi)
            gruppi.append((materiale[pz], [pz]))
    conta: dict[str, int] = {}
    nomi = []
    for mat, _ in gruppi:
        conta[mat] = conta.get(mat, 0) + 1
        nomi.append(mat if conta[mat] == 1 else f"{mat} {conta[mat]}")
    return nomi, di_pezzo


def _pezzi_chiusi(mesh) -> bool:
    """Vero se ogni solido dell'oggetto, preso da solo, è chiuso."""
    per: dict[int, list[int]] = {}
    for k, pz in enumerate(mesh.pezzo):
        per.setdefault(pz, []).append(k)
    for facce in per.values():
        conta: dict[tuple, int] = {}
        for k in facce:
            ks = [_chiave(mesh.v[i]) for i in mesh.f[k]]
            for a in range(len(ks)):
                e = (min(ks[a], ks[(a + 1) % len(ks)]), max(ks[a], ks[(a + 1) % len(ks)]))
                conta[e] = conta.get(e, 0) + 1
        if not all(n == 2 for n in conta.values()):
            return False
    return True


class _Unione:
    def __init__(self, n):
        self.p = list(range(n))

    def trova(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def unisci(self, a, b):
        self.p[self.trova(a)] = self.trova(b)


def _piano_2d(n):
    """Proiezione sul piano più largo, girata in modo che il senso antiorario 2D sia quello visto dalla normale."""
    asse = max(range(3), key=lambda i: abs(n[i]))
    a, b = (asse + 1) % 3, (asse + 2) % 3        # ordine ciclico (x, y, z)
    segno = -1.0 if n[asse] < 0 else 1.0
    return lambda p: (p[a], segno * p[b])


def _area2d(pts) -> float:
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                     for i in range(len(pts)))


def _dentro(p, poli) -> bool:
    x, y = p
    dentro = False
    for i in range(len(poli)):
        x1, y1 = poli[i]
        x2, y2 = poli[(i + 1) % len(poli)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            dentro = not dentro
    return dentro


def anelli_di_bordo(spigoli: list[tuple[int, int]], p2) -> list[list[int]]:
    """Concatena gli spigoli di bordo (orientati, la faccia a sinistra) in anelli. Dove un vertice ha più uscite
    (due regioni che si toccano in un punto) si prende la svolta più a sinistra: gli anelli restano semplici."""
    uscite: dict[int, list[int]] = {}
    for i, j in spigoli:
        uscite.setdefault(i, []).append(j)
    anelli = []
    while any(uscite.values()):
        inizio = next(i for i, js in uscite.items() if js)
        prec, cur = inizio, uscite[inizio].pop()
        anello = [inizio]
        guardia = 0
        while cur != inizio and guardia < 100000:
            guardia += 1
            anello.append(cur)
            js = uscite.get(cur) or []
            if not js:
                return []                    # bordo aperto: il chiamante usa le facce una per una
            if len(js) == 1:
                nxt = js.pop()
            else:
                din = (p2[cur][0] - p2[prec][0], p2[cur][1] - p2[prec][1])

                def svolta(j, din=din, cur=cur):
                    d = (p2[j][0] - p2[cur][0], p2[j][1] - p2[cur][1])
                    return math.atan2(din[0] * d[1] - din[1] * d[0], din[0] * d[0] + din[1] * d[1])

                nxt = max(js, key=svolta)
                js.remove(nxt)
            prec, cur = cur, nxt
        anelli.append(anello)
    return anelli


def _poligoni_del_gruppo(facce: list[list[int]], P) -> list[list[list[int]]] | None:
    """Fonde facce complanari che condividono spigoli: [[esterno, foro, ...], ...] o None se non si riesce."""
    conta: dict[tuple[int, int], int] = {}
    for f in facce:
        for a in range(len(f)):
            e = (f[a], f[(a + 1) % len(f)])
            conta[e] = conta.get(e, 0) + 1
    bordo = []
    for (i, j), n in conta.items():
        resto = n - conta.get((j, i), 0)
        if resto > 1:
            return None
        if resto == 1:
            bordo.append((i, j))
    n = normale_poligono([P[i] for i in facce[0]])
    proietta = _piano_2d(unitario(n))
    p2 = {i: proietta(P[i]) for e in bordo for i in e}
    anelli = anelli_di_bordo(bordo, p2)
    if not anelli:
        return None
    esterni, fori = [], []
    for a in anelli:
        if len(a) < 3:
            return None
        (esterni if _area2d([p2[i] for i in a]) > 0 else fori).append(a)
    if not esterni:
        return None
    out = [[e] for e in esterni]
    for foro in fori:
        # punto appena a sinistra del primo lato del foro: sta nella faccia, dentro l'esterno che lo contiene
        a, b = p2[foro[0]], p2[foro[1]]
        d = (b[0] - a[0], b[1] - a[1])
        ld = math.hypot(*d) or 1.0
        prova = ((a[0] + b[0]) / 2 - d[1] / ld * 1e-5, (a[1] + b[1]) / 2 + d[0] / ld * 1e-5)
        cont = [k for k, e in enumerate(esterni) if _dentro(prova, [p2[i] for i in e])]
        if not cont:
            return None
        k = min(cont, key=lambda k: abs(_area2d([p2[i] for i in esterni[k]])))
        out[k].append(foro)
    return out


def dati_oggetto(o: Oggetto, indice_materiali: dict[str, int]) -> dict:
    mesh = o.mesh
    unici: dict[tuple, int] = {}
    vertici: list[float] = []
    P: list[tuple] = []

    def vid(p):
        k = _chiave(p)
        if k not in unici:
            unici[k] = len(unici)
            vertici.extend(round(c, 6) for c in p)
            P.append(p)
        return unici[k]

    # facce della mesh ripulite: indici unici, materiale, piana o no
    pulite = []            # (k, ids, mat, piana)
    for k, fi in enumerate(mesh.f):
        ids = [vid(mesh.v[i]) for i in fi]
        ids = [ids[n] for n in range(len(ids)) if ids[n] != ids[n - 1]]
        if len(set(ids)) < 3:
            continue
        mat = indice_materiali[mesh.materiali[mesh.mat[k]]]
        piana = not mesh.liscia[k] and _piana([P[i] for i in ids]) and lunghezza(normale_poligono([P[i] for i in ids])) > 1e-12
        pulite.append((k, ids, mat, piana))

    # gruppi di facce piane complanari, dello stesso materiale, unite da spigoli (solo se l'oggetto lo chiede)
    unione = _Unione(len(pulite))
    piani = {}
    for n, (k, ids, mat, piana) in enumerate(pulite):
        if piana:
            nv = unitario(normale_poligono([P[i] for i in ids]))
            piani[n] = (nv, dot(nv, P[ids[0]]))
    # facce complanari dello stesso materiale che condividono uno spigolo: si fondono nei muri e nei solai, e negli
    # arredi quando sono dello stesso solido (un piano con il foro del lavello è una faccia sola, con il foro)
    per_spigolo: dict[tuple[int, int], list[int]] = {}
    for n, (k, ids, mat, piana) in enumerate(pulite):
        if piana:
            for a in range(len(ids)):
                i, j = ids[a], ids[(a + 1) % len(ids)]
                per_spigolo.setdefault((min(i, j), max(i, j)), []).append(n)
    for fs in per_spigolo.values():
        if len(fs) != 2:
            continue
        a, b = fs
        if not (o.fondi_complanari or mesh.pezzo[pulite[a][0]] == mesh.pezzo[pulite[b][0]]):
            continue
        (na, da), (nb, db) = piani[a], piani[b]
        if pulite[a][2] == pulite[b][2] and lunghezza(tuple(x - y for x, y in zip(na, nb))) < 1e-7 \
                and abs(da - db) < 1e-6:
            unione.unisci(a, b)

    gruppi: dict[int, list[int]] = {}
    for n in range(len(pulite)):
        gruppi.setdefault(unione.trova(n), []).append(n)

    poligoni: list[list] = []
    triangoli: list[list[int]] = []
    origine: list[tuple[bool, int]] = []  # per ogni triangolo: (superficie liscia, faccia della mesh)
    area = 0.0

    def aggiungi_triangoli(n_poli, n_faccia):
        nonlocal area
        ids = pulite[n_faccia][1]
        pts = [P[i] for i in ids]
        for a, b, c in triangola_poligono(pts):
            ar = _area_triangolo(pts[a], pts[b], pts[c])
            if ar < 1e-10:
                continue
            triangoli.append([n_poli, ids[a], ids[b], ids[c]])
            origine.append((False, n_faccia))
            area += ar

    for membri in sorted(gruppi.values()):
        mat = pulite[membri[0]][2]
        if all(pulite[n][3] for n in membri):
            fusi = _poligoni_del_gruppo([pulite[n][1] for n in membri], P) if len(membri) > 1 \
                else [[pulite[membri[0]][1]]]
            if fusi is not None and len(fusi) == 1:
                poligoni.append([mat] + fusi[0])
                for n in membri:
                    aggiungi_triangoli(len(poligoni) - 1, n)
                continue
        # facce curve, non piane o non fondibili: ognuna a sé (le curve come triangoli lisci)
        for n in membri:
            k, ids, _, piana = pulite[n]
            if piana:
                poligoni.append([mat, ids])
                aggiungi_triangoli(len(poligoni) - 1, n)
                continue
            pts = [P[i] for i in ids]
            for a, b, c in triangola_poligono(pts):
                if _area_triangolo(pts[a], pts[b], pts[c]) < 1e-10:
                    continue
                poligoni.append([mat, [ids[a], ids[b], ids[c]]])
                triangoli.append([len(poligoni) - 1, ids[a], ids[b], ids[c]])
                origine.append((mesh.liscia[k], n))
                area += _area_triangolo(pts[a], pts[b], pts[c])

    # spigoli lisci: tra due triangoli di superfici lisce (tende, cuscini) o dentro la stessa faccia non piana;
    # il bordo con una faccia piana resta visibile
    uso: dict[tuple[int, int], list[int]] = {}
    for n, t in enumerate(triangoli):
        v = t[1:]
        for a in range(3):
            uso.setdefault((min(v[a], v[(a + 1) % 3]), max(v[a], v[(a + 1) % 3])), []).append(n)
    lisci = {e for e, ts in uso.items() if len(ts) == 2 and (
        (origine[ts[0]][0] and origine[ts[1]][0]) or (origine[ts[0]][1] == origine[ts[1]][1]
                                                       and not pulite[origine[ts[0]][1]][3]))}
    # superfici curve fatte di facce piane (cilindri, aste, torniti, smussi): si riconoscono dalla forma, cioè due
    # facce piane dello stesso solido e materiale che piegano di poco; lo spigolo diventa morbido e la superficie
    # appare continua. Gli spigoli veri (scatole, tappi, ottagoni) restano visibili. Non nei muri e nei solai, dove
    # un angolo poco aperto tra due pareti è un angolo vero.
    # nei solidi di rivoluzione è morbido anche lo spigolo tra due facce laterali vicine, che piegano esattamente
    # di 360/segmenti gradi (un'asta a 10 segmenti piega di 36): così la linea sparisce con pochi o tanti segmenti
    if not o.fondi_complanari:
        for e, fs in per_spigolo.items():
            if len(fs) != 2:
                continue
            a, b = fs
            pz = mesh.pezzo[pulite[a][0]]
            if pulite[a][2] != pulite[b][2] or pz != mesh.pezzo[pulite[b][0]] or unione.trova(a) == unione.trova(b):
                continue
            coseno = dot(piani[a][0], piani[b][0])
            giro = mesh.rivoluzione.get(pz)
            if coseno > COS_SPIGOLO_MORBIDO or (
                    giro is not None and giro < 89 and abs(math.degrees(math.acos(max(-1.0, min(1.0, coseno)))) - giro) < 0.5):
                lisci.add(e)
    lisci = sorted(list(e) for e in lisci)

    dati = {"nome": o.nome, "tipo": o.tipo, "tag": tag_di(o), "contenitore": contenitore_di(o),
            "origine": [round(c, 6) for c in o.origine], "vertici": vertici, "poligoni": poligoni,
            "triangoli": [t for t in triangoli if not (len(poligoni[t[0]]) == 2 and len(poligoni[t[0]][1]) == 3)],
            "lisci": lisci,
            "area": round(area, 5), "chiuso": _chiuso(mesh)}
    if not o.fondi_complanari and len(set(mesh.pezzo)) > 1:
        nomi, di_pezzo = _parti(mesh)
        parte = [0] * len(poligoni)
        for t, (_, n_faccia) in zip(triangoli, origine):
            parte[t[0]] = di_pezzo[mesh.pezzo[pulite[n_faccia][0]]]
        if len(nomi) > 1:
            dati.update({"parti": nomi, "parte": parte, "chiuso": _pezzi_chiusi(mesh)})
    corpo = json.dumps(dati, sort_keys=True, separators=(",", ":"))
    dati["impronta"] = hashlib.sha1(corpo.encode("utf-8")).hexdigest()[:16]
    return dati


def dati_scena(scena: Scena) -> dict:
    nomi = scena.materiali_usati()
    indice = {n: i for i, n in enumerate(nomi)}
    materiali = []
    for n in nomi:
        r, g, b, _, _, alpha = MATERIALI[n]
        materiali.append({"nome": n, "colore": [r, g, b], "alpha": alpha})
    definizioni: dict[str, dict] = {}
    oggetti = []
    for o in scena.oggetti:
        if not o.componente:
            oggetti.append(dati_oggetto(o, indice))
            continue
        d = dati_oggetto(o.definizione, indice)
        if o.componente in definizioni and definizioni[o.componente]["impronta"] != d["impronta"]:
            raise ValueError(f"componente {o.componente!r}: due oggetti con lo stesso componente hanno forme diverse")
        definizioni[o.componente] = d
        copia = {"nome": o.nome, "tipo": o.tipo, "tag": tag_di(o), "contenitore": contenitore_di(o),
                 "componente": o.componente, "matrice": [round(v, 7) for v in o.matrice]}
        corpo = json.dumps(copia, sort_keys=True, separators=(",", ":")) + d["impronta"]
        copia["impronta"] = hashlib.sha1(corpo.encode("utf-8")).hexdigest()[:16]
        oggetti.append(copia)
    return {"formato": FORMATO, "versione": VERSIONE, "progetto": scena.nome, "unita": "m",
            "materiali": materiali, "definizioni": list(definizioni.values()), "oggetti": oggetti}


def scrivi_sketchup(scena: Scena, percorso: str | Path) -> Path:
    """Scrive il file per l'estensione di SketchUp. Il soffitto c'è, con un tag a parte ("Soffitto") che si spegne
    con un clic; il GLB invece esce senza soffitto."""
    p = Path(percorso).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    testo = json.dumps(dati_scena(scena), separators=(",", ":"), ensure_ascii=False)
    try:
        if p.read_text(encoding="utf-8") == testo:
            return p                                     # niente di nuovo: SketchUp ha già questo modello
    except OSError:
        pass
    provvisorio = p.with_name(p.name + ".tmp")           # scrittura atomica: SketchUp non legge mai un file a metà
    provvisorio.write_text(testo, encoding="utf-8")
    os.replace(provvisorio, p)
    return p
