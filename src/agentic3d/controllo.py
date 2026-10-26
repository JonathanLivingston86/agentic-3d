"""Controllore delle regole italiane sulla scheda di un alloggio.

Legge le regole in `agentic3d/regole/*.yaml` e la scheda del progetto, e produce un rapporto con tre esiti:
PASS, FAIL, NON VERIFICABILE (dato mancante o verifica non automatizzabile). Le regole che non si
applicano al caso (per destinazione o intervento) sono segnate NON APPLICABILE.

Il controllo non sostituisce la responsabilità del tecnico abilitato.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .scheda import a_locali

PASS = "PASS"
FAIL = "FAIL"
NON_VERIFICABILE = "NON VERIFICABILE"
NON_APPLICABILE = "NON APPLICABILE"

AVVISO = (
    "Questo rapporto non sostituisce la responsabilità del tecnico abilitato. "
    "Le norme comunali (regolamento edilizio, NTA, regolamento d'igiene) non sono verificate."
)

CARTELLA_REGOLE = Path(__file__).resolve().parent / "regole"


@dataclass
class Esito:
    regola: str
    titolo: str
    oggetto: str
    esito: str
    dettaglio: str
    fonte: str = ""


@dataclass
class Rapporto:
    esiti: list[Esito] = field(default_factory=list)
    note: list[str] = field(default_factory=list)
    ipotesi: list[str] = field(default_factory=list)

    def conteggio(self) -> dict[str, int]:
        c = {PASS: 0, FAIL: 0, NON_VERIFICABILE: 0, NON_APPLICABILE: 0}
        for e in self.esiti:
            c[e.esito] += 1
        return c

    @property
    def ok(self) -> bool:
        return self.conteggio()[FAIL] == 0

    def testo(self) -> str:
        righe = []
        c = self.conteggio()
        righe.append(
            f"Esito: {c[PASS]} PASS, {c[FAIL]} FAIL, {c[NON_VERIFICABILE]} NON VERIFICABILE, "
            f"{c[NON_APPLICABILE]} NON APPLICABILE"
        )
        for nome in (FAIL, NON_VERIFICABILE, PASS):
            gruppo = [e for e in self.esiti if e.esito == nome]
            if not gruppo:
                continue
            righe.append(f"\n{nome}")
            for e in gruppo:
                righe.append(f"- [{e.regola}] {e.oggetto}: {e.dettaglio}")
                if e.fonte and nome != PASS:
                    righe.append(f"    fonte: {e.fonte}")
        if self.ipotesi:
            righe.append("\nIpotesi usate (valori non presenti nella scheda)")
            righe += [f"- {i}" for i in self.ipotesi]
        if self.note:
            righe.append("\nNote")
            righe += [f"- {n}" for n in self.note]
        righe.append(f"\nAvviso: {AVVISO}")
        return "\n".join(righe)


# ---------------------------------------------------------------- caricamento

def carica_regole(cartella: Path | None = None) -> tuple[list[dict], list[dict]]:
    """Restituisce (regole automatiche, regole non automatizzate) da tutti i file YAML."""
    cartella = cartella or CARTELLA_REGOLE
    regole: list[dict] = []
    manuali: list[dict] = []
    for p in sorted(cartella.glob("*.yaml")):
        dati = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        regole += dati.get("regole", [])
        manuali += dati.get("non_automatizzate", [])
    return regole, manuali


def carica_scheda(percorso: Path) -> dict:
    return yaml.safe_load(Path(percorso).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ quantità

def _area_poligono(punti: list[list[float]]) -> float:
    s = 0.0
    for i, (x1, y1) in enumerate(punti):
        x2, y2 = punti[(i + 1) % len(punti)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def superficie(locale: dict) -> float | None:
    if locale.get("superficie_m2") is not None:
        return float(locale["superficie_m2"])
    if locale.get("poligono_m"):
        return _area_poligono(locale["poligono_m"])
    return None


def _finestra_apribile_m2(f: dict) -> float:
    return float(f["larghezza_m"]) * float(f["altezza_m"]) * float(f.get("quota_apribile", 1.0))


def quantita_locale(locale: dict, nome: str) -> Any:
    """Valore della grandezza per un locale, oppure None se il dato manca."""
    if nome == "altezza_m":
        return locale.get("altezza_m")
    if nome == "superficie_m2":
        return superficie(locale)
    if nome == "larghezza_m":
        return locale.get("larghezza_m")
    if nome == "superficie_per_alunno_m2":
        s, alunni = superficie(locale), locale.get("alunni")
        return None if s is None or not alunni else s / float(alunni)
    if nome == "finestra_apribile_presente":
        if "finestre" not in locale:
            return None
        return any(f.get("apribile", True) for f in locale["finestre"])
    if nome == "rapporto_aeroilluminante":
        s = superficie(locale)
        if s is None or "finestre" not in locale:
            return None
        apribile = sum(_finestra_apribile_m2(f) for f in locale["finestre"] if f.get("apribile", True))
        return apribile / s
    if nome == "bagno_ventilato":
        if "finestre" not in locale and "aspirazione_meccanica" not in locale:
            return None
        con_finestra = any(f.get("apribile", True) for f in locale.get("finestre", []))
        return bool(con_finestra or locale.get("aspirazione_meccanica"))
    return None


def quantita_elemento(el: dict, nome: str) -> Any:
    if nome == "due_alzate_piu_pedata_m":
        if "alzata_m" in el and "pedata_m" in el:
            return 2 * float(el["alzata_m"]) + float(el["pedata_m"])
        return None
    return el.get(nome)


# ------------------------------------------------------------------- confronto

def _confronta(valore: Any, operatore: str, soglia: Any, tolleranza: float = 0.0) -> bool:
    if operatore == ">=":
        return valore >= soglia - 1e-9
    if operatore == "<=":
        return valore <= soglia + 1e-9
    if operatore == "==":
        if isinstance(soglia, bool):
            return bool(valore) == soglia
        return abs(float(valore) - float(soglia)) <= tolleranza + 1e-9
    if operatore == "tra":
        return soglia[0] - 1e-9 <= valore <= soglia[1] + 1e-9
    raise ValueError(f"operatore sconosciuto: {operatore}")


def _descrivi_soglia(operatore: str, soglia: Any) -> str:
    if operatore == "tra":
        return f"tra {soglia[0]} e {soglia[1]}"
    if operatore == "==" and isinstance(soglia, bool):
        return "sì" if soglia else "no"
    return f"{operatore} {soglia}"


def _fonte(regola: dict) -> str:
    f = regola.get("fonte", {})
    return f"{f.get('atto', '?')}, {f.get('articolo', '?')}"


def _condizione_deroga(cond: dict, progetto: dict) -> tuple[bool | None, bool]:
    """(esito, dichiarata): esito True se soddisfatta, False se smentita, None se mancano dati.

    `dichiarata` è True quando la scheda afferma esplicitamente almeno una condizione della deroga
    (esempio: `asseverazione_salva_casa: true`). Un dato mancante non fa scattare la deroga:
    lettura prudente. Se la deroga è dichiarata ma incompleta il rapporto dice NON VERIFICABILE.
    """
    incompleto = False
    dichiarata = False
    for chiave, atteso in cond.items():
        if chiave == "intervento":
            if progetto.get("intervento") not in atteso:
                return False, False
            continue
        valore = progetto.get("altitudine_m") if chiave == "altitudine_m_minima" else progetto.get(chiave)
        if valore is None:
            incompleto = True
            continue
        if chiave == "altitudine_m_minima":
            if valore < atteso:
                return False, False
            dichiarata = True
        elif valore != atteso:
            return False, False
        else:
            dichiarata = True
    return (None if incompleto else True), dichiarata


def _valore_con_deroga(regola: dict, progetto: dict) -> tuple[Any, str, bool]:
    """Soglia effettiva, nota sulla deroga, e se una deroga dichiarata resta non confermata."""
    soglia = regola["valore"]
    nota = ""
    in_dubbio = False
    for d in regola.get("deroghe", []):
        esito, dichiarata = _condizione_deroga(d["condizione"], progetto)
        if esito is True:
            soglia = d["valore"]
            nota = f" (deroga {d['id']}: {soglia})"
            in_dubbio = False
            break
        if esito is None and dichiarata:
            in_dubbio = True
    return soglia, nota, in_dubbio


# --------------------------------------------------------------------- controllo

def _si_applica(regola: dict, progetto: dict) -> bool:
    if progetto.get("destinazione", "abitazione") not in regola.get("destinazione", ["abitazione"]):
        return False
    return progetto.get("intervento", "nuova") in regola.get("interventi", [progetto.get("intervento", "nuova")])


def controlla(progetto: dict, regole: list[dict] | None = None, manuali: list[dict] | None = None) -> Rapporto:
    if regole is None or manuali is None:
        r, m = carica_regole()
        regole = regole if regole is not None else r
        manuali = manuali if manuali is not None else m
    if "stanza" in progetto or "edificio" in progetto:
        progetto = a_locali(progetto)
    rapporto = Rapporto(ipotesi=list(progetto.get("ipotesi_applicate", [])))
    if progetto.get("intervento") == "esistente":
        rapporto.note.append(
            "Intervento su immobile esistente: i requisiti del DM 5 luglio 1975 sono riportati come riferimento; "
            "per un immobile legittimamente realizzato il tecnico verifica quali si applicano (diritti acquisiti). "
            "Le regole del DM 236/1989 sono NON APPLICABILI senza ristrutturazione.")
    rapporto.note += list(progetto.get("note_verifica", []))

    for regola in regole:
        if not _si_applica(regola, progetto):
            rapporto.esiti.append(Esito(regola["id"], regola["titolo"], "progetto", NON_APPLICABILE,
                                        "destinazione o tipo di intervento fuori dal campo della regola", _fonte(regola)))
            continue
        if regola.get("avvertenza") and regola["avvertenza"] not in rapporto.note:
            rapporto.note.append(regola["avvertenza"])
        if "locali" in regola:
            for locale in progetto.get("locali", []):
                if locale.get("tipo") in regola["locali"]:
                    rapporto.esiti.append(_valuta(regola, progetto, locale, locale.get("id", locale["tipo"]),
                                                  quantita_locale(locale, regola["grandezza"])))
        elif "elemento" in regola:
            trovato = False
            for locale in progetto.get("locali", []):
                for el in _elementi(locale, regola["elemento"]):
                    trovato = True
                    nome = f"{locale.get('id', locale['tipo'])} / {el.get('id', regola['elemento'])}"
                    rapporto.esiti.append(_valuta(regola, progetto, el, nome,
                                                  quantita_elemento(el, regola["grandezza"])))
            for el in _elementi(progetto, regola["elemento"]):
                trovato = True
                rapporto.esiti.append(_valuta(regola, progetto, el, el.get("id", regola["elemento"]),
                                              quantita_elemento(el, regola["grandezza"])))
            if not trovato:
                continue

    for m in manuali:
        if progetto.get("destinazione", "abitazione") not in m.get("destinazione", ["abitazione"]):
            rapporto.esiti.append(Esito(m["id"], m["titolo"], "progetto", NON_APPLICABILE,
                                        "destinazione fuori dal campo della verifica", _fonte(m)))
            continue
        rapporto.esiti.append(Esito(m["id"], m["titolo"], "progetto", NON_VERIFICABILE,
                                    f"verifica non automatizzata: {m['motivo']}", _fonte(m)))
    return rapporto


def _elementi(contenitore: dict, tipo: str) -> list[dict]:
    """Porte, parapetti, scale e lavabi di un locale o del progetto."""
    if tipo in ("porta_ingresso", "porta_interna", "porta"):
        out = []
        for p in contenitore.get("porte", []):
            ingresso = bool(p.get("ingresso", False))
            if tipo == "porta" or (tipo == "porta_ingresso") == ingresso:
                out.append(p)
        return out
    if tipo == "parapetto":
        return contenitore.get("parapetti", [])
    if tipo == "lavabo":
        return contenitore.get("lavabi", [])
    if tipo == "finestra":
        return contenitore.get("finestre", [])
    if tipo in ("scala_privata", "scala_comune"):
        uso = "privata" if tipo == "scala_privata" else "comune"
        return [s for s in contenitore.get("scale", []) if s.get("uso", "privata") == uso]
    return []


def _valuta(regola: dict, progetto: dict, _soggetto: dict, oggetto: str, valore: Any) -> Esito:
    e = _valuta_base(regola, progetto, _soggetto, oggetto, valore)
    if regola.get("nota") and e.esito in (FAIL, NON_VERIFICABILE):
        e.dettaglio += f". Nota: {regola['nota']}"
    return e


def _valuta_base(regola: dict, progetto: dict, _soggetto: dict, oggetto: str, valore: Any) -> Esito:
    base = (regola["id"], regola["titolo"], oggetto)
    fonte = _fonte(regola)
    if valore is None:
        return Esito(*base, NON_VERIFICABILE, f"dato mancante per `{regola['grandezza']}`", fonte)
    soglia, nota, in_dubbio = _valore_con_deroga(regola, progetto)
    tol = regola.get("tolleranza", 0.0)
    if _confronta(valore, regola["operatore"], soglia, tol):
        return Esito(*base, PASS, f"{_fmt(valore)} {_descrivi_soglia(regola['operatore'], soglia)}{nota}", fonte)
    if in_dubbio:
        return Esito(*base, NON_VERIFICABILE,
                     f"{_fmt(valore)} non rispetta {_descrivi_soglia(regola['operatore'], soglia)}; "
                     "una deroga potrebbe applicarsi ma le condizioni non sono tutte confermate nella scheda",
                     fonte)
    return Esito(*base, FAIL, f"{_fmt(valore)} non rispetta {_descrivi_soglia(regola['operatore'], soglia)}", fonte)


def _fmt(v: Any) -> str:
    if isinstance(v, bool):
        return "sì" if v else "no"
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)
