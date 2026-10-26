"""Uso (`agentic3d ...`, oppure `python -m agentic3d ...` dai sorgenti):
  agentic3d nuovo  "<Nome>" [--tipo stanza|edificio] [--esempio "<esempio>"] [--disegno file ...]   (crea un lavoro)
  agentic3d esempi                           (schede complete da cui partire)
  agentic3d chiudi "<Nome>"                  (riordina: Cestino per gli eccessi, svuota i temporanei)
  agentic3d controlla  "<Nome>" | "<scheda>.yaml"
  agentic3d costruisci "<Nome>" | "<scheda>.yaml" [--render] [--esporta] [--solo-script] [--senza-galleria] [--motore nucleo|classico]
  agentic3d importa "<Nome>" disegno.dxf [--livello-muri <livello>]   (scheda e tavola di lettura dal DXF)
  agentic3d tavola "<Nome>"                (tavola di lettura dalla scheda, da confermare prima di costruire)
  agentic3d impostazioni [lavori|temporanei|blender <percorso>]   (dove stanno lavori, temporanei e Blender)
  agentic3d impostazioni dopo_render automatico|apri|chiudi      (aprire il modello in Blender dopo i render)
  agentic3d informazioni                     (versione e crediti)
  agentic3d verifica                         (controlla l'installazione e dice come riparare)
  agentic3d installa-estensione              (copia l'estensione in ogni SketchUp trovato)
  agentic3d mcp                              (server MCP per gli agenti, trasporto stdio)
  agentic3d collega [--prova] | scollega     (Skill e server MCP negli agenti installati; --prova non scrive)
  agentic3d estensione-sketchup [cartella]   (crea "Agentic 3D per SketchUp.rbz")
  agentic3d blender avvia | chiudi | stato    (Blender con il ponte, senza finestre di terminale)
  agentic3d fonte cerca <url|file> "<testo>" | fonte verifica [--online]   (fonti delle norme)

`--render` produce le viste e il file di Blender: Blender lavora senza finestra e si chiude da solo, l'avanzamento
compare riga per riga e una galleria nel browser mostra le immagini appena pronte (`--senza-galleria` per non aprirla).
Poi il modello si apre in Blender secondo `dopo_render` (con `--tieni-blender` sempre).
`--esporta` scrive in `Esportazioni` il GLB e il file "per SketchUp.json" (estensione che si aggiorna da sola);
non ha bisogno di Blender.
"""

import sys
from pathlib import Path

from .controllo import controlla
from .costruttore import costruisci
from .scheda import carica_scheda, completa


def main(argv: list[str]) -> int:
    for flusso in (sys.stdout, sys.stderr):          # accenti e lettere greche anche nella console di Windows
        try:
            flusso.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if len(argv) >= 3 and argv[1] in ("nuovo", "chiudi"):
        from .ciclo import chiudi, nuovo
        try:
            if argv[1] == "nuovo":
                opz = argv[3:]
                tipo = opz[opz.index("--tipo") + 1] if "--tipo" in opz else "stanza"
                disegni = []
                if "--disegno" in opz:
                    k = opz.index("--disegno") + 1
                    while k < len(opz) and not opz[k].startswith("--"):
                        disegni.append(opz[k])
                        k += 1
                esempio = opz[opz.index("--esempio") + 1] if "--esempio" in opz else None
                righe = nuovo(argv[2], tipo, disegni, esempio=esempio)
            else:
                righe = chiudi(argv[2])
        except (ValueError, FileExistsError, FileNotFoundError) as e:
            print("Errore:", e)
            return 1
        print("\n".join(righe))
        return 0
    if len(argv) >= 4 and argv[1] == "importa":
        from .configurazione import cartella_temporanea
        from .importa import importa_disegno
        livello = argv[argv.index("--livello-muri") + 1] if "--livello-muri" in argv else None
        try:
            print(importa_disegno(trova_scheda(argv[2]).parent, argv[3], livello, cartella_temporanea()))
        except (ValueError, FileNotFoundError) as e:
            print("Errore:", e)
            return 1
        return 0
    if len(argv) >= 3 and argv[1] == "tavola":
        from .importa import tavola_di_lettura
        print("Tavola:", tavola_di_lettura(trova_scheda(argv[2]).parent))
        return 0
    if len(argv) >= 2 and argv[1] == "blender":
        from .blender.ponte import main as main_blender
        return main_blender(argv)
    if len(argv) >= 2 and argv[1] == "fonte":
        from .fonti import main as main_fonti
        return main_fonti(argv[1:])
    if len(argv) >= 2 and argv[1] == "mcp":
        from .server_mcp import avvia
        avvia()
        return 0
    if len(argv) >= 2 and argv[1] in ("collega", "scollega"):
        from .collegamenti import Contesto, collega, scollega
        ctx = Contesto(prova="--prova" in argv)
        print("\n".join(collega(ctx) if argv[1] == "collega" else scollega(ctx)))
        return 0
    if len(argv) >= 2 and argv[1] == "verifica":
        from .installazione import verifica_installazione
        print(verifica_installazione())
        return 0
    if len(argv) >= 2 and argv[1] == "installa-estensione":
        from .installazione import installa_estensione, sketchup_installati
        trovati = sketchup_installati()
        print("\n".join(installa_estensione(su) for su in trovati) or "Nessun SketchUp desktop trovato.")
        return 0 if trovati else 1
    if len(argv) >= 2 and argv[1] == "esempi":
        from .ciclo import esempi
        print("Esempi (agentic3d nuovo \"<Nome>\" --esempio \"<esempio>\"):")
        print("\n".join(f"  {e}" for e in esempi()))
        return 0
    if len(argv) >= 2 and argv[1] == "impostazioni":
        return _impostazioni(argv[2:])
    if len(argv) >= 2 and argv[1] in ("informazioni", "--version"):
        from .informazioni import testo
        print(testo())
        return 0
    if len(argv) >= 2 and argv[1] == "estensione-sketchup":
        from .estensione import crea_rbz
        print("scritto:", crea_rbz(argv[2] if len(argv) > 2 else None))
        return 0
    if len(argv) < 3 or argv[1] not in ("controlla", "costruisci"):
        print(__doc__)
        return 2
    percorso = trova_scheda(argv[2])
    scheda = carica_scheda(percorso)
    if argv[1] == "controlla":
        rapporto = controlla(completa(scheda))
        print(rapporto.testo())
        return 0 if rapporto.ok else 1
    opzioni = argv[3:]
    motore = "nucleo"
    if "--motore" in opzioni:
        motore = opzioni[opzioni.index("--motore") + 1]
    completata, esito = costruisci(scheda, percorso.parent, render="--render" in opzioni,
                                   esporta="--esporta" in opzioni, solo_script="--solo-script" in opzioni,
                                   motore=motore, tieni_blender="--tieni-blender" in opzioni,
                                   al_progresso=lambda n, tot, msg: print(msg, flush=True),
                                   apri_galleria="--senza-galleria" not in opzioni)
    if "--solo-script" in opzioni:
        print(esito["script"])
        return 0
    if "geometria" in esito:
        print(esito["geometria"])
    for a in esito.get("avvisi", []):
        print("AVVISO:", a)
    if "blender" in esito:
        print(_testo_blender(esito["blender"]))
    for f in esito.get("file", []):
        print("scritto:", f)
    if esito.get("peso"):
        print(esito["peso"])
    return 0


def _testo_blender(esito) -> str:
    """Riga di rapporto sul render (esito del Blender senza finestra, o risposta del ponte nel motore classico)."""
    if isinstance(esito, dict) and "esito" in esito:
        if esito["esito"] != "ok":
            return f"Render: ERRORE, {esito['errore']}"
        testo = f"Render: {len(esito['viste'])} viste in {esito['secondi']} s, galleria in {esito['galleria']}"
        return testo + (f"; {esito['aperto']}" if esito.get("aperto") else "")
    return str(esito)[:400]


def trova_scheda(indicazione: str) -> Path:
    """Percorso di una scheda, oppure nome di un lavoro nella cartella dei lavori (`Casa Rossi`)."""
    p = Path(indicazione)
    if p.is_dir():
        p = p / "Scheda stanze.yaml"
    if p.exists() or p.suffix:
        return p
    from .configurazione import cartella_lavori
    return cartella_lavori() / indicazione / "Scheda stanze.yaml"


def _impostazioni(argomenti: list[str]) -> int:
    from . import configurazione as c
    if len(argomenti) == 2:
        try:
            print("salvato in", c.scrivi_impostazione(argomenti[0], argomenti[1]))
        except ValueError as e:
            print("Errore:", e)
            return 1
        return 0
    blender = c.eseguibile_blender()
    print(f"file delle impostazioni: {c.file_impostazioni()}")
    print(f"lavori:      {c.cartella_lavori()}")
    print(f"temporanei:  {c.cartella_temporanea()}")
    print(f"blender:     {blender or 'non trovato (facoltativo, serve solo per i render)'}")
    print(f"dopo_render: {c.leggi_impostazioni().get('dopo_render', 'automatico')} "
          "(automatico: il modello si apre in Blender solo se manca SketchUp; apri: sempre; chiudi: mai)")
    print("per cambiarle: agentic3d impostazioni <lavori|temporanei|blender> <percorso>, "
          "oppure agentic3d impostazioni dopo_render <automatico|apri|chiudi>")
    return 0


def principale() -> None:
    """Punto d'ingresso del comando `agentic3d` installato."""
    sys.exit(main(sys.argv))


if __name__ == "__main__":
    principale()
