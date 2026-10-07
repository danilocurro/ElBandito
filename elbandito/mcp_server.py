"""Server MCP: ElBandito come connettore per Claude Code (o qualsiasi client MCP).

Avvio: `elbandito mcp` (stdio). Gli strumenti lavorano sullo stesso foglio
della web app: Google se c'è ELBANDITO_SHEET_ID, altrimenti i CSV locali.

Senza chiavi API, Claude Code fa da modello: `pagine_da_estrarre` gli passa
il testo delle pagine raccolte, lui compila le schede e le rimanda con
`salva_schede`, che applica le stesse verifiche dell'estrazione via API.
"""

from __future__ import annotations

import json
import logging
import sys

from mcp.server.fastmcp import FastMCP

from . import servizi
from .archivio import Archivio
from .config import Ambiente, Profilo, iso, oggi
from .foglio import apri
from .modelli import SchedaEstratta

logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

ISTRUZIONI_SERVER = """ElBandito raccoglie bandi, residenze, open call, premi e grant per artisti, \
li legge in schede strutturate e li ordina con un punteggio 0-100 sul profilo dell'utente.
Regole: non inviare mai candidature né messaggi per conto dell'utente; le scadenze estratte vanno \
verificate sul sito prima di considerarle sicure; quando estrai schede copia le frasi esatte del testo \
nei campi *_citazione. Le skill elbandito-* descrivono i flussi completi."""

mcp = FastMCP("elbandito", instructions=ISTRUZIONI_SERVER)


def _amb() -> Ambiente:
    return Ambiente()


def _foglio():
    return apri(_amb())


def _archivio() -> Archivio:
    return Archivio(_amb().cartella_dati / "archivio.sqlite")


# --- consultare ----------------------------------------------------------------

@mcp.tool()
def stato() -> dict:
    """Panoramica: bandi per stato, i migliori da valutare, scadenze entro 21 giorni, pagine in coda
    da estrarre, fonti in errore, ultimo giro e configurazione (backend, motori)."""
    amb = _amb()
    foglio = apri(amb)
    out = servizi.statistiche(foglio)
    profilo = Profilo(foglio.leggi("PROFILO"))
    arch = _archivio()
    out["pagine_in_coda"] = arch.quanti_in_coda()
    arch.chiudi()
    out["configurazione"] = {
        "backend": amb.backend, "cartella_dati": str(amb.cartella_dati),
        "motore_estrazione": profilo.testo("Motore estrazione", "auto"),
        "motore_ricerca": profilo.testo("Motore ricerca", "agente"),
        "chiave_gemini": bool(amb.gemini_key), "chiave_anthropic": bool(amb.anthropic_key),
    }
    return out


@mcp.tool()
def cerca_bandi(testo: str = "", tipo: str = "", stato: str = "", entro_giorni: int | None = None,
                quota_max: float | None = None, punteggio_min: float | None = None,
                mostra_esclusi: bool = False, limite: int = 20) -> list[dict]:
    """Cerca nei bandi, ordinati per punteggio.

    tipo: residenza | premio | open call | grant | festival | commissione | borsa.
    stato: Nuovo | Da preparare | Pronto | Inviato | Vinto | Non selezionato | Scartato | In attesa edizione.
    entro_giorni: solo scadenze entro N giorni. quota_max: euro (0 = gratis).
    mostra_esclusi: include i bandi esclusi dai filtri rigidi (età, residenza, quota, solo enti…)."""
    return servizi.cerca(_foglio(), testo, tipo, stato, entro_giorni, quota_max, punteggio_min, mostra_esclusi, limite)


@mcp.tool()
def scheda_bando(id_bando: str) -> dict:
    """Tutti i dati di un bando (es. B0007): punteggio e dettaglio per componente, motivazione, rischi,
    esclusione, scadenza con la frase citata, eleggibilità, materiali, link, storico e checklist."""
    return servizi.scheda(_foglio(), id_bando)


@mcp.tool()
def leggi_profilo() -> dict:
    """Il profilo dell'artista e i pesi del punteggio (scheda PROFILO)."""
    return {r["Campo"]: {"valore": r.get("Valore", ""), "nota": r.get("Note", "")}
            for r in _foglio().leggi("PROFILO") if r.get("Campo")}


@mcp.tool()
def elenco_fonti() -> list[dict]:
    """Le fonti monitorate con connettore, frequenza, ultimo esito e bandi portati."""
    campi = ("ID", "Nome", "URL", "Connettore", "Parametri", "Frequenza", "Attiva", "Ultima lettura",
             "Ultimo esito", "Bandi portati", "Errori consecutivi")
    return [{k: f.get(k, "") for k in campi} for f in _foglio().leggi("FONTI")]


# --- decidere e agire --------------------------------------------------------

@mcp.tool()
def registra_azione(id_bando: str, azione: str, data_esito: str = "", nota: str = "") -> dict:
    """Fa avanzare un bando nel ciclo di vita e calcola la prossima azione a ritroso dalla scadenza.

    azione: interessa (→ Da preparare, crea la checklist) | scarta | pronto | inviato (data_esito facoltativa,
    aaaa-mm-gg) | vinto | non_selezionato | prossimo_anno | riapri | archivia.
    Chiedi conferma all'utente prima di usarla: è una sua decisione."""
    return servizi.registra_azione(_foglio(), id_bando, azione, data_esito, nota)


@mcp.tool()
def conferma_scadenza(id_bando: str, data: str = "") -> str:
    """Segna la scadenza come "sicura" (eventualmente correggendola, aaaa-mm-gg). Solo dopo che l'utente
    l'ha verificata sul sito, o dopo che l'hai letta tu sulla pagina ufficiale."""
    servizi.conferma_scadenza(_foglio(), id_bando, data)
    return "Scadenza confermata"


@mcp.tool()
def salva_nota(id_bando: str, nota: str) -> str:
    """Sostituisce le note del bando."""
    servizi.salva_note(_foglio(), id_bando, nota)
    return "Nota salvata"


@mcp.tool()
def spunta_materiale(id_bando: str, voce: str, fatto: bool = True) -> list[dict]:
    """Segna una voce della checklist dei materiali (cercata per nome) o la aggiunge se manca."""
    return servizi.spunta(_foglio(), id_bando, voce, fatto)


@mcp.tool()
def salva_approfondimento(id_bando: str, testo: str) -> str:
    """Salva nella scheda il risultato di un'indagine "cerca a fondo" (giuria, vincitori passati,
    reputazione dell'ente, coerenza di scadenza e quota) fatta con la ricerca web. Testo breve con i link."""
    foglio = _foglio()
    servizi.scheda(foglio, id_bando)
    foglio.aggiorna("BANDI", "ID", {id_bando: {"Approfondimento": f"{iso(oggi())} · {testo.strip()}",
                                               "Aggiornato il": iso(oggi())}})
    return "Approfondimento salvato"


# --- raccogliere ---------------------------------------------------------------

@mcp.tool()
def esegui_giro(tipo: str = "giornaliero", fonti: list[str] | None = None) -> dict:
    """Legge le fonti (RSS, WordPress, API UE, elenchi, pagine open call), estrae, deduplica, dà il
    punteggio e scrive i bandi. tipo: giornaliero | settimanale. fonti: ID di FONTI da leggere (es. ["F02"]),
    per un giro veloce. Può richiedere alcuni minuti (pausa di 2-3 s per sito).
    Senza chiavi API le pagine finiscono in coda: poi usa pagine_da_estrarre e salva_schede."""
    from .pipeline import Giro

    g = Giro(tipo, _amb())
    if fonti:
        g.solo = set(fonti)
    r = g.esegui()
    return {"fonti_lette": r.fonti_lette, "pagine": r.pagine, "schede": r.schede, "nuovi": r.nuovi,
            "aggiornati": r.aggiornati, "pagine_in_coda": r.in_coda, "fonti_in_errore": r.fonti_errore,
            "domini_suggeriti": r.domini, "note": r.note, "errori": r.errori[:10]}


@mcp.tool()
def pagine_da_estrarre(limite: int = 3, max_caratteri: int = 12000) -> dict:
    """Restituisce pagine raccolte in attesa di estrazione, con istruzioni e schema.
    Per ognuna leggi il testo e chiama salva_schede(url, schede) — lista vuota se non contiene bandi aperti."""
    from .estrazione import ISTRUZIONI

    arch = _archivio()
    pagine = arch.in_coda(limite)
    restanti = arch.quanti_in_coda() - len(pagine)
    arch.chiudi()
    for p in pagine:
        p["testo"] = p["testo"][:max_caratteri]
        p["strutturato"] = json.loads(p["strutturato"] or "{}").get("json_ld", [])
    return {
        "oggi": iso(oggi()),
        "istruzioni": ISTRUZIONI,
        "campi": {k: (v.get("description") or v.get("type") or "") for k, v in
                  SchedaEstratta.model_json_schema()["properties"].items()},
        "obbligatori": ["titolo", "ente", "tipo", "disciplina"],
        "pagine": pagine,
        "restanti": max(0, restanti),
    }


@mcp.tool()
def salva_schede(url: str, schede: list[dict]) -> dict:
    """Salva le schede estratte da una pagina (anche più di una). Ogni scheda segue i campi indicati da
    pagine_da_estrarre; scadenza_citazione, quota_citazione ed eleggibilita_citazione devono essere
    frasi copiate esattamente dal testo, altrimenti il bando resta "da verificare".
    Le schede con scadenza passata vengono scartate. Lista vuota = nessun bando aperto nella pagina."""
    from .pipeline import salva_estratte

    return salva_estratte(url, schede, _amb())


@mcp.tool()
def aggiungi_da_link(url: str) -> dict:
    """Aggiunge un bando da un link (pagina, post, PDF). Con una chiave API lo estrae subito; altrimenti
    restituisce il testo della pagina: estrai tu le schede e chiama salva_schede con lo stesso url."""
    amb = _amb()
    profilo = Profilo(apri(amb).leggi("PROFILO"))
    motore = profilo.testo("Motore estrazione", "auto")
    if motore != "agente" and (amb.gemini_key or amb.anthropic_key):
        from .pipeline import aggiungi_da_link as con_api

        r = con_api(url, amb)
        return {"nuovi": r.nuovi, "aggiornati": r.aggiornati, "errori": r.errori}
    from .pipeline import accoda_link

    return {"da_estrarre": accoda_link(url, amb),
            "prossimo_passo": "Estrai le schede da 'testo' e chiama salva_schede con questo url."}


@mcp.tool()
def contesto_ricerca() -> dict:
    """Tutto ciò che serve per una ricerca web di nuove opportunità: profilo (solo dati professionali),
    filoni di ricerca, bandi già noti da non riproporre e domini già monitorati.
    Per ogni pagina promettente trovata, usa aggiungi_da_link."""
    from .dedup import dominio
    from .ricerca_ai import filoni

    foglio = _foglio()
    profilo = Profilo(foglio.leggi("PROFILO"))
    return {
        "oggi": iso(oggi()),
        "profilo": profilo.riassunto(),
        "filoni": filoni(profilo),
        "ricerche_massime": int(profilo.numero("Ricerche settimanali", 20)),
        "bandi_noti": [f"{b.get('Titolo')} — {b.get('Ente')}" for b in foglio.leggi("BANDI")
                       if b.get("Stato") != "Archiviato"][:300],
        "domini_monitorati": sorted({dominio(f.get("URL", "")) for f in foglio.leggi("FONTI") if f.get("URL")}),
    }


# --- configurare -------------------------------------------------------------

@mcp.tool()
def aggiorna_profilo(campo: str, valore: str) -> str:
    """Cambia (o aggiunge) un campo del profilo: es. "Temi", "Quota massima", "Peso tema", "Luoghi casa".
    Dopo modifiche a pesi o filtri usa ricalcola_punteggi."""
    servizi.salva_profilo(_foglio(), campo, valore)
    return f"{campo} = {valore}"


@mcp.tool()
def aggiungi_fonte(nome: str, url: str, connettore: str = "watch", parametri: str = "",
                   frequenza: str = "settimanale") -> str:
    """Aggiunge una fonte. connettore: watch (pagina open call che cambia) | rss | wordpress |
    listing (pagina-elenco; parametri "pattern=<regex href>; max=10") | browser."""
    return "Aggiunta " + servizi.aggiungi_fonte(_foglio(), nome, url, connettore, parametri, frequenza)


@mcp.tool()
def attiva_fonte(id_fonte: str, attiva: bool) -> str:
    """Mette in pausa o riattiva una fonte."""
    servizi.aggiorna_fonte(_foglio(), id_fonte, {"Attiva": "sì" if attiva else "no"})
    return f"{id_fonte}: {'attiva' if attiva else 'in pausa'}"


@mcp.tool()
def ricalcola_punteggi() -> str:
    """Ricalcola punteggi, motivazioni ed esclusioni di tutti i bandi con il profilo attuale."""
    from .pipeline import ricalcola

    return f"Ricalcolati {ricalcola(_amb())} bandi"


# --- vedere ------------------------------------------------------------------

@mcp.tool()
def apri_dashboard(apri_browser: bool = True) -> str:
    """Avvia la dashboard locale (Oggi, Esplora con mappa e calendario, Pipeline, Enti, Fonti, Profilo)
    e restituisce l'indirizzo."""
    from .dashboard import avvia

    return avvia(_amb(), apri_browser=apri_browser)


@mcp.tool()
def esporta_calendario() -> str:
    """Scrive un file .ics con le scadenze dei bandi aperti (da importare in Google Calendar) e ne
    restituisce il percorso."""
    amb = _amb()
    percorso = amb.cartella_dati / "elbandito.ics"
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(servizi.esporta_ics(apri(amb)), encoding="utf-8")
    return str(percorso)


@mcp.tool()
def crea_dati_esempio() -> str:
    """Prepara le schede e, se BANDI è vuota, inserisce 9 bandi d'esempio inventati per provare tutto."""
    from .demo import crea_demo

    n = crea_demo(_amb())
    return f"Inseriti {n} bandi d'esempio" if n else "BANDI non è vuota: nessun esempio aggiunto"


@mcp.tool()
def richiamo_insieme_oro() -> dict:
    """Test di regressione della rete di fonti: quante opportunità note sono coperte dalle fonti attive
    e quante sono state davvero trovate."""
    from .richiamo import copertura, richiamo

    foglio = _foglio()
    arch = _archivio()
    grezzi = [s for (s,) in arch.db.execute("SELECT scheda FROM grezzi")]
    arch.chiudi()
    return {
        "copertura": [{"opportunità": v["Opportunità"], "fonti": t, "canale": v.get("Canale")}
                      for v, t in copertura(foglio.leggi("FONTI"))],
        "trovate": [{"opportunità": v["Opportunità"], "trovata": ok} for v, ok in richiamo(foglio.leggi("BANDI"), grezzi)],
    }


def main() -> None:
    _foglio().prepara(con_seed=True)  # al primo avvio crea i CSV locali dal seed
    mcp.run()
