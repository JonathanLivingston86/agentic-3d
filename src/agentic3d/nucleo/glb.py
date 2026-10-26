"""Scrittura di un file GLB (glTF 2.0 binario) da una `Scena`, senza Blender e senza librerie esterne.

Stessa struttura del GLB che esportava Blender: un nodo piatto per oggetto con il suo nome, una mesh con una
primitiva per materiale, materiali con nome (colore, ruvidezza, metallo, trasparenza), unità in metri,
asse verticale Y come vuole lo standard glTF (x, y, z) -> (x, z, -y). Le facce piatte hanno normali di faccia,
quelle lisce normali medie sui vertici condivisi.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

from .materiali import MATERIALI
from .scena import Scena

_FLOAT, _USHORT, _UINT = 5126, 5123, 5125


def _y_alto(p):
    return (p[0], p[2], -p[1])


def _padding(b: bytes, riempimento: bytes) -> bytes:
    resto = (-len(b)) % 4
    return b + riempimento * resto


def glb_bytes(scena: Scena, generatore: str = "agentic3d nucleo") -> bytes:
    materiali: list[str] = []
    for o in scena.oggetti:
        for m in o.mesh.materiali:
            if m not in materiali:
                materiali.append(m)
    gltf_mat = []
    for nome in materiali:
        if nome not in MATERIALI:
            raise KeyError(f"materiale sconosciuto: {nome!r} (aggiungilo a nucleo/materiali.py)")
        r, g, b, rough, metal, alpha = MATERIALI[nome]
        voce = {"name": nome, "doubleSided": True,
                "pbrMetallicRoughness": {"baseColorFactor": [r, g, b, alpha], "metallicFactor": metal, "roughnessFactor": rough}}
        if alpha < 1.0:
            voce["alphaMode"] = "BLEND"
        gltf_mat.append(voce)

    binario = bytearray()
    viste, accessori, meshes, nodi = [], [], [], []

    def aggiungi(dati: bytes, bersaglio: int | None) -> int:
        while len(binario) % 4:
            binario.append(0)
        viste.append({"buffer": 0, "byteOffset": len(binario), "byteLength": len(dati),
                      **({"target": bersaglio} if bersaglio else {})})
        binario.extend(dati)
        return len(viste) - 1

    for o in scena.oggetti:
        mesh = o.mesh
        if not mesh.f:
            continue
        nf, nv = mesh.normali_angolo()
        per_mat: dict[int, dict] = {}
        for k, tris in mesh.triangoli():
            blocco = per_mat.setdefault(mesh.mat[k], {"pos": [], "nor": [], "idx": [], "chiavi": {}})
            for tri in tris:
                for vi in tri:
                    n = nv[vi] if (mesh.liscia[k] and vi in nv) else nf[k]
                    chiave = (vi, round(n[0], 6), round(n[1], 6), round(n[2], 6))
                    pos = blocco["chiavi"].get(chiave)
                    if pos is None:
                        pos = len(blocco["pos"])
                        blocco["chiavi"][chiave] = pos
                        blocco["pos"].append(_y_alto(mesh.v[vi]))
                        blocco["nor"].append(_y_alto(n))
                    blocco["idx"].append(pos)
        primitive = []
        for imat in sorted(per_mat):
            b = per_mat[imat]
            pos, nor, idx = b["pos"], b["nor"], b["idx"]
            va = aggiungi(struct.pack(f"<{3 * len(pos)}f", *[c for p in pos for c in p]), 34962)
            accessori.append({"bufferView": va, "componentType": _FLOAT, "count": len(pos), "type": "VEC3",
                              "min": [min(p[i] for p in pos) for i in range(3)],
                              "max": [max(p[i] for p in pos) for i in range(3)]})
            a_pos = len(accessori) - 1
            vn = aggiungi(struct.pack(f"<{3 * len(nor)}f", *[c for p in nor for c in p]), 34962)
            accessori.append({"bufferView": vn, "componentType": _FLOAT, "count": len(nor), "type": "VEC3"})
            a_nor = len(accessori) - 1
            if len(pos) < 65536:
                vi_ = aggiungi(struct.pack(f"<{len(idx)}H", *idx), 34963)
                tipo = _USHORT
            else:
                vi_ = aggiungi(struct.pack(f"<{len(idx)}I", *idx), 34963)
                tipo = _UINT
            accessori.append({"bufferView": vi_, "componentType": tipo, "count": len(idx), "type": "SCALAR"})
            a_idx = len(accessori) - 1
            primitive.append({"attributes": {"POSITION": a_pos, "NORMAL": a_nor}, "indices": a_idx,
                              "material": materiali.index(mesh.materiali[imat])})
        meshes.append({"name": o.nome, "primitives": primitive})
        nodo = {"mesh": len(meshes) - 1, "name": o.nome}
        if any(abs(c) > 1e-12 for c in o.origine):
            nodo["translation"] = list(_y_alto(o.origine))
        nodi.append(nodo)

    documento = {
        "asset": {"generator": generatore, "version": "2.0"},
        "scene": 0,
        "scenes": [{"name": scena.nome, "nodes": list(range(len(nodi)))}],
        "nodes": nodi, "materials": gltf_mat, "meshes": meshes, "accessors": accessori,
        "bufferViews": viste, "buffers": [{"byteLength": len(binario)}],
    }
    j = _padding(json.dumps(documento, separators=(",", ":")).encode("utf-8"), b" ")
    b = _padding(bytes(binario), b"\x00")
    totale = 12 + 8 + len(j) + 8 + len(b)
    return (struct.pack("<III", 0x46546C67, 2, totale) + struct.pack("<II", len(j), 0x4E4F534A) + j
            + struct.pack("<II", len(b), 0x004E4942) + b)


def scrivi_glb(scena: Scena, percorso: str | Path, includi_soffitto: bool = False) -> Path:
    """Scrive il GLB. Come in Blender, il soffitto non entra nel file per SketchUp (si può includere)."""
    p = Path(percorso).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    s = scena
    if not includi_soffitto:
        s = Scena(scena.nome)
        for o in scena.oggetti:
            if o.tipo != "soffitto":
                s.aggiungi(o)
    p.write_bytes(glb_bytes(s))
    return p
