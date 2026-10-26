---
name: esporta-per-sketchup
description: Porta un modello Agentic 3D in SketchUp, dal vivo con l'estensione o come GLB, e ne verifica il risultato leggendo il rapporto dell'estensione. Usala quando il modello va aperto, aggiornato o consegnato in SketchUp, o quando l'estensione dà problemi.
---

# Esportazione per SketchUp

`costruisci` (con `esporta`) scrive in `Esportazioni` il GLB e il file `<Nome> per SketchUp.json`, senza Blender. Due vie per aprirli in SketchUp.

## Via principale: estensione Agentic 3D (aggiornamento dal vivo)

**Installazione.** La fa l'installatore di Agentic 3D; per ripeterla o aggiornare: `installa_estensione_sketchup`, poi riavvia SketchUp. In alternativa `agentic3d estensione-sketchup` crea il file `.rbz` da installare con Estensioni > Gestione estensioni > Installa estensione.

**Uso.** Estensioni > Agentic 3D > "Collega modello..." e scegli il file `per SketchUp.json`; poi salva il modello. Da lì:
- ogni nuova esportazione compare da sola in pochi secondi ("Aggiornamento automatico", attivo dopo il collegamento). Se è aperto un contenitore o un oggetto di Agentic 3D, l'estensione lo chiude e aggiorna; se è aperto un gruppo dell'utente, aspetta e lo scrive nella barra di stato;
- il collegamento si salva nel `.skp`: riaprendo quel modello riprende da solo, gli altri modelli non vengono toccati; "Scollega" lo toglie;
- "Aggiorna" forza il controllo; "Blocca selezione" esclude un oggetto dagli aggiornamenti (per modificarlo a mano), "Sblocca selezione" lo riammette; "Strumenti" > "Ricostruisci tutto", "Controlla modello", "Apri registro".

**Cosa si trova nel modello.**
- Contenitori senza tag: **Muri** (`Tamponature` e `Tramezzi`, un solido ciascuno per piano), **Solai** con quattro sottocontenitori che si accendono e si spengono con un clic: Pavimenti, Soffitto (uno per piano, fino al filo esterno dei muri, con spessore), Controsoffitti, Balconi; **Serramenti**, **Arredi**. Con più piani il nome del piano segue quello dell'oggetto.
- Tag sugli oggetti: Muri, Solai (anche i balconi), Soffitto (a parte, per guardare dentro, anche i controsoffitti), Serramenti, Arredi.
- Ogni oggetto è un gruppo; quelli fatti di più solidi (porte, arredi) hanno un gruppo interno per materiale, così i solidi a contatto non si fondono.
- Facce intere, con i fori di porte, finestre e lavelli. Superfici curve (cilindri, aste, torniti, sfere) senza linee: gli spigoli tra facce che piegano meno di 35 gradi sono morbidi; scatole, tappi e muri restano a spigoli vivi.
- Oggetti ripetuti con `componente: <nome>` nella scheda diventano copie di un componente: modificandone uno cambiano tutti. Per personalizzarne uno: tasto destro > Rendi univoco, poi Blocca selezione. Nella scheda le copie si scrivono con gli ancoraggi YAML (`&nome` e `{<<: *nome, id: ..., posizione_m: ...}`); due copie con forme diverse sono un errore.

**Cosa succede alle modifiche fatte a mano.** Si aggiornano solo gli oggetti cambiati; uno spostamento fatto a mano si somma alla nuova posizione; ciò che si disegna fuori dai gruppi non si tocca; ogni aggiornamento si annulla in un colpo (Modifica > Annulla). Le modifiche dentro un gruppo si perdono al prossimo aggiornamento di quell'oggetto: prima si blocca l'oggetto.

## Verifica: la fa l'agente, non l'utente

`costruisci` aspetta l'aggiornamento e ne riporta l'esito; `rapporto_sketchup` lo rilegge. Senza server MCP leggi tu, qualche secondo dopo l'esportazione, nella cartella temporanea del sistema (`%TEMP%` su Windows, `$TMPDIR` su macOS):
- `Agentic 3D registro.txt`: comandi, collegamenti, riepilogo di ogni aggiornamento (nuovi, aggiornati, invariati, rimossi, bloccati), errori;
- `Agentic 3D controllo.json`: per ogni oggetto poligoni, facce, riserve a triangoli, area attesa e reale, solido.

Il risultato è buono quando ogni oggetto ha l'area attesa, `solido` vero dove il file lo dichiara chiuso, nessuna riserva e nessun problema. Se l'aggiornamento non compare nel registro: l'estensione non è collegata a quel modello (chiedi di usare "Collega modello...") oppure è aperto un gruppo dell'utente. Riferisci l'esito in poche righe; all'utente si chiede di guardare solo ciò che il rapporto non può dire (l'aspetto).

## Via alternativa: GLB

File > Importa e scegli il `.glb`; controlla una quota nota con il Metro. Il GLB contiene solo mesh con nomi e materiali leggibili, senza luci, camere e soffitto (per guardare dall'alto). SketchUp lo importa come un componente unico dentro "Assembly": per gruppi veri e aggiornamenti dal vivo serve l'estensione. FBX e OBJ non servono: SketchUp desktop importa il GLB, e Blender 5 non esporta COLLADA.

## Pulizia prima di consegnare

- Metri, scala 1.0, un oggetto per elemento reale con nome leggibile in italiano, materiali senza duplicati.
- Peso: arredo parametrico 2.000-6.000 triangoli, pezzo protagonista fino a 10.000, oggetto generato da immagine o testo ridotto a 10.000-20.000, scena sotto i 300.000. Ogni esportazione stampa `PESO`.
- Pacchetto: `Esportazioni` (GLB e file per SketchUp), `Render`, esito del controllo norme nella `Scheda del progetto.md`.
