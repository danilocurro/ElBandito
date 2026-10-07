"""Schemi dei dati: colonne del foglio e scheda estratta dall'LLM.

Il codice legge e scrive le colonne per nome di intestazione, come nel
gestionale: l'ordine nel foglio si può cambiare a mano senza rompere nulla.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# --- Schede del foglio -------------------------------------------------------

COLONNE = {
    "BANDI": [
        "ID", "Impronta", "Titolo", "Ente", "Tipo", "Disciplina", "Temi",
        "Paese", "Regione", "Città", "Lat", "Lon",
        "Scadenza", "Scadenza confermata", "Fuso scadenza", "Apertura", "Date attività",
        "Quota iscrizione", "Valore", "Eleggibilità", "Materiali richiesti",
        "Lingua candidatura", "Link bando", "Link candidatura", "Fonte", "N. fonti",
        "Estratto", "Punteggio", "Dettaglio punteggio", "Motivazione", "Rischi", "Esclusione",
        "Stato", "Prossima azione", "Data prossima azione", "Ricorrente", "Edizione",
        "Trovato il", "Aggiornato il", "Storico", "Note", "Approfondimento",
    ],
    "FONTI": [
        "ID", "Nome", "URL", "Connettore", "Parametri", "Frequenza", "Livello", "Tipo",
        "Attiva", "Ultima lettura", "Ultimo esito", "Bandi portati", "Errori consecutivi",
        "Ultimo bando", "Note",
    ],
    "PROFILO": ["Campo", "Valore", "Note"],
    "ENTI": ["Nome", "Tipo", "Livello", "Città", "Paese", "Sito", "Mesi call", "Storico", "Note"],
    "CANDIDATURE": [
        "ID bando", "Titolo", "Checklist", "Cartella", "Inviata il", "Esito", "Data esito",
        "Feedback", "Aggiornato il",
    ],
    "LOG": [
        "Data", "Tipo giro", "Fonti lette", "Fonti in errore", "Pagine nuove", "Schede estratte",
        "Bandi nuovi", "Bandi aggiornati", "In coda", "Domini suggeriti", "Note", "Errori", "Durata (s)",
    ],
}

TIPI = ["residenza", "premio", "open call", "grant", "festival", "commissione", "borsa", "altro"]

STATI = [
    "Nuovo", "Da preparare", "Pronto", "Inviato", "Vinto", "Non selezionato",
    "Scartato", "In attesa edizione", "Archiviato",
]

CONNETTORI = ["rss", "wordpress", "eu_sedia", "listing", "watch", "browser", "ai_search", "manuale"]


# --- Scheda estratta dall'LLM ------------------------------------------------

TipoBando = Literal["residenza", "premio", "open call", "grant", "festival", "commissione", "borsa", "altro"]


class SchedaEstratta(BaseModel):
    """Un'opportunità come la restituisce l'LLM.

    I campi critici (scadenza, quota, eleggibilità) hanno una citazione: la
    frase esatta del testo da cui vengono. Se la frase non si ritrova nel
    testo, il campo viene svuotato e la scheda resta "da verificare".
    """

    titolo: str = Field(description="Nome del bando come scritto dall'ente")
    ente: str = Field(description="Ente, festival o fondazione che lo promuove")
    tipo: TipoBando
    disciplina: str = Field(
        description="fotografia, lens-based, arti visive, video, cinema, multidisciplinare, performance, altro"
    )
    temi: list[str] = Field(default_factory=list, description="Temi richiesti o suggeriti dal bando")
    paese: str = Field("", description="Dove si svolge l'opportunità (paese)")
    regione: str = ""
    citta: str = ""
    online: bool = Field(False, description="Vero se si svolge solo online / senza luogo fisico")

    scadenza: str = Field("", description="Data di scadenza come scritta nel testo, senza riformularla")
    scadenza_citazione: str = Field("", description="Frase esatta del testo che contiene la scadenza")
    fuso_scadenza: str = Field("", description="Ora e fuso se indicati, es. '23:59 CET'")
    apertura: str = Field("", description="Data di apertura della call, se indicata")
    date_attivita: str = Field("", description="Periodo della residenza / mostra / festival")

    quota_iscrizione_eur: Optional[float] = Field(
        None, description="Quota di partecipazione in euro; 0 se gratuito; null se non indicato"
    )
    quota_citazione: str = ""
    valore: str = Field("", description="Premio, fee, alloggio, viaggio, produzione: testo breve")
    valore_eur: Optional[float] = Field(None, description="Valore economico complessivo stimato in euro")
    copre_viaggio: bool = False
    copre_alloggio: bool = False
    include_mostra: bool = Field(False, description="Prevede una mostra, pubblicazione o proiezione")

    eleggibilita: str = Field("", description="Età, nazionalità, residenza, soggetto ammesso")
    eleggibilita_citazione: str = ""
    eta_min: Optional[int] = None
    eta_max: Optional[int] = None
    nazionalita_ammesse: list[str] = Field(default_factory=list, description="Vuota se aperto a tutti")
    residenza_richiesta: str = Field("", description="Es. 'residenti in Lombardia'; vuoto se non richiesta")
    solo_enti: bool = Field(False, description="Vero se possono candidarsi solo enti, associazioni o imprese")

    materiali_richiesti: list[str] = Field(default_factory=list)
    lingue_candidatura: list[str] = Field(default_factory=list)
    link_candidatura: str = ""
    ricorrente: bool = Field(False, description="Vero se il testo indica un'edizione annuale / n-esima")
    edizione: Optional[int] = None


class Estrazione(BaseModel):
    """Una pagina può contenere zero, uno o più bandi (le rubriche mensili)."""

    bandi: list[SchedaEstratta] = Field(default_factory=list)
