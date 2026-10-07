"""Bandi d'esempio per provare ElBandito senza chiavi né rete.

Sono inventati e marcati come tali (titolo "(esempio)", nota, fonte "demo").
Passano comunque da verifica, punteggio e filtri veri, quindi mostrano come
il profilo cambia l'ordine e le esclusioni.
"""

from __future__ import annotations

from datetime import timedelta

from .config import Ambiente, Profilo, iso, oggi
from .connettori import Pagina
from .estrazione import verifica
from .foglio import FoglioBase, apri
from .modelli import SchedaEstratta
from .pipeline import _applica_esito, riga_da_scheda

NOTA = "Dato d'esempio: non è un bando reale."

# (giorni alla scadenza, stato, lat, lon, campi della scheda)
ESEMPI = [
    (45, "Nuovo", 44.4949, 11.3426, dict(
        titolo="Premio Portici per la fotografia (esempio)", ente="Fondazione Portici", tipo="premio",
        disciplina="fotografia", temi=["territorio", "memoria"], paese="Italia", regione="Emilia-Romagna",
        citta="Bologna", quota_iscrizione_eur=0, valore="3.000 € + mostra personale", valore_eur=3000,
        include_mostra=True, eleggibilita="Maggiorenni di ogni nazionalità",
        materiali_richiesti=["portfolio 15 immagini", "statement", "CV"], lingue_candidatura=["italiano", "inglese"])),
    (30, "Nuovo", 38.4667, 14.95, dict(
        titolo="Residenza Isole Minori (esempio)", ente="Associazione Arcipelago", tipo="residenza",
        disciplina="arti visive", temi=["acqua", "paesaggio"], paese="Italia", regione="Sicilia", citta="Lipari",
        quota_iscrizione_eur=0, valore="alloggio, vitto e 800 € di fee", valore_eur=800, copre_alloggio=True,
        date_attivita="giugno, 3 settimane", materiali_richiesti=["portfolio", "proposta di progetto"],
        lingue_candidatura=["italiano"])),
    (70, "Nuovo", 59.9139, 10.7522, dict(
        titolo="Nordic Documentary Photo Grant (esempio)", ente="North Light Foundation", tipo="grant",
        disciplina="fotografia", temi=["migrazione", "comunità"], paese="Norvegia", citta="Oslo",
        quota_iscrizione_eur=0, valore="5.000 €", valore_eur=5000, eleggibilita="Fotografi europei",
        materiali_richiesti=["portfolio 20 immagini", "budget", "statement"], lingue_candidatura=["inglese"])),
    (25, "Nuovo", 45.4642, 9.19, dict(
        titolo="Young Lens Award under 30 (esempio)", ente="Premio Giovani Visioni", tipo="premio",
        disciplina="fotografia", paese="Italia", regione="Lombardia", citta="Milano", quota_iscrizione_eur=35,
        valore="1.000 €", valore_eur=1000, eta_max=30, lingue_candidatura=["italiano"])),
    (40, "Nuovo", 50.8503, 4.3517, dict(
        titolo="Cooperation Projects for Cultural Organisations (esempio)", ente="Programma europeo", tipo="grant",
        disciplina="multidisciplinare", paese="Belgio", citta="Bruxelles", solo_enti=True,
        eleggibilita="Solo persone giuridiche", valore="fino a 200.000 €", valore_eur=200000)),
    (55, "Nuovo", 41.9028, 12.4964, dict(
        titolo="Call fotografica a pagamento (esempio)", ente="Galleria Vetrina", tipo="open call",
        disciplina="fotografia", paese="Italia", regione="Lazio", citta="Roma", quota_iscrizione_eur=45,
        valore="pubblicazione online", lingue_candidatura=["italiano"])),
    (18, "Da preparare", 43.7696, 11.2558, dict(
        titolo="Residenza Colline e Archivi (esempio)", ente="Villa delle Colline", tipo="residenza",
        disciplina="fotografia", temi=["archivio", "paesaggio"], paese="Italia", regione="Toscana", citta="Firenze",
        quota_iscrizione_eur=0, valore="alloggio + 1.500 € di produzione", valore_eur=1500, copre_alloggio=True,
        materiali_richiesti=["portfolio 12 immagini", "lettera di motivazione", "CV"],
        lingue_candidatura=["italiano", "inglese"])),
    (9, "Pronto", 45.4408, 12.3155, dict(
        titolo="Festival Laguna Open Call (esempio)", ente="Laguna Photo Festival", tipo="festival",
        disciplina="fotografia", paese="Italia", regione="Veneto", citta="Venezia", quota_iscrizione_eur=15,
        valore="mostra al festival e catalogo", include_mostra=True, lingue_candidatura=["inglese"])),
    (100, "Nuovo", 53.3498, -6.2603, dict(
        titolo="Island Photobook Prize (esempio)", ente="Harbour Books", tipo="premio", disciplina="fotografia",
        temi=["acqua", "isole"], paese="Irlanda", citta="Dublino", quota_iscrizione_eur=20,
        valore="pubblicazione del libro + 2.000 €", valore_eur=2000, include_mostra=True,
        lingue_candidatura=["inglese"])),
]


def crea_demo(amb: Ambiente | None = None, foglio: FoglioBase | None = None, forza: bool = False) -> int:
    amb = amb or Ambiente()
    foglio = foglio or apri(amb)
    foglio.prepara(con_seed=True)
    if foglio.leggi("BANDI") and not forza:
        return 0
    profilo = Profilo(foglio.leggi("PROFILO"))
    enti = foglio.leggi("ENTI")
    righe = []
    for n, (giorni, stato, lat, lon, campi) in enumerate(ESEMPI, start=1):
        scadenza = oggi() + timedelta(days=giorni)
        frase = f"Le candidature si chiudono il {scadenza.strftime('%d/%m/%Y')}."
        citazioni = {"scadenza_citazione": frase}
        frasi = [frase]
        if campi.get("quota_iscrizione_eur") is not None:
            q = campi["quota_iscrizione_eur"]
            citazioni["quota_citazione"] = "La partecipazione è gratuita." if q == 0 else f"Quota di partecipazione: {q:.0f} euro."
            frasi.append(citazioni["quota_citazione"])
        if campi.get("eleggibilita"):
            citazioni["eleggibilita_citazione"] = f"Possono partecipare: {campi['eleggibilita']}."
            frasi.append(citazioni["eleggibilita_citazione"])
        testo = " ".join(frasi)
        scheda = SchedaEstratta(scadenza=iso(scadenza), **citazioni, **campi)
        v = verifica(scheda, testo)
        pagina = Pagina(url=f"https://example.org/elbandito/esempio-{n}", titolo=scheda.titolo, testo=testo,
                        fonte="demo")
        riga = riga_da_scheda(v, pagina)
        riga.update({
            "ID": f"B{n:04d}", "Lat": lat, "Lon": lon, "Stato": stato, "Note": NOTA,
            "Prossima azione": {"Nuovo": "Valutare", "Da preparare": "Preparare i materiali",
                                "Pronto": "Inviare la candidatura"}[stato],
            "Data prossima azione": iso(oggi() + timedelta(days=3 if stato == "Nuovo" else max(0, giorni - 10))),
            "Trovato il": iso(oggi() - timedelta(days=n % 5)), "Aggiornato il": iso(oggi()),
            "Storico": f"{iso(oggi())} creato come esempio",
        })
        _applica_esito(riga, v, profilo, enti)
        righe.append(riga)
    foglio.aggiungi("BANDI", righe)
    from . import servizi

    for r in righe:
        if r["Stato"] in ("Da preparare", "Pronto"):
            servizi._assicura_candidatura(foglio, r)
    servizi.spunta(foglio, "B0007", "portfolio", True)
    return len(righe)
