/**
 * ElBandito — web app (Apps Script) legata al foglio "ElBandito".
 *
 * Il foglio è l'unico database. Il collettore Python (GitHub Actions) scrive
 * i bandi nuovi; qui si decide e si agisce: stato, checklist, note,
 * calendario, notifiche email (solo a te), assistente.
 *
 * Chiavi in Proprietà dello script → UserProperties (mai nel codice):
 *   GEMINI_API_KEY   assistente e bozze di statement
 *   GITHUB_TOKEN     token "fine-grained" con permesso Actions: write sul solo repo
 *   GITHUB_REPO      es. tuo-utente/ElBandito
 * Se lo script non è legato al foglio, anche SHEET_ID.
 */

var FUSO = 'Europe/Rome';
var STATI = ['Nuovo', 'Da preparare', 'Pronto', 'Inviato', 'Vinto', 'Non selezionato',
             'Scartato', 'In attesa edizione', 'Archiviato'];
var MODELLO_GEMINI = 'gemini-flash-lite-latest';

// ---------------------------------------------------------------- web app

function doGet() {
  return HtmlService.createTemplateFromFile('Index').evaluate()
    .setTitle('ElBandito')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL); // incorporabile in WordPress
}

// ---------------------------------------------------------------- foglio

function prop_(k) { return PropertiesService.getUserProperties().getProperty(k) || PropertiesService.getScriptProperties().getProperty(k); }

function foglio_() {
  var id = prop_('SHEET_ID');
  return id ? SpreadsheetApp.openById(id) : SpreadsheetApp.getActiveSpreadsheet();
}

function oggi_() { return Utilities.formatDate(new Date(), FUSO, 'yyyy-MM-dd'); }

function cella_(v) {
  if (v instanceof Date) return Utilities.formatDate(v, FUSO, 'yyyy-MM-dd');
  return v === null || v === undefined ? '' : v;
}

/** Righe come oggetti {intestazione: valore}, con il numero di riga in _riga. */
function leggi_(nome) {
  var sh = foglio_().getSheetByName(nome);
  if (!sh || sh.getLastRow() < 2) return [];
  var valori = sh.getDataRange().getValues();
  var intest = valori[0];
  var out = [];
  for (var i = 1; i < valori.length; i++) {
    if (valori[i].join('') === '') continue;
    var o = { _riga: i + 1 };
    for (var j = 0; j < intest.length; j++) o[intest[j]] = cella_(valori[i][j]);
    out.push(o);
  }
  return out;
}

function intestazioni_(sh) { return sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0]; }

/** Scrive solo le colonne indicate, per nome di intestazione. */
function scrivi_(nome, riga, campi) {
  var sh = foglio_().getSheetByName(nome);
  var intest = intestazioni_(sh);
  Object.keys(campi).forEach(function (k) {
    var j = intest.indexOf(k);
    if (j >= 0) sh.getRange(riga, j + 1).setValue(campi[k]);
  });
}

function aggiungi_(nome, oggetto) {
  var sh = foglio_().getSheetByName(nome);
  var intest = intestazioni_(sh);
  sh.appendRow(intest.map(function (k) { return oggetto[k] === undefined ? '' : oggetto[k]; }));
}

function trovaBando_(id) {
  var b = leggi_('BANDI').filter(function (r) { return r.ID === id; })[0];
  if (!b) throw new Error('Bando non trovato: ' + id);
  return b;
}

function piuGiorni_(iso, n) {
  var base = iso ? new Date(iso + 'T12:00:00') : new Date();
  base.setDate(base.getDate() + n);
  return Utilities.formatDate(base, FUSO, 'yyyy-MM-dd');
}

function nonPrimaDiOggi_(iso) { return iso && iso < oggi_() ? oggi_() : iso; }

// ---------------------------------------------------------------- lettura

function getBandi() {
  var profilo = {}, profiloNote = {};
  leggi_('PROFILO').forEach(function (r) { profilo[r.Campo] = r.Valore; profiloNote[r.Campo] = r.Note || ''; });
  var bandi = leggi_('BANDI').filter(function (b) { return b.Stato !== 'Archiviato'; });
  bandi.forEach(function (b) {
    try { b['Dettaglio punteggio'] = b['Dettaglio punteggio'] ? JSON.parse(b['Dettaglio punteggio']) : {}; }
    catch (e) { b['Dettaglio punteggio'] = {}; }
  });
  var candidature = {};
  leggi_('CANDIDATURE').forEach(function (c) {
    try { c.Checklist = c.Checklist ? JSON.parse(c.Checklist) : []; } catch (e) { c.Checklist = []; }
    candidature[c['ID bando']] = c;
  });
  return JSON.stringify({
    oggi: oggi_(),
    bandi: bandi,
    candidature: candidature,
    profilo: profilo,
    profiloNote: profiloNote,
    fonti: leggi_('FONTI'),
    enti: leggi_('ENTI'),
    log: leggi_('LOG').slice(-15).reverse(),
    stati: STATI,
    linkGitHub: prop_('GITHUB_REPO') ? 'https://github.com/' + prop_('GITHUB_REPO') + '/actions' : ''
  });
}

// ---------------------------------------------------------------- azioni

/**
 * Ciclo di vita del bando: stesse regole di registraAzione del gestionale.
 * extra: { dataEsito, nota }
 */
function registraAzione(id, azione, extra) {
  extra = extra || {};
  var b = trovaBando_(id);
  var scad = b.Scadenza;
  var regole = {
    interessa:       ['Da preparare', 'Preparare i materiali', scad ? nonPrimaDiOggi_(piuGiorni_(scad, -10)) : piuGiorni_('', 7)],
    scarta:          ['Scartato', '', ''],
    pronto:          ['Pronto', 'Inviare la candidatura', scad ? nonPrimaDiOggi_(piuGiorni_(scad, -2)) : piuGiorni_('', 2)],
    inviato:         ['Inviato', "Attendere l'esito", extra.dataEsito || ''],
    vinto:           ['Vinto', 'Pianificare', piuGiorni_('', 7)],
    non_selezionato: ['Non selezionato', 'Annotare il feedback', piuGiorni_('', 7)],
    prossimo_anno:   ['In attesa edizione', 'Controllare la nuova call', aperturaStimata_(b)],
    riapri:          ['Nuovo', 'Valutare', piuGiorni_('', 3)],
    archivia:        ['Archiviato', '', '']
  };
  var r = regole[azione];
  if (!r) throw new Error('Azione sconosciuta: ' + azione);
  var storico = (b.Storico ? b.Storico + '\n' : '') + oggi_() + ' ' + azione.replace('_', ' ') + (extra.nota ? ' — ' + extra.nota : '');
  scrivi_('BANDI', b._riga, {
    'Stato': r[0], 'Prossima azione': r[1], 'Data prossima azione': r[2],
    'Aggiornato il': oggi_(), 'Storico': storico
  });
  if (azione === 'interessa') assicuraCandidatura_(b);
  if (azione === 'inviato' || azione === 'vinto' || azione === 'non_selezionato') {
    var campi = { 'Aggiornato il': oggi_() };
    if (azione === 'inviato') { campi['Inviata il'] = oggi_(); if (extra.dataEsito) campi['Data esito'] = extra.dataEsito; }
    else campi['Esito'] = azione === 'vinto' ? 'Vinto' : 'Non selezionato';
    var c = assicuraCandidatura_(b);
    scrivi_('CANDIDATURE', c._riga, campi);
  }
  return getBandi();
}

function aperturaStimata_(b) {
  var base = b.Apertura || (b.Scadenza ? piuGiorni_(b.Scadenza, -60) : '');
  return base ? piuGiorni_(base, 365 - 14) : piuGiorni_('', 300);
}

function assicuraCandidatura_(b) {
  var c = leggi_('CANDIDATURE').filter(function (r) { return r['ID bando'] === b.ID; })[0];
  if (c) return c;
  var voci = String(b['Materiali richiesti'] || '').split(/[;\n]/).map(function (s) { return s.trim(); })
    .filter(String).map(function (s) { return { voce: s, fatto: false }; });
  if (!voci.length) voci = ['Portfolio', 'Statement', 'CV'].map(function (s) { return { voce: s, fatto: false }; });
  aggiungi_('CANDIDATURE', {
    'ID bando': b.ID, 'Titolo': b.Titolo, 'Checklist': JSON.stringify(voci), 'Aggiornato il': oggi_()
  });
  return leggi_('CANDIDATURE').filter(function (r) { return r['ID bando'] === b.ID; })[0];
}

function salvaChecklist(id, checklist, cartella) {
  var c = assicuraCandidatura_(trovaBando_(id));
  var campi = { 'Checklist': JSON.stringify(checklist), 'Aggiornato il': oggi_() };
  if (cartella !== undefined) campi['Cartella'] = cartella;
  scrivi_('CANDIDATURE', c._riga, campi);
  return getBandi();
}

function salvaFeedback(id, feedback) {
  var c = assicuraCandidatura_(trovaBando_(id));
  scrivi_('CANDIDATURE', c._riga, { 'Feedback': feedback, 'Aggiornato il': oggi_() });
  return getBandi();
}

function salvaNote(id, note) {
  var b = trovaBando_(id);
  scrivi_('BANDI', b._riga, { 'Note': note, 'Aggiornato il': oggi_() });
  return getBandi();
}

/** La scadenza estratta dall'AI entra nei promemoria solo dopo questa conferma. */
function confermaScadenza(id, data) {
  var b = trovaBando_(id);
  scrivi_('BANDI', b._riga, {
    'Scadenza': data || b.Scadenza, 'Scadenza confermata': 'sicura', 'Aggiornato il': oggi_(),
    'Storico': (b.Storico ? b.Storico + '\n' : '') + oggi_() + ' scadenza confermata a mano'
  });
  return getBandi();
}

function aggiornaFonte(id, campi) {
  var f = leggi_('FONTI').filter(function (r) { return r.ID === id; })[0];
  if (!f) throw new Error('Fonte non trovata');
  scrivi_('FONTI', f._riga, campi);
  return getBandi();
}

function aggiungiFonte(f) {
  var fonti = leggi_('FONTI');
  var n = fonti.reduce(function (m, r) { var k = parseInt(String(r.ID).replace(/\D/g, ''), 10); return k > m ? k : m; }, 0) + 1;
  aggiungi_('FONTI', {
    'ID': 'F' + (n < 10 ? '0' + n : n), 'Nome': f.Nome, 'URL': f.URL, 'Connettore': f.Connettore || 'watch',
    'Parametri': f.Parametri || '', 'Frequenza': f.Frequenza || 'settimanale', 'Livello': f.Livello || '',
    'Tipo': f.Tipo || '', 'Attiva': 'sì', 'Bandi portati': 0, 'Errori consecutivi': 0, 'Note': 'Aggiunta dalla web app'
  });
  return getBandi();
}

function salvaProfilo(campo, valore) {
  var r = leggi_('PROFILO').filter(function (x) { return x.Campo === campo; })[0];
  if (r) scrivi_('PROFILO', r._riga, { 'Valore': valore });
  else aggiungi_('PROFILO', { 'Campo': campo, 'Valore': valore });
  return getBandi();
}

// ---------------------------------------------------------------- collettore su richiesta

/** Fa partire il workflow "su-richiesta" su GitHub: link | approfondisci | ricalcola | giornaliero. */
function avviaCollettore(comando, argomento) {
  var token = prop_('GITHUB_TOKEN'), repo = prop_('GITHUB_REPO');
  if (!token || !repo) throw new Error('Imposta GITHUB_TOKEN e GITHUB_REPO nelle proprietà dello script');
  var r = UrlFetchApp.fetch('https://api.github.com/repos/' + repo + '/actions/workflows/su-richiesta.yml/dispatches', {
    method: 'post', muteHttpExceptions: true, contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' },
    payload: JSON.stringify({ ref: 'main', inputs: { comando: comando, argomento: argomento || '' } })
  });
  if (r.getResponseCode() >= 300) throw new Error('GitHub ha risposto ' + r.getResponseCode() + ': ' + r.getContentText().slice(0, 200));
  return 'Avviato. Il risultato compare nel foglio fra un paio di minuti.';
}

function aggiungiDaLink(url) {
  if (!/^https?:\/\//.test(url)) throw new Error('Serve un link completo (https://…)');
  return avviaCollettore('link', url);
}

function cercaAFondo(id) { trovaBando_(id); return avviaCollettore('approfondisci', id); }

// ---------------------------------------------------------------- calendario .ics

function esportaICS() {
  var righe = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//ElBandito//IT', 'CALSCALE:GREGORIAN', 'X-WR-CALNAME:ElBandito'];
  var adesso = Utilities.formatDate(new Date(), 'UTC', "yyyyMMdd'T'HHmmss'Z'");
  leggi_('BANDI').forEach(function (b) {
    if (!b.Scadenza || ['Nuovo', 'Da preparare', 'Pronto'].indexOf(b.Stato) < 0 || b.Esclusione) return;
    var giorno = String(b.Scadenza).replace(/-/g, '');
    var titolo = (b['Scadenza confermata'] === 'sicura' ? '' : '[da verificare] ') + 'Scadenza: ' + b.Titolo;
    righe.push('BEGIN:VEVENT', 'UID:' + b.ID + '-scadenza@ElBandito', 'DTSTAMP:' + adesso,
      'DTSTART;VALUE=DATE:' + giorno, 'SUMMARY:' + ics_(titolo),
      'DESCRIPTION:' + ics_((b.Ente || '') + ' · punteggio ' + (b.Punteggio || '') + ' · ' + (b['Link bando'] || '')),
      'URL:' + (b['Link bando'] || ''),
      'BEGIN:VALARM', 'TRIGGER:-P7D', 'ACTION:DISPLAY', 'DESCRIPTION:' + ics_(titolo), 'END:VALARM',
      'END:VEVENT');
  });
  righe.push('END:VCALENDAR');
  return righe.join('\r\n');
}

function ics_(s) { return String(s).replace(/\\/g, '\\\\').replace(/[,;]/g, function (c) { return '\\' + c; }).replace(/\n/g, '\\n'); }

// ---------------------------------------------------------------- assistente (Gemini)

/**
 * modo: 'domanda' (sui bandi) | 'statement' (bozza da copiare, mai inviata).
 * Risposta JSON: { risposta, azioni: [{id, azione, perche}] } — le azioni si applicano solo con "✓ Applica".
 */
function assistente(modo, testo, idBando) {
  var key = prop_('GEMINI_API_KEY');
  if (!key) throw new Error('Imposta GEMINI_API_KEY nelle proprietà dello script');
  var dati = JSON.parse(getBandi());
  var p = dati.profilo;
  var profilo = 'Artista (' + (p['Tema'] || 'arti visive') + '), base ' + (p['Base'] || '') + '. Temi: ' + (p['Temi'] || '') +
    '. Linguaggi: ' + (p['Discipline piene'] || '') + '. Curriculum: ' + (p['Curriculum'] || '') +
    '. Lingue: ' + (p['Lingue'] || '') + '. Quota massima ' + (p['Quota massima'] || '') + ' €.';
  var prompt;
  if (modo === 'statement') {
    var b = trovaBando_(idBando);
    prompt = 'Scrivi in ' + (/ingl|engl/i.test(b['Lingua candidatura']) && !/ital/i.test(b['Lingua candidatura']) ? 'inglese' : 'italiano') +
      ' una bozza di statement / lettera di motivazione (max 2.000 battute) per questo bando, in prima persona, ' +
      'sobria, senza superlativi, collegando i temi del bando al lavoro dell\'artista. Non inventare premi o mostre non elencati.\n\n' +
      'Profilo: ' + profilo + '\n\nBando: ' + JSON.stringify({ titolo: b.Titolo, ente: b.Ente, tipo: b.Tipo, temi: b.Temi,
        valore: b.Valore, materiali: b['Materiali richiesti'], eleggibilita: b['Eleggibilità'], estratto: b.Estratto }) +
      (testo ? '\n\nIndicazioni dell\'artista: ' + testo : '') +
      '\n\nRispondi in JSON: {"risposta": "<bozza>", "azioni": []}';
  } else {
    var elenco = dati.bandi.filter(function (b) { return !b.Esclusione; }).slice(0, 200).map(function (b) {
      return [b.ID, b.Titolo, b.Ente, b.Tipo, b['Città'] || b.Paese, b.Scadenza, 'quota ' + b['Quota iscrizione'], b.Valore, 'punti ' + b.Punteggio, b.Stato].join(' | ');
    }).join('\n');
    prompt = 'Sei l\'assistente di ElBandito. Oggi è ' + dati.oggi + '. Rispondi in italiano, breve, citando gli ID dei bandi.\n' +
      'Se è utile proponi azioni sullo stato (interessa, scarta, pronto, inviato, archivia): verranno applicate solo dopo conferma.\n\n' +
      'Profilo: ' + profilo + '\n\nBandi (ID | titolo | ente | tipo | luogo | scadenza | quota | valore | punti | stato):\n' + elenco +
      '\n\nDomanda: ' + testo + '\n\nRispondi in JSON: {"risposta": "...", "azioni": [{"id": "B0001", "azione": "interessa", "perche": "..."}]}';
  }
  var r = UrlFetchApp.fetch('https://generativelanguage.googleapis.com/v1beta/models/' + MODELLO_GEMINI + ':generateContent', {
    method: 'post', contentType: 'application/json', muteHttpExceptions: true, headers: { 'x-goog-api-key': key },
    payload: JSON.stringify({ contents: [{ role: 'user', parts: [{ text: prompt }] }],
      generationConfig: { responseMimeType: 'application/json', temperature: 0.4 } })
  });
  if (r.getResponseCode() >= 300) throw new Error('Gemini: ' + r.getResponseCode());
  var testoRisposta = JSON.parse(r.getContentText()).candidates[0].content.parts[0].text;
  var out = JSON.parse(testoRisposta);
  out.azioni = (out.azioni || []).filter(function (a) {
    return ['interessa', 'scarta', 'pronto', 'inviato', 'archivia'].indexOf(a.azione) >= 0;
  });
  return JSON.stringify(out);
}

// ---------------------------------------------------------------- notifiche (solo a te)

function mail_(oggetto, html) {
  MailApp.sendEmail({ to: Session.getEffectiveUser().getEmail(), subject: '[ElBandito] ' + oggetto, htmlBody: html, name: 'ElBandito' });
}

function urlApp_() { try { return ScriptApp.getService().getUrl(); } catch (e) { return ''; } }

function rigaMail_(b) {
  return '<tr><td style="padding:6px 10px;font-weight:bold">' + (b.Punteggio || '–') + '</td>' +
    '<td style="padding:6px 10px"><a href="' + (b['Link bando'] || '#') + '">' + esc_(b.Titolo) + '</a><br>' +
    '<span style="color:#666">' + esc_(b.Ente || '') + ' · ' + esc_(b.Motivazione || '') + '</span></td>' +
    '<td style="padding:6px 10px;white-space:nowrap">' + (b.Scadenza || '—') +
    (b['Scadenza confermata'] === 'sicura' ? '' : ' <em>(da verificare)</em>') + '</td></tr>';
}

function tabella_(righe) {
  return '<table style="border-collapse:collapse;font-family:Helvetica,Arial,sans-serif;font-size:14px">' + righe.join('') + '</table>' +
    (urlApp_() ? '<p><a href="' + urlApp_() + '">Apri ElBandito</a></p>' : '');
}

function esc_(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

/** Lunedì: i 10 bandi migliori ancora da valutare. */
function digestSettimanale() {
  var migliori = leggi_('BANDI').filter(function (b) {
    return b.Stato === 'Nuovo' && !b.Esclusione && (!b.Scadenza || b.Scadenza >= oggi_());
  }).sort(function (a, b) { return (b.Punteggio || 0) - (a.Punteggio || 0); }).slice(0, 10);
  if (!migliori.length) return;
  mail_('I 10 bandi della settimana', '<p>Ecco i bandi da valutare, ordinati per punteggio.</p>' + tabella_(migliori.map(rigaMail_)));
}

/** Ogni mattina: avviso per i bandi ≥ soglia trovati ieri o oggi, e promemoria a 14/7/2 giorni. */
function controlloGiornaliero() {
  var profilo = {};
  leggi_('PROFILO').forEach(function (r) { profilo[r.Campo] = r.Valore; });
  var soglia = Number(profilo['Soglia avviso'] || 80);
  var ieri = piuGiorni_('', -1);
  var bandi = leggi_('BANDI');
  var forti = bandi.filter(function (b) {
    return Number(b.Punteggio) >= soglia && !b.Esclusione && b.Stato === 'Nuovo' && b['Trovato il'] >= ieri;
  });
  if (forti.length) mail_(forti.length === 1 ? 'Un bando da guardare subito' : forti.length + ' bandi da guardare subito', tabella_(forti.map(rigaMail_)));

  var promemoria = bandi.filter(function (b) {
    if (['Da preparare', 'Pronto'].indexOf(b.Stato) < 0 || !b.Scadenza) return false;
    if (b['Scadenza confermata'] !== 'sicura') return false; // le date non confermate non generano promemoria
    var giorni = Math.round((new Date(b.Scadenza + 'T12:00:00') - new Date(oggi_() + 'T12:00:00')) / 864e5);
    return giorni === 14 || giorni === 7 || giorni === 2;
  });
  if (promemoria.length) mail_('Scadenze in arrivo', tabella_(promemoria.map(rigaMail_)));
}

/** Il primo del mese: candidature, esiti, fonti utili e fonti in errore. */
function riepilogoMensile() {
  var mese = piuGiorni_('', -31);
  var cand = leggi_('CANDIDATURE').filter(function (c) { return c['Inviata il'] >= mese || c['Aggiornato il'] >= mese; });
  var fonti = leggi_('FONTI');
  var utili = fonti.filter(function (f) { return Number(f['Bandi portati']) > 0; })
    .sort(function (a, b) { return b['Bandi portati'] - a['Bandi portati']; }).slice(0, 8);
  var rotte = fonti.filter(function (f) { return Number(f['Errori consecutivi']) >= 3 || (f.Attiva === 'sì' && f['Ultimo bando'] && f['Ultimo bando'] < piuGiorni_('', -30)); });
  var html = '<h3>Candidature del mese</h3><ul>' + (cand.map(function (c) {
    return '<li>' + esc_(c.Titolo) + ' — ' + (c.Esito || (c['Inviata il'] ? 'inviata il ' + c['Inviata il'] : 'in preparazione')) + '</li>';
  }).join('') || '<li>nessuna</li>') + '</ul>' +
    '<h3>Fonti più utili</h3><ul>' + utili.map(function (f) { return '<li>' + esc_(f.Nome) + ': ' + f['Bandi portati'] + '</li>'; }).join('') + '</ul>' +
    '<h3>Fonti da controllare</h3><ul>' + (rotte.map(function (f) { return '<li>' + esc_(f.Nome) + ' — ' + esc_(f['Ultimo esito'] || '') + '</li>'; }).join('') || '<li>nessuna</li>') + '</ul>';
  mail_('Riepilogo del mese', html);
}

/** Da eseguire una volta dall'editor: installa i trigger delle notifiche. */
function installaTrigger() {
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('digestSettimanale').timeBased().onWeekDay(ScriptApp.WeekDay.MONDAY).atHour(9).inTimezone(FUSO).create();
  ScriptApp.newTrigger('controlloGiornaliero').timeBased().everyDays(1).atHour(8).inTimezone(FUSO).create();
  ScriptApp.newTrigger('riepilogoMensile').timeBased().onMonthDay(1).atHour(9).inTimezone(FUSO).create();
  return 'Trigger installati';
}
