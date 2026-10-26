---
name: image-text-to-3d-interni
description: Decide come ottenere un oggetto 3D da una foto o da un testo per un interno (arredi, decori), con controllo di licenza e costi, e lo porta alle misure reali e alla pulizia necessaria prima dell'uso. Usala quando l'utente chiede image to 3D, text to 3D, o un arredo da una foto.
---

# Image to 3D e text to 3D per interni

## Prima la scheda parametrica

Per stanze e arredi la strada più economica e affidabile è la scheda: un prompt breve ("cameretta per due bambini 5 x 3 m, due letti, scrivania") diventa una scheda con i valori mancanti conformi alle norme (`interni-italia-progettazione`) e il motore costruisce senza generare mesh. Anche un arredo da una foto si ricostruisce di solito meglio con le forme libere (`oggetto`, `cuscino`) e le misure del produttore.

## Quando un modello generato va bene

- **Sì:** decori e arredi non critici visti a distanza media (vaso, lampada, pianta, cuscini, una sedia di fantasia).
- **No:** muri, solai, aperture, scale, sanitari, cucine su misura, tutto ciò che il controllo norme misura: nascono dalla scheda.
- Un oggetto generato ha scala e proporzioni casuali: si riporta sempre alle misure reali.

## Albero decisionale (costo crescente)

1. **Esiste già gratis?** Poly Haven (CC0) o librerie con licenza chiara.
2. **In locale, costo zero.** TripoSR (licenza MIT) gira con circa 6 GB di memoria video; qualità media, adatta a decori semplici.
3. **Servizi gratuiti online.** Spazi di Hugging Face con modelli a licenza permissiva (es. TRELLIS, MIT), se il materiale dell'utente non è riservato. Controlla la licenza dello Spazio e del modello prima di usare il risultato per un cliente.
4. **A pagamento, solo con approvazione dell'utente e un tetto di spesa:** Tripo, Meshy. Il piano gratuito di Meshy impone CC BY 4.0 (citare Meshy), quello di Tripo è non commerciale: per lavoro per clienti serve un piano a pagamento o la licenza confermata per iscritto.

Da testo funziona meglio in due passi: testo, immagine di riferimento, immagine a 3D.

## Licenze

- **Hunyuan3D (Tencent) è escluso:** la sua licenza non si applica in Unione Europea, Regno Unito e Corea del Sud, nemmeno in locale.
- Registra nella `Scheda del progetto.md`: modello o servizio, licenza, data, link.

## Pulizia obbligatoria

1. Orientamento: fronte verso -Y, alto verso +Z.
2. Misure reali per categoria con un solo fattore di scala uniforme, poi scala applicata.
3. Origine al centro della base.
4. Sotto i 20.000 triangoli per oggetto d'arredo (riduzione con Decimate in Blender, controllando la forma).
5. Niente vertici sciolti né facce interne; bordi chiusi.
6. Materiali con nomi leggibili, texture al massimo 2K, nome dell'oggetto in italiano.
