# Installare Agentic 3D

Istruzioni scritte per l'agente (Claude Code, Codex, OpenCode, Gemini CLI, Cursor, Copilot): l'utente gli chiede di installare Agentic 3D e l'agente esegue questi passi nel terminale, poi riferisce l'esito in parole semplici. Non servono diritti di amministratore.

Gli stessi passi li esegue l'installatore a doppio clic (`Windows/Installa.cmd` o `Mac/Installa.command`, spiegati in `Guida.html`): se l'utente preferisce, basta lanciare quello.

Requisiti: Windows 10 o 11, oppure macOS 13 o successivo. SketchUp desktop (2021 o successivo) per lavorare dal vivo nel modello; Blender solo per i render, facoltativo.

## Passi

1. **uv** (il programma che installa Agentic 3D e il suo Python, senza toccare il resto del computer). Controlla con `uv --version`. Se manca:
   - Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
   - macOS (Terminale): `curl -LsSf https://astral.sh/uv/install.sh | sh`

   uv finisce in `~/.local/bin`: se il terminale non lo trova subito, usa il percorso completo (`~/.local/bin/uv`, su Windows `%USERPROFILE%\.local\bin\uv.exe`).
2. **Agentic 3D**: `uv tool install --python 3.13 "<pacchetto>"`, dove `<pacchetto>` è il percorso completo del file `agentic3d-*.whl` nella cartella `componenti`, la stessa di queste istruzioni (lo ZIP va estratto prima). uv scarica Python da solo se serve. Poi `uv tool update-shell`, così il comando `agentic3d` si trova anche nei terminali nuovi; in quello aperto usa `~/.local/bin/agentic3d`.
3. **Collegamento agli agenti**: `agentic3d collega`. Aggiunge il server MCP e le Skill di Agentic 3D a ogni agente installato, con una copia di sicurezza dei file che cambia; `agentic3d collega --prova` mostra prima cosa cambierebbe. Riferisci all'utente le righe `ATTENZIONE` e `DA FARE`.
4. **SketchUp**: `agentic3d installa-estensione`. Se risponde che non trova SketchUp, chiedi all'utente di aprirlo una volta e chiuderlo, poi ripeti.
5. **Verifica**: `agentic3d verifica`. Ogni riga è OK, ATTENZIONE o ERRORE, con il rimedio: applicalo e ripeti finché non restano errori.
6. **Cosa dire all'utente**:
   - riavviare l'agente (così vede il server e le Skill) e SketchUp;
   - al primo avvio SketchUp può chiedere di approvare l'estensione "Agentic 3D": approvarla;
   - Claude desktop: caricare una volta le Skill dalla cartella indicata da `agentic3d collega`.

## Primo lavoro, dopo il riavvio

Con gli strumenti MCP di Agentic 3D: `nuovo_lavoro` (nome `Prova`, esempio `Appartamento di esempio`), poi `costruisci`. In SketchUp l'utente sceglie Estensioni > Agentic 3D > Collega modello... e apre `Prova per SketchUp.json` nella cartella `Esportazioni` del lavoro (`impostazioni` dice dov'è la cartella dei lavori). Da lì ogni modifica compare da sola; `rapporto_sketchup` dice se il modello è arrivato pulito.

## Aggiornare e disinstallare

- Aggiornare: `uv tool install --reinstall --python 3.13 "<pacchetto nuovo>"`, poi `agentic3d collega` e `agentic3d installa-estensione`.
- Disinstallare: `agentic3d scollega` (toglie server e Skill dagli agenti), poi `uv tool uninstall agentic3d`. I lavori restano nella loro cartella.

## Se qualcosa non va

`agentic3d verifica` (o lo strumento `verifica_installazione`) è sempre il primo passo: dice cosa manca e come si ripara.

---

Agentic 3D è ideato e sviluppato da Andrea Lucarelli.
