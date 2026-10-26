---
name: interni-italia-progettazione
description: Porta un brief di interni (stanza, alloggio, arredi) a un modello coerente con le regole italiane ed europee e con le buone pratiche di arredo, con scheda dati e controllo delle norme prima della consegna. Usala quando l'utente chiede di progettare, arredare, modificare o verificare una stanza o un alloggio.
---

# Progettazione di interni in Italia

## Flusso

1. **Brief.** Raccogli destinazione, tipo di intervento (`nuova`, `ristrutturazione`, `esistente`), occupanti, comune, altitudine. Un dato che cambia l'esito si chiede; gli altri diventano ipotesi scritte nella scheda.
2. **Scheda dati.** `Scheda stanze.yaml` del lavoro, con `leggi_scheda` e `scrivi_scheda` (`lavoro-3d-ciclo-di-vita`). Da un disegno: `da-disegno-a-modello`.
3. **Controllo prima di costruire.** `controlla_norme`. Con un FAIL correggi la scheda o proponi la modifica all'utente; si costruisce su una scheda che fallisce solo se l'utente lo chiede.
4. **Costruzione.** `costruisci` (esporta sempre, render solo se richiesti) (`esporta-per-sketchup`, `render-con-blender`).
5. **Controllo dopo.** Rapporto `GEOMETRIA`, misure rilette nel modello, controllo norme rieseguito.
6. **Consegna.** FAIL, NON VERIFICABILE e avviso sulla responsabilità del tecnico abilitato. La formula è "nessun FAIL nelle regole automatizzate", mai "a norma".

Una richiesta di modifica ("sposta il divano di 30 cm verso la finestra") si esegue nella scheda, poi si esporta: gli oggetti che dipendono da quello spostato (il quadro sopra il divano, il tavolino accanto) si spostano con lui, e lo si dice.

## Brief breve: i valori mancanti

`agentic3d.scheda.completa()` riempie i valori mancanti in modo da rispettare le regole generali e li elenca come **ipotesi usate**. Un valore dato dall'utente non viene mai sovrascritto.

| Valore mancante | Predefinito | Base |
|---|---|---|
| Altezza | 2,70 m | DM 5 luglio 1975, art. 1 |
| Larghezza finestra | rapporto aeroilluminante di almeno 1/8 con margine 10% (altezza 1,40 m) | DM 5 luglio 1975, art. 5 |
| Quota del davanzale | 1,00 m | DM 236/1989, art. 8.1.3 |
| Luce netta della porta | 0,80 m (altezza 2,10 m) | DM 236/1989, art. 8.1.1 |
| Altezza maniglia | 0,90 m | DM 236/1989, art. 8.1.1 |
| Spessore pareti | 0,10 m; 0,30 m se c'è una finestra | prassi |
| Comune, intervento | Roma, nuova | scelta di partenza |

## Controllore delle norme

- Tipi di locale: `camera_singola`, `camera_doppia`, `soggiorno`, `cucina`, `bagno`, `corridoio`, `disimpegno`, `ripostiglio`, `monostanza_1p`, `monostanza_2p`.
- Esiti: `PASS` (rispettata con i dati forniti), `FAIL` (cita regola e fonte), `NON VERIFICABILE` (dato mancante o verifica non automatizzabile: resta tale), `NON APPLICABILE` (non vale per destinazione o intervento).
- **Deroga Salva Casa** (altezze fino a 2,40 m, monostanza fino a 20 o 28 mq): servono nella scheda `intervento` esistente o ristrutturazione, `asseverazione_salva_casa: true`, `adattabilita_verificata: true`, `recupero_o_progetto_alternativo: true`. Sono dichiarazioni del progettista: si chiedono all'utente.
- Norme EN e ISO (luce naturale, illuminazione, comfort) sono indicizzate senza testo: si citano per numero. Diventano regole solo con valori forniti da chi ha accesso legittimo alla norma.
- Limiti: norme comunali non verificate; fattore di luce diurna e temperature non calcolati; il controllo non sostituisce il tecnico abilitato.

## Misure correnti di progettazione (prassi, non norma)

Ordini di grandezza per impostare un arredo quando il brief non li dà; si presentano come prassi, mai come prescrizioni.

| Elemento | Misura indicativa |
|---|---|
| Tavolo da pranzo, altezza piano | 0,72-0,76 m |
| Seduta di sedia, altezza | 0,43-0,47 m |
| Divano, altezza seduta / profondità | 0,40-0,45 m / 0,85-1,00 m |
| Letto matrimoniale / singolo (rete) | 1,60-1,80 x 2,00 m / 0,80-0,90 x 2,00 m |
| Passaggio libero tra arredi | almeno 0,70 m, meglio 0,90 m |
| Armadio, profondità | 0,60 m, 0,55 m minimo |
| Divano - tavolino basso | 0,40-0,45 m |
| Divano - televisore | circa 3 volte la diagonale (55 pollici: 2,5-3,5 m) |
| Quadro sopra il divano | bordo basso 20-40 cm sopra lo schienale, largo circa 2/3 del divano |
| Interruttori / prese | 0,90-1,10 m / 0,30 m da terra; accessibilità: 0,40-1,40 m (DM 236) |

**Cucina**: piano a 0,90 m, profondità 0,60 m; pensili a 1,50 m (almeno 0,55-0,65 m sopra i fuochi); almeno 1,10-1,20 m liberi davanti al piano; lavello tra frigo e fuochi, non vicini tra loro; bancone a 1,05 m con sgabelli a seduta 0,75 m. Il lavello è un foro nel piano (`piano_forato`) con vasca incassata (`vasca`) e mobile sotto aperto in alto.

**Ingresso**: un armadio va dove non intralcia l'apertura della porta d'ingresso (rapporto `GEOMETRIA`).

## Arredare "per assonanza"

- Si parte dal pezzo dato (es. una poltrona di design in velluto senape con base nera): se ne ricavano materiali, colori ed epoca, e gli altri arredi li riprendono senza ripeterli tutti.
- Il pezzo dato si modella con le misure del produttore, citate nella scheda.
- Prima gli usi (zona conversazione, televisore, luce da lettura), poi i controlli: arco delle porte, davanti delle finestre, passaggi.
- Sanitari: `lavabo` (vasca incassata nel piano, rubinetto, mobile sospeso o a terra, `mobile: false` per il solo lavabo). Mai una scatola piena per un lavabo o un lavello: per il lavello della cucina, `oggetto` con `piano_forato` e `vasca`.
- Imbottiti: `poltrona_guscio`, `divano_imbottito`, o la forma libera `cuscino` (superellissoide liscio: `tondo`, `piega_m` per schienali avvolgenti, `inclina_gradi`, `bottoni_m` per il capitonné).
- Oggetti ripetuti (moduli di cucina, sgabelli, lampade, sedie): `componente: <nome>`, così in SketchUp si modificano tutti insieme e il file pesa meno.
- Materiali: la tavolozza ha colori, non texture con venature; per un materiale nuovo si sceglie il più vicino e lo si dichiara.

## Peso del modello

Arredo parametrico 2.000-6.000 triangoli; pezzo protagonista fino a 10.000; oggetto da immagine o testo ridotto a 10.000-20.000; scena sotto i 300.000 (SketchUp resta fluido). Ogni esportazione stampa `PESO`.
