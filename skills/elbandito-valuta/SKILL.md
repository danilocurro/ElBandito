---
name: elbandito-valuta
description: Analizza e confronta i bandi di ElBandito, spiega i punteggi, approfondisce un ente ("cerca a fondo"), prepara bozze di statement e checklist, aggiorna lo stato delle candidature e ritocca i pesi del punteggio. Usala per domande come "quali bandi mi convengono?", "perché questo ha 62?", "approfondisci B0012", "scrivimi lo statement", "ho inviato la candidatura".
---

# Valutare e agire sui bandi

## Domande sui bandi

Usa `cerca_bandi` (filtri: `testo`, `tipo`, `stato`, `entro_giorni`, `quota_max`, `punteggio_min`, `mostra_esclusi`) e `scheda_bando`. Rispondi citando gli ID (B0007) e, per ognuno, scadenza, giorni rimasti, quota, valore e una riga sul perché.

## Spiegare un punteggio

`scheda_bando` dà il `Dettaglio punteggio` per componente: disciplina, tema, geografia, valore, prestigio, costo. Confrontalo con i pesi di `leggi_profilo`: ogni componente vale al massimo il suo peso, e il totale è riportato su 100. Spiega cosa alza e cosa abbassa il punteggio, e ricorda che `Esclusione` (filtri rigidi) conta più del punteggio.

## Cerca a fondo

Per un bando che interessa: cerca sul web l'ente (anni di attività, partner, segnali di "vanity call"), la giuria o i curatori, i vincitori delle ultime edizioni, e controlla che scadenza e quota coincidano con la pagina ufficiale. Scrivi al massimo 250 parole con i link e salvale con `salva_approfondimento`. Se la scadenza sulla pagina ufficiale è chiara, proponi `conferma_scadenza`.

## Bozza di statement o lettera

Parti dal profilo (`leggi_profilo`: temi, curriculum) e dalla scheda (temi, materiali richiesti, lingua). Scrivi una bozza sobria in prima persona, nella lingua richiesta dal bando, entro il limite di battute se indicato. Non inventare premi, mostre o progetti: se ti serve un dato, chiedilo. **È una bozza da copiare: non inviare mai nulla a nessuno.**

## Stato e checklist

Gli stati seguono il ciclo: interessa → pronto → inviato → vinto / non_selezionato, oppure scarta, prossimo_anno, riapri, archivia. Usa `registra_azione` **solo quando l'utente lo dice o conferma**: la data della prossima azione si calcola a ritroso dalla scadenza. Per i materiali c'è `spunta_materiale(id, voce)`.

## Ritoccare i pesi

Dopo circa 15 decisioni ("interessa" o "scarta", che restano nella colonna Storico), confronta il `Dettaglio punteggio` dei bandi tenuti con quello dei bandi scartati: quale componente separa davvero le scelte? Proponi nuovi pesi con una spiegazione. Applicali con `aggiorna_profilo("Peso <componente>", valore)` e `ricalcola_punteggi` solo dopo l'ok dell'utente.

## Vedere tutto

`apri_dashboard` apre l'interfaccia completa: Oggi, Esplora con lista, mappa e calendario, Pipeline, Enti, Fonti e Profilo. `esporta_calendario` produce un file .ics per Google Calendar.
