"""Questionario guidato per il profilo: `elbandito configura`.

Fa le stesse domande della skill elbandito-avvio, ma da terminale. Ogni
risposta vuota tiene il valore attuale. Alla fine salva il profilo nel
foglio attivo e una copia in <cartella dati>/personale/profilo.csv, che è
fuori da git e ha la precedenza sul seed se il foglio viene ricreato.
"""

from __future__ import annotations

import csv
from typing import Callable

from . import servizi
from .config import Ambiente, Profilo
from .foglio import apri

# Preset dei pesi: si sceglie un'intenzione, non sei numeri.
PRESET_PESI = {
    "equilibrato": {"disciplina": 25, "tema": 5, "geografia": 10, "valore": 15, "prestigio": 15, "costo": 15},
    "conta il tema": {"disciplina": 20, "tema": 25, "geografia": 10, "valore": 15, "prestigio": 15, "costo": 15},
    "vicino a casa": {"disciplina": 20, "tema": 10, "geografia": 30, "valore": 15, "prestigio": 10, "costo": 15},
    "carriera": {"disciplina": 20, "tema": 10, "geografia": 5, "valore": 20, "prestigio": 30, "costo": 15},
    "budget stretto": {"disciplina": 20, "tema": 10, "geografia": 10, "valore": 20, "prestigio": 10, "costo": 30},
}

# (campo, domanda, spiegazione breve). Le sezioni guidano l'ordine delle domande.
SEZIONI = [
    ("Chi sei", [
        ("Tema", "Su quale ambito cerchi bandi?", "es. fotografia, cinema documentario, illustrazione, editoria"),
        ("Discipline piene", "Linguaggi che pratichi (contano il 100%)", "separati da virgole"),
        ("Discipline metà", "Ambiti affini che ti interessano a metà", "es. arti visive, multidisciplinare"),
        ("Anno di nascita", "Anno di nascita", "serve solo per i limiti d'età (under 30, under 35…)"),
        ("Nazionalità", "Nazionalità", "es. italiana"),
    ]),
    ("Dove sei", [
        ("Base", "Città dove vivi o lavori", "anche più d'una, separate da virgole"),
        ("Città di riferimento", "Città da cui calcolare le distanze sulla mappa", ""),
        ("Paese", "Paese", ""),
        ("Regioni di residenza", "Regioni (o città) in cui risiedi", "per i bandi riservati ai residenti"),
        ("Regioni con partner", "Regioni dove hai partner residenti (amici, enti)", "i bandi per residenti lì non vengono esclusi, ma segnalati: serve un partner"),
        ("Luoghi casa", "Luoghi che consideri 'casa' (punteggio geografico pieno)",
         "regione e città principali, separate da virgole"),
        ("Etichetta casa", "Come chiamare quest'area nelle motivazioni", "es. Sicilia, Emilia-Romagna"),
        ("Luoghi vicini", "Luoghi vicini (80% del punteggio geografico)", "regioni o città confinanti"),
    ]),
    ("Come ti candidi", [
        ("Si candida come", "Ti candidi come…", "persona | persona e associazione | persona e partita IVA"),
        ("Lingue", "Lingue in cui puoi scrivere una candidatura", "es. italiano, inglese"),
        ("Quota massima", "Quota d'iscrizione massima che accetti (euro)", "sopra questa soglia il bando è escluso"),
        ("Giorni minimi preparazione", "Giorni minimi per preparare una candidatura", "i bandi più vicini sono esclusi"),
        ("Disponibilità fuori casa (settimane)", "Quante settimane puoi passare fuori per una residenza?", ""),
    ]),
    ("Il tuo lavoro", [
        ("Temi", "Temi ricorrenti del tuo lavoro", "4-8 parole chiave, separate da virgole"),
        ("Curriculum", "Curriculum in due righe (premi, residenze, mostre)",
         "solo dati professionali: entra nei prompt e nelle bozze di statement"),
        ("Parole chiave", "Parole da cercare nei siti WordPress e su SearXNG",
         "in italiano e in inglese, separate da virgole"),
    ]),
]


def _domanda(chiedi: Callable[[str], str], testo: str, attuale: str, aiuto: str) -> str:
    righe = f"\n{testo}" + (f"\n  ({aiuto})" if aiuto else "") + f"\n  [{attuale or '—'}] > "
    risposta = chiedi(righe).strip()
    return risposta or attuale


def _coordinate(citta: str) -> tuple[str, str] | None:
    """Coordinate della città con Open-Meteo (gratuito, senza chiave), se raggiungibile."""
    try:
        import httpx

        from .config import USER_AGENT

        r = httpx.get("https://geocoding-api.open-meteo.com/v1/search", headers={"User-Agent": USER_AGENT},
                      params={"name": citta.split(",")[0].strip(), "count": 1, "language": "it"}, timeout=15)
        dati = r.json().get("results") or []
        if dati:
            return f"{float(dati[0]['latitude']):.4f}", f"{float(dati[0]['longitude']):.4f}"
    except Exception:
        pass
    return None


def configura(amb: Ambiente | None = None, chiedi: Callable[[str], str] = input,
              scrivi: Callable[[str], None] = print, geocodifica: bool = True) -> dict[str, str]:
    amb = amb or Ambiente()
    foglio = apri(amb)
    foglio.prepara(con_seed=True)
    profilo = Profilo(foglio.leggi("PROFILO"))
    nuovi: dict[str, str] = {}

    scrivi("ElBandito — il tuo profilo. Premi Invio per tenere il valore tra parentesi.")
    scrivi("Restano sul tuo computer, fuori da git: " + str(amb.cartella_dati))
    for titolo, campi in SEZIONI:
        scrivi(f"\n── {titolo} ──")
        for campo, testo, aiuto in campi:
            attuale = nuovi.get(campo) or profilo.testo(campo)
            if campo == "Città di riferimento" and nuovi.get("Base") and attuale == profilo.testo(campo):
                attuale = nuovi["Base"].split(",")[0].strip()
            valore = _domanda(chiedi, testo, attuale, aiuto)
            if valore != profilo.testo(campo):
                nuovi[campo] = valore
        if titolo == "Dove sei" and "Città di riferimento" in nuovi and geocodifica:
            coord = _coordinate(nuovi["Città di riferimento"])
            if coord:
                nuovi["Base lat"], nuovi["Base lon"] = coord
                scrivi(f"  Coordinate di {nuovi['Città di riferimento']}: {coord[0]}, {coord[1]}")

    scrivi("\n── Cosa conta di più ──")
    nomi = list(PRESET_PESI)
    for i, nome in enumerate(nomi, start=1):
        pesi = " ".join(f"{k} {v}" for k, v in PRESET_PESI[nome].items())
        scrivi(f"  {i}. {nome:<15} {pesi}")
    scelta = chiedi("Scegli un preset (1-5), oppure Invio per tenere i pesi attuali > ").strip()
    if scelta.isdigit() and 1 <= int(scelta) <= len(nomi):
        for k, v in PRESET_PESI[nomi[int(scelta) - 1]].items():
            nuovi[f"Peso {k}"] = str(v)

    scrivi("\n── Chi legge le pagine ──")
    scrivi("  auto: Gemini o Claude API se c'è una chiave in .env, altrimenti Claude Code via MCP")
    motore = _domanda(chiedi, "Motore estrazione", profilo.testo("Motore estrazione", "auto"),
                      "auto | gemini | claude-api | agente")
    if motore != profilo.testo("Motore estrazione", "auto"):
        nuovi["Motore estrazione"] = motore

    for campo, valore in nuovi.items():
        servizi.salva_profilo(foglio, campo, valore)
    salva_copia_personale(amb)
    if nuovi and foglio.leggi("BANDI"):
        from .pipeline import ricalcola

        ricalcola(amb)
        scrivi("Punteggi ricalcolati.")
    scrivi(f"\nFatto: {len(nuovi)} campi aggiornati. Copia in {amb.cartella_dati / 'personale' / 'profilo.csv'}")
    scrivi("Guida completa ai campi e ai pesi: docs/GUIDA-PROFILO.md")
    return nuovi


def salva_copia_personale(amb: Ambiente) -> None:
    """Copia PROFILO in <dati>/personale/profilo.csv: se ricrei il foglio, riparte dai tuoi valori."""
    righe = apri(amb).leggi("PROFILO")
    cartella = amb.cartella_dati / "personale"
    cartella.mkdir(parents=True, exist_ok=True)
    with (cartella / "profilo.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["Campo", "Valore", "Note"], extrasaction="ignore")
        w.writeheader()
        w.writerows(righe)
