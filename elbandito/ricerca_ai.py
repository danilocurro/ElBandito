"""Ricerca settimanale per ciò che le fonti fisse non vedono.

Tre motori, scelti con "Motore ricerca" in PROFILO:
- agente (predefinito): la ricerca la fa Claude Code con la sua ricerca web,
  guidato dalla skill elbandito-ricerca e dagli strumenti MCP;
- claude-api: un Message Batch (metà prezzo) con lo strumento di
  ricerca web; ogni richiesta copre un filone e fa al massimo qualche ricerca;
- searxng: un'istanza SearXNG ospitata da te; gratuito, ma i risultati sono
  link grezzi e la qualità dipende dai motori che SearXNG interroga.

In entrambi i casi ne escono solo URL: ogni pagina passa poi dalla stessa
estrazione con citazioni e dalla stessa deduplica delle fonti fisse.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass

from .config import Ambiente, Profilo, iso, oggi

log = logging.getLogger(__name__)

FILONI_PREDEFINITI = [
    "residenze d'artista per {tema} in Europa (con alloggio o fee) aperte ad artisti di nazionalità {nazionalita}",
    "premi e concorsi di {tema} in {paese} senza quota o con quota bassa",
    "bandi, residenze e open call in {casa} e dintorni per arti visive e {tema}",
    "grant e fondi di produzione per progetti di {tema} documentaria in Europa",
    "open call di festival europei di {tema} (mostre, letture portfolio, premi)",
    "bandi pubblici in {paese} per {tema} contemporanea (ministero, regioni, fondazioni)",
    "residenze e premi sui temi {temi}",
    "fondi di mobilità e viaggio per artisti visivi (Culture Moves Europe e simili)",
]


@dataclass
class Segnalazione:
    url: str
    titolo: str = ""
    ente: str = ""
    scadenza: str = ""
    nota: str = ""


def filoni(profilo: Profilo) -> list[str]:
    propri = [f.strip() for f in profilo.testo("Filoni ricerca").split(";") if f.strip()]
    if propri:
        return propri
    valori = {
        "tema": profilo.testo("Tema", "fotografia"), "paese": profilo.testo("Paese", "Italia"),
        "nazionalita": profilo.testo("Nazionalità", "italiana"),
        "casa": profilo.testo("Etichetta casa") or profilo.testo("Base"),
        "temi": ", ".join(profilo.lista("Temi")[:5]),
    }
    return [f.format(**valori) for f in FILONI_PREDEFINITI]


def _prompt(filone: str, profilo: Profilo, noti: list[str]) -> str:
    elenco = "\n".join(f"- {n}" for n in noti[:150]) or "(nessuno)"
    return f"""Oggi è {iso(oggi())}. Cerca sul web opportunità APERTE (scadenza futura) su questo filone:
{filone}

Profilo dell'artista:
{profilo.riassunto()}

Bandi già noti, da NON riproporre:
{elenco}

Regole:
- Solo opportunità con scadenza dopo oggi, a cui una persona fisica può candidarsi.
- Preferisci la pagina ufficiale dell'ente all'articolo che ne parla.
- Non inventare URL: riporta solo link che hai visto nei risultati.
- Al massimo 10 segnalazioni.

Rispondi alla fine con un blocco ```json contenente una lista di oggetti con le chiavi
"url", "titolo", "ente", "scadenza", "nota" (una riga sul perché è adatta)."""


def _leggi_json(testo: str) -> list[dict]:
    m = re.search(r"```json\s*(.*?)```", testo, re.S)
    grezzo = m.group(1) if m else testo[testo.find("[") : testo.rfind("]") + 1]
    try:
        dati = json.loads(grezzo)
    except (json.JSONDecodeError, ValueError):
        return []
    return [d for d in dati if isinstance(d, dict) and str(d.get("url", "")).startswith("http")]


def cerca_claude(amb: Ambiente, profilo: Profilo, noti: list[str], attesa_max_min: int = 120) -> list[Segnalazione]:
    import anthropic

    client = anthropic.Anthropic(api_key=amb.anthropic_key or None)
    modello = profilo.testo("Modello ricerca")
    elenco_filoni = filoni(profilo)
    per_filone = max(1, round(profilo.numero("Ricerche settimanali", 20) / len(elenco_filoni)))

    def richiesta(i: int, filone: str, con_fallback: bool) -> dict:
        params = {
            "model": modello,
            "max_tokens": 16000,
            "output_config": {"effort": "medium"},
            "tools": [{"type": "web_search_20260209", "name": "web_search", "max_uses": per_filone}],
            "messages": [{"role": "user", "content": _prompt(filone, profilo, noti)}],
        }
        if con_fallback:
            params["fallbacks"] = "default"
        return {"custom_id": f"filone-{i}", "params": params}

    try:
        lotto = client.beta.messages.batches.create(
            requests=[richiesta(i, f, True) for i, f in enumerate(elenco_filoni)],
            betas=["server-side-fallback-2026-07-01"],
        )
    except anthropic.BadRequestError as e:
        log.warning("Batch con fallback rifiutato (%s): riprovo senza", e)
        lotto = client.beta.messages.batches.create(requests=[richiesta(i, f, False) for i, f in enumerate(elenco_filoni)])

    inizio = time.monotonic()
    while True:
        stato = client.beta.messages.batches.retrieve(lotto.id)
        if stato.processing_status == "ended":
            break
        if time.monotonic() - inizio > attesa_max_min * 60:
            log.error("Batch %s non concluso dopo %d minuti", lotto.id, attesa_max_min)
            return []
        time.sleep(60)

    out: list[Segnalazione] = []
    for ris in client.beta.messages.batches.results(lotto.id):
        if ris.result.type != "succeeded":
            log.warning("Filone %s: %s", ris.custom_id, ris.result.type)
            continue
        msg = ris.result.message
        if msg.stop_reason == "refusal":
            continue
        testo = "".join(b.text for b in msg.content if b.type == "text")
        for d in _leggi_json(testo):
            out.append(Segnalazione(url=d["url"], titolo=str(d.get("titolo", "")), ente=str(d.get("ente", "")),
                                    scadenza=str(d.get("scadenza", "")), nota=str(d.get("nota", ""))))
    return out


def cerca_searxng(amb: Ambiente, profilo: Profilo, rete) -> list[Segnalazione]:
    if not amb.searxng_url:
        raise RuntimeError("Motore searxng scelto ma SEARXNG_URL non impostato")
    out = []
    for q in profilo.lista("Parole chiave"):
        r = rete.get(f"{amb.searxng_url.rstrip('/')}/search", params={"q": q, "format": "json", "time_range": "month"})
        for ris in r.json().get("results", [])[:5]:
            out.append(Segnalazione(url=ris.get("url", ""), titolo=ris.get("title", ""), nota=ris.get("content", "")))
    return [s for s in out if s.url]


def cerca(amb: Ambiente, profilo: Profilo, noti: list[str], rete) -> list[Segnalazione]:
    motore = profilo.testo("Motore ricerca", "claude").lower()
    if motore == "searxng":
        return cerca_searxng(amb, profilo, rete)
    if motore in ("claude-api", "claude"):
        return cerca_claude(amb, profilo, noti)
    raise RuntimeError(f"Motore ricerca '{motore}': la ricerca la fa Claude Code, non il collettore")


# --- "cerca a fondo" su un singolo bando ----------------------------------------

def approfondisci(amb: Ambiente, profilo: Profilo, bando: dict) -> str:
    """Indagine su giuria, vincitori delle edizioni passate e reputazione dell'ente.

    Restituisce un testo breve (markdown) da scrivere nella colonna Approfondimento.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=amb.anthropic_key or None)
    domanda = f"""Oggi è {iso(oggi())}. Indaga su questa opportunità per un artista:
Titolo: {bando.get('Titolo')}
Ente: {bando.get('Ente')}
Link: {bando.get('Link bando')}
Scadenza indicata: {bando.get('Scadenza')}

Profilo dell'artista:
{profilo.riassunto()}

Cerca e riporta, con i link alle fonti:
1. chi è l'ente e che reputazione ha (anni di attività, partner, eventuali segnalazioni di "vanity call");
2. giuria o curatori di questa edizione, se noti;
3. vincitori o selezionati delle ultime edizioni e che tipo di lavori erano;
4. se la scadenza e la quota indicate sopra coincidono con la pagina ufficiale;
5. in due righe: quanto è adatta a questo artista e perché.
Rispondi in italiano, massimo 250 parole, in elenco puntato."""
    messaggi: list = [{"role": "user", "content": domanda}]
    params = {
        "model": profilo.testo("Modello ricerca"),
        "max_tokens": 16000,
        "output_config": {"effort": "medium"},
        "tools": [{"type": "web_search_20260209", "name": "web_search", "max_uses": 6}],
    }
    testo = ""
    for _ in range(4):  # pause_turn: il server chiede di continuare il giro di ricerche
        try:
            msg = client.beta.messages.create(messages=messaggi, fallbacks="default",
                                              betas=["server-side-fallback-2026-07-01"], **params)
        except anthropic.BadRequestError:
            msg = client.beta.messages.create(messages=messaggi, **params)
        testo = "".join(b.text for b in msg.content if b.type == "text")
        if msg.stop_reason != "pause_turn":
            break
        messaggi = messaggi + [{"role": "assistant", "content": msg.content}]
    if msg.stop_reason == "refusal":
        return "Indagine non disponibile per questo bando."
    return f"{iso(oggi())} · {testo.strip()}"
