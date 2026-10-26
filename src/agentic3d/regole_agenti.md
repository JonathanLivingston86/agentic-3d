# Cartella dei lavori di Agentic 3D

Regole per qualunque agente AI che lavora in questa cartella (scritte da Agentic 3D, che le aggiorna da solo).

1. **I modelli si creano e si modificano solo con gli strumenti MCP di Agentic 3D** (`nuovo_lavoro`, `leggi_scheda`, `scrivi_scheda`, `modifica_scheda`, `costruisci`, `verifica_installazione`) seguendo le Skill di Agentic 3D (prima `lavoro-3d-ciclo-di-vita`). Mai con altri programmi o con codice scritto al momento: niente three.js, pagine web, server locali, script di Blender o file 3D fatti a mano.
2. **Se gli strumenti di Agentic 3D non ci sono, fermarsi.** Eseguire `agentic3d verifica` (su Windows `%USERPROFILE%\.local\bin\agentic3d.exe verifica`, su macOS `~/.local/bin/agentic3d verifica`) e dire all'utente cosa manca e come rimediare: di solito rilanciare l'installatore di Agentic 3D e riavviare l'agente. Nel frattempo non costruire niente.
3. **Le misure vengono solo dal disegno, dal brief o dall'utente.** Una quota illeggibile o mancante si chiede; un valore scelto per completare si dichiara come ipotesi. Non si inventano stanze, aperture, spessori o altezze.
4. **Non creare file o cartelle qui a mano**: ogni lavoro ha la struttura creata da `nuovo_lavoro` (Riferimenti, Modello, Esportazioni, Render, schede).
5. **Niente programmi scaricati o installati** dall'agente (convertitori, librerie, eseguibili da internet), e niente codice interno di Agentic 3D richiamato dal terminale: solo gli strumenti MCP.
6. **File DWG**: Agentic 3D legge i DXF. Per un DWG si chiede all'utente di salvarlo come DXF dal proprio programma CAD (Salva con nome > DXF), senza convertirlo in altri modi.
7. **Si racconta solo ciò che è già successo**, dopo il risultato dello strumento: niente annunci di passi futuri o già fatti da altri.
