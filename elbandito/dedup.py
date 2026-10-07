"""Deduplica: lo stesso bando arriva da 3-4 fonti (ente, Exibart, AgenziaCult…).

Prima l'impronta esatta (ente + titolo normalizzato + anno), poi le coppie
simili: stesso ente e titolo con somiglianza sopra 90 (RapidFuzz).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import urlparse

from rapidfuzz import fuzz

AGGREGATORI = {
    "exibart.com", "artribune.com", "agenziacult.it", "artapartofculture.net", "artrabbit.com",
    "artconnect.com", "resartis.org", "on-the-move.org", "callforentry.org", "giovaniartisti.it",
    "residenzeartistiche.it", "transartists.org", "lensculture.com", "facebook.com", "instagram.com",
}

PAROLE_VUOTE = {
    "bando", "call", "open", "for", "the", "di", "del", "della", "per", "a", "e", "il", "la", "lo",
    "edizione", "edition", "concorso", "2024", "2025", "2026", "2027", "2028", "artists", "artisti",
    "applications", "candidature", "aperte", "now", "deadline",
}


def normalizza(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b\d{1,2}(st|nd|rd|th|a|°|ª)?\b", " ", s)  # numeri di edizione
    s = re.sub(r"\b(19|20)\d{2}\b", " ", s)
    s = re.sub(r"\b[ivxlc]+\b(?= edizione)", " ", s)
    parole = [p for p in re.findall(r"[a-z0-9]+", s) if p not in PAROLE_VUOTE]
    return " ".join(parole)


def impronta(ente: str, titolo: str, anno: int | str) -> str:
    base = f"{normalizza(ente)}|{normalizza(titolo)}|{anno}"
    return hashlib.sha1(base.encode()).hexdigest()[:12]


def stesso_ente(a: str, b: str) -> bool:
    na, nb = normalizza(a), normalizza(b)
    if not na or not nb:
        return True  # ente sconosciuto: decide il titolo
    return na in nb or nb in na or fuzz.token_set_ratio(na, nb) >= 85


def simili(a: dict, b: dict, soglia: int = 90) -> bool:
    if not stesso_ente(a.get("Ente", ""), b.get("Ente", "")):
        return False
    return fuzz.token_set_ratio(normalizza(a.get("Titolo", "")), normalizza(b.get("Titolo", ""))) >= soglia


def trova(nuovo: dict, esistenti: list[dict]) -> dict | None:
    for r in esistenti:
        if r.get("Impronta") and r.get("Impronta") == nuovo.get("Impronta"):
            return r
    for r in esistenti:
        if simili(nuovo, r):
            return r
    return None


def dominio(url: str) -> str:
    d = urlparse(url or "").netloc.lower()
    return d[4:] if d.startswith("www.") else d


def link_migliore(a: str, b: str) -> str:
    """Tiene il link più vicino all'ente: il sito ufficiale batte l'aggregatore."""
    if not a:
        return b
    if not b:
        return a
    a_agg, b_agg = dominio(a) in AGGREGATORI, dominio(b) in AGGREGATORI
    if a_agg and not b_agg:
        return b
    return a


def unisci_fonti(a: str, b: str) -> str:
    voci = [x.strip() for x in f"{a},{b}".split(",") if x.strip()]
    return ", ".join(dict.fromkeys(voci))
