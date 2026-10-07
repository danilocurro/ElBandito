# ElBandito

**Trova, legge e ordina bandi, residenze, open call, premi e grant per artisti visivi.**

ElBandito tiene d'occhio una rete di fonti: riviste d'arte, siti WordPress, l'API dei bandi UE, aggregatori di residenze e pagine "open call" di festival e fondazioni. Da ogni pagina estrae una scheda strutturata con scadenza, quota, valore, eleggibilità e materiali richiesti, e la ordina con un punteggio da 0 a 100 sul tuo profilo d'artista.

Ogni punteggio è spiegato, e i bandi che non fanno per te (limite d'età, residenza, quota troppo alta, solo enti, call a pagamento senza premio) vengono marcati come esclusi, con il motivo. Poi ti accompagna fino alla candidatura: pipeline, checklist dei materiali, scadenze a ritroso, calendario .ics. **Non invia mai niente da solo.**

Il primo tema configurato è la fotografia d'autore, ma tema, fonti, profilo e pesi stanno nei dati, non nel codice.

## Tre modi di usarlo

| | Ti serve | Cosa ottieni |
| --- | --- | --- |
| **1. Dentro Claude Code** (consigliato) | [Claude Code](https://claude.com/claude-code) + [uv](https://docs.astral.sh/uv/) | Server MCP con 24 strumenti, 4 skill, regole. Claude raccoglie, estrae le schede, cerca sul web, spiega i punteggi, scrive bozze di statement. **Nessuna chiave API necessaria** |
| **2. Dashboard locale** | uv | L'interfaccia completa nel browser (Oggi, Esplora con mappa e calendario, Pipeline, Enti, Fonti, Profilo) sui tuoi dati locali |
| **3. Automatico nel cloud** (facoltativo) | GitHub, un foglio Google, chiave Gemini gratuita | Giro ogni mattina su GitHub Actions, foglio Google come database, web app Apps Script ed email: digest del lunedì, avvisi, promemoria |

I tre modi usano gli stessi dati e la stessa interfaccia: si possono combinare.

## Prova in due minuti

```bash
git clone https://github.com/<utente>/ElBandito.git
```

```bash
cd ElBandito && uv run elbandito demo
```

```bash
uv run elbandito dashboard
```

`demo` crea nove bandi **inventati** (marcati "(esempio)") che passano dai filtri e dal punteggio veri, con il profilo d'esempio di un artista immaginario. La dashboard si apre su `http://127.0.0.1:8787`.

## Il tuo profilo

ElBandito parte con il profilo di un artista immaginario. Per avere un ordine che abbia senso per te, compila il tuo in uno dei tre modi qui sotto. Bastano dieci minuti.

| Modo | Come |
| --- | --- |
| Parlando con Claude Code | «impostiamo il mio profilo» (skill `elbandito-avvio`) |
| Questionario da terminale | `uv run elbandito configura` |
| A mano | vista **Profilo** della dashboard: ogni campo ha una nota d'aiuto e ci sono i preset dei pesi |

I campi decisivi sono: tema e discipline, anno di nascita (limiti d'età), luoghi "casa" e "vicini", lingue, quota massima, temi del tuo lavoro. Poi scegli un preset di pesi (`equilibrato`, `conta il tema`, `vicino a casa`, `carriera`, `budget stretto`). Dopo circa 15 decisioni (*Mi interessa* o *Scarta*), Claude Code può ritoccare i pesi sulle tue scelte reali.

Tutto resta nella tua cartella dati, esclusa da git. **[docs/GUIDA-PROFILO.md](docs/GUIDA-PROFILO.md)** spiega ogni campo, il calcolo del punteggio con un esempio, i preset, la taratura, enti, fonti e insieme d'oro.

## In Claude Code

**Come progetto**: apri la cartella `ElBandito` in Claude Code e approva il server MCP `elbandito` quando te lo chiede (la prima volta `uv` installa le dipendenze). Poi chiedi, per esempio:

- «prova ElBandito con i dati d'esempio e apri la dashboard»
- «impostiamo il mio profilo»
- «fai il giro delle fonti ed estrai i bandi»
- «cerca residenze estive in Sud Europa con alloggio pagato e senza quota»
- «perché B0007 ha 62 punti?» · «approfondisci B0003» · «scrivimi lo statement per B0001»
- «ho inviato la candidatura per B0008, l'esito arriva il 10 gennaio»

**Come plugin**, per averlo in ogni progetto:

```
/plugin marketplace add <utente>/ElBandito
```

```
/plugin install elbandito@elbandito
```

Da plugin i dati stanno in `~/.elbandito/`. Dal clone stanno in `dati/` dentro la cartella.

### Cosa c'è per Claude Code

- **`.mcp.json`**: il server `elbandito` (`uv run elbandito mcp`). Strumenti per consultare (`stato`, `cerca_bandi`, `scheda_bando`, `leggi_profilo`, `elenco_fonti`), raccogliere (`esegui_giro`, `pagine_da_estrarre`, `salva_schede`, `aggiungi_da_link`, `contesto_ricerca`), agire (`registra_azione`, `conferma_scadenza`, `spunta_materiale`, `salva_nota`, `salva_approfondimento`), configurare (`aggiorna_profilo`, `applica_preset_pesi`, `aggiungi_fonte`, `attiva_fonte`, `ricalcola_punteggi`) e vedere (`apri_dashboard`, `esporta_calendario`, `crea_dati_esempio`, `richiamo_insieme_oro`).
- **Skill** in `skills/`: `elbandito-avvio` (prova e profilo), `elbandito-raccolta` (giro ed estrazione), `elbandito-ricerca` (ricerca web e nuove fonti), `elbandito-valuta` (analisi, cerca a fondo, statement, stato, pesi).
- **`CLAUDE.md`**: le regole. Mai inviare candidature, mai spacciare per certe le date da verificare, privacy dei dati.
- **`.claude-plugin/`**: manifest del plugin e del marketplace.

### Claude Code fa da modello

Senza chiavi API il collettore scarica e ripulisce le pagine, poi le mette in coda. Claude Code le legge con `pagine_da_estrarre` e rimanda le schede con `salva_schede`. Il server applica comunque le stesse difese dell'estrazione automatica:

- schema validato;
- ogni dato critico (scadenza, quota, eleggibilità) deve citare una frase che **esiste davvero** nel testo, altrimenti il bando resta "da verificare";
- le date passano da `dateparser`, e le scadenze passate si scartano;
- i duplicati arrivati da più fonti si uniscono.

## Motori: chi legge le pagine e chi cerca sul web

Si scelgono nella scheda PROFILO, senza toccare il codice.

| Campo | Valori | Note |
| --- | --- | --- |
| `Motore estrazione` | **`auto`** · `gemini` · `claude-api` · `agente` | `auto`: Gemini se c'è `GEMINI_API_KEY` (piano gratuito), poi Claude Haiku se c'è `ANTHROPIC_API_KEY`, altrimenti la coda per Claude Code |
| `Motore ricerca` | **`agente`** · `claude-api` · `searxng` | `agente`: la ricerca la fa Claude Code (skill `elbandito-ricerca`). `claude-api`: un Message Batch settimanale con ricerca web, utile per l'automazione nel cloud (pochi euro al mese). `searxng`: un'istanza tua di SearXNG, gratuita ma da mantenere |

Le chiavi vanno in un file `.env` nella cartella dati: parti da `.env.esempio`. Non vanno mai nel codice né nel foglio.

## I tuoi dati

- Tutto ciò che è tuo sta nella cartella dati: le schede del foglio in CSV (`foglio/`), l'archivio SQLite, `.env` e `personale/`. È esclusa da git.
- `seed/` contiene solo esempi anonimi: circa 40 fonti pubbliche italiane ed europee, enti noti, un profilo d'esempio e un insieme d'oro di prova.
- `personale/` (dentro la cartella dati) contiene i tuoi file di partenza: `profilo.csv`, `enti.csv`, `fonti.csv` e `insieme_oro.csv`, con le stesse colonne dei file in `seed/`. Hanno la precedenza sul seed quando il foglio viene creato. `elbandito configura` e Claude Code tengono aggiornata da soli la copia del profilo.
- Il foglio Google, se lo usi, sostituisce i CSV: imposta `ELBANDITO_SHEET_ID` e le credenziali del service account.

## Automazione nel cloud (facoltativa)

Serve se vuoi che ElBandito giri da solo ogni giorno, anche a computer spento.

1. **Fork privato** di questo repository.
2. **Foglio Google** vuoto. In [Google Cloud](https://console.cloud.google.com): abilita la Google Sheets API, crea un service account e scarica la chiave JSON. Condividi il foglio con l'email del service account come Editor.
3. **Secrets del repository** (*Settings → Secrets and variables → Actions*): `ELBANDITO_SHEET_ID`, `GOOGLE_SERVICE_ACCOUNT_JSON` (il contenuto del JSON), `GEMINI_API_KEY`. Se vuoi la ricerca settimanale via API, anche `ANTHROPIC_API_KEY` e `Motore ricerca = claude-api` nel PROFILO.
4. *Actions → Su richiesta dalla web app → Run workflow* con comando `prepara`: crea le schede dal seed. Poi aggiungi la *variable* `ELBANDITO_ATTIVO = sì` (stessa pagina dei secrets, scheda Variables): solo da quel momento `giornaliero.yml` gira ogni mattina e `settimanale.yml` il lunedì.
5. **Web app**: nel foglio, *Estensioni → Apps Script*, copia `apps-script/Codice.gs`, `Index.html` e il manifest `appsscript.json` (oppure usa [clasp](https://github.com/google/clasp)).
   - In *Proprietà script* imposta `GEMINI_API_KEY` (assistente), `GITHUB_REPO` (`utente/ElBandito`) e `GITHUB_TOKEN` (token fine-grained con *Actions: write* solo su questo repository).
   - Esegui una volta `installaTrigger`.
   - Pubblica come *App web*, eseguita come te, con accesso "Solo io".

La web app è la stessa interfaccia della dashboard locale. In più ha l'assistente Gemini e le email, che vanno solo a te.

## Come funziona

```
fonti: RSS · WordPress (wp-json) · API UE Funding & Tenders · pagine-elenco · pagine "open call" · link incollati
        │
        ▼
collettore (elbandito/)  ──  testo pulito (trafilatura)  ──  estrazione: Gemini | Claude API | Claude Code via MCP
        │                                                    + verifica delle citazioni + date (dateparser)
        ▼
deduplica (impronta + RapidFuzz)  ──  filtri rigidi + punteggio 0-100 spiegato  ──  BANDI · FONTI · PROFILO · ENTI · CANDIDATURE · LOG
        │                                                                              (CSV locali o foglio Google)
        ▼
Claude Code (MCP + skill)   ·   dashboard locale   ·   web app Apps Script + email
```

**Punteggio**: disciplina 25, tema 5, geografia 10, valore 15, prestigio 15 e costo 15. I pesi si cambiano nel PROFILO e il totale viene riportato su 100. La geografia segue i `Luoghi casa` e i `Luoghi vicini` del profilo, poi il paese, l'Europa e il resto del mondo. Il prestigio sale per gli enti in ENTI e per i bandi segnalati da più fonti.

**Ciclo di vita**: Nuovo → Da preparare → Pronto → Inviato → Vinto / Non selezionato, oppure Scartato o In attesa edizione. La prossima azione si calcola a ritroso dalla scadenza. Ogni decisione resta nello Storico: dopo circa 15 decisioni si possono ritoccare i pesi sui gusti reali (skill `elbandito-valuta`).

**Etica di raccolta**: lo user-agent si dichiara, `robots.txt` viene rispettato e c'è una pausa di 2-3 secondi per dominio. I siti che rispondono 403 restano fuori. Dagli articoli si conservano solo i dati del bando e le frasi citate.

```
ElBandito/
  elbandito/           collettore, servizi, server MCP, dashboard, demo
  skills/              skill per Claude Code (anche in .claude/skills)
  apps-script/         Codice.gs + Index.html (l'unica interfaccia, usata anche in locale)
  seed/                fonti, enti, profilo d'esempio, insieme d'oro (anonimi)
  docs/                guida al profilo e alla taratura
  tests/               test automatici, senza rete né chiavi
  .github/workflows/   giornaliero · settimanale · su-richiesta · test
  .mcp.json  CLAUDE.md  .claude-plugin/
```

## Comandi

```bash
uv run elbandito --help
```

I comandi sono: `configura`, `demo`, `dashboard`, `mcp`, `coda`, `prepara`, `giornaliero`, `settimanale`, `link URL`, `approfondisci ID`, `ricalcola` e `richiamo` (copertura e richiamo dell'insieme d'oro, il test di regressione della rete di fonti).

```bash
uv run pytest -q
```

## Limiti noti

- I siti con protezioni anti-bot si vedono solo con la ricerca web. ElBandito non aggira le protezioni.
- Le scadenze estratte possono sbagliare: per questo citano la frase d'origine. Le date "da verificare" non generano promemoria finché non le confermi.
- I social network non vengono letti: un post si aggiunge incollandone il link.
- Molte fonti `watch` puntano alla home del sito: conviene sostituirle con l'URL esatto della pagina "open call".
- Le fonti cambiano indirizzo: il LOG e la vista Fonti segnalano quelle in errore.

## Licenza

MIT.
