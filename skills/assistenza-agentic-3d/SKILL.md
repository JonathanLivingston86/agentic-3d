---
name: assistenza-agentic-3d
description: Diagnosi e riparazione di Agentic 3D quando qualcosa non funziona: installazione interrotta, comando o strumenti MCP che non compaiono, estensione assente in SketchUp, modello che non si aggiorna, render che non parte. Usala appena l'utente segnala un problema o un errore di Agentic 3D, prima di qualunque altra prova.
---

# Assistenza Agentic 3D

L'utente non è un tecnico e non c'è un servizio di assistenza: la diagnosi la fa l'agente, con i passi qui sotto, e spiega in parole semplici cosa ha trovato e cosa ha fatto.

## 1. Prima di tutto: la verifica

Strumento MCP `verifica_installazione`; se gli strumenti di Agentic 3D non compaiono, nel terminale `agentic3d verifica` (se il comando non si trova: `~/.local/bin/agentic3d verifica`, su Windows `%USERPROFILE%\.local\bin\agentic3d.exe verifica`).

Ogni riga è OK, ATTENZIONE o ERRORE con il suo rimedio: applica i rimedi, uno alla volta, e ripeti la verifica finché restano solo OK (o ATTENZIONE che l'utente accetta, come SketchUp assente su un computer dove non lo usa).

Se l'installazione si è interrotta, leggi il **Rapporto installazione.txt** nella cartella di configurazione (Windows `%APPDATA%\Agentic 3D`, macOS `~/Library/Application Support/Agentic 3D`): l'ultima riga rossa o "interrotta" dice dove.

## 2. Problemi frequenti

| Sintomo | Causa probabile | Rimedio |
|---|---|---|
| `agentic3d` non è riconosciuto come comando | il terminale è stato aperto prima dell'installazione | percorso completo (sopra), poi `uv tool update-shell` e un terminale nuovo |
| Installazione ferma su Python o su una libreria | versione di Python troppo nuova scelta da uv | `uv tool install --reinstall --python 3.13 "<pacchetto>.whl"` |
| Gli strumenti di Agentic 3D non compaiono nell'agente | agente non riavviato, oppure non collegato | `agentic3d collega`, poi chiudere e riaprire l'agente; la verifica dice per ogni agente se server e Skill ci sono |
| Claude desktop non usa le Skill | in Claude desktop le Skill si caricano a mano | caricare gli ZIP indicati da `agentic3d collega` (Personalizza > Skill > Carica una skill) |
| In SketchUp manca il menu Estensioni > Agentic 3D | estensione non installata o non approvata | `installa_estensione_sketchup`, riavviare SketchUp; in Estensioni > Gestione estensioni, Agentic 3D deve essere attiva; se SketchUp blocca le estensioni non firmate, impostare il criterio di caricamento su "Approva le estensioni non identificate" |
| SketchUp non si aggiorna dopo `costruisci` | modello non collegato, o aggiornamento automatico spento | Estensioni > Agentic 3D > Collega modello... e scegliere il file "per SketchUp.json" del lavoro; poi `rapporto_sketchup` dice com'è andata |
| Un gruppo aperto in SketchUp blocca l'aggiornamento | l'utente sta modificando dentro un gruppo suo | chiedere di uscire dal gruppo (doppio clic fuori), poi Aggiorna |
| Render: "Blender non trovato" | Blender assente o in una cartella non standard | installare Blender (blender.org) oppure `impostazioni` con chiave `blender` e il percorso |
| Render interrotto con un errore | messaggio di Blender nel risultato di `costruisci` e nella galleria | leggere il messaggio; ripetere una volta; se si ripete, render con meno viste o senza, e dirlo all'utente |
| Dopo il render si apre Blender | sul computer non c'è SketchUp (impostazione `dopo_render` = automatico) | è voluto; per non aprirlo: `impostazioni` con `dopo_render` = `chiudi` |
| Cartella dei lavori non scrivibile (OneDrive, permessi) | cartella sincronizzata o protetta | `impostazioni` con chiave `lavori` e una cartella locale |

## 3. Regole

- Una prova alla volta, con la verifica dopo ogni rimedio: non cambiare più cose insieme.
- Non modificare a mano i file di configurazione degli agenti: lo fa `agentic3d collega`, con una copia di sicurezza (cartella "Copie di sicurezza" nella cartella di configurazione).
- Non cancellare lavori, schede o copie di sicurezza.
- Se dopo tre tentativi diversi il problema resta, fermati e riassumi all'utente: cosa non va, cosa hai provato, l'uscita della verifica. Aggiornare o reinstallare: rilanciare l'installatore (a doppio clic) con il pacchetto più recente.
