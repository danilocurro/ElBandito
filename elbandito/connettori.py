"""Connettori: uno per tipo di fonte, non uno per sito.

Ogni connettore riceve una riga di FONTI e restituisce delle Pagine: testo
pulito pronto per l'estrazione. La colonna "Parametri" di FONTI accetta
coppie chiave=valore separate da ";" (es. "filtro=fotograf|open call; max=10").
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import urljoin, urlparse

import feedparser
import trafilatura
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from .archivio import Archivio, hash_testo
from .config import Profilo, oggi
from .modelli import SchedaEstratta
from .rete import Rete

log = logging.getLogger(__name__)

MIN_TESTO = 600  # sotto questa lunghezza un riassunto RSS non basta: si apre la pagina


@dataclass
class Pagina:
    url: str
    titolo: str
    testo: str
    fonte: str  # ID della riga di FONTI
    data: str = ""
    # dati strutturati già affidabili (JSON-LD, API): aiutano l'LLM
    strutturato: dict = field(default_factory=dict)
    # schede già pronte senza LLM (es. API UE)
    schede: list[SchedaEstratta] = field(default_factory=list)


def parametri(fonte: dict) -> dict[str, str]:
    out = {}
    for pezzo in str(fonte.get("Parametri", "")).split(";"):
        if "=" in pezzo:
            k, v = pezzo.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def testo_da_html(html: str, url: str = "") -> str:
    testo = trafilatura.extract(html, url=url or None, include_tables=True, include_links=False, favor_recall=True)
    if testo:
        return testo
    albero = HTMLParser(html)
    for nodo in albero.css("script, style, nav, footer, header"):
        nodo.decompose()
    return " ".join((albero.body.text(separator=" ") if albero.body else "").split())


def _titolo_html(html: str) -> str:
    t = HTMLParser(html).css_first("title")
    return t.text(strip=True) if t else ""


def _passa_filtro(testo: str, filtro: str) -> bool:
    return not filtro or re.search(filtro, testo, re.IGNORECASE) is not None


def _apri(rete: Rete, url: str, fonte: str) -> Pagina:
    r = rete.get(url)
    html = r.text
    return Pagina(url=str(r.url), titolo=_titolo_html(html), testo=testo_da_html(html, url), fonte=fonte,
                  strutturato=_jsonld(html, url))


def _apri_o_salta(rete: Rete, url: str, fonte: str) -> Pagina | None:
    """Una scheda rotta (404, 403) non deve fermare tutta la fonte."""
    try:
        return _apri(rete, url, fonte)
    except Exception as e:
        log.warning("Salto %s: %s", url, e)
        return None


def _jsonld(html: str, url: str) -> dict:
    """Estrae JSON-LD utile (Event, JobPosting, CreativeWork…) se presente."""
    try:
        import extruct

        dati = extruct.extract(html, base_url=url, syntaxes=["json-ld"], uniform=True).get("json-ld", [])
    except Exception:
        return {}
    utili = [d for d in dati if str(d.get("@type", "")) not in ("WebSite", "BreadcrumbList", "Organization", "WebPage")]
    return {"json_ld": utili[:3]} if utili else {}


# --- rss ---------------------------------------------------------------------

def rss(fonte: dict, rete: Rete, arch: Archivio, profilo: Profilo) -> list[Pagina]:
    p = parametri(fonte)
    feed = feedparser.parse(rete.get(fonte["URL"]).content)
    pagine = []
    for voce in feed.entries[: int(p.get("max", 30))]:
        link = voce.get("link", "")
        if not link or not arch.nuovo(link):
            continue
        titolo = voce.get("title", "")
        corpo = ""
        if voce.get("content"):
            corpo = voce.content[0].get("value", "")
        corpo = corpo or voce.get("summary", "")
        testo = testo_da_html(corpo) if "<" in corpo else corpo
        if not _passa_filtro(f"{titolo} {testo}", p.get("filtro", "")):
            arch.segna(link, fonte["ID"])
            continue
        if len(testo) < MIN_TESTO:
            if pagina := _apri_o_salta(rete, link, fonte["ID"]):
                pagine.append(pagina)
        else:
            pagine.append(Pagina(url=link, titolo=titolo, testo=testo, fonte=fonte["ID"],
                                 data=voce.get("published", "")))
    return pagine


# --- wordpress ---------------------------------------------------------------

def wordpress(fonte: dict, rete: Rete, arch: Archivio, profilo: Profilo) -> list[Pagina]:
    """Ricerca nell'API pubblica wp-json/wp/v2 con le parole chiave del profilo."""
    p = parametri(fonte)
    base = fonte["URL"].rstrip("/")
    radice = base.split("/wp-json")[0]
    parole = [x.strip() for x in p["cerca"].split("|")] if p.get("cerca") else profilo.lista("Parole chiave")
    tipi = p.get("tipi", "posts").split("|")
    giorni = int(p.get("giorni", 21))
    dopo = (oggi() - timedelta(days=giorni)).isoformat() + "T00:00:00"
    visti: set[str] = set()
    pagine = []
    for tipo in tipi:
        for parola in parole:
            r = rete.get(
                f"{radice}/wp-json/wp/v2/{tipo}",
                params={"search": parola, "modified_after": dopo, "per_page": 20,
                        "_fields": "id,link,title,modified,content"},
            )
            risposta = r.json()
            for post in risposta if isinstance(risposta, list) else []:
                link = post.get("link", "")
                if not link or link in visti:
                    continue
                visti.add(link)
                testo = testo_da_html(post.get("content", {}).get("rendered", ""), link)
                h = hash_testo(testo)
                if not arch.cambiato(link, h):
                    continue
                titolo = HTMLParser(post.get("title", {}).get("rendered", "")).text(strip=True)
                if not _passa_filtro(f"{titolo} {testo}", p.get("filtro", "")):
                    arch.segna(link, fonte["ID"], h)
                    continue
                pagine.append(Pagina(url=link, titolo=titolo, testo=testo, fonte=fonte["ID"],
                                     data=post.get("modified", "")[:10], strutturato={"hash": h}))
    return pagine


# --- eu_sedia ----------------------------------------------------------------

SEDIA = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
STATO_SEDIA = {"31094501": "in arrivo", "31094502": "aperto"}


def eu_sedia(fonte: dict, rete: Rete, arch: Archivio, profilo: Profilo) -> list[Pagina]:
    """Bandi UE dal portale Funding & Tenders. Dati già strutturati: niente LLM."""
    import json

    p = parametri(fonte)
    testo_ricerca = p.get("testo", "***")  # con programma=43251814 (Europa Creativa) nei Parametri
    query = {
        "bool": {
            "must": [
                {"terms": {"type": ["1", "2", "8"]}},
                {"terms": {"status": list(STATO_SEDIA)}},
            ]
        }
    }
    if p.get("programma"):
        query["bool"]["must"].append({"terms": {"frameworkProgramme": p["programma"].split("|")}})
    r = rete.post(
        SEDIA,
        params={"apiKey": "SEDIA", "text": testo_ricerca, "pageSize": p.get("max", "50"), "pageNumber": "1"},
        files={
            "query": ("blob", json.dumps(query), "application/json"),
            "languages": ("blob", '["en"]', "application/json"),
            "sort": ("blob", '{"field":"sortStatus","order":"ASC"}', "application/json"),
        },
    )
    pagine = []
    for ris in r.json().get("results", []):
        md = ris.get("metadata", {}) or {}

        def primo(chiave: str) -> str:
            v = md.get(chiave, [""])
            return str(v[0] if isinstance(v, list) and v else v or "")

        ident = primo("identifier") or ris.get("reference", "")
        if not ident:
            continue
        link = f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{ident}"
        titolo = primo("title") or ris.get("summary", "") or ident
        scadenza = primo("deadlineDate")[:10]
        h = hash_testo(f"{titolo}{scadenza}")
        if not arch.cambiato(link, h):
            continue
        frase = f"Deadline: {scadenza}" if scadenza else ""
        scheda = SchedaEstratta(
            titolo=titolo, ente="Commissione europea", tipo="grant", disciplina="multidisciplinare",
            paese="Unione europea", scadenza=scadenza, scadenza_citazione=frase,
            apertura=primo("startDate")[:10], eleggibilita="Persone giuridiche (enti, consorzi)",
            eleggibilita_citazione="", solo_enti=True, link_candidatura=link,
        )
        pagine.append(Pagina(url=link, titolo=titolo, testo=f"{titolo}\n{frase}\n{ident}", fonte=fonte["ID"],
                             data=scadenza, strutturato={"hash": h, "sedia": ident}, schede=[scheda]))
    return pagine


# --- listing -----------------------------------------------------------------

def listing(fonte: dict, rete: Rete, arch: Archivio, profilo: Profilo) -> list[Pagina]:
    """Pagina-elenco: ricava i link alle schede e apre solo quelli nuovi.

    Parametri: link=<selettore CSS dei link> (predefinito "a"),
    pattern=<regex sull'href>, filtro=<regex sul testo del link>,
    max=<schede nuove per giro>.
    """
    p = parametri(fonte)
    html = rete.get(fonte["URL"]).text
    albero = HTMLParser(html)
    host = urlparse(fonte["URL"]).netloc
    schema = re.compile(p.get("pattern", r"/(open-?calls?|opportunit|bandi|concorsi|residenc|call)"), re.I)
    link: list[str] = []
    for a in albero.css(p.get("link", "a")):
        href = a.attributes.get("href") or ""
        assoluto = urljoin(fonte["URL"], href).split("#")[0]
        if urlparse(assoluto).netloc != host or assoluto.rstrip("/") == fonte["URL"].rstrip("/"):
            continue
        if not _passa_filtro(a.text(strip=True) + " " + assoluto, p.get("filtro", "")):
            continue
        if schema.search(assoluto) and assoluto not in link:
            link.append(assoluto)
    pagine = []
    for url in [u for u in link if arch.nuovo(u)][: int(p.get("max", 15))]:
        if pagina := _apri_o_salta(rete, url, fonte["ID"]):
            pagine.append(pagina)
    return pagine


# --- watch -------------------------------------------------------------------

def watch(fonte: dict, rete: Rete, arch: Archivio, profilo: Profilo) -> list[Pagina]:
    """Pagina "open call" di un festival o fondazione: passa solo se è cambiata."""
    pagina = _apri(rete, fonte["URL"], fonte["ID"])
    h = hash_testo(pagina.testo)
    if not arch.cambiato(fonte["URL"], h):
        return []
    pagina.strutturato["hash"] = h
    return [pagina]


# --- browser -----------------------------------------------------------------

def browser(fonte: dict, rete: Rete, arch: Archivio, profilo: Profilo) -> list[Pagina]:
    """Pagine con JavaScript pesante: crawl4ai (Playwright). Ritmo lento, niente aggiramenti."""
    import asyncio

    try:
        from crawl4ai import AsyncWebCrawler
    except ImportError as e:
        raise RuntimeError("Connettore browser: installare l'extra [browser] e 'playwright install chromium'") from e

    if not rete._permesso(fonte["URL"]):
        return []

    async def leggi() -> tuple[str, str]:
        async with AsyncWebCrawler() as crawler:
            ris = await crawler.arun(url=fonte["URL"])
            return str(ris.markdown or ""), ris.metadata.get("title", "") if ris.metadata else ""

    testo, titolo = asyncio.run(leggi())
    h = hash_testo(testo)
    if not testo or not arch.cambiato(fonte["URL"], h):
        return []
    return [Pagina(url=fonte["URL"], titolo=titolo, testo=testo, fonte=fonte["ID"], strutturato={"hash": h})]


# --- da link (pulsante "aggiungi da link") --------------------------------------

def da_link(url: str, rete: Rete) -> Pagina:
    return _apri(rete, url, "manuale")


CONNETTORI = {
    "rss": rss,
    "wordpress": wordpress,
    "eu_sedia": eu_sedia,
    "listing": listing,
    "watch": watch,
    "browser": browser,
}
