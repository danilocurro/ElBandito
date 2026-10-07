---
name: elbandito-ricerca
description: Ricerca web di bandi, residenze e open call che le fonti fisse di ElBandito non vedono. Usala per "cerca altre opportunità", "ricerca settimanale", "trovami residenze/premi su …", o per scoprire nuove fonti da monitorare.
---

# Ricerca web di nuove opportunità

Questa ricerca sostituisce il batch Claude via API: la fai tu con la ricerca web di Claude Code, e il risultato passa dalle stesse verifiche delle fonti fisse.

1. `contesto_ricerca`. Ottieni il profilo, i `filoni`, il budget `ricerche_massime`, i `bandi_noti` (da non riproporre) e i `domini_monitorati`.
2. Se l'utente ha chiesto qualcosa di preciso ("residenze estive in Sud Europa con alloggio"), usa quello come filone unico. Altrimenti distribuisci il budget sui filoni, 2-3 ricerche ciascuno. Cerca in italiano e in inglese.
3. Tieni solo le opportunità con scadenza futura, aperte a persone, coerenti con il profilo (disciplina, età, nazionalità, quota massima). Preferisci la pagina ufficiale dell'ente all'articolo che ne parla. Scarta quelle già in `bandi_noti`.
4. Per ogni candidata: `aggiungi_da_link(url)`. Se ricevi `da_estrarre`, estrai le schede seguendo la skill `elbandito-raccolta` (citazioni esatte dal testo della pagina, non dai risultati di ricerca) e chiama `salva_schede`. Se la pagina dà accesso negato, non aggirarlo: dillo all'utente e passa oltre.
5. Alla fine riporta i bandi nuovi con punteggio e scadenza. Elenca anche i **domini che hanno dato più di un bando buono e non sono in `domini_monitorati`**, e proponi di aggiungerli come fonti (`aggiungi_fonte`, connettore `watch` sulla pagina open call). Aggiungili solo se l'utente è d'accordo.

Limiti: niente social network (Instagram, Facebook). L'utente può incollare un link a mano con la skill `elbandito-raccolta`. Rispetta il budget di ricerche.
