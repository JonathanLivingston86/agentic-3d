"""Controlli geometrici sul modello costruito: compenetrazioni, fessure, oggetti sospesi.

Funzioni pure, senza importazioni: girano sia nei test sia dentro Blender (vengono incollate nello script
generato, dopo `blender/costruttore_classico.py`). Le "parti" sono scatole sugli assi, una per ogni scatola,
cilindro o prisma con cui è costruito un oggetto: un arredo a gradini (cassettiera con colonne di altezze
diverse) ha una parte per colonna, quindi non dà falsi allarmi.

Una parte è una tupla: (oggetto, categoria, (xmin, ymin, zmin), (xmax, ymax, zmax)),
con categoria "architettura" (muri, pavimento, aperture) oppure "arredo". Le parti inclinate (pareti non
ortogonali, arredi ruotati) hanno un quinto elemento, la scatola orientata (centro, tre assi unitari, mezze misure):
con quella si controlla il contatto vero, non quello della scatola sugli assi che la contiene (che darebbe falsi
allarmi). Il confronto tra scatole orientate usa il test dell'asse separatore.

Soglie: compenetrazione oltre 1 mm = ERRORE; fessura tra 0,3 e 6 mm = AVVISO (quasi a contatto: di solito
due misure arrotondate in modo diverso); arredo che non tocca né il pavimento né un altro oggetto = AVVISO.
"""

TOL_COMPENETRAZIONE = 0.001
FESSURA_MIN = 0.0003
FESSURA_MAX = 0.006
TOL_CONTATTO = 0.0005


def colonne_estremi(spec):
    """Per una cassettiera a colonne: lista di (u_inizio, u_fine, altezza) lungo la parete."""
    u = float(spec["da_m"])
    out = []
    for c in spec["colonne"]:
        w = float(c["larghezza_m"])
        out.append((u, u + w, float(c["altezza_m"])))
        u += w
    return out


def estremi_piano(spec_piano, arredi):
    """Estremi (u0, u1, z0) di un piano appoggiato su colonne di cassettiere.

    `su: {unita: [id, id], colonna: N}`: il piano va dal bordo sinistro della colonna N della prima unità al
    bordo destro della colonna N dell'ultima, e poggia sulla loro sommità. Le coordinate non si scrivono a mano:
    derivano dalle colonne, così non possono più essere incoerenti con esse."""
    su = spec_piano["su"]
    per_id = {a.get("id"): a for a in arredi}
    n = int(su.get("colonna", 2)) - 1
    prima = colonne_estremi(per_id[su["unita"][0]])[n]
    ultima = colonne_estremi(per_id[su["unita"][-1]])[n]
    if abs(prima[2] - ultima[2]) > 1e-6:
        raise ValueError("le colonne di appoggio del piano hanno altezze diverse")
    return prima[0], ultima[1], prima[2]


def _sovrapposizioni(a, b):
    return [min(a[3][i], b[3][i]) - max(a[2][i], b[2][i]) for i in range(3)]


def _inclinata(p):
    return len(p) > 4 and p[4] is not None


def _obb(p):
    """Scatola orientata di una parte: (centro, assi, mezze misure)."""
    if _inclinata(p):
        return p[4]
    a, b = p[2], p[3]
    return (tuple((a[i] + b[i]) / 2 for i in range(3)), ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            tuple((b[i] - a[i]) / 2 for i in range(3)))


def _prod(u, v):
    return u[0] * v[0] + u[1] * v[1] + u[2] * v[2]


def _separazioni(p, q):
    """Separazione (positiva) o sovrapposizione (negativa) lungo i 6 assi delle facce e i 9 dei prodotti vettoriali."""
    cp, ap, hp = _obb(p)
    cq, aq, hq = _obb(q)
    d = (cq[0] - cp[0], cq[1] - cp[1], cq[2] - cp[2])
    facce, spigoli = [], []
    assi = [(x, 0) for x in ap] + [(x, 1) for x in aq]
    for L, _ in assi:
        rp = sum(hp[i] * abs(_prod(ap[i], L)) for i in range(3))
        rq = sum(hq[i] * abs(_prod(aq[i], L)) for i in range(3))
        facce.append(abs(_prod(d, L)) - rp - rq)
    for i in range(3):
        for j in range(3):
            L = (ap[i][1] * aq[j][2] - ap[i][2] * aq[j][1], ap[i][2] * aq[j][0] - ap[i][0] * aq[j][2],
                 ap[i][0] * aq[j][1] - ap[i][1] * aq[j][0])
            n = _prod(L, L) ** 0.5
            if n < 1e-6:
                continue
            L = (L[0] / n, L[1] / n, L[2] / n)
            rp = sum(hp[k] * abs(_prod(ap[k], L)) for k in range(3))
            rq = sum(hq[k] * abs(_prod(aq[k], L)) for k in range(3))
            spigoli.append(abs(_prod(d, L)) - rp - rq)
    return facce, spigoli


def _esame(a, b):
    """(profondità di compenetrazione o None, contatto, fessura o None) per due parti. Per due scatole sugli assi
    il risultato è quello del confronto per intervalli; se una è inclinata si usa l'asse separatore."""
    if not (_inclinata(a) or _inclinata(b)):
        o = _sovrapposizioni(a, b)
        if all(v > TOL_COMPENETRAZIONE for v in o):
            return min(o), False, None
        lontani = [k for k in range(3) if o[k] < 0]
        contatto = len(lontani) <= 1 and all(v >= -TOL_CONTATTO for v in o) and any(abs(v) <= TOL_CONTATTO for v in o)
        gap = None
        if len(lontani) == 1:
            k = lontani[0]
            altri = [x for x in range(3) if x != k]
            g = -o[k]
            if all(o[x] > TOL_COMPENETRAZIONE for x in altri) and FESSURA_MIN < g <= FESSURA_MAX:
                gap = g
        return None, contatto, gap
    facce, spigoli = _separazioni(a, b)
    tutte = facce + spigoli
    massima = max(tutte)
    if massima < -TOL_COMPENETRAZIONE:
        return -massima, False, None                      # compenetrazione: l'asse con meno sovrapposizione
    contatto = massima <= TOL_CONTATTO and massima >= -TOL_CONTATTO
    gap = None
    ap, aq = _obb(a)[1], _obb(b)[1]
    direzioni = list(ap) + list(aq)                      # nello stesso ordine di `facce`
    separati = [k for k, s in enumerate(facce) if s > 0]
    if separati:
        d0 = direzioni[separati[0]]
        parallele = [k for k in range(6) if abs(_prod(direzioni[k], d0)) > 0.9999]
        if all(k in parallele for k in separati) and                 FESSURA_MIN < max(facce[k] for k in separati) <= FESSURA_MAX and                 all(s < -TOL_COMPENETRAZIONE for k, s in enumerate(facce) if k not in parallele) and                 max(tutte) <= max(facce[k] for k in separati) + 1e-9:
            gap = max(facce[k] for k in separati)
    return None, contatto, gap


def _tocca(a, b):
    """Le due parti si toccano o si compenetrano (entro la tolleranza di contatto)."""
    if not (_inclinata(a) or _inclinata(b)):
        return all(v >= -TOL_CONTATTO for v in _sovrapposizioni(a, b))
    facce, spigoli = _separazioni(a, b)
    return max(facce + spigoli) <= TOL_CONTATTO


CELLA = 2.0   # lato (m) delle celle della griglia che limita i confronti ai pezzi vicini


def _celle(a, b, margine):
    """Celle (ix, iy) della griglia coperte dalla scatola (a, b) allargata del margine."""
    ix0, ix1 = int((a[0] - margine) // CELLA), int((b[0] + margine) // CELLA)
    iy0, iy1 = int((a[1] - margine) // CELLA), int((b[1] + margine) // CELLA)
    return [(x, y) for x in range(ix0, ix1 + 1) for y in range(iy0, iy1 + 1)]


def verifica(parti):
    """Restituisce una lista di problemi: dict con gravita, tipo, oggetti, dettaglio.

    Per tenere veloci anche gli edifici grandi si confrontano solo i pezzi che stanno nelle stesse celle di una
    griglia da 2 m (il risultato è identico al confronto di tutte le coppie)."""
    problemi = {}
    contatti = set()   # coppie di oggetti che si toccano in almeno un punto: i loro piccoli scarti sono voluti
    n = len(parti)
    griglia = {}
    for i in range(n):
        for c in _celle(parti[i][2], parti[i][3], FESSURA_MAX):
            griglia.setdefault(c, []).append(i)
    coppie = set()
    for membri in griglia.values():
        for a in range(len(membri)):
            for b in range(a + 1, len(membri)):
                coppie.add((membri[a], membri[b]))       # membri è in ordine crescente
    for i, j in sorted(coppie):
        a, b = parti[i], parti[j]
        if a[0] == b[0] or (a[1] == "architettura" and b[1] == "architettura"):
            continue
        chiave = tuple(sorted((a[0], b[0])))
        profondita, contatto, gap = _esame(a, b)
        if profondita is not None:
            prec = problemi.get((chiave, "compenetrazione"))
            if prec is None or profondita > prec["mm"] / 1000:
                problemi[(chiave, "compenetrazione")] = {
                    "gravita": "ERRORE", "tipo": "compenetrazione", "oggetti": chiave, "mm": profondita * 1000,
                    "dettaglio": f"{chiave[0]} e {chiave[1]} si compenetrano di {profondita * 1000:.1f} mm"}
            continue
        if contatto:
            contatti.add(chiave)
        if gap is not None:
            prec = problemi.get((chiave, "fessura"))
            if prec is None or gap * 1000 < prec["mm"]:
                problemi[(chiave, "fessura")] = {
                    "gravita": "AVVISO", "tipo": "fessura", "oggetti": chiave, "mm": gap * 1000,
                    "dettaglio": f"tra {chiave[0]} e {chiave[1]} resta una fessura di {gap * 1000:.1f} mm"}
    for coppia in contatti:   # un'anta o un cassetto leggermente arretrati non sono una fessura
        problemi.pop((coppia, "fessura"), None)
    # arredi sospesi: devono toccare il pavimento o un altro oggetto
    nomi = sorted({p[0] for p in parti if p[1] == "arredo"})
    per_nome = {}
    for i in range(n):
        per_nome.setdefault(parti[i][0], []).append(i)
    for nome in nomi:
        proprie = [parti[i] for i in per_nome[nome]]
        if min(p[2][2] for p in proprie) <= TOL_CONTATTO:
            continue
        tocca = False
        for i in per_nome[nome]:
            p = parti[i]
            visti = set()
            for c in _celle(p[2], p[3], TOL_CONTATTO):
                for j in griglia.get(c, ()):
                    if j in visti or parti[j][0] == nome:
                        continue
                    visti.add(j)
                    if _tocca(p, parti[j]):   # si toccano o si compenetrano: è sostenuto
                        tocca = True
                        break
                if tocca:
                    break
            if tocca:
                break
        if not tocca:
            problemi[((nome,), "sospeso")] = {
                "gravita": "AVVISO", "tipo": "sospeso", "oggetti": (nome,), "mm": 0.0,
                "dettaglio": f"{nome} non tocca né il pavimento né altri oggetti (sospeso)"}
    # parti sospese dentro un oggetto sostenuto (un rubinetto sopra il vuoto del lavabo, un pomolo staccato):
    # ogni parte deve essere legata, attraverso parti che si toccano, al pavimento o a un altro oggetto
    for nome in nomi:
        indici = per_nome[nome]
        if len(indici) < 2 or ((nome,), "sospeso") in problemi:
            continue
        ancorate = set()
        for i in indici:
            p = parti[i]
            if p[2][2] <= TOL_CONTATTO:
                ancorate.add(i)
                continue
            for c in _celle(p[2], p[3], TOL_CONTATTO):
                if any(parti[j][0] != nome and _tocca(p, parti[j]) for j in griglia.get(c, ())):
                    ancorate.add(i)
                    break
        raggiunte, coda = set(ancorate), list(ancorate)
        while coda:
            i = coda.pop()
            for j in indici:
                if j not in raggiunte and _tocca(parti[i], parti[j]):
                    raggiunte.add(j)
                    coda.append(j)
        staccate = [i for i in indici if i not in raggiunte]
        if staccate:
            p = parti[staccate[0]]
            centro = ", ".join(f"{(p[2][k] + p[3][k]) / 2:.2f}" for k in range(3))
            problemi[((nome,), "parte sospesa")] = {
                "gravita": "AVVISO", "tipo": "parte sospesa", "oggetti": (nome,), "mm": 0.0,
                "dettaglio": f"{nome}: {len(staccate)} parte/i non toccano il resto dell'oggetto né altro "
                             f"(la prima ha il centro in {centro} m)"}
    return sorted(problemi.values(), key=lambda p: (p["gravita"] != "ERRORE", p["tipo"], p["oggetti"]))


def rapporto_in_testo(problemi):
    if not problemi:
        return "GEOMETRIA: nessuna compenetrazione, fessura o oggetto sospeso."
    righe = [f"GEOMETRIA: {sum(p['gravita'] == 'ERRORE' for p in problemi)} ERRORI, "
             f"{sum(p['gravita'] == 'AVVISO' for p in problemi)} AVVISI"]
    righe += [f"- {p['gravita']}: {p['dettaglio']}" for p in problemi]
    return "\n".join(righe)
