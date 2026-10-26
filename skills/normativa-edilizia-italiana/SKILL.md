---
name: normativa-edilizia-italiana
description: Mappa delle norme edilizie italiane ed europee per interni e design, con le regole su come citarle e cosa si può riprodurre. Usala quando serve una norma, una citazione, un chiarimento su un esito del controllo, o una regola nuova.
---

# Normativa edilizia italiana

## Principi

- Una norma si cita solo dopo averne letto il testo ufficiale, con data di verifica; mai a memoria.
- **Leggi e decreti** sono pubblici: si leggono su Normattiva (`normattiva.it`) e Gazzetta Ufficiale e si possono citare e codificare con articolo e comma.
- **Norme UNI, EN, ISO, CEI** sono protette dal diritto d'autore: si citano per numero, titolo e ambito, senza riprodurne il testo. I loro valori diventano regole solo se li fornisce chi ha accesso legittimo alla norma.
- **Norme comunali** (regolamento edilizio, NTA del piano regolatore, regolamento d'igiene) cambiano da comune a comune: se mancano, l'esito è `NON VERIFICABILE`.
- Ordine degli ambiti: Italia e Unione Europea, poi comune.
- Ogni rapporto ricorda che il controllo non sostituisce la responsabilità del tecnico abilitato.

## Cosa controlla il motore

Le regole stanno in dati, con fonte, articolo, estratto alla lettera e data di verifica (`agentic3d/regole/`):

- **Igiene degli alloggi**: DM Sanità 5 luglio 1975 (altezze, superfici, finestre, rapporto aeroilluminante 1/8, bagno) e deroga Salva Casa (DPR 380/2001, art. 24, commi 5-bis e 5-ter).
- **Accessibilità**: DM 14 giugno 1989 n. 236, art. 8 (porte, maniglie, corridoi, parapetti, scale, lavabo).
- **Edilizia scolastica**: DM 18 dicembre 1975 (altezza aule 3,00 m, superficie per alunno 1,80 e 1,96 mq). Dal 1996 vale solo come indice di riferimento (L. 23/1996): il rapporto lo dice. Non fissa un rapporto finestra/pavimento.
- **Norme tecniche**: indice UNI, EN, ISO e CEI senza testo.

## Norme di riferimento non ancora codificate

DPR 380/2001 (Testo Unico Edilizia); L. 13/1989 e DPR 503/1996 (accessibilità); DM 37/2008 (impianti); DM 3 agosto 2015 e DM 18 ottobre 2019 (prevenzione incendi); D.Lgs. 192/2005 e DM 26 giugno 2015 (energia); DM 17 gennaio 2018 (NTC) e Circolare 7/2019; DPCM 5 dicembre 1997 (requisiti acustici passivi); D.Lgs. 81/2008 (luoghi di lavoro); D.Lgs. 36/2023, allegato I.9 (BIM nei lavori pubblici); Regolamento Edilizio Tipo; Regolamento (UE) 305/2011; direttiva europea sulla prestazione energetica degli edifici.

Una domanda su queste norme si risponde leggendo il testo ufficiale e citandolo; il controllo automatico non le copre.

## Come citare nei rapporti

`atto, articolo (data di verifica)`, esempio: "DM 5 luglio 1975, art. 5 (verificato il 20 ottobre 2026)". Per una copia non primaria: "copia del testo, da riscontrare con la Gazzetta".

## Regola nuova

Aggiungere o cambiare una regola tocca il motore: si fa nel repository di sviluppo, seguendo `docs/sviluppo.md` (lettura del testo, estratto alla lettera, verifica online, test). All'utente finale si propone come richiesta, con la fonte.
