"""Galleria dei render: una pagina HTML nella cartella Render che si riempie mentre Blender lavora.

La pagina non si ricarica (niente lampeggio): durante il render legge ogni 1,5 secondi un piccolo file di dati
(`Galleria dei render (dati).js`, caricato come script perché funziona anche aperto dal disco, senza server) e
aggiunge solo le immagini nuove, ciascuna con una sola dissolvenza. Un clic su un'immagine apre un lightbox con le
frecce per scorrere le viste (anche con i tasti freccia; Esc chiude). A fine render i dati entrano nella pagina e il
file dei dati si cancella: nella cartella resta solo la pagina, che fa da indice delle viste.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import quote

NOME_FILE = "Galleria dei render.html"
NOME_DATI = "Galleria dei render (dati).js"
RITARDO_PULIZIA = 4.0      # secondi: la pagina aperta legge la fine del render prima che il file dei dati sparisca


def percorso(cartella_render: Path) -> Path:
    return Path(cartella_render) / NOME_FILE


def _dati(cartella: Path, lavoro: str, viste: list[str], fatte: dict[str, float], stima: str, finito: bool,
          errore: str | None) -> dict:
    voci = []
    for v in viste:
        img = cartella / f"{v}.png"
        pronta = v in fatte and img.exists()
        voci.append({"nome": v, "secondi": round(fatte[v]) if v in fatte else None,
                     "src": f"{quote(img.name)}?v={img.stat().st_mtime_ns}" if pronta else None})
    n = sum(1 for v in voci if v["src"])
    if errore:
        stato = f"Render interrotto: {errore}"
    elif finito:
        stato = f"Render completato: {n} viste in {sum(fatte.values()) / 60:.1f} minuti."
    else:
        stato = f"Vista {min(n + 1, len(viste))} di {len(viste)} in lavorazione, {stima}."
    return {"lavoro": lavoro, "viste": voci, "stato": stato, "errore": bool(errore), "finito": finito,
            "percento": round(100 * n / len(viste)) if viste else 100}


def _scrivi_atomico(destinazione: Path, testo: str) -> None:
    provvisorio = destinazione.with_name(destinazione.name + ".tmp")
    provvisorio.write_text(testo, encoding="utf-8")
    try:
        os.replace(provvisorio, destinazione)
    except PermissionError:          # Windows: file in lettura proprio ora; si scrive direttamente
        destinazione.write_text(testo, encoding="utf-8")
        provvisorio.unlink(missing_ok=True)


def scrivi(cartella_render: Path, lavoro: str, viste: list[str], fatte: dict[str, float], stima: str,
           finito: bool = False, errore: str | None = None) -> Path:
    """Aggiorna i dati (e la pagina) della galleria. A fine render i dati vanno dentro la pagina."""
    cartella = Path(cartella_render)
    cartella.mkdir(parents=True, exist_ok=True)
    dati = json.dumps(_dati(cartella, lavoro, viste, fatte, stima, finito or bool(errore), errore), ensure_ascii=False)
    file_dati = cartella / NOME_DATI
    pagina = percorso(cartella)
    if finito or errore:
        # la pagina già aperta legge ancora il file dei dati: vi trova la fine e smette di chiedere; il file si
        # cancella poco dopo, la pagina riaperta usa i dati scritti dentro di sé
        _scrivi_atomico(file_dati, f"window.aggiornaGalleria({dati});\n")
        _scrivi_atomico(pagina, PAGINA.replace("/*DATI*/null", dati))
        import threading
        threading.Timer(RITARDO_PULIZIA, lambda: file_dati.unlink(missing_ok=True)).start()
    else:
        _scrivi_atomico(file_dati, f"window.aggiornaGalleria({dati});\n")
        if not pagina.exists() or "/*DATI*/null" not in pagina.read_text(encoding="utf-8"):
            _scrivi_atomico(pagina, PAGINA)
    return pagina


PAGINA = """<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<title>Render</title>
<style>
:root { color-scheme: light dark; --fondo:#f6f5f2; --carta:#fff; --testo:#1d1d1b; --tenue:#77756f; --accento:#2f6f5e; }
@media (prefers-color-scheme: dark) { :root { --fondo:#1b1b1a; --carta:#262624; --testo:#ecebe6; --tenue:#9a988f; --accento:#6fb59f; } }
* { box-sizing:border-box; }
body { margin:0; padding:32px clamp(16px,4vw,48px); background:var(--fondo); color:var(--testo);
       font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }
header { max-width:1400px; margin:0 auto 24px; }
h1 { font-size:22px; font-weight:600; margin:0 0 4px; }
#stato { margin:4px 0 12px; color:var(--tenue); }
#stato.errore { color:#b3261e; }
.barra { height:6px; background:color-mix(in srgb,var(--tenue) 25%,transparent); border-radius:3px; overflow:hidden; }
#avanzamento { height:100%; width:0; background:var(--accento); transition:width .4s; }
main { max-width:1400px; margin:0 auto; display:grid; gap:20px; grid-template-columns:repeat(auto-fill,minmax(380px,1fr)); }
figure { margin:0; background:var(--carta); border-radius:10px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,.08); }
.immagine { aspect-ratio:16/9; position:relative; }
.immagine img { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; cursor:zoom-in;
                opacity:0; transition:opacity .6s ease-out; }
.immagine img.vista { opacity:1; }
.vuoto { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; color:var(--tenue); }
.vuoto p { margin:10px 0 0; font-size:13px; }
.segno { width:26px; height:26px; border-radius:50%; border:3px solid color-mix(in srgb,var(--tenue) 30%,transparent); }
.in-corso .segno { border-top-color:var(--accento); animation:gira 1s linear infinite; }
@keyframes gira { to { transform:rotate(360deg); } }
figcaption { display:flex; justify-content:space-between; padding:10px 14px; font-weight:500; }
figcaption small { color:var(--tenue); font-weight:400; }
#lightbox { position:fixed; inset:0; background:rgba(10,10,10,.92); display:none; align-items:center; justify-content:center; z-index:9; }
#lightbox.aperto { display:flex; }
#lightbox img { max-width:92vw; max-height:84vh; box-shadow:0 8px 40px rgba(0,0,0,.5); }
#didascalia { position:absolute; bottom:22px; left:0; right:0; text-align:center; color:#eee; }
#lightbox button { position:absolute; background:rgba(255,255,255,.12); color:#fff; border:0; border-radius:50%;
                   width:52px; height:52px; font-size:26px; cursor:pointer; }
#lightbox button:hover { background:rgba(255,255,255,.25); }
#prima { left:24px; } #dopo { right:24px; } #chiudi { top:20px; right:24px; font-size:22px; }
</style></head>
<body>
<header><h1 id="titolo">Render</h1><p id="stato">In attesa di Blender...</p><div class="barra"><div id="avanzamento"></div></div></header>
<main id="griglia"></main>
<div id="lightbox" role="dialog" aria-modal="true">
  <button id="chiudi" aria-label="Chiudi">&#x2715;</button>
  <button id="prima" aria-label="Vista precedente">&#x2039;</button>
  <img id="grande" alt="">
  <button id="dopo" aria-label="Vista successiva">&#x203A;</button>
  <div id="didascalia"></div>
</div>
<script>
const DATI_INIZIALI = /*DATI*/null;
const FILE_DATI = "Galleria dei render (dati).js";
const schede = {};
let ultimi = null, indice = -1, attesa = null;

function scheda(nome) {
  if (schede[nome]) return schede[nome];
  const f = document.createElement("figure");
  f.innerHTML = '<div class="immagine"><div class="vuoto"><div class="segno"></div><p>in attesa</p></div></div>' +
                '<figcaption><span></span><small></small></figcaption>';
  f.querySelector("span").textContent = nome;
  document.getElementById("griglia").appendChild(f);
  return schede[nome] = f;
}

window.aggiornaGalleria = function (d) {
  ultimi = d;
  document.title = (d.finito ? "" : "(" + d.viste.filter(v => v.src).length + "/" + d.viste.length + ") ") + "Render: " + d.lavoro;
  document.getElementById("titolo").textContent = d.lavoro;
  const stato = document.getElementById("stato");
  stato.textContent = d.stato; stato.className = d.errore ? "errore" : "";
  document.getElementById("avanzamento").style.width = d.percento + "%";
  const prossima = d.finito ? null : d.viste.find(v => !v.src);
  d.viste.forEach(v => {
    const f = scheda(v.nome);
    const box = f.querySelector(".immagine");
    let img = box.querySelector("img");
    if (v.src && (!img || img.dataset.src !== v.src)) {           // solo le immagini nuove o rifatte
      if (!img) { img = document.createElement("img"); box.appendChild(img); }
      img.dataset.src = v.src; img.alt = v.nome;
      img.onload = () => { img.classList.add("vista"); const vuoto = box.querySelector(".vuoto"); if (vuoto) vuoto.remove(); };
      img.onclick = () => apri(v.nome);
      img.src = v.src;
      f.querySelector("small").textContent = v.secondi + " s";
    }
    const vuoto = box.querySelector(".vuoto");
    if (vuoto) {
      const inCorso = prossima && prossima.nome === v.nome;
      f.className = inCorso ? "in-corso" : "";
      vuoto.querySelector("p").textContent = inCorso ? "in lavorazione" : "in attesa";
    }
  });
  if (d.finito && attesa) { clearInterval(attesa); attesa = null; }
};

function chiedi() {                                              // nuovi dati senza ricaricare la pagina
  const vecchio = document.getElementById("dati");
  if (vecchio) vecchio.remove();
  const s = document.createElement("script");
  s.id = "dati"; s.src = encodeURI(FILE_DATI) + "?t=" + Date.now();
  document.body.appendChild(s);
}

function pronte() { return ultimi ? ultimi.viste.filter(v => v.src) : []; }
function mostra() {
  const p = pronte(); if (!p.length) return;
  indice = (indice + p.length) % p.length;
  document.getElementById("grande").src = p[indice].src;
  document.getElementById("didascalia").textContent = p[indice].nome + "  (" + (indice + 1) + " / " + p.length + ")";
  const piu = p.length > 1;
  document.getElementById("prima").style.display = piu ? "" : "none";
  document.getElementById("dopo").style.display = piu ? "" : "none";
}
function apri(nome) { indice = pronte().findIndex(v => v.nome === nome); document.getElementById("lightbox").classList.add("aperto"); mostra(); }
function chiudi() { document.getElementById("lightbox").classList.remove("aperto"); }
document.getElementById("prima").onclick = e => { e.stopPropagation(); indice--; mostra(); };
document.getElementById("dopo").onclick = e => { e.stopPropagation(); indice++; mostra(); };
document.getElementById("chiudi").onclick = chiudi;
document.getElementById("lightbox").onclick = e => { if (e.target.id === "lightbox") chiudi(); };
document.addEventListener("keydown", e => {
  if (!document.getElementById("lightbox").classList.contains("aperto")) return;
  if (e.key === "Escape") chiudi();
  if (e.key === "ArrowLeft") { indice--; mostra(); }
  if (e.key === "ArrowRight") { indice++; mostra(); }
});

if (DATI_INIZIALI) { window.aggiornaGalleria(DATI_INIZIALI); }
else { chiedi(); attesa = setInterval(chiedi, 1500); }
</script>
</body></html>
"""
