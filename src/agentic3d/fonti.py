"""Strumento per le fonti delle norme: legge un testo ufficiale, cerca i passi, controlla le regole in dati.

Una regola in `agentic3d/regole/*.yaml` può portare nella sua `fonte`:
  url:       dove si legge il testo (pagina HTML o PDF)
  estratto:  il passo, copiato alla lettera dal testo, da cui viene il valore
La verifica controlla che (1) il valore della regola compaia nell'estratto e (2) con `--online` che l'estratto compaia
davvero nel testo della fonte. Così un numero non può più restare in una regola senza una frase che lo giustifica.

    python -m agentic3d fonte cerca <url|file> "<testo o espressione>" [--contesto 250]
    python -m agentic3d fonte verifica [--online]
"""

from __future__ import annotations

import html
import re
import sys
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from .controllo import carica_regole


@dataclass
class FonteTesto:
    origine: str
    contenuto: str                  # testo normalizzato (spazi uniti)
    pagine: list[int]               # posizione dell'inizio di ogni pagina nel contenuto (solo PDF)

    def pagina_di(self, posizione: int) -> int | None:
        if not self.pagine:
            return None
        n = 0
        for k, inizio in enumerate(self.pagine):
            if inizio <= posizione:
                n = k + 1
        return n


def normalizza(t: str) -> str:
    """Spazi uniti, trattini di sillabazione a fine riga tolti, caratteri tipografici resi semplici."""
    t = t.replace(" ", " ").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = t.replace("–", "-").replace("−", "-")
    t = re.sub(r"(?<=[a-zàèéìòù])-\s*\n\s*(?=[a-zàèéìòù])", "", t)       # "abita-\nbili" -> "abitabili"
    return re.sub(r"\s+", " ", t).strip()


class _TestoDaHtml(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parti: list[str] = []
        self._salta = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._salta += 1
        if tag in ("p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4"):
            self.parti.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._salta:
            self._salta -= 1

    def handle_data(self, dati):
        if not self._salta:
            self.parti.append(dati)


def da_byte(dati: bytes, origine: str = "") -> FonteTesto:
    if dati[:5] == b"%PDF-":
        import pymupdf
        doc = pymupdf.open(stream=dati, filetype="pdf")
        pezzi, inizi, pos = [], [], 0
        for pagina in doc:
            t = normalizza(pagina.get_text())
            inizi.append(pos)
            pezzi.append(t)
            pos += len(t) + 1
        return FonteTesto(origine, " ".join(pezzi), inizi)
    for codifica in ("utf-8", "cp1252", "latin-1"):
        try:
            testo = dati.decode(codifica)
            break
        except UnicodeDecodeError:
            continue
    if "<html" in testo[:2000].lower() or "<body" in testo[:5000].lower():
        p = _TestoDaHtml()
        p.feed(testo)
        testo = html.unescape("".join(p.parti))
    return FonteTesto(origine, normalizza(testo), [])


def leggi_testo(origine: str | Path, timeout: float = 40.0) -> FonteTesto:
    """Legge un file locale o scarica un indirizzo (HTML o PDF) e ne ricava il testo normalizzato."""
    s = str(origine)
    if s.startswith(("http://", "https://")):
        richiesta = urllib.request.Request(s, headers={"User-Agent": "Mozilla/5.0 (agentic3d fonti)"})
        with urllib.request.urlopen(richiesta, timeout=timeout) as r:
            return da_byte(r.read(), s)
    return da_byte(Path(s).read_bytes(), s)


def cerca(testo: FonteTesto, schema: str, contesto: int = 200, massimo: int = 12) -> list[dict]:
    """Passi del testo che contengono `schema` (espressione regolare, senza distinguere maiuscole)."""
    out = []
    for m in re.finditer(schema, testo.contenuto, flags=re.IGNORECASE):
        a, b = max(0, m.start() - contesto), min(len(testo.contenuto), m.end() + contesto)
        out.append({"posizione": m.start(), "pagina": testo.pagina_di(m.start()), "passo": testo.contenuto[a:b]})
        if len(out) >= massimo:
            break
    return out


# ------------------------------------------------------------------ verifica delle regole
def varianti_del_valore(valore) -> list[str]:
    """Modi in cui un valore numerico può essere scritto in un testo italiano: 2,70 2.70 270 (centimetri)."""
    if isinstance(valore, bool) or valore is None:
        return []
    if isinstance(valore, (list, tuple)):
        return [v for x in valore for v in varianti_del_valore(x)]
    x = float(valore)
    candidati = {f"{x:.2f}", f"{x:.1f}", f"{x:g}", f"{x:.3f}"}
    candidati |= {f"{x * 100:.0f}", f"{x * 100:g}"}
    return sorted({c.replace(".", ",") for c in candidati} | candidati)


def _contiene_valore(estratto_norm: str, valore) -> bool:
    for v in varianti_del_valore(valore):
        if re.search(r"(?<![\d,.])" + re.escape(v) + r"(?![\d])", estratto_norm):
            return True
    return False


def _fonti_di(regola: dict):
    yield regola["id"], regola["fonte"], regola.get("valore"), regola.get("valori_nel_testo")
    for d in regola.get("deroghe", []):
        yield f"{regola['id']} (deroga {d['id']})", d["fonte"], d.get("valore"), d.get("valori_nel_testo")


def verifica_regole(regole: list[dict], manuali: list[dict], online: bool = False, leggi=leggi_testo) -> dict:
    """Esito del controllo delle fonti: `problemi` (da correggere), `senza_estratto` (da riscontrare), `ok`."""
    problemi, senza, ok = [], [], []
    cache: dict[str, FonteTesto | None] = {}
    for regola in list(regole) + list(manuali):
        for nome, fonte, valore, esplicito in _fonti_di(regola):
            estratto = fonte.get("estratto")
            if not estratto:
                senza.append(nome)
                continue
            norm = normalizza(estratto)
            attesi = esplicito if esplicito is not None else valore
            if esplicito is not None:
                trovato = all(normalizza(str(a)) in norm for a in esplicito)
            elif attesi is None or isinstance(attesi, bool):
                trovato = True
            else:
                trovato = _contiene_valore(norm, attesi)
            if not trovato:
                problemi.append(f"{nome}: il valore {attesi!r} non compare nell'estratto")
                continue
            if online and fonte.get("url"):
                url = fonte["url"]
                if url not in cache:
                    try:
                        cache[url] = leggi(url)
                    except Exception as e:                     # rete, pagina spostata...
                        cache[url] = None
                        problemi.append(f"{nome}: fonte non raggiungibile ({url}): {e}")
                t = cache[url]
                if t is not None and norm not in t.contenuto:
                    problemi.append(f"{nome}: l'estratto non compare nel testo di {url}")
                    continue
            ok.append(nome)
    return {"problemi": problemi, "senza_estratto": senza, "ok": ok}


def main(argv: list[str]) -> int:
    if len(argv) >= 4 and argv[1] == "cerca":
        opz = argv[4:]
        contesto = int(opz[opz.index("--contesto") + 1]) if "--contesto" in opz else 200
        try:
            t = leggi_testo(argv[2])
        except Exception as e:                                   # rete, indirizzo errato, file mancante
            print(f"Errore: non riesco a leggere {argv[2]}: {e}")
            return 1
        trovati = cerca(t, argv[3], contesto)
        print(f"{len(t.contenuto)} caratteri letti da {argv[2]}; {len(trovati)} passi")
        for r in trovati:
            pag = f" (pagina {r['pagina']})" if r["pagina"] else ""
            print(f"\n--- posizione {r['posizione']}{pag}\n{r['passo']}")
        return 0
    if len(argv) >= 2 and argv[1] == "verifica":
        regole, manuali = carica_regole()
        esito = verifica_regole(regole, manuali, online="--online" in argv)
        print(f"{len(esito['ok'])} fonti riscontrate, {len(esito['senza_estratto'])} senza estratto, "
              f"{len(esito['problemi'])} problemi")
        for p in esito["problemi"]:
            print("PROBLEMA:", p)
        for s in esito["senza_estratto"]:
            print("senza estratto:", s)
        return 1 if esito["problemi"] else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
