"""Insieme d'oro: opportunità note che la rete di fonti deve far emergere.

Nel repository c'è un esempio anonimo; la tua versione (per esempio le
opportunità che hai davvero colto) va in dati/personale/insieme_oro.csv.

Serve come test di regressione della rete di fonti: a ogni modifica di
FONTI si rimisura quante di queste lo strumento avrebbe fatto emergere.
Due misure:
- copertura: per ogni opportunità, almeno una delle fonti attese è in FONTI e attiva;
- richiamo: l'opportunità compare davvero fra i bandi trovati (BANDI o archivio grezzo).
"""

from __future__ import annotations

import csv
import re

from .dedup import dominio
from .foglio import file_seed


def insieme_oro() -> list[dict]:
    with file_seed("insieme_oro").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def copertura(fonti: list[dict]) -> list[tuple[dict, list[str]]]:
    attive = {dominio(f.get("URL", "")) for f in fonti
              if str(f.get("Attiva", "")).strip().lower() in ("sì", "si", "x", "true", "1")}
    out = []
    for voce in insieme_oro():
        attese = [d.strip() for d in voce.get("Fonti attese", "").split(",") if d.strip()]
        trovate = [d for d in attese if any(d in a for a in attive)]
        out.append((voce, trovate))
    return out


def richiamo(bandi: list[dict], grezzi: list[str]) -> list[tuple[dict, bool]]:
    corpus = [f"{b.get('Titolo', '')} {b.get('Ente', '')}" for b in bandi] + grezzi
    out = []
    for voce in insieme_oro():
        schema = re.compile(voce["Riconosci"], re.I)
        out.append((voce, any(schema.search(t) for t in corpus)))
    return out
