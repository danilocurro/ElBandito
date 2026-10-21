"""Da testo pulito a schede strutturate.

Gemini Flash-Lite (piano gratuito) estrae su schema rigido; se la risposta
non valida lo schema si ripiega su Claude Haiku. Poi due difese:
1. ogni campo critico deve citare una frase che esiste davvero nel testo;
2. le date passano da dateparser dopo l'LLM; una scadenza passata si scarta.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date

import dateparser
import httpx
from pydantic import ValidationError
from rapidfuzz import fuzz

from .config import Ambiente, Profilo, iso, oggi
from .connettori import Pagina
from .modelli import Estrazione, SchedaEstratta

log = logging.getLogger(__name__)

MAX_CARATTERI = 24_000  # oltre, si tiene l'inizio: i bandi mettono i dati chiave in alto

ISTRUZIONI = """Sei un assistente che legge pagine web su opportunità per artisti visivi \
(bandi, residenze, open call, premi, grant, festival, borse, commissioni) e le trasforma in schede.

Regole:
- Estrai SOLO opportunità a cui un artista può candidarsi. Se la pagina è una notizia, una recensione \
o l'annuncio dei vincitori, restituisci "bandi": [].
- Una pagina può contenerne più d'una (rubriche, elenchi): una scheda per opportunità.
- Se il testo dice che il bando è già scaduto, chiuso o concluso (anche "edizione scaduta il…"), non estrarlo.
- Per bandi ricorrenti con più finestre l'anno ("1-28 febbraio e 1-31 agosto"), scadenza = la prossima finestra futura.
- Non inventare nulla. Un campo che il testo non dice resta vuoto (o null).
- Per scadenza, quota ed eleggibilità copia nei campi *_citazione la frase ESATTA del testo, \
carattere per carattere, da cui ricavi il dato. Se non c'è una frase, lascia vuoti dato e citazione.
- "scadenza" va copiata come scritta nel testo (es. "15 aprile 2026", "March 3rd, 23:59 CET").
- quota_iscrizione_eur: 0 solo se il testo dice che è gratuito; converti in euro se in altra valuta.
- solo_enti = true se possono candidarsi solo enti, associazioni, imprese o istituzioni.
- disciplina: fotografia, lens-based, arti visive, video, cinema, multidisciplinare, performance, altro.
- Testo dei campi in italiano, tranne titolo ed ente che restano come nell'originale."""


@dataclass
class SchedaVerificata:
    scheda: SchedaEstratta
    scadenza: date | None
    confermata: bool  # tutte le citazioni critiche ritrovate nel testo
    estratto: str  # le frasi citate, per la colonna "Estratto"


def _normalizza(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"[’‘`´]", "'", s)
    s = re.sub(r"[“”«»]", '"', s)
    return " ".join(s.split())


def citazione_presente(citazione: str, testo: str) -> bool:
    if not citazione.strip():
        return False
    c, t = _normalizza(citazione), _normalizza(testo)
    if c in t:
        return True
    return len(c) >= 12 and fuzz.partial_ratio(c, t) >= 92


MESI = {
    "gen": 1, "jan": 1, "janv": 1, "feb": 2, "febr": 2, "fév": 2, "fev": 2, "mar": 3, "mär": 3, "apr": 4, "avr": 4,
    "mag": 5, "may": 5, "mai": 5, "giu": 6, "jun": 6, "juin": 6, "lug": 7, "jul": 7, "juil": 7, "ago": 8, "aug": 8,
    "aoû": 8, "aou": 8, "set": 9, "sett": 9, "sep": 9, "sept": 9, "ott": 10, "oct": 10, "okt": 10, "nov": 11,
    "dic": 12, "dec": 12, "déc": 12, "dez": 12,
}
_MESE = r"([a-zàâäéèêëîïôöûüç]{3,10})\.?(?:[a-zàâäéèêëîïôöûüç]{3,10}\.?)?"  # anche bilingue: "Ago.Aug."
_GIORNO_MESE_ANNO = re.compile(r"\b(\d{1,2})(?:°|º|st|nd|rd|th|er)?\s+(?:de\s+)?" + _MESE + r"\s+(?:de\s+)?(20\d{2})\b", re.I)
_MESE_GIORNO_ANNO = re.compile(r"\b" + _MESE + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d{2})\b", re.I)
_NUMERICA = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](20\d{2})\b")


def _mese(nome: str) -> int | None:
    nome = nome.lower()
    for k in sorted(MESI, key=len, reverse=True):
        if nome.startswith(k):
            return MESI[k]
    return None


def cerca_date(testo: str) -> list[date]:
    """Tutte le date complete (giorno, mese, anno) scritte nel testo, in più lingue, in ordine di apparizione."""
    trovate = []
    for m in _GIORNO_MESE_ANNO.finditer(testo or ""):
        mese = _mese(m.group(2))
        if mese:
            trovate.append((m.start(), int(m.group(1)), mese, int(m.group(3))))
    for m in _MESE_GIORNO_ANNO.finditer(testo or ""):
        mese = _mese(m.group(1))
        if mese:
            trovate.append((m.start(), int(m.group(2)), mese, int(m.group(3))))
    for m in _NUMERICA.finditer(testo or ""):
        trovate.append((m.start(), int(m.group(1)), int(m.group(2)), int(m.group(3))))
    out = []
    for _, g, mm, a in sorted(trovate):
        try:
            out.append(date(a, mm, g))
        except ValueError:
            pass
    return out


def leggi_data(testo: str, rif: date | None = None) -> date | None:
    """Data da testo libero in più lingue ("entro il 15 aprile", "March 3rd")."""
    if not testo.strip():
        return None
    m = re.search(r"\d{4}-\d{2}-\d{2}", testo)
    if m:
        try:
            return date.fromisoformat(m.group(0))
        except ValueError:
            pass
    complete = cerca_date(testo)  # una data con l'anno scritto vince: niente indovinelli
    if complete:
        return complete[0]
    pulito = re.sub(r"(?i)\b(di )?ogni anno\b|\bannualmente\b|\bevery year\b|\beach year\b", " ", testo)  # bandi ricorrenti
    pulito = re.sub(r"(?i)\b(entro( e non oltre)?( il)?|non oltre( il)?|scadenza|deadline|until|by|bis|avant le|ore|h\.?)\b", " ", pulito)
    pulito = re.sub(r"(?i)\b(le )?ore \d{1,2}([:.]\d{2})?( del| dell'| di)?\b", " ", pulito)  # "entro le ore 12 del 9 febbraio"
    pulito = re.sub(r"(?i)\b\d{1,2}[:.]\d{2}\b.*$", "", pulito).strip(" :,-")
    d = dateparser.parse(
        pulito,
        languages=["it", "en", "fr", "de"],
        settings={"DATE_ORDER": "DMY", "PREFER_DAY_OF_MONTH": "last", "PREFER_DATES_FROM": "future",
                  "RELATIVE_BASE": _datetime(rif or oggi())},
    )
    return d.date() if d else None


def _datetime(d: date):
    from datetime import datetime

    return datetime(d.year, d.month, d.day)


def verifica(scheda: SchedaEstratta, testo: str) -> SchedaVerificata | None:
    """Applica le due regole. None = da scartare (scadenza passata)."""
    confermata = True
    frasi = []
    for dato, cit in (("scadenza", "scadenza_citazione"), ("quota_iscrizione_eur", "quota_citazione"),
                      ("eleggibilita", "eleggibilita_citazione")):
        valore = getattr(scheda, dato)
        if valore in ("", None):
            continue
        citazione = getattr(scheda, cit)
        if citazione_presente(citazione, testo):
            frasi.append(citazione.strip())
        else:
            # la scadenza resta (serve a ordinare) ma senza frase non è "sicura";
            # una quota senza frase si svuota, l'eleggibilità resta come indizio
            confermata = False
            if dato == "quota_iscrizione_eur":
                setattr(scheda, dato, None)
            setattr(scheda, cit, "")
    scadenza = leggi_data(scheda.scadenza) if scheda.scadenza else None
    if scadenza is None and scheda.scadenza_citazione:
        date_frase = cerca_date(scheda.scadenza_citazione)  # la data è nella frase citata
        scadenza = date_frase[0] if date_frase else None
    if scadenza is None:
        confermata = False
        # nessuna scadenza: se tutte le date citate sono passate, il bando è vecchio
        citate = cerca_date(" ".join([scheda.scadenza_citazione, scheda.date_attivita, scheda.apertura]))
        if citate and max(citate) < oggi():
            return None
    elif scadenza < oggi():
        return None
    return SchedaVerificata(scheda, scadenza, confermata, " · ".join(dict.fromkeys(frasi)))


# --- LLM ---------------------------------------------------------------------

def _prompt(pagina: Pagina) -> str:
    testo = pagina.testo[:MAX_CARATTERI]
    extra = ""
    if pagina.strutturato.get("json_ld"):
        extra = "\n\nDati strutturati della pagina (JSON-LD):\n" + json.dumps(
            pagina.strutturato["json_ld"], ensure_ascii=False)[:4000]
    return (f"Oggi è {iso(oggi())}.\nURL: {pagina.url}\nTitolo pagina: {pagina.titolo}\n\n"
            f"Testo della pagina:\n<<<\n{testo}\n>>>{extra}")


def _gemini(prompt: str, amb: Ambiente, modello: str) -> Estrazione:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modello}:generateContent"
    corpo = {
        "systemInstruction": {"parts": [{"text": ISTRUZIONI}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseJsonSchema": Estrazione.model_json_schema(),
        },
    }
    for tentativo in range(4):
        r = httpx.post(url, headers={"x-goog-api-key": amb.gemini_key}, json=corpo, timeout=90)
        if r.status_code not in (429, 503) or tentativo == 3:
            break
        # piano gratuito: poche richieste al minuto; si aspetta e si riprova
        import time

        time.sleep(int(r.headers.get("retry-after", 0) or 20 * (tentativo + 1)))
    r.raise_for_status()
    parti = r.json()["candidates"][0]["content"]["parts"]
    return Estrazione.model_validate_json("".join(p.get("text", "") for p in parti))


def _claude(prompt: str, amb: Ambiente, modello: str) -> Estrazione:
    import anthropic

    client = anthropic.Anthropic(api_key=amb.anthropic_key or None)
    risposta = client.messages.parse(
        model=modello,
        max_tokens=16000,
        system=ISTRUZIONI,
        messages=[{"role": "user", "content": prompt}],
        output_format=Estrazione,
    )
    if risposta.stop_reason == "refusal" or risposta.parsed_output is None:
        raise RuntimeError(f"Claude non ha restituito una scheda ({risposta.stop_reason})")
    return risposta.parsed_output


class DaEstrarre(Exception):
    """Nessun modello via API: la pagina va in coda e la estrae Claude Code (MCP)."""


def verifica_tutte(grezze: list[SchedaEstratta], pagina: Pagina) -> list[SchedaVerificata]:
    testo = pagina.testo + "\n" + json.dumps(pagina.strutturato.get("json_ld", ""), ensure_ascii=False)
    return [v for s in grezze if (v := verifica(s, testo))]


class Estrattore:
    """Motore da PROFILO ("Motore estrazione"):
    auto      Gemini se c'è la chiave, poi Claude API, altrimenti coda per Claude Code;
    gemini    Gemini con ripiego su Claude API;
    claude-api solo Claude API (Haiku);
    agente    sempre in coda per Claude Code (nessuna chiave necessaria).
    """

    def __init__(self, amb: Ambiente, profilo: Profilo):
        self.amb = amb
        self.motore = profilo.testo("Motore estrazione", "auto").lower()
        self.modello = profilo.testo("Modello estrazione")
        self.ripiego = profilo.testo("Modello ripiego")
        self.chiamate = {"gemini": 0, "claude": 0, "errori": 0}

    def estrai(self, pagina: Pagina) -> list[SchedaVerificata]:
        grezze = pagina.schede if pagina.schede else self._llm(_prompt(pagina)).bandi
        return verifica_tutte(grezze, pagina)

    def _llm(self, prompt: str) -> Estrazione:
        if self.motore == "agente":
            raise DaEstrarre()
        if self.motore in ("auto", "gemini") and self.amb.gemini_key:
            try:
                self.chiamate["gemini"] += 1
                return _gemini(prompt, self.amb, self.modello)
            except (ValidationError, httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as e:
                log.warning("Gemini non valido (%s), ripiego su Claude", type(e).__name__)
        if self.amb.anthropic_key:
            self.chiamate["claude"] += 1
            return _claude(prompt, self.amb, self.ripiego)
        if self.motore == "auto":
            raise DaEstrarre()
        self.chiamate["errori"] += 1
        raise RuntimeError(f"Motore {self.motore}: manca GEMINI_API_KEY o ANTHROPIC_API_KEY")
