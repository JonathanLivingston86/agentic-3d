---
name: da-disegno-a-modello
description: Trasforma un disegno 2D (PDF da CAD, DXF, planimetria catastale, rilievo o schizzo a mano con quote) in scheda dati e modello 3D di una stanza o di un appartamento, con misure riscontrate. Usala quando l'utente porta una pianta, dei prospetti, uno schizzo o un disegno di arredo da realizzare in 3D.
---

# Da disegno 2D a modello 3D

## 1. Cartella del lavoro

Apri il lavoro con `lavoro-3d-ciclo-di-vita` (`nuovo_lavoro` con `disegni` copia il disegno in `Riferimenti`).

## 2. Leggere il disegno

Ogni misura ha **una sola fonte**, la più precisa disponibile: il disegno CAD, poi le quote scritte, mai la stima a occhio.

### Disegno CAD (DXF): lettura automatica

1. `importa_disegno` con il percorso del DXF: Agentic 3D legge da solo masse dei muri (anche disegnati con una faccia sola), vani con il tipo (comprese le ante scorrevoli disegnate lungo il muro), stanze con nome, altezza e superficie dai testi, controsoffitti e balconi, con le misure del CAD, e scrive la scheda e la **Tavola di lettura** (in `Riferimenti`). Non si legge il DXF in altri modi.
2. Mostra la tavola all'utente insieme ai punti "DA CONFERMARE" del rapporto (spessori ipotizzati, davanzali non scritti, superfici calcolate diverse da quelle scritte, stanze non chiuse) e aspetta la conferma o le correzioni.
3. Le correzioni si fanno con `modifica_scheda`; poi `costruisci`.
4. Se la lettura non trova i muri, chiedi all'utente come si chiama il livello dei muri nel suo CAD e ripeti con `livello_muri`.

**DWG**: Agentic 3D non lo legge. Chiedi all'utente di aprirlo nel suo programma CAD e salvarlo come DXF (Salva con nome > DXF). Niente convertitori scaricati. **PDF stampato da CAD**: chiedi se c'è il DXF; altrimenti trattalo come immagine (sotto).

### Foto, schizzo, PDF scansionato: lettura dell'agente con conferma

1. **Orientamento prima di tutto**: se molte quote si leggono capovolte, la foto è girata di 180 gradi; ruotala mentalmente prima di assegnare nord, sud, sinistra e destra.
2. Leggi le quote una per una e scrivi la scheda (`edificio` con `pareti`, `stanze`, `aperture`), con ogni lettura incerta tra le ipotesi.
3. **`tavola_di_lettura`**, poi mostra la tavola all'utente accanto alla foto: stanze, muri, aperture con le larghezze. Nessuna costruzione prima della sua conferma.
4. Per leggere foto e schizzi serve un modello AI con buona visione: se le quote non si leggono con sicurezza, chiedile all'utente invece di indovinarle.

### Schizzo a mano o rilievo (nessun vettore)

- Le quote scritte sono l'unica fonte: leggile una per una, girando l'immagine per quelle capovolte. Il disegno stampato di un catastale serve solo per la disposizione: non è in scala, e in foto è in prospettiva.
- Guarda dove cadono i segni di quota: tra due filetti interni è una misura al filo interno; lungo una parete misurano da muro a muro. Converti in `da_m` dall'angolo sud-ovest.
- **Le parziali devono chiudere sul totale.** Oltre 2-3 cm di scarto non si aggiusta in silenzio: scegli la lettura più coerente, scrivila tra i dubbi della scheda del progetto e chiedi una misura di controllo.
- Ciò che il disegno non dice (davanzale, ante, lato della cerniera, finiture) resta al valore predefinito di `completa()` oppure va in `ipotesi_applicate`. Gli arredi che lo schizzo non mostra non si aggiungono.
- Niente fascia di colore sulle pareti (`fascia_altezza_m`), colori o finiture particolari se il disegno o l'utente non li chiedono: pareti a tinta unica. Gli esempi del pacchetto mostrano il formato, non scelte da copiare.
- Destinazione diversa dall'alloggio (aula, ufficio): `destinazione: scuola` e simili; se mancano le regole della destinazione, scrivilo in `note_verifica`.

### Simboli della planimetria catastale (da far confermare all'utente prima di costruire)

- Finestre e porte finestre hanno lo stesso simbolo: chiedi quali sono porte finestre e dove sono i balconi, se il rilievo non lo segna (es. "PF"). Una larghezza che comprende due aperture vicine si divide con un montante.
- Rettangolo con la diagonale: di solito armadio a muro (chiedi da quale stanza si apre e se ha ante scorrevoli: `tipo: porta`, `apertura: scorrevole`). Piccolo rettangolo pieno accanto ai muri: di solito pilastro. Nel dubbio chiedi se è pilastro, cavedio o nicchia.
- Pilastri e risalti: si disegnano dal filo del muro verso la stanza (`da` sulla faccia del muro), uno per lato se il pilastro sporge da entrambi; un pezzo che parte dentro lo spessore di un muro dà l'avviso "si sovrappongono" e va ridisegnato.
- Muro più sottile solo attorno a una finestra: è una nicchia. La finestra sta nel pezzo sottile e i tratti accanto restano spessi: ogni cambio di filo interno è un pezzo di facciata a sé.

## 3. Scheda stanze

Esempi completi nel pacchetto (strumento `esempi`): `Aula di esempio` (stanza singola da uno schizzo) e `Appartamento di esempio` (pareti a rete, più stanze); `nuovo_lavoro` con `esempio` parte da una loro copia.

**Stanza singola** (`stanza:`): pareti, aperture e arredi con `parete` cardinale e `da_m` (distanza dall'angolo sud-ovest lungo la parete). Tipi di arredo: `letto`, `cassettiera_cestoni`, `piano`, `sgabello`, `pensile_libri`, `mensola_portalibri`, `quadro`, `arco_decorativo`, `tv`, `termosifone`, `tenda`, `bastone_tende`, `armadio_a_muro`, `poltrona_guscio`, `divano_imbottito`, `lavabo` (vasca incassata, rubinetto, mobile), `oggetto` (forme libere).

**Relazioni dichiarate, non ricopiate**: un piano su due colonne si scrive `su: {unita: [...], colonna: N}`, una tenda si appende al bastone, una mensola si appoggia a un'altra. Ogni coordinata si scrive una volta sola.

**Edificio o appartamento** (`edificio:`, partenza `nuovo_lavoro` con `tipo: edificio`). Coordinate globali in metri, X est, Y nord.
- **Pareti**: linee d'asse `{id, da: [x, y], a: [x, y], spessore_m}`, anche non ortogonali; si dividono da sole nei nodi a T e i giunti si chiudono puliti. Tra spessori molto diversi (facciata e tramezzo) il muro spesso prosegue e il sottile vi si appoggia. Parete curva: `{id, tipo: arco, centro, raggio_m, da_gradi, a_gradi, spessore_m, passo_gradi}`.
- **Facciate**: disegna la faccia esterna con `linea: filo_sinistro` (il muro sta a destra della linea) o `filo_destro`; lo spessore cresce verso l'interno, così i risalti del rilievo restano dentro. Un tramezzo che arriva dove la facciata cambia spessore è gestito dai giunti: i pezzi non si spostano a mano.
- **Stanze**: `{id, tipo, poligono_m}` al filo interno, anche concave. L'avviso "lato che non coincide con una parete" (oltre 2 cm) si corregge nel poligono. Dalle stanze vengono solai, fascia di colore e controllo norme per stanza.
- **Aperture**: `finestra`, `portafinestra` (dal pavimento, 2,40 m se non scritto), `porta` (anche `apertura: scorrevole`). Sulla parete: `parete: <id>`, `lato: sinistra|destra` (dove sta la stanza guardando da `da` ad `a`), `da_m` dall'inizio della parete. Le porte si aprono verso la stanza del `lato` (`apre_verso: opposto` per l'altra), cerniera alla fine del vano (`cerniera: inizio` per l'altro lato).
- **Arredi**: stessi tipi, con `stanza` + `parete` cardinale oppure `parete: <id>` + `lato`, oppure `posizione_m` e `rotazione_gradi` in coordinate globali. `oggetto` con `parti` e `forma`: scatola, scatola_parete, cilindro, asse, estrusione, torno, sfera, prisma, smussato, piano_forato, vasca, cuscino (materiali dalla tavolozza).
- **Piani**: elenco `piani` con `altezza_m` (2,70 se non scritta) e `spessore_solaio_m`; quote e soffitti si calcolano da soli. `edificio.soffitto: false` lascia tutto aperto sopra.
- Limiti: aperture su pareti curve solo dentro un segmento; arredi su pareti curve non supportati.

## 4. Controllo, costruzione, verifica

`controlla_norme`, poi `costruisci` (strumenti MCP; comandi in `lavoro-3d-ciclo-di-vita`).

- Ogni costruzione stampa `GEOMETRIA`: compenetrazioni oltre 1 mm sono ERRORI (non si consegna), fessure di 0,3-6 mm, oggetti sospesi, arredi nell'arco di una porta o davanti a una finestra sono AVVISI da correggere o spiegare. Leggi dove si aprono le porte prima di disporre gli arredi.
- **Riscontro con il disegno**: per ogni quota letta (dimensioni della stanza, altezza, aperture, posizione e profondità degli arredi) confronta il valore della scheda con il disegno, tolleranza 2,5 mm sui vettori. Una quota che non torna si corregge nella scheda, mai nel modello.
- Guarda il risultato (SketchUp o render) e confrontalo con il disegno: misure, posizioni, orientamento.

## 5. Consegna

Riferisci: come è stato letto il disegno (scala, quote riscontrate), le ipotesi, l'esito del controllo norme (FAIL, NON VERIFICABILE, note) e il pacchetto (`esporta-per-sketchup`). Un'incongruenza trovata (finestra sotto il rapporto 1/8, davanzale sotto 1,00 m) è un risultato utile: va detta. I colori scelti per un disegno in bianco e nero sono una scelta tua: dichiarali. Pulizia finale con `lavoro-3d-ciclo-di-vita`.
