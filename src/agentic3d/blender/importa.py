"""Importa in Blender il GLB scritto dal nucleo. Gira DENTRO Blender, dopo `regia.py`.

La geometria nasce nel nucleo senza Blender; Blender serve per luci, camere e render. Questo codice legge il GLB con
l'operatore di importazione (consentito dalla modalità sicura), rimette i materiali della tavolozza (stessi valori
di sempre) e dispone gli oggetti nelle raccolte Architettura, Arredi, Tessili.
"""


def importa_glb(percorso, raccolte):
    """`raccolte`: dizionario nome dell'oggetto -> nome della raccolta. Restituisce i nomi degli oggetti importati."""
    imposta_unita()
    prima = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=percorso)
    nuovi = [o for o in bpy.data.objects if o not in prima]
    for ob in nuovi:
        if ob.type != "MESH":            # eventuali nodi vuoti creati dall'importatore
            bpy.data.objects.remove(ob, do_unlink=True)
    importati = []
    for ob in [o for o in nuovi if o.name in bpy.data.objects]:
        for i, slot in enumerate(ob.material_slots):
            vecchio = slot.material
            if vecchio is None:
                continue
            slot.material = materiale(vecchio.name.split(".")[0])
        for c in list(ob.users_collection):
            c.objects.unlink(ob)
        collezione(raccolte.get(ob.name, "Arredi")).objects.link(ob)
        importati.append(ob.name)
    for m in [m for m in bpy.data.materials if m.users == 0]:
        bpy.data.materials.remove(m)
    return sorted(importati)
