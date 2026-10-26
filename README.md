# Agentic 3D

Modellazione 3D di interni guidata da un agente AI: da un brief, una planimetria o uno schizzo con le quote a un modello controllato sulle norme italiane ed europee, che si apre e si aggiorna dal vivo in SketchUp.

![Flusso di Agentic 3D](docs/Flusso%20di%20Agentic%203D.png)

## Installare

1. Scaricare lo ZIP dell'ultima versione dalla pagina **Releases** ed estrarlo.
2. Doppio clic su `Windows/Installa.cmd` oppure `Mac/Installa.command`.
3. Seguire la **guida** (`Guida.html`, nello ZIP): spiega anche gli avvisi di Windows e del Mac per i programmi senza firma a pagamento.

In alternativa si può chiedere al proprio agente AI di installarlo seguendo `componenti/INSTALLA.md`.

Serve uno di questi agenti: Claude (Code o desktop), Codex, Gemini CLI, Cursor, GitHub Copilot, OpenCode. SketchUp desktop (2021 o successivo) per il modello dal vivo; Blender, facoltativo, per i render.

## Come funziona

1. L'agente segue le **Skill** di Agentic 3D (procedure di mestiere nel formato aperto Agent Skills) e usa gli strumenti del **server MCP** di Agentic 3D.
2. Il progetto è descritto in una **scheda** di testo (stanze, pareti, aperture, arredi); i valori mancanti vengono scelti in modo coerente con le norme e dichiarati come ipotesi.
3. Il **motore** costruisce la geometria, controlla compenetrazioni, parti sospese, porte bloccate e arredi davanti alle finestre, verifica le norme (regole in dati con fonte e articolo) e scrive in pochi millisecondi il modello per SketchUp e il file GLB.
4. L'**estensione per SketchUp** costruisce gruppi, componenti e solidi puliti, si aggiorna da sola a ogni modifica e rimanda all'agente un rapporto di controllo.
5. **Blender** (facoltativo) fa i render in sottofondo, con avanzamento e una galleria che si riempie nel browser.

Il controllo delle norme aiuta il progettista e non sostituisce la responsabilità del tecnico abilitato.

## Contenuto del repository

- `src/agentic3d/`: motore, server MCP, regole normative in dati, estensione per SketchUp, esempi.
- `skills/`: Skill per gli agenti.
- `distribuzione/`: installatori e guida.
- `scripts/crea_pacchetto.py`: costruisce il pacchetto da distribuire.

## Licenza

Uso consentito anche professionale; redistribuzione e rivendita vietate. Testo completo in [LICENZA.md](LICENZA.md). Software fornito senza garanzie e senza assistenza.

---

Agentic 3D è ideato e sviluppato da Andrea Lucarelli.
