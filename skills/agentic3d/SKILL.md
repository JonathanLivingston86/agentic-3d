---
name: agentic3d
description: Punto d'ingresso di Agentic 3D (comando /agentic3d; in Codex $agentic3d). Usala quando l'utente scrive /agentic3d o $agentic3d oppure chiede di avviare Agentic 3D, di trasformare un disegno, una foto o una descrizione in un modello 3D di interni, o di modificare un modello Agentic 3D.
---

# Agentic 3D

1. **Controlla di avere gli strumenti MCP di Agentic 3D** (`nuovo_lavoro`, `modifica_scheda`, `costruisci`, `verifica_installazione`...). Se non ci sono, fermati: esegui `agentic3d verifica` nel terminale (Windows `%USERPROFILE%\.local\bin\agentic3d.exe verifica`, macOS `~/.local/bin/agentic3d verifica`) e spiega all'utente cosa manca. Non costruire nulla in altro modo.
2. **Capisci cosa chiede l'utente**, dal testo dopo il comando e dagli allegati:
   - un lavoro nuovo da un DXF: `nuovo_lavoro` (tipo edificio), poi `importa_disegno` e conferma della tavola (`da-disegno-a-modello`); da un DWG: chiedi il DXF;
   - un lavoro nuovo da foto, schizzo o descrizione: apri il lavoro con `lavoro-3d-ciclo-di-vita`, poi `da-disegno-a-modello` (con la tavola di conferma) o `interni-italia-progettazione` per un brief;
   - una modifica a un lavoro esistente (`elenca_lavori` se non è chiaro quale): `modifica_scheda`, risposta breve;
   - un problema: `assistenza-agentic-3d`.
3. Se il comando arriva senza altro testo, chiedi in una frase cosa realizzare (e se c'è un disegno da allegare) o quale lavoro riprendere.

Le regole di `lavoro-3d-ciclo-di-vita` valgono sempre: modelli solo con gli strumenti di Agentic 3D, misure solo dal disegno, dal brief o dall'utente, prima costruzione accurata e modifiche veloci.
