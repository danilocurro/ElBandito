---
name: elbandito-avvio
description: Primo avvio e profilo di ElBandito. Usala quando l'utente vuole provare ElBandito, configurarlo, impostare o cambiare il proprio profilo d'artista (età, città, temi, lingue, quota massima, discipline), o chiede "come si usa".
---

# Avvio di ElBandito

ElBandito trova bandi, residenze, open call, premi e grant per artisti, li legge in schede e li ordina con un punteggio 0-100 sul profilo dell'utente. Lavori con gli strumenti MCP del server `elbandito`.

## 1. Guarda a che punto siamo

Chiama `stato`. Dalla risposta capisci:

- `bandi_totali = 0`: è un'installazione nuova;
- `configurazione.backend`: `locale` (file CSV nella cartella dati) o `google` (foglio Google);
- `configurazione.chiave_gemini` / `chiave_anthropic`: se mancano entrambe va benissimo, l'estrazione la fai tu (vedi skill `elbandito-raccolta`).

## 2. Per una prova veloce

Se l'utente vuole solo vedere come funziona: `crea_dati_esempio`, poi `apri_dashboard`. Spiega che i 9 bandi sono inventati e servono a mostrare punteggi, esclusioni (under 30, solo enti, call a pagamento senza premio), pipeline, mappa e calendario.

## 3. Il profilo (il passo che conta)

Il profilo d'esempio è di un artista immaginario di Bologna. Chiama `leggi_profilo` e fai all'utente poche domande, a gruppi, non un interrogatorio:

1. **Chi**: tema principale (fotografia, cinema, illustrazione…), discipline in cui lavora, anno di nascita (serve solo per i limiti d'età), nazionalità.
2. **Dove**: città base (ricava tu lat/lon e la città di riferimento), regione di residenza, luoghi "casa" e luoghi "vicini" per il punteggio geografico.
3. **Come**: lingue in cui può candidarsi, quota d'iscrizione massima, se si candida solo come persona o anche con un'associazione o una partita IVA, settimane che può passare fuori casa.
4. **Cosa**: 4-8 temi ricorrenti del suo lavoro e un curriculum in due righe (premi, residenze, mostre).

Salva ogni risposta con `aggiorna_profilo(campo, valore)`, usando i nomi di campo esatti di `leggi_profilo`. Le liste vanno separate da virgole. Alla fine chiama `ricalcola_punteggi`.

Privacy: nel profilo vanno solo dati professionali. Non chiedere indirizzo, email, telefono o dati economici. La cartella dati non va mai su git.

## 4. Fonti

`elenco_fonti` mostra circa 40 fonti italiane ed europee. Chiedi se l'utente segue festival, fondazioni o riviste che mancano e aggiungili con `aggiungi_fonte`:

- `watch` per una pagina "open call" che cambia;
- `rss` per un feed;
- `wordpress` per un sito WordPress (cerca con le parole chiave del profilo);
- `listing` per una pagina-elenco, con parametri `pattern=<regex sugli href>; max=10`.

## 5. Primo giro

Proponi un giro veloce su 3-4 fonti (`esegui_giro` con `fonti=["F02","F08","F09"]`), poi la skill `elbandito-raccolta` per estrarre le pagine in coda. A fine giro, `apri_dashboard`.

## Facoltativo: chiavi API e automazione

Con `GEMINI_API_KEY` (gratuita) o `ANTHROPIC_API_KEY` nel file `.env` della cartella dati, il collettore estrae da solo e può girare ogni giorno su GitHub Actions scrivendo su un foglio Google. Senza chiavi funziona tutto lo stesso, ma l'estrazione e la ricerca le fai tu in Claude Code. Il README spiega la configurazione.
