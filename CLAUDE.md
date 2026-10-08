# ElBandito — regole per Claude

ElBandito trova bandi, residenze, open call, premi e grant per artisti visivi, li legge in schede strutturate e li ordina sul profilo dell'utente. In questo repository il server MCP `elbandito` è configurato in `.mcp.json`; le skill sono in `skills/` (collegate da `.claude/skills`).

## Usare ElBandito

- Per tutto ciò che riguarda bandi, profilo, fonti e candidature usa gli strumenti MCP `elbandito`, non i file CSV a mano.
- Skill: `elbandito-avvio` (prova e profilo), `elbandito-raccolta` (giro ed estrazione), `elbandito-ricerca` (ricerca web), `elbandito-valuta` (analisi, statement, stato, pesi).
- Non inviare mai candidature, email o messaggi per conto dell'utente. Statement e lettere sono bozze da copiare.
- Cambia lo stato di un bando (`registra_azione`) o il profilo solo su richiesta o conferma dell'utente.
- Una scadenza estratta diventa "sicura" solo se la frase citata esiste nel testo, o dopo una conferma esplicita. Non spacciare per certa una data "da verificare".
- Raccolta etica: rispetta robots.txt e il ritmo del collettore; se un sito blocca l'accesso, non aggirarlo.

## Privacy

- I dati dell'utente stanno nella cartella dati (`dati/` nel repository, `~/.elbandito` come plugin): CSV, archivio SQLite, `.env` e `personale/`. Sono esclusi da git e **non vanno mai committati**, copiati in `seed/` o citati in issue e PR.
- `seed/` contiene solo esempi anonimi. Il profilo d'esempio è un artista immaginario.
- Nei prompt e nelle ricerche usa solo dati professionali del profilo.

## Sviluppo

- Python ≥ 3.11, pacchetto unico `elbandito/`. Test: `uv run --extra dev pytest -q` (devono restare verdi, e senza rete né chiavi).
- Il foglio si legge e si scrive per nome di colonna (`modelli.COLONNE`). Le date sono stringhe `aaaa-mm-gg`, fuso Europe/Rome.
- La logica delle azioni è in `servizi.py` ed è duplicata in `apps-script/Codice.gs`: se cambi una, allinea l'altra.
- L'interfaccia è una sola (`apps-script/Index.html`) per tre backend: Apps Script, dashboard locale (`/api/<nome>`) e dati d'esempio.
- Commenti e testi in italiano, nello stile del codice esistente.
