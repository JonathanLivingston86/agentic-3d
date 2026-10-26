"""Costruttore parametrico di stanze per Blender. Gira DENTRO Blender: usa solo bpy, bmesh, mathutils, math.

Compatibile con la modalità sicura del ponte MCP (nessun import vietato, nessun accesso a file se non con
operatori bpy). Lo script completo si genera con `python -m agentic3d costruisci "<scheda>.yaml"`, che
incolla i dati della scheda sopra questo codice e lo invia a Blender.

Costruttore CLASSICO: costruisce la geometria con bmesh dentro Blender. Il percorso predefinito oggi è il nucleo
senza Blender (`nucleo/`); questo resta come riferimento e per confronto (`--motore classico`). Lo script generato
incolla prima il preambolo con la tavolozza e `regia.py`, di cui questo codice usa `materiale`,
`collezione`, `pulisci_scena`, `luci_e_cielo`.

Sistema di riferimento: origine nell'angolo interno sud-ovest, X est, Y nord, Z alto, metri.
Per gli oggetti appoggiati a una parete si usano coordinate di parete (u, d, z):
u = distanza lungo la parete dall'angolo sud-ovest, d = distanza dalla parete verso l'interno, z = quota.

Ogni arredo è UN solo oggetto con più materiali, nome leggibile e origine alla base: in SketchUp diventa
un solo componente con il suo nome.
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

def mappa(parete, L, W):
    """Funzione (u, d, z) -> punto del mondo, per una parete."""
    if parete == "sud":
        return lambda u, d, z: Vector((u, d, z))
    if parete == "nord":
        return lambda u, d, z: Vector((u, W - d, z))
    if parete == "ovest":
        return lambda u, d, z: Vector((d, u, z))
    if parete == "est":
        return lambda u, d, z: Vector((L - d, u, z))
    raise ValueError(f"parete sconosciuta: {parete}")


PARTI = []   # parti (scatole sugli assi) di tutti gli oggetti, per i controlli geometrici


def _aabb(punti):
    return (Vector((min(p[0] for p in punti), min(p[1] for p in punti), min(p[2] for p in punti))),
            Vector((max(p[0] for p in punti), max(p[1] for p in punti), max(p[2] for p in punti))))


class Pezzo:
    """Un oggetto fatto di scatole, prismi e cilindri, con materiali per faccia. Si chiude in un solo mesh."""

    def __init__(self, nome, raccolta, registra=True):
        self.nome = nome
        self.raccolta = raccolta
        self.registra = registra
        self.bm = bmesh.new()
        self.mats = []
        self.parti = []

    def _parte(self, punti):
        self.parti.append(_aabb(punti))

    def _idx(self, mat):
        if mat not in self.mats:
            self.mats.append(mat)
        return self.mats.index(mat)

    def _faccia(self, verts, mat):
        vs = [self.bm.verts.new(v) for v in verts]
        f = self.bm.faces.new(vs)
        f.material_index = self._idx(mat)
        return f

    def box(self, p0, p1, mat):
        """Scatola con spigoli sugli assi: p0 e p1 sono due angoli opposti."""
        x0, y0, z0 = (min(p0[i], p1[i]) for i in range(3))
        x1, y1, z1 = (max(p0[i], p1[i]) for i in range(3))
        if x1 - x0 < 1e-6 or y1 - y0 < 1e-6 or z1 - z0 < 1e-6:
            return
        self._parte([(x0, y0, z0), (x1, y1, z1)])
        v = [Vector(c) for c in ((x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                                 (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1))]
        for a, b, c, d in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            self._faccia([v[a], v[b], v[c], v[d]], mat)

    def box_p(self, m, u0, d0, z0, u1, d1, z1, mat):
        """Scatola in coordinate di parete."""
        a, b = m(u0, d0, z0), m(u1, d1, z1)
        self.box(a, b, mat)

    def prisma(self, m, punti_uz, d0, d1, mat):
        """Poligono nel piano (u, z) estruso tra d0 e d1."""
        n = len(punti_uz)
        fronte = [m(u, d0, z) for u, z in punti_uz]
        retro = [m(u, d1, z) for u, z in punti_uz]
        self._parte(fronte + retro)
        facce = [self._faccia(fronte, mat), self._faccia(list(reversed(retro)), mat)]
        for i in range(n):
            j = (i + 1) % n
            facce.append(self._faccia([fronte[i], fronte[j], retro[j], retro[i]], mat))
        centro = sum(fronte + retro, Vector((0, 0, 0))) / (2 * n)
        for f in facce:  # il prisma è convesso: le normali devono allontanarsi dal centro
            f.normal_update()
            if f.normal.dot(f.calc_center_median() - centro) < 0:
                f.normal_flip()

    def cilindro(self, cx, cy, z0, z1, r, mat, seg=20):
        basso = [Vector((cx + r * math.cos(2 * math.pi * i / seg), cy + r * math.sin(2 * math.pi * i / seg), z0)) for i in range(seg)]
        alto = [Vector((v.x, v.y, z1)) for v in basso]
        self._parte(basso + alto)
        self._faccia(list(reversed(basso)), mat)
        self._faccia(alto, mat)
        for i in range(seg):
            j = (i + 1) % seg
            self._faccia([basso[i], basso[j], alto[j], alto[i]], mat)

    def cilindro_asse(self, a, b, r, mat, seg=14):
        """Cilindro tra due punti qualsiasi (bastone, gambe)."""
        a, b = Vector(a), Vector(b)
        asse = (b - a).normalized()
        ref = Vector((0, 0, 1)) if abs(asse.z) < 0.9 else Vector((1, 0, 0))
        e1 = asse.cross(ref).normalized()
        e2 = asse.cross(e1).normalized()
        c0 = [a + r * (math.cos(2 * math.pi * i / seg) * e1 + math.sin(2 * math.pi * i / seg) * e2) for i in range(seg)]
        c1 = [p + (b - a) for p in c0]
        self._parte(c0 + c1)
        self._faccia(list(reversed(c0)), mat)
        self._faccia(c1, mat)
        for i in range(seg):
            j = (i + 1) % seg
            self._faccia([c0[i], c0[j], c1[j], c1[i]], mat)

    def smussato(self, p0, p1, mat, raggio=0.02, segmenti=2):
        """Scatola con spigoli arrotondati (materassi, cuscini)."""
        tmp = bmesh.new()
        bmesh.ops.create_cube(tmp, size=1.0)
        for v in tmp.verts:
            v.co = Vector((p0[0] + (v.co.x + 0.5) * (p1[0] - p0[0]),
                           p0[1] + (v.co.y + 0.5) * (p1[1] - p0[1]),
                           p0[2] + (v.co.z + 0.5) * (p1[2] - p0[2])))
        bmesh.ops.bevel(tmp, geom=list(tmp.edges), offset=raggio, segments=segmenti, affect="EDGES")
        self._parte([p0, p1])
        idx = self._idx(mat)
        mesh = bpy.data.meshes.new("_tmp")
        tmp.to_mesh(mesh)
        tmp.free()
        prima = len(self.bm.faces)
        self.bm.from_mesh(mesh)
        bpy.data.meshes.remove(mesh)
        self.bm.faces.ensure_lookup_table()
        for f in self.bm.faces[prima:]:
            f.material_index = idx
            f.smooth = True

    def griglia(self, quadri, mat):
        """Superficie libera da una lista di quadrilateri (4 punti ciascuno)."""
        self._parte([v for q in quadri for v in q])
        for q in quadri:
            self._faccia(q, mat)

    def chiudi(self, trasf=None, origine_base=True, liscio=False, nome=None, ricalcola_normali=False):
        bm = self.bm
        if ricalcola_normali:  # solo per superfici chiuse e continue (tende): saldatura e normali coerenti
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        if trasf is not None:
            bmesh.ops.transform(bm, matrix=trasf, verts=bm.verts)
            self.parti = [_aabb([trasf @ Vector((x, y, z)) for x in (a.x, b.x) for y in (a.y, b.y) for z in (a.z, b.z)])
                          for a, b in self.parti]
        if liscio:
            for f in bm.faces:
                f.smooth = True
        xs = [v.co.x for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        zs = [v.co.z for v in bm.verts]
        centro = Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, min(zs))) if origine_base else Vector((0, 0, 0))
        if origine_base:
            bmesh.ops.translate(bm, vec=-centro, verts=bm.verts)
        mesh = bpy.data.meshes.new(nome or self.nome)
        bm.to_mesh(mesh)
        bm.free()
        for mat in self.mats:
            mesh.materials.append(materiale(mat))
        ob = bpy.data.objects.new(nome or self.nome, mesh)
        ob.location = centro
        self.raccolta.objects.link(ob)
        if self.registra:
            categoria = "architettura" if self.raccolta.name == "Architettura" else "arredo"
            for a, b in self.parti:
                PARTI.append((ob.name, categoria, tuple(a), tuple(b)))
        return ob


# ------------------------------------------------------------------ architettura
def _spessore(st, parete):
    return float(st["pareti"][parete]["spessore_m"])


def _taglia(ob, cutter_obj):
    mod = ob.modifiers.new("taglio", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.object = cutter_obj
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.ops.object.modifier_apply(modifier=mod.name)


def _pulisci_mesh(ob, fascia, piano, normale):
    """Unisce i triangoli complanari, taglia la fascia a quota `fascia` e assegna i materiali."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(0.5), verts=bm.verts, edges=bm.edges)
    if fascia:
        bmesh.ops.bisect_plane(bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
                               plane_co=(0, 0, fascia), plane_no=(0, 0, 1))
    bm.normal_update()
    ob.data.materials.clear()
    ob.data.materials.append(materiale("Intonaco pareti"))
    ob.data.materials.append(materiale("Fascia pareti verde salvia"))
    for f in bm.faces:
        c = f.calc_center_median()
        sul_piano = abs((c - piano).dot(normale)) < 1e-4 and abs(f.normal.dot(normale)) > 0.99
        f.material_index = 1 if (fascia and sul_piano and c.z < fascia - 1e-4) else 0
    bm.to_mesh(ob.data)
    bm.free()


def costruisci_architettura(st, L, W, H):
    col = collezione("Architettura")
    t = {p: _spessore(st, p) for p in ("sud", "nord", "ovest", "est")}
    fascia = st.get("fascia_altezza_m")
    x0, x1 = -t["ovest"], L + t["est"]
    y0, y1 = -t["sud"], W + t["nord"]
    oggetti = {}

    # pavimento e soffitto
    pav = Pezzo("Pavimento", col)
    pav.box((x0, y0, -0.10), (x1, y1, 0), "Intonaco pareti")
    ob = pav.chiudi()
    ob.data.materials.clear()
    ob.data.materials.append(materiale("Pavimento rovere"))
    ob.data.materials.append(materiale("Intonaco pareti"))
    for p in ob.data.polygons:
        p.material_index = 0 if (p.normal.z > 0.99) else 1
    oggetti["Pavimento"] = ob
    if st.get("soffitto", True):      # senza soffitto (esterni, oggetti): `soffitto: false` nella stanza
        sof = Pezzo("Soffitto", col)
        sof.box((x0, y0, H), (x1, y1, H + 0.10), "Soffitto bianco")
        oggetti["Soffitto"] = sof.chiudi()

    # pareti: nord e sud coprono gli angoli, ovest ed est vanno da y=0 a y=W
    fascia_geo = {
        "sud": ((x0, y0, 0), (x1, 0, H), Vector((0, 0, 0)), Vector((0, 1, 0))),
        "nord": ((x0, W, 0), (x1, y1, H), Vector((0, W, 0)), Vector((0, -1, 0))),
        "ovest": ((x0, 0, 0), (0, W, H), Vector((0, 0, 0)), Vector((1, 0, 0))),
        "est": ((L, 0, 0), (x1, W, H), Vector((L, 0, 0)), Vector((-1, 0, 0))),
    }
    nomi = {"sud": "Muro Sud", "nord": "Muro Nord", "ovest": "Muro Ovest", "est": "Muro Est"}
    for parete, (a, b, piano, normale) in fascia_geo.items():
        p = Pezzo(nomi[parete], col)
        p.box(a, b, "Intonaco pareti")
        ob = p.chiudi(origine_base=False)
        for ap in st.get("aperture", []):
            if ap["parete"] != parete:
                continue
            u0, u1 = ap["da_m"], ap["da_m"] + ap["larghezza_m"]
            z0 = ap.get("quota_davanzale_m", 0.0) if ap["tipo"] == "finestra" else -0.05
            z1 = z0 + ap["altezza_m"] if ap["tipo"] == "finestra" else ap["altezza_m"]
            m = mappa(parete, L, W)
            cut = Pezzo("taglio", col, registra=False)
            cut.box(m(u0, -t[parete] - 0.02, z0), m(u1, 0.02, z1), "Intonaco pareti")
            c = cut.chiudi(origine_base=False)
            _taglia(ob, c)
            bpy.data.objects.remove(c, do_unlink=True)
        _pulisci_mesh(ob, fascia, piano, normale)
        oggetti[nomi[parete]] = ob
    return oggetti


def costruisci_aperture(st, L, W):
    col = collezione("Architettura")
    t = {p: _spessore(st, p) for p in ("sud", "nord", "ovest", "est")}
    for ap in st.get("aperture", []):
        parete = ap["parete"]
        m = mappa(parete, L, W)
        u0, u1 = ap["da_m"], ap["da_m"] + ap["larghezza_m"]
        spess = t[parete]
        if ap["tipo"] == "finestra":
            q, h = ap["quota_davanzale_m"], ap["altezza_m"]
            z0, z1 = q, q + h
            p = Pezzo(ap.get("id", "Finestra"), col)
            prof, prof_d = 0.06, 0.08
            d_stanza = -(spess * 0.5 - prof_d / 2)      # faccia del telaio verso la stanza
            d_fondo = d_stanza - prof_d
            # telaio fisso, dentro lo spessore del muro
            for a, b in (((u0, z0), (u1, z0 + prof)), ((u0, z1 - prof), (u1, z1)),
                         ((u0, z0 + prof), (u0 + prof, z1 - prof)), ((u1 - prof, z0 + prof), (u1, z1 - prof))):
                p.box_p(m, a[0], d_fondo, a[1], b[0], d_stanza, b[1], "Telaio bianco")
            n = max(ap.get("ante", 2), 1)
            anta = (u1 - u0 - 2 * prof) / n
            for i in range(n):
                a0 = u0 + prof + i * anta
                a1 = a0 + anta
                pr = 0.045
                dd0, dd1 = d_stanza + 0.002, d_stanza + 0.04
                zz0, zz1 = z0 + prof, z1 - prof
                g = 0.0005   # piccolo distacco tra ante vicine
                for a, b in (((a0 + g, zz0 + 0.001), (a1 - g, zz0 + pr)), ((a0 + g, zz1 - pr), (a1 - g, zz1 - 0.001)),
                             ((a0 + g, zz0 + pr), (a0 + pr, zz1 - pr)), ((a1 - pr, zz0 + pr), (a1 - g, zz1 - pr))):
                    p.box_p(m, a[0], dd0, a[1], b[0], dd1, b[1], "Telaio bianco")
                p.box_p(m, a0 + pr, d_stanza + 0.015, zz0 + pr, a1 - pr, d_stanza + 0.023, zz1 - pr, "Vetro")
            # davanzale interno: sporge di 3 cm dal filo del muro
            p.box_p(m, u0 - 0.04, -spess * 0.5, z0 - 0.03, u1 + 0.04, 0.03, z0 + 0.001, "Laccato bianco")   # 1 mm sopra il vano: niente facce complanari
            p.chiudi()
        elif ap["tipo"] == "porta":
            h = ap["altezza_m"]
            p = Pezzo(ap.get("id", "Porta"), col)
            arch, arch_d = 0.09, 0.014
            for a, b in (((u0 - arch, 0.0), (u0, h + arch)), ((u1, 0.0), (u1 + arch, h + arch)),
                         ((u0, h), (u1, h + arch))):
                p.box_p(m, a[0], 0.0, a[1], b[0], arch_d, b[1], "Porta laccata")
            # anta chiusa dentro il vano, a metà dello spessore del muro
            f0, f1 = -(spess * 0.5 + 0.02), -(spess * 0.5 - 0.02)
            p.box_p(m, u0 + 0.004, f0, 0.0, u1 - 0.004, f1, h - 0.004, "Porta laccata")
            # maniglia sul lato opposto alla cerniera
            quota_m = ap.get("altezza_maniglia_m", 0.90)
            cerniera_a_u1 = ap.get("cerniera", "est") in ("est", "nord")  # lato di u crescente
            um = u0 + 0.07 if cerniera_a_u1 else u1 - 0.07
            p.box_p(m, um - 0.025, f1, quota_m - 0.035, um + 0.025, f1 + 0.01, quota_m + 0.035, "Maniglia")
            p.box_p(m, um - 0.07, f1 + 0.01, quota_m - 0.012, um + 0.02, f1 + 0.035, quota_m + 0.012, "Maniglia")
            p.chiudi()


# ------------------------------------------------------------------ arredi
def _trasf_letto(testa, cx, cy):
    ang = {"nord": 0.0, "sud": math.pi, "ovest": math.pi / 2, "est": -math.pi / 2}[testa]
    return Matrix.Translation((cx, cy, 0)) @ Matrix.Rotation(ang, 4, "Z")


def letto(sp, col):
    testa = sp["testa"]
    dx, dy = sp["dx_m"], sp["dy_m"]
    lunghezza, larghezza = (dy, dx) if testa in ("nord", "sud") else (dx, dy)
    w, l = larghezza, lunghezza
    p = Pezzo(sp["id"], col)
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
    return p.chiudi(_trasf_letto(testa, cx, cy))


def cassettiera(sp, col, L, W):
    m = mappa(sp["parete"], L, W)
    p = Pezzo(sp["id"], col)
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


def piano_scrivania(sp, col, L, W, arredi):
    """Piano su colonne di cassettiere: se c'è `su`, estremi e quota derivano dalle colonne (mai a mano)."""
    m = mappa(sp["parete"], L, W)
    p = Pezzo(sp["id"], col)
    if "su" in sp:
        u0, u1, z0 = estremi_piano(sp, arredi)
    else:
        u0, u1, z0 = sp["da_m"], sp["a_m"], sp["z0_m"]
    p.box_p(m, u0, 0.0, z0, u1, sp["profondita_m"], z0 + sp["spessore_m"], "Legno chiaro")
    return p.chiudi()


def sgabello(sp, col):
    p = Pezzo(sp["id"], col)
    r, h = sp["diametro_m"] / 2, sp["altezza_m"]
    cx, cy = sp["x_m"], sp["y_m"]
    p.cilindro(cx, cy, h - 0.04, h, r, "Sgabello senape", 28)
    for i in range(4):
        a = math.pi / 4 + i * math.pi / 2
        gx, gy = cx + 0.62 * r * math.cos(a), cy + 0.62 * r * math.sin(a)
        p.cilindro_asse((gx, gy, 0.0), (gx, gy, h - 0.04), 0.014, "Legno chiaro", 10)
    return p.chiudi()


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


def pensile_libri(sp, col, L, W):
    """Pensile a scomparti. Uno scomparto "libri" con `elementi: [[u0, larghezza, altezza], ...]` usa i dorsi
    del disegno; senza `elementi` i libri sono generici (pseudo-casuali) e `completa()` lo dichiara come ipotesi."""
    m = mappa(sp["parete"], L, W)
    p = Pezzo(sp["id"], col)
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
                zb = z0 + s + j * 0.115
                uc = (ua + ub) / 2
                poly = [(uc - 0.07, zb), (uc + 0.07, zb), (uc + 0.115, zb + 0.095), (uc - 0.115, zb + 0.095)]
                p.prisma(m, poly, 0.03, pr - 0.02, CESTONI[(i + j) % 3])
    return p.chiudi()


def mensola_vassoio(sp, col, L, W):
    """Vassoio a muro (fondo, due bordi, schienale e frontale) con blocchi [u0, larghezza, altezza] appoggiati
    sul fondo: libri o scatole come nel disegno."""
    m = mappa(sp["parete"], L, W)
    p = Pezzo(sp["id"], col)
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


def mensola_portalibri(sp, col, L, W):
    m = mappa(sp["parete"], L, W)
    p = Pezzo(sp["id"], col)
    u0, w, pr = sp["da_m"], sp["larghezza_m"], sp["profondita_m"]
    z0, h = sp["z0_m"], sp["altezza_m"]
    p.box_p(m, u0, 0, z0, u0 + w, pr, z0 + h, "Legno chiaro")
    _libri(p, m, u0 + 0.02, u0 + w - 0.02, 0.02, pr - 0.015, z0 + h, 0.145, indice0=int(u0 * 10))
    return p.chiudi()


def quadro(sp, col, L, W):
    m = mappa(sp["parete"], L, W)
    p = Pezzo(sp["id"], col)
    c, w, h, z0 = sp["centro_m"], sp["larghezza_m"], sp["altezza_m"], sp["z0_m"]
    p.box_p(m, c - w / 2, 0, z0, c + w / 2, 0.025, z0 + h, "Cornice nera")
    idx = int("".join(ch for ch in sp["id"] if ch.isdigit()) or 1) - 1
    p.box_p(m, c - w / 2 + 0.01, 0.025, z0 + 0.01, c + w / 2 - 0.01, 0.027, z0 + h - 0.01, TELE[idx % 4])
    return p.chiudi()


def arco(sp, col, L, W):
    m = mappa(sp["parete"], L, W)
    p = Pezzo(sp["id"], col)
    u0, w, h = sp["da_m"], sp["larghezza_m"], sp["altezza_m"]
    r = w / 2
    pts = [(u0, 0.0), (u0 + w, 0.0)]
    seg = 20
    for i in range(seg + 1):
        a = math.pi * i / seg
        pts.append((u0 + r + r * math.cos(a), h - r + r * math.sin(a)))
    p.prisma(m, pts, 0.0, 0.012, "Arco terracotta")
    return p.chiudi()


def tv(sp, col, L, W):
    m = mappa(sp["parete"], L, W)
    p = Pezzo(sp["id"], col)
    u0, w, h, z0 = sp["da_m"], sp["larghezza_m"], sp["altezza_m"], sp["z0_m"]
    p.box_p(m, u0, 0, z0, u0 + w, 0.04, z0 + h, "Televisore nero")
    p.box_p(m, u0 + 0.015, 0.04, z0 + 0.015, u0 + w - 0.015, 0.042, z0 + h - 0.015, "Schermo spento")
    return p.chiudi()


def termosifone(sp, col, L, W):
    m = mappa(sp["parete"], L, W)
    p = Pezzo(sp["id"], col)
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


def bastone_tende(sp, col, L, W):
    m = mappa(sp["parete"], L, W)
    p = Pezzo(sp["id"], col)
    a = m(sp["da_m"], 0.10, sp["z_m"])
    b = m(sp["a_m"], 0.10, sp["z_m"])
    p.cilindro_asse(a, b, 0.012, "Metallo bastone", 16)
    for u in (sp["da_m"] + 0.03, sp["a_m"] - 0.03):
        p.cilindro_asse(m(u, 0.0, sp["z_m"]), m(u, 0.10, sp["z_m"]), 0.008, "Metallo bastone", 8)
    return p.chiudi()


def tenda(sp, col, L, W, z_bastone=2.977):
    """Tenda a pieghe: superficie ondulata con spessore, appesa al bastone e lunga fino a 2 cm da terra."""
    m = mappa(sp["parete"], L, W)
    p = Pezzo(sp["id"], col)
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


def armadio_a_muro(sp, col, L, W, H):
    m = mappa(sp["parete"], L, W)
    p = Pezzo(sp["id"], col)
    pr = sp["profondita_m"]
    p.box_p(m, 0.0, 0.0, 0.0, W, pr, H, "Laccato bianco")
    aw, ah = sp["anta_larghezza_m"], sp["anta_altezza_m"]
    ua = W - aw if sp.get("anta_lato", "nord") == "nord" else 0.0
    p.box_p(m, ua, pr, 0.0, ua + aw, pr + 0.02, ah, "Anta armadio")
    um = ua + 0.05 if sp.get("anta_lato", "nord") == "nord" else ua + aw - 0.05
    p.box_p(m, um - 0.008, pr + 0.02, 1.0, um + 0.008, pr + 0.05, 1.12, "Maniglia")
    return p.chiudi()


def rapporto_geometria():
    """Testo del controllo geometrico sul modello appena costruito (vedi verifica_geometria.py)."""
    return rapporto_in_testo(verifica(PARTI))


# ------------------------------------------------------------------ regia
def costruisci(dati):
    """Costruisce la stanza descritta da `dati` (scheda completata). Restituisce i nomi degli oggetti creati."""
    st = dati["stanza"]
    L, W, H = float(st["lunghezza_m"]), float(st["larghezza_m"]), float(st["altezza_m"])
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    sc.unit_settings.length_unit = "METERS"
    pulisci_scena()
    del PARTI[:]
    costruisci_architettura(st, L, W, H)
    costruisci_aperture(st, L, W)
    col = collezione("Arredi")
    tessili = collezione("Tessili")
    for sp in st.get("arredi", []):
        t = sp["tipo"]
        if t == "letto":
            letto(sp, col)
        elif t == "cassettiera_cestoni":
            cassettiera(sp, col, L, W)
        elif t == "piano":
            piano_scrivania(sp, col, L, W, st.get("arredi", []))
        elif t == "sgabello":
            sgabello(sp, col)
        elif t == "pensile_libri":
            pensile_libri(sp, col, L, W)
        elif t == "mensola_portalibri":
            mensola_portalibri(sp, col, L, W)
        elif t == "mensola_vassoio":
            mensola_vassoio(sp, col, L, W)
        elif t == "quadro":
            quadro(sp, col, L, W)
        elif t == "arco_decorativo":
            arco(sp, col, L, W)
        elif t == "tv":
            tv(sp, col, L, W)
        elif t == "termosifone":
            termosifone(sp, col, L, W)
        elif t == "bastone_tende":
            bastone_tende(sp, col, L, W)
        elif t == "tenda":
            tenda(sp, tessili, L, W)
        elif t == "armadio_a_muro":
            armadio_a_muro(sp, col, L, W, H)
        else:
            raise ValueError(f"tipo di arredo sconosciuto: {t}")
    finestra = next((a for a in st.get("aperture", []) if a.get("tipo") == "finestra"), None)
    luci_e_cielo(L, W, H, finestra["parete"] if finestra else "ovest")
    return sorted(o.name for o in bpy.data.objects)
