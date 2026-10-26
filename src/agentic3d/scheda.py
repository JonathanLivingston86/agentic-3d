"""Scheda del progetto 3D: lettura, valori predefiniti conformi alle norme, conversione per il controllore.

Una scheda minima (poche righe) basta per partire: `completa()` aggiunge i valori che mancano scegliendoli
in modo da rispettare le regole generali italiane (altezza, rapporto aeroilluminante, porte, maniglie) e
registra ogni scelta in `ipotesi_applicate`, così il rapporto dice sempre cosa è dato e cosa è stato assunto.

Sistema di riferimento della stanza: origine nell'angolo interno sud-ovest, X verso est, Y verso nord, Z in alto,
tutto in metri. Le pareti si chiamano `sud`, `nord`, `ovest`, `est`. La posizione di un'apertura o di un arredo
su una parete è la distanza `da_m` dall'angolo sud-ovest lungo la parete (X per sud e nord, Y per ovest ed est).
"""

from __future__ import annotations

import copy
import math
from pathlib import Path

import yaml

PARETI = ("sud", "nord", "ovest", "est")

# Valori usati quando la scheda non li dice. Ogni voce ha la base: norma o prassi.
PREDEFINITI = {
    "altezza_m": (2.70, "DM 5 luglio 1975, art. 1: altezza minima dei locali abitabili"),
    "spessore_parete_m": (0.10, "prassi: tramezzo o parete interna"),
    "spessore_parete_con_finestra_m": (0.30, "prassi: muratura perimetrale"),
    "porta_luce_netta_m": (0.80, "DM 236/1989, art. 8.1.1: 0,80 m per la porta di accesso, 0,75 m per le altre"),
    "porta_altezza_m": (2.10, "prassi: porta interna standard"),
    "altezza_maniglia_m": (0.90, "DM 236/1989, art. 8.1.1: tra 0,85 e 0,95 m, consigliata 0,90 m"),
    "finestra_altezza_m": (1.40, "prassi: finestra a due ante"),
    "portafinestra_altezza_m": (2.40, "prassi: porta finestra alta come la sommità delle finestre (1,00 + 1,40 m)"),
    "finestra_quota_davanzale_m": (1.00, "DM 236/1989, art. 8.1.3: parapetto complessivo di almeno 1,00 m"),
    "margine_rapporto_aeroilluminante": (1.10, "margine del 10% sul minimo di 1/8 (DM 5 luglio 1975, art. 5)"),
}


def carica_scheda(percorso: str | Path) -> dict:
    return yaml.safe_load(Path(percorso).read_text(encoding="utf-8"))


def _area(stanza: dict) -> float:
    return float(stanza["lunghezza_m"]) * float(stanza["larghezza_m"])


def completa(scheda: dict) -> dict:
    """Restituisce una copia della scheda con i valori mancanti riempiti e `ipotesi_applicate` aggiornata."""
    s = copy.deepcopy(scheda)
    ip: list[str] = list(s.get("ipotesi_applicate", []))
    if "edificio" in s:
        return _completa_edificio(s, ip)
    st = s.get("stanza")
    if not st:
        return s

    def imposta(d: dict, chiave: str, nome: str, valore=None, etichetta: str = ""):
        if d.get(chiave) is None:
            v, base = PREDEFINITI[nome] if valore is None else (valore, PREDEFINITI[nome][1])
            d[chiave] = v
            ip.append(f"{etichetta or chiave} = {v} m (predefinito; base: {base})")

    imposta(st, "altezza_m", "altezza_m", etichetta=f"{st.get('id', 'stanza')}: altezza")
    s.setdefault("intervento", "nuova")
    s.setdefault("destinazione", "abitazione")
    s.setdefault("comune", "Roma")

    pareti = st.setdefault("pareti", {})
    ha_finestra = {a.get("parete") for a in st.get("aperture", []) if a.get("tipo") in ("finestra", "portafinestra")}
    for nome in PARETI:
        p = pareti.setdefault(nome, {})
        if p.get("spessore_m") is None:
            chiave = "spessore_parete_con_finestra_m" if nome in ha_finestra else "spessore_parete_m"
            p["spessore_m"] = PREDEFINITI[chiave][0]
            ip.append(f"parete {nome}: spessore = {p['spessore_m']} m (predefinito; base: {PREDEFINITI[chiave][1]})")

    area = _area(st)
    conteggio = {}
    for a in st.get("aperture", []):
        if a.get("id") is None:  # nome unico e leggibile: diventa il nome dell'oggetto in Blender e in SketchUp
            tipo = a.get("tipo", "apertura").capitalize()
            conteggio[tipo] = conteggio.get(tipo, 0) + 1
            a["id"] = tipo if conteggio[tipo] == 1 else f"{tipo} {conteggio[tipo]}"
    for i, a in enumerate(st.get("aperture", [])):
        nome = a.get("id", f"apertura {i + 1}")
        if a.get("tipo") == "porta":
            imposta(a, "larghezza_m", "porta_luce_netta_m", etichetta=f"{nome}: luce netta")
            imposta(a, "altezza_m", "porta_altezza_m", etichetta=f"{nome}: altezza")
            imposta(a, "altezza_maniglia_m", "altezza_maniglia_m", etichetta=f"{nome}: altezza maniglia")
        elif a.get("tipo") == "portafinestra":
            a["quota_davanzale_m"] = 0.0                       # la porta finestra parte dal pavimento
            imposta(a, "altezza_m", "portafinestra_altezza_m", etichetta=f"{nome}: altezza")
            if a.get("larghezza_m") is None:
                raise ValueError(f"{nome}: la larghezza della porta finestra va indicata (larghezza_m)")
        elif a.get("tipo") == "finestra":
            imposta(a, "quota_davanzale_m", "finestra_quota_davanzale_m", etichetta=f"{nome}: quota davanzale")
            imposta(a, "altezza_m", "finestra_altezza_m", etichetta=f"{nome}: altezza")
            if a.get("larghezza_m") is None:
                minimo = area / 8.0 * PREDEFINITI["margine_rapporto_aeroilluminante"][0]
                larg = math.ceil(minimo / a["altezza_m"] / 0.05) * 0.05
                a["larghezza_m"] = round(larg, 2)
                ip.append(f"{nome}: larghezza = {a['larghezza_m']} m (calcolata per un rapporto aeroilluminante "
                          f"di almeno 1/8 con margine del 10%; base: DM 5 luglio 1975, art. 5)")
    for sp in st.get("arredi", []):   # decorazioni non lette dal disegno: vanno dichiarate
        if sp.get("tipo") == "mensola_portalibri":
            ip.append(f"{sp.get('id')}: libri generici (altezze e larghezze pseudo-casuali), non letti dal disegno")
        if sp.get("tipo") == "pensile_libri":
            for k, sc in enumerate(sp.get("scomparti", [])):
                tipo = sc.get("tipo") if isinstance(sc, dict) else sc
                if tipo == "libri" and not (isinstance(sc, dict) and sc.get("elementi")):
                    ip.append(f"{sp.get('id')}, scomparto {k + 1}: libri generici, non letti dal disegno")
    s["ipotesi_applicate"] = ip
    return s


def _completa_edificio(s: dict, ip: list[str]) -> dict:
    """Valori predefiniti per un edificio con più stanze e pareti a rete (le dichiara in `ipotesi_applicate`)."""
    s.setdefault("intervento", "nuova")
    s.setdefault("destinazione", "abitazione")
    s.setdefault("comune", "Roma")
    conteggio: dict[str, int] = {}
    for k, piano in enumerate(s["edificio"].get("piani", [])):
        nome_piano = piano.get("id", f"Piano {k + 1}")
        if piano.get("altezza_m") is None:
            piano["altezza_m"] = PREDEFINITI["altezza_m"][0]
            ip.append(f"{nome_piano}: altezza = {piano['altezza_m']} m (predefinito; base: {PREDEFINITI['altezza_m'][1]})")
        for w in piano.get("pareti", []):
            if w.get("spessore_m") is None:
                chiave = "spessore_parete_con_finestra_m" if w.get("tipo_parete") == "esterna" else "spessore_parete_m"
                w["spessore_m"] = PREDEFINITI[chiave][0]
                ip.append(f"parete {w['id']}: spessore = {w['spessore_m']} m (predefinito; base: {PREDEFINITI[chiave][1]})")
        for a in piano.get("aperture", []):
            if a.get("id") is None:
                tipo = a.get("tipo", "apertura").capitalize()
                conteggio[tipo] = conteggio.get(tipo, 0) + 1
                a["id"] = tipo if conteggio[tipo] == 1 else f"{tipo} {conteggio[tipo]}"
            nome = a["id"]
            if a.get("tipo") == "porta":
                for chiave, nm in (("larghezza_m", "porta_luce_netta_m"), ("altezza_m", "porta_altezza_m"),
                                   ("altezza_maniglia_m", "altezza_maniglia_m")):
                    if a.get(chiave) is None:
                        a[chiave] = PREDEFINITI[nm][0]
                        ip.append(f"{nome}: {chiave[:-2].replace('_', ' ')} = {a[chiave]} m (predefinito; base: {PREDEFINITI[nm][1]})")
            elif a.get("tipo") == "portafinestra":
                if a.get("larghezza_m") is None:
                    raise ValueError(f"{nome}: la larghezza della porta finestra va indicata (larghezza_m)")
                a["quota_davanzale_m"] = 0.0
                if a.get("altezza_m") is None:
                    a["altezza_m"] = PREDEFINITI["portafinestra_altezza_m"][0]
                    ip.append(f"{nome}: altezza = {a['altezza_m']} m (predefinito; base: {PREDEFINITI['portafinestra_altezza_m'][1]})")
            elif a.get("tipo") == "finestra":
                if a.get("larghezza_m") is None:
                    raise ValueError(f"{nome}: in un edificio la larghezza della finestra va indicata (larghezza_m)")
                for chiave, nm in (("quota_davanzale_m", "finestra_quota_davanzale_m"), ("altezza_m", "finestra_altezza_m")):
                    if a.get(chiave) is None:
                        a[chiave] = PREDEFINITI[nm][0]
                        ip.append(f"{nome}: {chiave[:-2].replace('_', ' ')} = {a[chiave]} m (predefinito; base: {PREDEFINITI[nm][1]})")
    s["ipotesi_applicate"] = ip
    return s


def a_locali(scheda: dict) -> dict:
    """Converte la scheda con `stanza` nel formato `locali` letto dal controllore delle norme."""
    s = copy.deepcopy(scheda)
    if "edificio" in s:
        from .nucleo.edificio import locali_da_edificio
        s["locali"] = locali_da_edificio(s)
        return s
    st = s.get("stanza")
    if not st:
        return s
    locale = {
        "id": st.get("id", "Stanza"),
        "tipo": st["tipo"],
        "superficie_m2": round(_area(st), 4),
        "altezza_m": st.get("altezza_m"),
        "finestre": [],
        "porte": [],
    }
    if st.get("alunni") is not None:
        locale["alunni"] = st["alunni"]
    for a in st.get("aperture", []):
        if a.get("tipo") in ("finestra", "portafinestra"):
            larg = a.get("larghezza_apribile_m", a["larghezza_m"])
            alt = a.get("altezza_apribile_m", a["altezza_m"])
            locale["finestre"].append({
                "id": a.get("id", "Finestra"),
                "larghezza_m": larg, "altezza_m": alt,
                "apribile": a.get("apribile", True),
                # porta finestra: il parapetto è quello del balcone, fuori dal modello
                "quota_davanzale_m": None if a.get("tipo") == "portafinestra" else a.get("quota_davanzale_m"),
            })
        elif a.get("tipo") == "porta":
            locale["porte"].append({
                "id": a.get("id", "Porta"),
                "luce_netta_m": a["larghezza_m"],
                "ingresso": bool(a.get("ingresso", False)),
                "altezza_maniglia_m": a.get("altezza_maniglia_m"),
            })
    s["locali"] = [locale]
    return s
