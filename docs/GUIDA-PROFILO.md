# Guida al profilo e alla taratura

ElBandito ordina i bandi su di te. Questa guida spiega cosa compilare, cosa cambia ogni campo e come tarare il punteggio finché l'ordine somiglia alle tue scelte.

## In breve: i primi 15 minuti

1. Compila il profilo in uno dei tre modi descritti sotto. Contano soprattutto: tema e discipline, anno di nascita, luoghi casa e luoghi vicini, lingue, quota massima e temi.
2. Scegli un preset di pesi (`equilibrato` va bene per iniziare).
3. Guarda le fonti: metti in pausa quelle che non ti interessano e aggiungi i festival e le fondazioni che segui.
4. Fai un giro, apri i primi 10 bandi e decidi: *Mi interessa* o *Scarta*.
5. Dopo circa 15 decisioni chiedi a Claude Code di ritoccare i pesi (vedi [Taratura](#taratura-sulle-tue-scelte)).

## Dove stanno i tuoi dati

Tutto ciò che è tuo sta nella **cartella dati**, che git ignora:

| Come usi ElBandito | Cartella dati |
| --- | --- |
| Dal repository clonato | `dati/` |
| Come plugin di Claude Code | `~/.elbandito/` |
| Con una cartella scelta da te | quella indicata in `ELBANDITO_DATI` |

```
<cartella dati>/
  foglio/        le sei schede come CSV: BANDI, FONTI, PROFILO, ENTI, CANDIDATURE, LOG
  personale/     i tuoi file di partenza (profilo.csv, enti.csv, fonti.csv, insieme_oro.csv)
  archivio.sqlite
  .env           chiavi API facoltative (parti da .env.esempio)
```

Quando la scheda PROFILO viene creata per la prima volta, ElBandito parte da `personale/profilo.csv` se esiste, altrimenti da `seed/profilo.csv`: l'artista immaginario di Bologna. Vale lo stesso per enti, fonti e insieme d'oro.

`elbandito configura` e lo strumento MCP `aggiorna_profilo` tengono aggiornata da soli la copia in `personale/profilo.csv`. Così se cancelli `foglio/` o passi al foglio Google, riparti dai tuoi valori.

> Non copiare mai i tuoi file in `seed/`: è la parte pubblica del repository.

## Tre modi per compilare il profilo

**1. Parlando con Claude Code.** Apri la cartella in Claude Code, o usa il plugin, e scrivi «impostiamo il mio profilo». La skill `elbandito-avvio` fa le domande a gruppi, salva le risposte e ricalcola i punteggi.

**2. Con il questionario da terminale.**

```bash
uv run elbandito configura
```

Premi Invio per tenere il valore proposto. Ricava le coordinate della città da OpenStreetMap e alla fine ti fa scegliere un preset di pesi.

**3. A mano.** Usa la vista **Profilo** della dashboard (`uv run elbandito dashboard`), con una nota d'aiuto sotto ogni campo e i preset dei pesi. Oppure modifica la scheda PROFILO del foglio Google, se usi l'automazione nel cloud. Dopo le modifiche premi *Ricalcola ora*, oppure lancia `uv run elbandito ricalcola`.

Le liste vanno separate da virgole. I campi non compilati prendono i valori predefiniti.

## Campo per campo

**Filtro** vuol dire che un bando che non corrisponde viene **escluso**, e il motivo è scritto nella scheda (si vede con "mostra esclusi"). **Punteggio** vuol dire che il campo cambia solo l'ordine.

### Chi sei

| Campo | Effetto | Esempio |
| --- | --- | --- |
| `Tema` | Guida la ricerca web e i filoni | `fotografia`, `cinema documentario`, `illustrazione` |
| `Discipline piene` | Punteggio: disciplina al 100% | `fotografia, lens-based, documentario, photography` |
| `Discipline metà` | Punteggio: disciplina al 50% | `arti visive, multidisciplinare, video` |
| `Anno di nascita` | Filtro: limiti d'età dei bandi | `1990`: nel 2026 escluso dagli under 35 |
| `Nazionalità` | Filtro: bandi riservati a certe nazionalità | `italiana` |

Metti nelle discipline anche i termini in inglese: molti bandi internazionali scrivono *photography*, non *fotografia*.

### Dove sei

| Campo | Effetto | Esempio |
| --- | --- | --- |
| `Base`, `Città di riferimento` | Mappa e distanze | `Bologna` |
| `Base lat`, `Base lon` | Coordinate della città di riferimento | `44.4949`, `11.3426` |
| `Regioni di residenza` | Filtro: bandi "riservati ai residenti in…" (regioni o città) | `Emilia-Romagna` |
| `Regioni con partner` | I bandi per residenti in queste regioni non sono esclusi ma segnalati: "serve un partner residente" | `Lazio, Roma` |
| `Luoghi casa` + `Etichetta casa` | Punteggio: geografia al 100% | `Emilia-Romagna, Bologna, Modena, Parma` |
| `Luoghi vicini` + `Etichetta vicini` | Punteggio: geografia all'80% | `Toscana, Veneto, Lombardia, Firenze` |
| `Paese` | Punteggio: geografia al 60% | `Italia` |
| `Paesi UE` | Punteggio: geografia al 40% ("Europa") | già compilato |

Il resto del mondo vale il 20%, i bandi solo online il 50%, quelli senza luogo il 30%. I luoghi si riconoscono per parola nel testo di città, regione e paese del bando: elenca la regione e le città principali, comprese le isole e le province che ti interessano.

### Come ti candidi

| Campo | Effetto | Esempio |
| --- | --- | --- |
| `Si candida come` | Filtro: con `persona`, i bandi riservati a enti e imprese sono esclusi. Se nomini un ente (associazione, università capofila, partita IVA) restano, segnalati con "serve un ente proponente" | `persona`, `persona e con ente capofila (università, associazione)` |
| `Lingue` | Filtro: un bando solo in altre lingue è escluso | `italiano, inglese` |
| `Quota massima` | Filtro sopra la soglia; sotto, il punteggio "costo" scende con la quota | `50` |
| `Giorni minimi preparazione` | Filtro: scadenze troppo vicine | `7` |
| `Disponibilità fuori casa (settimane)` | Promemoria per le residenze lunghe | `4` |

C'è un filtro sempre attivo: una call **a pagamento senza premio, mostra, viaggio o alloggio** viene esclusa come "vanity call".

### Il tuo lavoro

| Campo | Effetto | Consiglio |
| --- | --- | --- |
| `Temi` | Punteggio: ogni tema ritrovato nel bando alza il "tema" (pieno con due) | 4-8 parole precise: `migrazione, paesaggio, acqua, archivio` |
| `Curriculum` | Entra nei prompt, nella ricerca e nelle bozze di statement | Due righe: premi, residenze, mostre. Solo dati professionali |
| `Parole chiave` | Ricerche nei siti WordPress e su SearXNG | In italiano e in inglese |

## Come si calcola il punteggio

Sei componenti valgono ciascuna da 0 al proprio peso. Il totale viene riportato su 100.

| Componente | Peso base | Pieno quando… |
| --- | --- | --- |
| disciplina | 25 | il bando nomina una delle `Discipline piene` (metà con le `Discipline metà`) |
| tema | 5 | due o più `Temi` compaiono nel bando |
| geografia | 10 | si svolge nei `Luoghi casa` |
| valore | 15 | premio di circa 5.000 € o più, con viaggio, alloggio o mostra |
| prestigio | 15 | ente di livello 1 in ENTI, citato da più fonti |
| costo | 15 | gratuito |

**Esempio.** Il bando d'esempio "Premio Portici" (Bologna, gratuito, 3.000 € più mostra, temi *territorio* e *memoria*), con il profilo d'esempio:

| disciplina | tema | geografia | valore | prestigio | costo | somma | punteggio |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 25 | 5 | 10 | 11,4 | 3 | 15 | 69,4 su 85 | **82** |

Il prestigio è basso perché l'ente non è in ENTI. Se lo aggiungi al livello 1, la componente passa da 3 a 15 e il punteggio da 82 a 96. Nella dashboard ogni scheda mostra queste barre.

### Preset dei pesi

Se non sai che numeri dare, scegli un'intenzione: dalla dashboard (vista Profilo), da `elbandito configura`, o chiedendo a Claude Code («usa il preset vicino a casa»).

| Preset | disciplina | tema | geografia | valore | prestigio | costo | Per chi |
| --- | --- | --- | --- | --- | --- | --- | --- |
| equilibrato | 25 | 5 | 10 | 15 | 15 | 15 | per cominciare |
| conta il tema | 20 | 25 | 10 | 15 | 15 | 15 | ha una ricerca precisa e vuole bandi tematici |
| vicino a casa | 20 | 10 | 30 | 15 | 10 | 15 | non può spostarsi molto |
| carriera | 20 | 10 | 5 | 20 | 30 | 15 | punta a festival e istituzioni note |
| budget stretto | 20 | 10 | 10 | 20 | 10 | 30 | vuole solo bandi gratuiti e pagati |

Conta il rapporto tra i pesi, non la somma.

### Taratura sulle tue scelte

Ogni *Mi interessa* o *Scarta* resta nello Storico del bando, insieme al dettaglio del punteggio. Dopo circa 15 decisioni chiedi a Claude Code: «guarda le mie ultime decisioni e proponi nuovi pesi». La skill `elbandito-valuta` confronta i bandi tenuti con quelli scartati, trova la componente che li separa davvero, propone i pesi e li applica solo dopo il tuo ok. Ripeti ogni tanto: i gusti cambiano.

Segnali che vale la pena ritoccare:
- **Scarti spesso bandi in alto**: forse il valore o il prestigio pesano troppo rispetto al tema.
- **Ti interessano bandi lontani da casa ma in basso**: abbassa la geografia.
- **Molti bandi giusti risultano esclusi**: controlla lingue, quota massima e `Si candida come`, non i pesi.

## Enti noti (scheda ENTI)

Gli enti alzano la componente prestigio:

| Livello | Prestigio |
| --- | --- |
| 1 | 100% |
| 2 | 70% |
| 3 | 45% |
| non in elenco | 20% |

Si aggiunge +15% se il bando è segnalato da due fonti, +30% da tre. Il seed contiene festival, fondazioni e premi pubblici; aggiungi quelli che conosci tu. La colonna `Storico` serve per annotare le tue esperienze passate con quell'ente. È personale: tienila nella tua cartella dati, non in `seed/`.

## Fonti (scheda FONTI)

Si aggiungono dalla dashboard (vista Fonti), con lo strumento MCP `aggiungi_fonte` o nel foglio.

| Connettore | Quando | Parametri (colonna `Parametri`, coppie `chiave=valore` separate da `;`) |
| --- | --- | --- |
| `rss` | il sito ha un feed | `filtro=bando\|open call\|premio` (regex), `max=30` |
| `wordpress` | sito WordPress (prova `https://sito/wp-json/`) | `cerca=fotografia\|residenza`, `tipi=posts\|pages`, `giorni=21` |
| `listing` | pagina-elenco di open call | `pattern=/open-call/[^/]+/?$` (regex sugli href), `filtro=…`, `max=15` |
| `watch` | pagina "open call" di un festival o di una fondazione | nessuno: si estrae solo quando la pagina cambia |
| `eu_sedia` | bandi UE Funding & Tenders | `programma=43251814` (Europa Creativa), `testo=…` |
| `browser` | siti con molto JavaScript | richiede l'extra `[browser]` |

Consigli:
- per le fonti `watch` usa l'**URL esatto** della pagina open call, non la home: meno rumore, meno estrazioni inutili;
- `Frequenza` può essere `giornaliera`, `settimanale` (il lunedì) o `mensile`;
- una fonte con 3 o più errori consecutivi compare in rosso: spesso ha cambiato indirizzo;
- dopo una ricerca web, Claude Code ti propone i domini che portano bandi buoni come nuove fonti.

## Insieme d'oro (test della rete di fonti)

`insieme_oro.csv` elenca opportunità che la tua rete di fonti *deve* trovare. Nella tua versione mettici quelle che hai davvero colto in passato, in `personale/insieme_oro.csv`. Con `uv run elbandito richiamo`, o lo strumento `richiamo_insieme_oro`, vedi quante sono coperte dalle fonti attive e quante sono state trovate. Rifallo quando cambi le fonti.

| Colonna | Significato |
| --- | --- |
| `Opportunità` | il nome del bando |
| `Riconosci` | regex sul titolo o sull'ente (`driving energy`) |
| `Fonti attese` | domini che dovrebbero segnalarla |
| `Canale` | `fonti` oppure `passaparola` (non trovabile dalle fonti fisse) |

## Motori

| Campo | Valori |
| --- | --- |
| `Motore estrazione` | `auto` (Gemini, poi Claude API, poi Claude Code) · `gemini` · `claude-api` · `agente` (sempre Claude Code) |
| `Motore ricerca` | `agente` (Claude Code) · `claude-api` (batch settimanale, a consumo) · `searxng` |

Senza chiavi API tutto funziona con Claude Code. Le chiavi servono solo per l'automazione senza di te: vanno nel file `.env` della cartella dati, mai nel profilo.

## Un secondo tema

Per cercare, per esempio, bandi di cinema documentario, usa un'altra cartella dati:

```bash
ELBANDITO_DATI=~/elbandito-cinema uv run elbandito configura
```

Poi imposta `Tema`, le discipline, le parole chiave e fonti adatte (festival di cinema, fondi per lo sviluppo). Il codice non cambia.
