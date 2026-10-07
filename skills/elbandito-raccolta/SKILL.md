---
name: elbandito-raccolta
description: Raccoglie nuovi bandi dalle fonti di ElBandito ed estrae le schede dalle pagine in coda. Usala per "cerca nuovi bandi", "fai il giro", "aggiorna il radar", "estrai le pagine in coda", o quando l'utente incolla il link di un bando o di un post.
---

# Raccolta ed estrazione

## Giro delle fonti

1. `esegui_giro` (tipo `giornaliero`). Per un giro veloce passa `fonti` con alcuni ID di FONTI. Il giro rispetta robots.txt e aspetta 2-3 secondi per sito, quindi può durare qualche minuto.
2. Se nella risposta `pagine_in_coda > 0`, non c'è una chiave API e l'estrazione tocca a te: passa alla sezione successiva.

## Estrazione delle pagine in coda

Ripeti finché `restanti` è 0, o finché l'utente vuole:

1. `pagine_da_estrarre(limite=3)`. Leggi `istruzioni` e `campi`.
2. Per ogni pagina decidi se contiene opportunità **aperte** a cui una persona può candidarsi. Notizie, recensioni e annunci di vincitori → `salva_schede(url, [])`.
3. Per ogni opportunità compila una scheda con i nomi di campo esatti:
   - obbligatori: `titolo`, `ente`, `tipo` (residenza | premio | open call | grant | festival | commissione | borsa | altro), `disciplina`;
   - `scadenza` va copiata come è scritta ("15 gennaio 2027"). La conversione in data la fa il server;
   - **`scadenza_citazione`, `quota_citazione` ed `eleggibilita_citazione` sono frasi copiate carattere per carattere dal testo.** Se una frase non c'è, lascia vuoti sia il dato sia la citazione. Il server controlla che ogni frase esista: se è inventata, il bando diventa "da verificare";
   - `quota_iscrizione_eur`: 0 solo se il testo dice "gratuito", `null` se non lo dice;
   - `eta_max`, `eta_min`, `solo_enti`, `residenza_richiesta`, `nazionalita_ammesse` e `lingue_candidatura` servono ai filtri rigidi: compilali quando il testo li dice;
   - non inventare nulla. Una pagina con più bandi (rubriche, elenchi) dà più schede.
4. `salva_schede(url, schede)`. Nella risposta ci sono gli ID creati, punteggio, esclusione ed `errori` di schema: se ce ne sono, correggi e richiama per la stessa pagina.

## Link incollato dall'utente

`aggiungi_da_link(url)`. Con una chiave API il bando viene estratto subito. Altrimenti ricevi `da_estrarre.testo`: estrai come sopra e chiama `salva_schede` con lo stesso url.

## Alla fine

Riassumi in poche righe: quanti bandi nuovi, i 3-5 migliori (titolo, punteggio, scadenza, motivazione) e quelli "da verificare" con scadenza vicina. Proponi `apri_dashboard` se l'utente vuole guardarli. Non cambiare lo stato dei bandi senza che l'utente lo chieda.
