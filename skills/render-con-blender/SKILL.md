---
name: render-con-blender
description: Render, luci e controlli visivi di un modello Agentic 3D con Blender (facoltativo), anche tramite il ponte MCP. Usala quando servono immagini del progetto, un `.blend`, oppure un ritocco o un oggetto da fare direttamente in Blender.
---

# Render con Blender

Blender è facoltativo: geometria, GLB e file per SketchUp li produce il motore in Python. Blender riceve il GLB, rimette i materiali della tavolozza, aggiunge luci e camere e fa i render. Per cambiare una parete o un arredo si cambia la scheda, mai la scena in Blender.

## Render di un progetto

`costruisci` con `render` (comando: `agentic3d costruisci "<Nome>" --render --esporta`)

- Blender lavora in sottofondo, senza finestra e senza ponte, e si chiude da solo: fa le viste (pianta, dall'alto, una per stanza, più quelle in `edificio.viste`), salva il `.blend` in `Modello` e le immagini in `Render`.
- Durante il render: lo strumento manda l'avanzamento ("render 3 di 7: Vista Cucina, mancano circa 40 secondi") e la `Galleria dei render.html` si apre nel browser e mostra ogni vista appena è pronta. Riferisci all'utente l'avanzamento e dove guardare. Le stime partono dalla seconda vista e diventano precise dal secondo render dello stesso lavoro.
- Dopo il render, l'impostazione `dopo_render` decide se il `.blend` si apre in un Blender normale per continuare lì: `automatico` (predefinito) solo se SketchUp non è installato, `apri` sempre, `chiudi` mai (strumento `impostazioni`). Se l'utente ha modificato il `.blend` a mano, il nuovo va accanto con "(nuovo)" nel nome e l'originale non si tocca: dillo all'utente. Le modifiche fatte in Blender non tornano nella scheda: per cambiare il progetto si cambia la scheda.
- Guarda ogni immagine prima di consegnarla e confrontala con il brief. Una vista nera o tagliata di solito è una camera dentro un arredo: aggiungi o correggi una vista nella scheda (`edificio.viste`, per nome).

## Ritocchi tramite il ponte MCP

Il ponte (server `blender`, `mcp-for-blender` con versione fissata) non serve per i render. Serve solo per guardare (`look`), per piccoli ritocchi e per oggetti fuori dal motore, dove è installato.

1. Se gli strumenti `blender` non compaiono, avvia Blender con `agentic3d blender avvia`. Se ancora non ci sono, dillo all'utente invece di aggirare il ponte.
2. Chiama `get_scene_info`: la scena può non essere vuota.
3. La modalità sicura è attiva: il codice importa solo `bpy`, `bmesh`, `mathutils` e moduli Python puri. File e cartelle si gestiscono con operatori `bpy` e percorsi assoluti.
4. Un passo logico per chiamata, poi `look` e confronto con il brief prima di proseguire.

## Regole di costruzione in Blender

- Metri, `scale_length = 1.0`; trasformazioni applicate prima di esportare.
- Nomi leggibili in italiano per oggetti, materiali e collezioni (`Muro Nord`, `Intonaco bianco`), collezioni `Architettura`, `Arredi`, `Luci e camera`, `Riferimenti`.
- Origine alla base, fronte verso -Y.
- Due facce sovrapposte sullo stesso piano danno macchie nere: lascia 1 mm tra pezzi vicini.
- Percorsi sempre assoluti: con un percorso relativo Blender salva nella sua cartella di lavoro.
- Colori: trasformazione "Standard" con luci moderate (con "AgX" i pastelli si scoloriscono).

## Blender 5.x

- Niente COLLADA (`.dae`): glTF (`export_scene.gltf`), FBX, OBJ.
- `Mesh.use_auto_smooth` non esiste più: modificatore o facce smussate.
- Motori: `'CYCLES'`, `'BLENDER_EEVEE'`; nel dubbio leggi `bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items.keys()`.
- GPU: il render sceglie da solo la scheda video (`CUDA` per NVIDIA, `METAL` su Mac, `HIP` per AMD, `ONEAPI` per Intel), altrimenti il processore; `'OPTIX'` richiede driver recenti.
- `bpy.ops.wm.read_factory_settings` spegne il ponte: per pulire la scena rimuovi oggetti e dati.
- Davanti a un errore d'API leggi il messaggio o la documentazione e cambia approccio.

## Qualità e costi

- Bozza: Cycles 64 campioni, 960 x 540, riduzione del rumore. Finale: 256 campioni, 1920 x 1080. Texture al massimo 2K.
- `generate_3d` e asset a pagamento solo con approvazione dell'utente. Poly Haven (CC0) è sempre ammesso.
- Chiudi Blender a fine lavoro: il server del ponte accetta codice da qualunque programma locale.
