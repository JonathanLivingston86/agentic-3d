"""Confronto tra il modello costruito da Blender (costruttore classico) e quello del nucleo senza Blender.

Per ogni oggetto si confrontano: nome, estremi (scatola che lo contiene), area per materiale e volume. È la prova
che il nucleo non cambia il risultato. Il confronto con Blender richiede Blender aperto con il ponte acceso.

Uso:  uv run python -m agentic3d.nucleo.equivalenza "lavori/<Nome>/Scheda stanze.yaml"
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from .scena import Scena

# Eseguito dentro Blender dopo la costruzione: stampa le metriche di ogni mesh (coordinate del mondo).
SCRIPT_METRICHE = '''
def _metriche():
    bpy.context.view_layer.update()
    out = {}
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.transform(bm, matrix=ob.matrix_world, verts=bm.verts)
        xs = [v.co.x for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        zs = [v.co.z for v in bm.verts]
        aree = {}
        for f in bm.faces:
            nome = ob.data.materials[f.material_index].name
            aree[nome] = aree.get(nome, 0.0) + f.calc_area()
        out[ob.name] = {"min": (min(xs), min(ys), min(zs)), "max": (max(xs), max(ys), max(zs)),
                        "aree": aree, "volume": bm.calc_volume(signed=True), "facce": len(bm.faces)}
        bm.free()
    return out
print("METRICHE=" + repr(_metriche()))
'''


def metriche_scena(scena: Scena) -> dict:
    out = {}
    for o in scena.oggetti:
        (x0, y0, z0), (x1, y1, z1) = o.mesh.limiti()
        ox, oy, oz = o.origine
        out[o.nome] = {"min": (x0 + ox, y0 + oy, z0 + oz), "max": (x1 + ox, y1 + oy, z1 + oz),
                       "aree": o.mesh.area_per_materiale(), "volume": o.mesh.volume(), "facce": len(o.mesh.f)}
    return out


def leggi_metriche_blender(risposta: dict) -> dict:
    testo = risposta["result"]["result"]
    riga = next(r for r in testo.splitlines() if r.startswith("METRICHE="))
    return ast.literal_eval(riga[len("METRICHE="):])


def confronta(blender: dict, nucleo: dict, tol_estremi=5e-6, tol_rel=1e-4, tol_arrotondati=0.06,
              arrotondati=("Letto",), solo_presenza=frozenset()) -> list[str]:
    """Elenco delle differenze (vuoto = equivalenti). Gli oggetti con spigoli arrotondati (letti) hanno la tolleranza
    `tol_arrotondati` su area e volume: la smussatura di Blender (`bmesh.ops.bevel` con il profilo predefinito)
    lascia sugli spigoli un gradino quadrato di lato pari al raggio, il nucleo li arrotonda davvero come
    dichiara il nome `smussato` (stessi estremi, stesso raggio, 4% di area in meno di materiale tolto).
    Blender memorizza i vertici in precisione singola: da qui le tolleranze di pochi micrometri.
    Gli oggetti in `solo_presenza` (le porte, migliorate nel nucleo il 22 ottobre 2026: mostre e maniglie su tutte e
    due le facce) si controllano soltanto per nome: il costruttore classico resta com'era."""
    problemi = []
    mancanti = set(blender) - set(nucleo)
    extra = set(nucleo) - set(blender)
    if mancanti:
        problemi.append(f"oggetti solo in Blender: {sorted(mancanti)}")
    if extra:
        problemi.append(f"oggetti solo nel nucleo: {sorted(extra)}")
    for nome in sorted(set(blender) & set(nucleo)):
        if nome in solo_presenza:
            continue
        b, n = blender[nome], nucleo[nome]
        tol = tol_arrotondati if nome.startswith(arrotondati) else tol_rel
        for k in range(3):
            for lato in ("min", "max"):
                if abs(b[lato][k] - n[lato][k]) > tol_estremi:
                    problemi.append(f"{nome}: estremo {lato}[{k}] {b[lato][k]:.6f} (Blender) contro {n[lato][k]:.6f}")
        materiali = set(b["aree"]) | set(n["aree"])
        for mat in sorted(materiali):
            ab, an = b["aree"].get(mat, 0.0), n["aree"].get(mat, 0.0)
            if abs(ab - an) > tol * max(ab, an, 1e-9) + 1e-9:
                problemi.append(f"{nome}: area di '{mat}' {ab:.6f} (Blender) contro {an:.6f}")
        vb, vn = b["volume"], n["volume"]
        if abs(vb - vn) > tol * max(abs(vb), abs(vn), 1e-9) + 1e-9:
            problemi.append(f"{nome}: volume {vb:.6f} (Blender) contro {vn:.6f}")
    return problemi


def confronta_con_blender(percorso_scheda: str | Path) -> tuple[list[str], dict, dict]:
    from ..costruttore import genera_script, invia_a_blender
    from ..scheda import carica_scheda, completa
    from .costruzione import scena_da_scheda

    scheda = completa(carica_scheda(percorso_scheda))
    codice = genera_script(scheda, Path(percorso_scheda).parent) + "\n" + SCRIPT_METRICHE
    blender = leggi_metriche_blender(invia_a_blender(codice))
    scena = scena_da_scheda(scheda, muri_uniti=False)     # il costruttore classico fa un oggetto per muro
    nucleo = metriche_scena(scena)
    porte = frozenset(o.nome for o in scena.oggetti if o.tipo == "porta")
    return confronta(blender, nucleo, solo_presenza=porte), blender, nucleo


if __name__ == "__main__":
    problemi, b, n = confronta_con_blender(sys.argv[1])
    print(f"{len(b)} oggetti in Blender, {len(n)} nel nucleo")
    print("\n".join(problemi) if problemi else "EQUIVALENTI")
    sys.exit(1 if problemi else 0)
