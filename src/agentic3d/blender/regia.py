"""Regia per Blender: materiali, scena, luci, camere, render ed esportazione. Gira DENTRO Blender.

Non conosce stanze né arredi: riceve oggetti già pronti (dal costruttore classico `costruttore_classico.py` oppure
importati dal GLB del nucleo, vedi `importa.py`). Usa solo bpy, bmesh, mathutils e math, compatibili con la
modalità sicura del ponte MCP. Prima di questo codice lo script generato incolla il preambolo con la tavolozza
(`MATERIALI`, `LIBRI`, `CESTONI`, `TESSUTI`, `TELE`) presa da `nucleo/materiali.py`.
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

def materiale(nome):
    m = bpy.data.materials.get(nome)
    if m:
        return m
    r, g, b, rough, metal, alpha = MATERIALI[nome]
    m = bpy.data.materials.new(nome)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if nome.startswith("Velluto"):                 # il velluto riflette radente: lucentezza morbida sui bordi
        try:
            bsdf.inputs["Sheen Weight"].default_value = 0.8
            bsdf.inputs["Sheen Roughness"].default_value = 0.35
        except KeyError:
            pass
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        try:
            m.surface_render_method = "BLENDED"
        except Exception:
            pass
    m.diffuse_color = (r, g, b, alpha)
    return m


# ------------------------------------------------------------------ scena
def imposta_unita():
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    sc.unit_settings.length_unit = "METERS"


def pulisci_scena():
    """Svuota la scena senza ripristinare le impostazioni di fabbrica (che spegnerebbero il ponte MCP)."""
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for raccolta in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras, bpy.data.curves,
                     bpy.data.images):
        for d in list(raccolta):
            raccolta.remove(d)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)


def collezione(nome):
    c = bpy.data.collections.get(nome)
    if c is None:
        c = bpy.data.collections.new(nome)
        bpy.context.scene.collection.children.link(c)
    return c


# ------------------------------------------------------------------ luci, camere, esportazione, render
def luci_e_cielo(L, W, H, parete_finestra="ovest"):
    col = collezione("Luci e camera")
    sole = bpy.data.lights.new("Sole dalla finestra", "SUN")
    sole.energy = 2.6
    so = bpy.data.objects.new("Sole dalla finestra", sole)
    col.objects.link(so)
    # raggi verso l'interno e verso il basso (elevazione 38 gradi): entrano dalla finestra, da qualunque parete
    angolo = {"ovest": 0.0, "est": math.pi, "sud": math.pi / 2, "nord": -math.pi / 2}[parete_finestra]
    so.rotation_euler = (math.radians(8), -(math.pi / 2 - math.radians(38)), angolo)
    area = bpy.data.lights.new("Luce di riempimento", "AREA")
    grandezza = max(1.0, L * W / 14.9)      # la cameretta (14,9 m2) è la stanza di taratura: 45 W
    area.energy = 45.0 * grandezza
    area.size = 2.2 * grandezza ** 0.5
    ao = bpy.data.objects.new("Luce di riempimento", area)
    ao["energia_base"] = area.energy
    col.objects.link(ao)
    ao.location = (L / 2, W / 2, H - 0.06)
    cielo = bpy.data.worlds.new("Cielo") if "Cielo" not in bpy.data.worlds else bpy.data.worlds["Cielo"]
    cielo.use_nodes = True
    bg = cielo.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.78, 0.87, 1.0, 1.0)
    bg.inputs[1].default_value = 0.55
    bpy.context.scene.world = cielo


def luci_edificio(stanze, direzione_sole):
    """Luci per un edificio: il sole entra dalle finestre nella direzione orizzontale `direzione_sole` (dx, dy) con
    elevazione di 38 gradi; una luce di riempimento per stanza sotto il soffitto, già dimensionata e posizionata
    dal costruttore (`luce_della_stanza`: un quadrato tutto dentro la stanza, mai a cavallo di una parete).
    `stanze` = [(x, y, lato, energia, quota della luce)]."""
    col = collezione("Luci e camera")
    sole = bpy.data.lights.new("Sole dalla finestra", "SUN")
    sole.energy = 2.6
    so = bpy.data.objects.new("Sole dalla finestra", sole)
    col.objects.link(so)
    dx, dy = direzione_sole
    el = math.radians(38)
    so.rotation_euler = Vector((dx * math.cos(el), dy * math.cos(el), -math.sin(el))).to_track_quat("-Z", "Y").to_euler()
    for k, (cx, cy, lato, energia, z_luce) in enumerate(stanze):
        # luce a sfera morbida a due terzi dell'altezza, invisibile alla camera: un pannello sotto il soffitto
        # illuminava i muri di striscio e lasciava una fascia chiara lungo il soffitto
        luce = bpy.data.lights.new("Luce di riempimento %d" % (k + 1), "POINT")
        luce.energy = energia
        luce.shadow_soft_size = max(0.1, min(0.6, lato / 2))
        lo = bpy.data.objects.new("Luce di riempimento %d" % (k + 1), luce)
        lo["energia_base"] = luce.energy
        col.objects.link(lo)
        lo.location = (cx, cy, z_luce)
        lo.visible_camera = False
    cielo = bpy.data.worlds.new("Cielo") if "Cielo" not in bpy.data.worlds else bpy.data.worlds["Cielo"]
    cielo.use_nodes = True
    bg = cielo.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.78, 0.87, 1.0, 1.0)
    bg.inputs[1].default_value = 0.55
    bpy.context.scene.world = cielo


# (moltiplicatore della luce di riempimento, moltiplicatore del cielo): "aperto" = viste dall'alto e in pianta,
# con il soffitto nascosto e il cielo che entra da sopra; "interno" = viste da dentro con il soffitto,
# dove la luce arriva solo dalle finestre e dalla luce di riempimento.
PROFILI_LUCE = {"aperto": (1.0, 1.0), "interno": (0.5, 2.0)}


def imposta_luci(profilo):
    f_area, f_cielo = PROFILI_LUCE[profilo]
    for ob in bpy.data.objects:                       # tutte le luci di riempimento (una per stanza negli edifici)
        if ob.type == "LIGHT" and "energia_base" in ob:
            ob.data.energy = ob["energia_base"] * f_area
    cielo = bpy.data.worlds.get("Cielo")
    if cielo is not None:
        cielo.node_tree.nodes["Background"].inputs[1].default_value = 0.55 * f_cielo


def camera(nome, posizione, bersaglio, lente=22.0, ortografica=None):
    """Camera puntata su `bersaglio`. `ortografica`: larghezza inquadrata in metri (vista in pianta)."""
    col = collezione("Luci e camera")
    cam = bpy.data.cameras.new(nome)
    cam.lens = lente
    if ortografica:
        cam.type = "ORTHO"
        cam.ortho_scale = ortografica
    cam.clip_start = 0.05
    # un arredo con lo stesso nome (la "Pianta" verde e la vista "Pianta") farebbe rinominare la camera in
    # "Pianta.001": la camera prende allora un nome suo, e `render` la cerca tra le camere
    ob = bpy.data.objects.new(nome if nome not in bpy.data.objects else "Camera " + nome, cam)
    col.objects.link(ob)
    ob.location = posizione
    direzione = Vector(bersaglio) - Vector(posizione)
    ob.rotation_euler = direzione.to_track_quat("-Z", "Y").to_euler()
    return ob


def imposta_render(larghezza=1280, altezza=720, campioni=96):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    sc.cycles.device = "CPU"
    # la prima scheda video disponibile: NVIDIA (CUDA), Mac (METAL), AMD (HIP), Intel (ONEAPI); altrimenti il processore
    for tipo in ("CUDA", "METAL", "HIP", "ONEAPI"):
        try:
            prefs.compute_device_type = tipo
            prefs.refresh_devices()
        except Exception:
            continue
        schede = [d for d in prefs.devices if d.type == tipo]
        if schede:
            for d in prefs.devices:
                d.use = d.type == tipo
            sc.cycles.device = "GPU"
            break
    sc.cycles.samples = campioni
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = larghezza, altezza
    sc.render.image_settings.file_format = "PNG"
    sc.view_settings.view_transform = "Standard"   # colori fedeli a quelli assegnati ai materiali
    sc.view_settings.exposure = -0.2


def render(percorso, nome_camera, nascondi=(), luci="aperto"):
    """Render da una camera; `nascondi` = oggetti da togliere solo da questa immagine (soffitto, muro in vista);
    `luci` = profilo di illuminazione (vedi PROFILI_LUCE)."""
    sc = bpy.context.scene
    imposta_luci(luci)
    sc.camera = next(o for o in bpy.data.objects if o.type == "CAMERA" and o.data.name == nome_camera)
    sc.render.filepath = percorso
    nascosti = []
    for nome in nascondi:
        o = bpy.data.objects.get(nome)
        if o:
            nascosti.append((o, o.hide_render))
            o.hide_render = True
    try:
        bpy.ops.render.render(write_still=True)
    except RuntimeError:
        # file bloccato (per esempio aperto nel visualizzatore di foto): l'immagine va accanto con un altro nome
        alternativo = percorso[:-4] + " (nuova).png"
        bpy.data.images["Render Result"].save_render(alternativo)
        print("ATTENZIONE: %s era bloccato (aperto in un altro programma?): salvato come %s" % (percorso, alternativo))
    finally:
        for o, stato in nascosti:
            o.hide_render = stato


def esporta_glb(percorso, includi_soffitto=False):
    """Esporta in GLB le sole mesh dell'architettura e degli arredi, senza luci né camere."""
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in bpy.context.scene.objects:
        if o.type == "MESH" and (includi_soffitto or o.name != "Soffitto"):
            o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=percorso, export_format="GLB", use_selection=True,
                              export_apply=True, export_cameras=False, export_lights=False)


def salva_blend(percorso):
    bpy.ops.wm.save_as_mainfile(filepath=percorso, copy=True)
