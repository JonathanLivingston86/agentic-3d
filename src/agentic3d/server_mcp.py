"""Server MCP di Agentic 3D: gli strumenti con cui un agente crea, controlla, costruisce ed esporta un lavoro.

Avvio (lo fa l'agente, configurato dall'installazione): `agentic3d mcp`, trasporto stdio. Gli strumenti parlano di
lavori per nome; le cartelle vengono dalle impostazioni (`configurazione.py`). Nessuno strumento cancella file: le
versioni precedenti di una scheda restano nella cartella temporanea.
"""

from __future__ import annotations

import contextlib
import functools
import inspect
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
import anyio
import anyio.from_thread
import anyio.to_thread
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import ciclo, installazione
from . import configurazione as conf
from .informazioni import AUTORE, NOME, testo as testo_informazioni, versione

ISTRUZIONI = """Agentic 3D modella interni da una scheda YAML (stanze, pareti, aperture, arredi) e li porta in SketchUp.
Flusso: nuovo_lavoro (o un esempio) -> importa_disegno (DXF) oppure scrivi_scheda (foto, schizzo, brief) ->
tavola_di_lettura e conferma dell'utente -> controlla_norme -> costruisci (esporta) -> rapporto_sketchup. Dopo la prima costruzione, ogni modifica chiesta dall'utente si fa con una sola chiamata a
modifica_scheda (cambia le righe, controlla, ricostruisce e aggiorna SketchUp) e si risponde in una o due frasi; render
solo se chiesti. I modelli nascono solo da questi strumenti: mai da codice scritto al momento, pagine web o altri
programmi; le misure vengono dal disegno, dal brief o dall'utente, mai inventate. Niente programmi scaricati e niente
codice interno del motore richiamato dal terminale; un DWG si chiede all'utente in DXF. Le procedure complete sono nelle
Skill di Agentic 3D. Se qualcosa non funziona, prima di tutto verifica_installazione."""

server = MCPServer(name=NOME, title=NOME, instructions=ISTRUZIONI, version=versione())


def strumento(fn):
    """Registra uno strumento; gli errori dell'utente (nome sbagliato, scheda non valida) arrivano all'agente come
    messaggio leggibile invece che come errore generico."""
    errori = (ValueError, FileExistsError, FileNotFoundError)
    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def avvolto_asincrono(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except errori as e:
                raise ToolError(str(e)) from None
        return server.tool()(avvolto_asincrono)

    @functools.wraps(fn)
    def avvolto(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except errori as e:
            raise ToolError(str(e)) from None
    return server.tool()(avvolto)


@contextlib.contextmanager
def _silenzioso():
    """Nel trasporto stdio l'uscita standard è il canale del protocollo: le stampe del motore vanno su stderr."""
    with contextlib.redirect_stdout(sys.stderr):
        yield


def _scheda(lavoro: str) -> Path:
    p = conf.cartella_lavori() / lavoro / "Scheda stanze.yaml"
    if not p.is_file():
        disponibili = ", ".join(_nomi_lavori()) or "nessuno"
        raise ValueError(f"lavoro {lavoro!r} non trovato in {conf.cartella_lavori()} (lavori: {disponibili})")
    return p


def _nomi_lavori() -> list[str]:
    base = conf.cartella_lavori()
    return sorted(p.parent.name for p in base.glob("*/Scheda stanze.yaml")) if base.is_dir() else []


@strumento
def nuovo_lavoro(nome: str, tipo: str = "stanza", esempio: str | None = None, disegni: list[str] | None = None) -> str:
    """Crea un lavoro nella cartella dei lavori: sottocartelle, scheda stanze di partenza e scheda del progetto.
    `tipo`: "stanza" o "edificio" (più stanze). `esempio`: parte dalla copia di un esempio (vedi `esempi`).
    `disegni`: percorsi di planimetrie o foto da copiare in Riferimenti. Il nome è leggibile, con spazi, senza
    trattini o underscore."""
    with _silenzioso():
        return "\n".join(ciclo.nuovo(nome, tipo, disegni or [], esempio=esempio))


@strumento
def importa_disegno(lavoro: str, disegno: str, livello_muri: str | None = None) -> str:
    """Legge da solo una planimetria DXF (percorso `disegno`) e scrive la scheda del lavoro: masse dei muri, vani
    (porte, finestre, porte finestre, passaggi), stanze con nome, altezza e superficie dai testi, controsoffitti e
    balconi, con le misure esatte del CAD. Disegna in Riferimenti la "Tavola di lettura.png" e riporta cosa è stato
    letto e cosa va confermato: mostrare la tavola all'utente e costruire solo dopo la sua conferma. Un DWG non si
    legge: chiedere all'utente di salvarlo come DXF. `livello_muri`: il livello dei muri, se la lettura non lo trova."""
    from .importa import importa_disegno as importa
    p = _scheda(lavoro)
    with _silenzioso():
        return importa(p.parent, disegno, livello_muri, conf.cartella_temporanea())


@strumento
def tavola_di_lettura(lavoro: str) -> str:
    """Disegna la pianta 2D di ciò che dice la scheda (stanze, muri, vani con le larghezze, altezze, balconi) nella
    "Tavola di lettura.png" del lavoro. Per foto e schizzi è il passaggio obbligato: dopo aver scritto la scheda si
    mostra la tavola all'utente, che la confronta con il disegno e conferma o corregge, prima di costruire."""
    from .importa import tavola_di_lettura as tavola
    p = _scheda(lavoro)
    with _silenzioso():
        return f"Tavola da mostrare all'utente: {tavola(p.parent)}"


@strumento
def esempi() -> list[str]:
    """Schede complete compresi nel pacchetto, da usare con `nuovo_lavoro(esempio=...)`."""
    return ciclo.esempi()


@strumento
def elenca_lavori() -> str:
    """Lavori nella cartella dei lavori, con la data dell'ultima modifica della scheda."""
    base = conf.cartella_lavori()
    righe = [f"Cartella dei lavori: {base}"]
    for nome in _nomi_lavori():
        quando = datetime.fromtimestamp((base / nome / "Scheda stanze.yaml").stat().st_mtime)
        righe.append(f"- {nome} (scheda modificata il {quando:%d/%m/%Y %H:%M})")
    return "\n".join(righe) if len(righe) > 1 else righe[0] + "\nNessun lavoro: usa `nuovo_lavoro`."


@strumento
def leggi_scheda(lavoro: str) -> str:
    """Testo della `Scheda stanze.yaml` del lavoro (misure, pareti, aperture, arredi)."""
    return _scheda(lavoro).read_text(encoding="utf-8")


@strumento
def scrivi_scheda(lavoro: str, testo: str) -> str:
    """Sostituisce la `Scheda stanze.yaml` del lavoro con `testo`, dopo aver controllato che sia YAML valido e
    completabile. La versione precedente resta nella cartella temporanea. Per piccole modifiche a una scheda già
    costruita è più veloce `modifica_scheda`."""
    return _salva_scheda(_scheda(lavoro), lavoro, testo)


def _salva_scheda(p: Path, lavoro: str, testo: str) -> str:
    try:
        dati = yaml.safe_load(testo)
    except yaml.YAMLError as e:
        raise ValueError(f"YAML non valido: {e}") from None
    if not isinstance(dati, dict) or not ({"stanza", "edificio"} & set(dati)):
        raise ValueError("la scheda deve contenere un blocco `stanza:` oppure `edificio:`")
    from .scheda import completa
    with _silenzioso():
        completa(dati)
    copia = conf.cartella_temporanea() / f"{lavoro} scheda {datetime.now():%Y%m%d %H%M%S}.yaml"
    shutil.copy2(p, copia)
    provvisorio = p.with_name(p.name + ".tmp")
    provvisorio.write_text(testo, encoding="utf-8")
    provvisorio.replace(p)
    return f"Scheda salvata ({len(testo.splitlines())} righe). Versione precedente: {copia}"


@strumento
def controlla_norme(lavoro: str) -> str:
    """Controllo delle norme italiane ed europee sulla scheda: PASS, FAIL, NON VERIFICABILE, NON APPLICABILE, con
    fonti e ipotesi usate. Non sostituisce il tecnico abilitato."""
    from .controllo import controlla
    from .scheda import carica_scheda, completa
    with _silenzioso():
        return controlla(completa(carica_scheda(_scheda(lavoro)))).testo()


def _applica_modifiche(testo: str, modifiche: list[dict]) -> str:
    """Sostituzioni esatte: ogni `cerca` deve comparire una sola volta, così non si cambia la riga sbagliata."""
    for k, m in enumerate(modifiche, 1):
        cerca, nuovo = m.get("cerca"), m.get("sostituisci")
        if not isinstance(cerca, str) or not isinstance(nuovo, str) or not cerca:
            raise ValueError(f"modifica {k}: servono `cerca` e `sostituisci` (testo)")
        volte = testo.count(cerca)
        if volte != 1:
            raise ValueError(f"modifica {k}: {cerca!r} compare {volte} volte nella scheda (deve essere una sola): "
                             "allarga il testo da cercare con la riga intera o l'id dell'oggetto, oppure leggi_scheda")
        testo = testo.replace(cerca, nuovo)
    return testo


@strumento
async def modifica_scheda(lavoro: str, modifiche: list[dict], ctx: Context, render: bool = False) -> str:
    """Modifica veloce di un lavoro già costruito, in una sola chiamata: applica le `modifiche` alla scheda
    ([{"cerca": testo esatto, "sostituisci": testo nuovo}], ogni `cerca` presente una sola volta), la controlla,
    conserva la versione precedente, verifica norme e geometria, ricostruisce, aggiorna SketchUp e risponde in breve
    (per intero se c'è un problema). Render solo se l'utente li chiede."""
    p = _scheda(lavoro)
    testo = _applica_modifiche(p.read_text(encoding="utf-8"), modifiche)
    _salva_scheda(p, lavoro, testo)
    from .controllo import controlla
    from .scheda import carica_scheda, completa
    with _silenzioso():
        norme = controlla(completa(carica_scheda(p)))
    falliti = [r for r in norme.testo().splitlines() if "FAIL" in r and not r.startswith("Esito")]
    esito = await _costruisci_asincrono(p, ctx, True, render, 10)
    prefisso = f"Scheda modificata ({len(modifiche)} {'modifica' if len(modifiche) == 1 else 'modifiche'}). "
    if falliti:
        prefisso += "NORME: " + " | ".join(falliti[:6]) + "\n"
    return prefisso + esito


@strumento
async def costruisci(lavoro: str, ctx: Context, esporta: bool = True, render: bool = False,
                     attendi_sketchup_secondi: int = 10) -> str:
    """Costruisce il modello dalla scheda. `esporta`: GLB e file per SketchUp (pochi millisecondi; se l'estensione è
    collegata, SketchUp si aggiorna da solo e questo strumento ne riporta l'esito). `render`: immagini con Blender
    senza finestra (facoltativo, richiede minuti): l'avanzamento arriva come notifica e una galleria nel browser
    mostra ogni vista appena pronta. Riporta controllo geometrico (ERRORI e AVVISI), file scritti e peso."""
    return await _costruisci_asincrono(_scheda(lavoro), ctx, esporta, render, attendi_sketchup_secondi)


async def _costruisci_asincrono(p: Path, ctx: Context, esporta: bool, render: bool, attendi: int) -> str:
    def progresso(fatte: int, totale: int, messaggio: str) -> None:
        print(messaggio, file=sys.stderr, flush=True)
        try:
            anyio.from_thread.run(ctx.report_progress, fatte, totale, messaggio)
        except Exception:
            pass                     # l'agente che non chiede l'avanzamento non lo riceve: il render continua

    try:
        return await anyio.to_thread.run_sync(
            functools.partial(_costruisci, p, esporta, render, attendi, progresso), abandon_on_cancel=True)
    except anyio.get_cancelled_exc_class():
        from .blender import sottofondo
        sottofondo.ferma_tutti()             # l'agente ha annullato: Blender non resta a lavorare da solo
        raise


def _costruisci(p: Path, esporta: bool, render: bool, attendi_sketchup_secondi: int, progresso) -> str:
    from .costruttore import costruisci as costruisci_modello
    from .scheda import carica_scheda
    inizio = time.time()
    with _silenzioso():
        _, esito = costruisci_modello(carica_scheda(p), p.parent, render=render, esporta=esporta,
                                      al_progresso=progresso)
    file_sketchup = next((f for f in esito.get("file", []) if f.endswith("per SketchUp.json")), None)
    if file_sketchup and not installazione.collegato_a(file_sketchup):
        attendi_sketchup_secondi = 0            # SketchUp chiuso o collegato ad altro: niente attesa inutile
        esito.setdefault("avvisi", []).append(installazione.non_collegato(file_sketchup))
    # il file per SketchUp si riscrive solo se il modello cambia: il controllo di SketchUp va confrontato con la sua
    # ora di modifica, non con l'inizio della costruzione (modello invariato = già applicato)
    riferimento = inizio
    if file_sketchup and Path(file_sketchup).is_file():
        riferimento = min(inizio, Path(file_sketchup).stat().st_mtime)
    if conf.modalita() == "veloce":
        return _risposta_breve(esito, inizio, esporta, render, attendi_sketchup_secondi, riferimento)
    righe = [esito.get("geometria", "")]
    righe += [f"AVVISO: {a}" for a in esito.get("avvisi", [])]
    righe += [f"scritto: {f}" for f in esito.get("file", [])]
    if esito.get("peso"):
        righe.append(esito["peso"])
    if "blender" in esito:
        from .__main__ import _testo_blender
        righe.append(_testo_blender(esito["blender"]))
    if esporta and attendi_sketchup_secondi > 0:
        righe.append("--- SketchUp ---")
        righe.append(installazione.rapporto_sketchup(dopo=riferimento, attesa=attendi_sketchup_secondi))
    return "\n".join(r for r in righe if r)


def _risposta_breve(esito: dict, inizio: float, esporta: bool, render: bool, attesa: int,
                    riferimento: float | None = None) -> str:
    """Modalità veloce: tutti i controlli restano, ma si riporta solo ciò che richiede attenzione. Nessun file
    elencato, nessun dettaglio se è tutto in ordine."""
    righe = []
    geometria = esito.get("geometria", "")
    if geometria and not geometria.startswith("GEOMETRIA: nessuna"):
        righe.append(geometria)
    righe += [f"AVVISO: {a}" for a in esito.get("avvisi", [])]
    righe += [r for r in esito.get("peso", "").splitlines() if "oltre" in r or "supera" in r]
    if render and "blender" in esito:
        from .__main__ import _testo_blender
        righe.append(_testo_blender(esito["blender"]))
    sketchup = installazione.rapporto_sketchup_breve(riferimento or inizio, attesa) if esporta and attesa > 0 else ""
    if sketchup.startswith("SketchUp aggiornato"):
        testa = f"Fatto in {time.time() - inizio:.1f} s: geometria in ordine. {sketchup}."
    else:
        testa = f"Fatto in {time.time() - inizio:.1f} s."
        if sketchup:
            righe.append(sketchup)
    return "\n".join([testa] + righe)


@strumento
def chiudi_lavoro(lavoro: str) -> str:
    """Pulizia a fine lavoro: file in eccesso nel Cestino (recuperabili), temporanei svuotati, segnalazioni di file
    sciolti, esportazioni più vecchie della scheda e Blender ancora aperto."""
    _scheda(lavoro)
    with _silenzioso():
        return "\n".join(ciclo.chiudi(lavoro))


@strumento
def rapporto_sketchup() -> str:
    """Esito dell'ultimo aggiornamento fatto dall'estensione in SketchUp: oggetti, aree, solidi, problemi, errori."""
    return installazione.rapporto_sketchup()


@strumento
def installa_estensione_sketchup() -> str:
    """Installa o aggiorna l'estensione Agentic 3D in ogni SketchUp desktop trovato. Poi va riavviato SketchUp."""
    trovati = installazione.sketchup_installati()
    if not trovati:
        return "Nessun SketchUp desktop trovato: aprilo una volta e riprova."
    return "\n".join(installazione.installa_estensione(su) for su in trovati)


@strumento
def verifica_installazione() -> str:
    """Primo strumento da usare quando qualcosa non funziona: controlla motore, cartelle, SketchUp, estensione e
    Blender e dice per ogni problema come si ripara."""
    return installazione.verifica_installazione()


@strumento
def impostazioni(chiave: str | None = None, valore: str | None = None) -> str:
    """Senza argomenti mostra dove stanno lavori, temporanei e Blender, cosa succede dopo i render e la modalità.
    Con `chiave` ("lavori", "temporanei", "blender": `valore` è un percorso; "dopo_render": `valore` è "automatico",
    cioè il modello si apre in Blender solo se SketchUp non è installato, "apri" o "chiudi"; "modalita": "veloce",
    risposte brevi a ogni modifica, o "diagnostica", risposte complete) la cambia."""
    if chiave is not None:
        if valore is None:
            raise ValueError("serve anche `valore`")
        conf.scrivi_impostazione(chiave, valore)
    return (f"lavori: {conf.cartella_lavori()}\ntemporanei: {conf.cartella_temporanea()}\n"
            f"blender: {conf.eseguibile_blender() or 'non trovato (facoltativo)'}\n"
            f"dopo_render: {conf.leggi_impostazioni().get('dopo_render', 'automatico')}\n"
            f"modalita: {conf.modalita()}\nfile: {conf.file_impostazioni()}")


@strumento
def informazioni() -> str:
    """Nome, versione e autore di Agentic 3D."""
    return testo_informazioni()


def avvia() -> None:
    conf.prepara_cartella_lavori()
    server.run("stdio")


__all__ = ["server", "avvia", "AUTORE"]
