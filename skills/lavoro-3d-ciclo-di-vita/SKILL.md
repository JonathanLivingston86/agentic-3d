---
name: lavoro-3d-ciclo-di-vita
description: Avvia Agentic 3D e governa ogni lavoro 3D, dall'apertura alle modifiche veloci fino a controllo qualità e pulizia. Usala quando l'utente chiede di avviare o usare Agentic 3D, di modellare un interno, di aprire un nuovo lavoro, di modificare un modello esistente o di chiuderne uno.
---

# Ciclo di vita di un lavoro 3D

## Regole che valgono sempre

1. I modelli si creano e si modificano solo con gli strumenti di Agentic 3D. Mai con codice scritto al momento, pagine web (three.js), server locali, script di Blender o file 3D fatti a mano.
2. Se gli strumenti MCP di Agentic 3D non compaiono, fermati: `agentic3d verifica` nel terminale, poi spiega all'utente cosa manca (di solito rilanciare l'installatore e riavviare l'agente). Non costruire nulla nel frattempo.
3. Le misure vengono solo dal disegno, dal brief o dall'utente. Una quota illeggibile o mancante si chiede; un valore scelto per completare si dichiara come ipotesi.
4. Niente programmi scaricati o installati, niente codice interno di Agentic 3D richiamato dal terminale: solo gli strumenti MCP. Un DWG non si converte: si chiede all'utente di salvarlo come DXF dal suo CAD.
5. All'utente si racconta solo ciò che è già successo, dopo il risultato dello strumento.

## Strumenti

Il motore si usa con gli strumenti MCP del server `Agentic 3D`; dove l'agente ha un terminale e il server non è collegato, valgono i comandi equivalenti.

| Strumento MCP | Comando | A cosa serve |
|---|---|---|
| `nuovo_lavoro`, `esempi` | `agentic3d nuovo "<Nome>" [--tipo edificio] [--esempio "<esempio>"] [--disegno file]`, `agentic3d esempi` | Aprire un lavoro, anche da un esempio |
| `elenca_lavori`, `leggi_scheda`, `scrivi_scheda` | file `Scheda stanze.yaml` del lavoro | Leggere e scrivere tutta la scheda (`scrivi_scheda` la controlla e conserva la versione precedente) |
| `modifica_scheda` | (solo MCP) | Modifica veloce: cambia solo le righe indicate, controlla norme e geometria, ricostruisce e aggiorna SketchUp in una chiamata |
| `importa_disegno` | `agentic3d importa "<Nome>" disegno.dxf` | Lettura automatica di un DXF: scheda e tavola di lettura da confermare |
| `tavola_di_lettura` | `agentic3d tavola "<Nome>"` | Pianta 2D della scheda da mostrare all'utente prima di costruire |
| `controlla_norme` | `agentic3d controlla "<Nome>"` | Controllo delle norme |
| `costruisci` | `agentic3d costruisci "<Nome>" --esporta [--render]` | Modello, GLB, file per SketchUp, render; riporta anche l'esito in SketchUp |
| `rapporto_sketchup` | file di rapporto dell'estensione (`esporta-per-sketchup`) | Esito dell'ultimo aggiornamento in SketchUp |
| `chiudi_lavoro` | `agentic3d chiudi "<Nome>"` | Pulizia a fine lavoro |
| `installa_estensione_sketchup` | `agentic3d installa-estensione` | Installare o aggiornare l'estensione |
| `verifica_installazione`, `impostazioni`, `informazioni` | `agentic3d verifica`, `agentic3d impostazioni`, `agentic3d informazioni` | Diagnosi, cartelle, versione |

## Modalità di lavoro

**Prima costruzione: accurata.** Lettura del disegno o del brief, domande sulle quote incerte, scheda completa, `controlla_norme`, `costruisci`, riscontro con il disegno: con la cura descritta in `da-disegno-a-modello` e `interni-italia-progettazione`.

**Dopo: veloce (predefinita).** Ogni modifica chiesta dall'utente ("sposta il divano di 30 cm", "togli la fascia verde") si applica subito:
1. una sola chiamata a `modifica_scheda` con le righe da cambiare (se non le conosci, prima un `leggi_scheda`);
2. risposta in una o due frasi: cosa è cambiato ed eventuali problemi riportati dallo strumento;
3. niente render se l'utente non li chiede, niente riletture o verifiche in più se lo strumento non segnala problemi, niente elenchi di file.

I controlli restano tutti: lo strumento riporta per intero ogni ERRORE, AVVISO, FAIL delle norme o problema in SketchUp, e quelli vanno sempre detti e corretti.

**Diagnostica, su richiesta.** Quando l'utente chiede di capire cosa succede ("modalità diagnostica", "spiegami nel dettaglio"), `impostazioni` con `modalita` = `diagnostica`: gli strumenti tornano a riportare file, pesi e controlli completi e la spiegazione è passo per passo. Si torna alla veloce con `modalita` = `veloce`.

## Apertura

`nuovo_lavoro` crea tutto in un colpo: rifiuta nomi con trattini o underscore e non sovrascrive un lavoro esistente.

1. Chiedi un nome breve e leggibile in italiano, con spazi (esempio `Camera da letto Via Appia`).
2. Nasce `<Nome>` nella cartella dei lavori (`impostazioni` la mostra) con le sole sottocartelle `Riferimenti` (disegni, foto, appunti: copie, mai originali spostati), `Modello`, `Esportazioni`, `Render`, una `Scheda stanze.yaml` di partenza che si costruisce subito e la `Scheda del progetto.md`.
3. Nella `Scheda del progetto.md` tieni: brief, committente se utile, comune, tipo di intervento, misure note e loro fonte, ipotesi e dubbi aperti, decisioni, esito del controllo norme, provenienza e licenza degli oggetti generati.
4. Prosegui con `interni-italia-progettazione` (brief) o `da-disegno-a-modello` (planimetria o schizzo).

I file temporanei (render di prova, mesh intermedie, `.blend1`) vanno nella cartella temporanea del motore (`impostazioni`), mai dentro il lavoro.

## Controllo qualità prima della consegna

Il lavoro è consegnabile quando ogni voce è vera:

- [ ] Controllo norme eseguito e riportato (FAIL, NON VERIFICABILE, avviso sulla responsabilità del tecnico).
- [ ] Rapporto `GEOMETRIA` senza ERRORI; ogni AVVISO corretto o spiegato.
- [ ] Misure chiave rilette nel modello e uguali alla scheda; quote del disegno riscontrate.
- [ ] Ipotesi e dubbi scritti nella scheda del progetto, non taciuti.
- [ ] Render guardati e coerenti con il brief (se richiesti).
- [ ] In SketchUp, rapporto dell'estensione senza problemi (`esporta-per-sketchup`).
- [ ] Peso della scena sotto i 300.000 triangoli.
- [ ] Licenze degli oggetti generati registrate.
- [ ] I difetti che vedi e sai correggere dentro il compito sono corretti; all'utente proponi solo ciò che richiede una sua scelta.

## Pulizia a fine lavoro

`chiudi_lavoro` sposta nel Cestino i file in eccesso (`.blend1`, render di prova, duplicati: recuperabili), svuota i temporanei del lavoro, segnala file sciolti, sottocartelle senza scopo, esportazioni più vecchie della scheda e Blender ancora aperto.

Poi:
1. Il materiale dubbio non si cancella: si segnala.
2. Chiudi Blender se è aperto.
3. Riepiloga all'utente: cosa è stato fatto, cosa è stato verificato e come, cosa resta aperto.
